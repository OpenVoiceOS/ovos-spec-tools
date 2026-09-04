"""SessionManager (singleton registry) + forward/reply session stamping.

SessionManager is an implementation detail enforcing the OVOS-SESSION-1 §4
value-passing contract; these tests pin its core invariants.
"""
import json
import unittest

from ovos_spec_tools.session import (DEFAULT_SESSION_ID, MalformedSession,
                                     Session, SessionManager, carried_fields,
                                     resolve_session_id)
from ovos_spec_tools.message import Message


class TestSessionManagerRegistry(unittest.TestCase):
    def setUp(self):
        SessionManager.sessions.clear()
        SessionManager.default_session = None

    def test_the_registry_holds_only_the_default_session(self):
        # §2.2: no orchestrator state for a named id, not even briefly. The
        # working session travels through the utterance flow instead.
        sess = Session("s1")
        self.assertIs(SessionManager.update(sess), sess)
        self.assertNotIn("s1", SessionManager.sessions)
        SessionManager.get_default_session()
        self.assertEqual(list(SessionManager.sessions), ["default"])

    def test_held_reference_to_the_default_store_observes_later_arrivals(self):
        held = SessionManager.get_default_session()
        snap = {"session_id": "default",
                "active_handlers": [{"skill_id": "k", "activated_at": 1.0}]}
        SessionManager.fold_inbound(Message("x", context={"session": snap}))
        self.assertEqual([h["skill_id"] for h in held.active_handlers], ["k"])

    def test_default_arrival_lands_on_the_live_store(self):
        d = SessionManager.get_default_session()
        SessionManager.fold_inbound(
            Message("x", context={"session": {"session_id": "default",
                                              "lang": "pt-PT"}}))
        self.assertEqual(d.lang, "pt-PT")
        self.assertIs(d, SessionManager.get_default_session())

    def test_default_session_attribute_mirrors_the_registry(self):
        # Pre-spec readers (hivemind-websocket-client, ovoscope) still touch
        # SessionManager.default_session directly; it must track the
        # registry entry it mirrors, not lag behind it.
        SessionManager.get_default_session()
        self.assertIs(SessionManager.default_session,
                      SessionManager.sessions[DEFAULT_SESSION_ID])
        fresh = SessionManager.reset_default_session()
        self.assertIs(SessionManager.default_session, fresh)
        self.assertIs(SessionManager.default_session,
                      SessionManager.sessions[DEFAULT_SESSION_ID])


class TestForwardReplyStamping(unittest.TestCase):
    def setUp(self):
        SessionManager.sessions.clear()
        SessionManager.default_session = None

    def test_forward_refreshes_to_the_default_store(self):
        # get -> mutate -> forward: the derived message carries the live state,
        # not the originating message's pre-mutation snapshot.
        live = SessionManager.get_default_session()
        live.add_active_handler("my.skill")
        orig = Message("utt", context={"session": {"session_id": "default"}})
        fwd = orig.forward("my.skill.activate")
        ah = fwd.context["session"]["active_handlers"]
        self.assertEqual([h["skill_id"] for h in ah], ["my.skill"])

    def test_reply_refreshes_to_the_default_store(self):
        live = SessionManager.get_default_session()
        live.add_active_handler("my.skill")
        orig = Message("ask", context={"session": {"session_id": "default"},
                                       "source": "A", "destination": "B"})
        rep = orig.reply("ask.response")
        ah = rep.context["session"]["active_handlers"]
        self.assertEqual([h["skill_id"] for h in ah], ["my.skill"])
        # §5.2 routing still reversed
        self.assertEqual(rep.context["source"], "B")
        self.assertEqual(rep.context["destination"], "A")

    def test_reply_with_explicit_session_not_stamped(self):
        # an author-supplied session via context= is honoured, not refreshed
        live = SessionManager.update(Session("123"))
        live.add_active_handler("live.skill")
        orig = Message("ask", context={"session": {"session_id": "123"}})
        rep = orig.reply("ask.response",
                         context={"session": {"session_id": "123",
                                              "lang": "explicit"}})
        self.assertEqual(rep.context["session"], {"session_id": "123",
                                                  "lang": "explicit"})

    def test_reply_without_explicit_session_is_stamped(self):
        live = SessionManager.get_default_session()
        live.add_active_handler("live.skill")
        orig = Message("ask", context={"session": {"session_id": "default"},
                                       "source": "A"})
        # context= overrides routing only -> session still refreshed
        rep = orig.reply("ask.response", context={"destination": "X"})
        ah = rep.context["session"]["active_handlers"]
        self.assertEqual([h["skill_id"] for h in ah], ["live.skill"])

    def test_named_session_is_carried_verbatim(self):
        # §2.2 / §2.5: the orchestrator holds nothing authoritative for a
        # named id, so its carrier is the only authority and stands as sent.
        snap = {"session_id": "remote", "active_handlers": []}
        fwd = Message("u", context={"session": dict(snap)}).forward("x")
        self.assertEqual(fwd.context["session"], snap)

    def test_session_less_message_stays_session_less(self):
        fwd = Message("u", context={}).forward("x")
        self.assertNotIn("session", fwd.context)

    def test_idless_session_normalizes_to_default(self):
        # §4.1/§4.3: a session that names no id IS the default session.
        SessionManager.get_default_session().add_active_handler("d.skill")
        fwd = Message("u", context={"session": {"lang": "en-US"}}).forward("x")
        self.assertEqual(fwd.context["session"]["session_id"], "default")

    def test_stamp_is_noop_when_nothing_changed(self):
        # no intervening update -> stamp re-serializes the same state
        live = SessionManager.get_default_session()
        live.add_active_handler("a")
        orig = Message("u", context={"session": live.to_dict()})
        fwd = orig.forward("x")
        self.assertEqual([h["skill_id"] for h in fwd.context["session"]["active_handlers"]],
                         ["a"])



class TestDefaultSessionStoreMerge(unittest.TestCase):
    """OVOS-SESSION-2 §5.1 — an inbound Message on the default session is
    merged into the store field by field.

    §5.1 owns this as a deliberate deviation from OVOS-SESSION-1 §2.1: for
    `session_id == "default"` the orchestrator is the authoritative holder,
    so an omitted inbound field is filled from the store rather than from
    deployment defaults. Named sessions keep the §2.2 stateless reading and
    are pinned here too.
    """

    def setUp(self):
        SessionManager.sessions.clear()
        SessionManager.default_session = None

    @staticmethod
    def _inbound(snap):
        return SessionManager.fold_inbound(
            Message("recognizer_loop:utterance", context={"session": snap}))

    def test_omitted_field_leaves_stored_value_unchanged(self):
        self._inbound({"session_id": "default", "lang": "en-US",
                       "intent_context": {"naptime:sleeping": {"value": True}},
                       "site_id": "kitchen"})
        # a second turn from the same device carries only what the client
        # knows; server-owned state it never saw must survive the arrival
        live = self._inbound({"session_id": "default", "lang": "en-US"})
        self.assertEqual(live.intent_context,
                         {"naptime:sleeping": {"value": True}})
        self.assertEqual(live.site_id, "kitchen")

    def test_present_field_replaces_stored_value(self):
        self._inbound({"session_id": "default",
                       "intent_context": {"naptime:sleeping": {"value": True}}})
        live = self._inbound({"session_id": "default",
                              "intent_context": {"naptime:sleeping": {"value": False}}})
        self.assertEqual(live.intent_context,
                         {"naptime:sleeping": {"value": False}})

    def test_intent_context_merges_entry_by_entry(self):
        # OVOS-CONTEXT-1 §5.3: disjoint keys written by different handlers do
        # not overwrite each other, and a null entry removes its key.
        self._inbound({"session_id": "default",
                       "intent_context": {"a:x": {"value": 1}}})
        live = self._inbound({"session_id": "default",
                              "intent_context": {"b:y": {"value": 2}}})
        self.assertEqual(live.intent_context,
                         {"a:x": {"value": 1}, "b:y": {"value": 2}})
        live = self._inbound({"session_id": "default",
                              "intent_context": {"a:x": None}})
        self.assertEqual(live.intent_context, {"b:y": {"value": 2}})

    def test_other_carrier_fields_follow_the_same_rule(self):
        self._inbound({"session_id": "default", "lang": "pt-PT",
                       "blacklisted_skills": ["skill.a"],
                       "active_handlers": [{"skill_id": "k",
                                            "activated_at": 1.0}]})
        live = self._inbound({"session_id": "default", "lang": "pt-PT"})
        self.assertEqual(live.blacklisted_skills, ["skill.a"])
        self.assertEqual([h["skill_id"] for h in live.active_handlers], ["k"])
        live = self._inbound({"session_id": "default", "lang": "en-US",
                              "blacklisted_skills": ["skill.b"]})
        self.assertEqual(live.lang, "en-US")
        self.assertEqual(live.blacklisted_skills, ["skill.b"])

    def test_explicit_null_leaves_stored_value_unchanged(self):
        # §2.1: an explicit null is malformed and treated as omitted, so the
        # §5.1 omitted-field rule applies to it.
        self._inbound({"session_id": "default", "site_id": "kitchen"})
        live = self._inbound({"session_id": "default", "site_id": None})
        self.assertEqual(live.site_id, "kitchen")

    def test_malformed_field_counts_as_not_carried(self):
        # §2.1 tolerates a malformed field by treating it as omitted, and
        # §5.1 leaves an omitted field's stored value standing.
        self._inbound({"session_id": "default",
                       "active_handlers": [{"skill_id": "k",
                                            "activated_at": 1.0}],
                       "response_mode": {"skill_id": "k",
                                         "expires_at": 2.0}})
        live = self._inbound({"session_id": "default",
                              "active_handlers": [{}]})
        self.assertEqual([h["skill_id"] for h in live.active_handlers], ["k"])
        live = self._inbound({"session_id": "default",
                              "response_mode": {"foo": 1}})
        self.assertEqual(live.response_mode["skill_id"], "k")

    def test_empty_list_is_equivalent_to_omission(self):
        # §3.4 makes an empty list wire-equivalent to omission, so it reads as
        # "no opinion" here, not as a clear.
        self._inbound({"session_id": "default",
                       "blacklisted_skills": ["skill.a"]})
        live = self._inbound({"session_id": "default",
                              "blacklisted_skills": []})
        self.assertEqual(live.blacklisted_skills, ["skill.a"])

    def test_merged_lang_conflict_resolves_instead_of_raising(self):
        # §3.2.2 forbids secondary_langs to contain lang. Both carriers below
        # are legal on their own; the merge must not synthesize the illegal
        # pair, which would be sticky — the store would keep it and raise on
        # every later arrival.
        self._inbound({"session_id": "default", "lang": "en-US",
                       "secondary_langs": ["pt-PT"]})
        live = self._inbound({"session_id": "default", "lang": "pt-PT"})
        self.assertEqual(live.lang, "pt-PT")
        self.assertIsNone(live.secondary_langs)
        # the store stays usable for the turns that follow
        live = self._inbound({"session_id": "default", "site_id": "kitchen"})
        self.assertEqual(live.site_id, "kitchen")

    def test_merged_lang_conflict_resolves_from_the_other_direction(self):
        self._inbound({"session_id": "default", "lang": "pt-PT"})
        live = self._inbound({"session_id": "default",
                              "secondary_langs": ["pt-PT", "en-US"]})
        self.assertEqual(live.lang, "pt-PT")
        self.assertEqual(live.secondary_langs, ["en-US"])

    def test_equivalent_default_carriers_carry_nothing(self):
        # SESSION-1 §3.1 / SESSION-2 §6.5: the local device may omit the
        # carrier entirely or send {}. Both name the default session and
        # carry no field, so the store stands untouched.
        self._inbound({"session_id": "default", "site_id": "kitchen"})
        live = SessionManager.fold_inbound(Message("u", context={}))
        self.assertEqual(live.site_id, "kitchen")
        live = self._inbound({})
        self.assertEqual(live.site_id, "kitchen")
        live = self._inbound({"lang": "en-US"})
        self.assertEqual(live.site_id, "kitchen")
        self.assertEqual(live.lang, "en-US")

    def test_a_named_session_does_not_survive_its_utterance(self):
        # §2.2: no cross-utterance state for a named id. Round two carries
        # only what the client sent; nothing of round one is left to find.
        self._inbound({"session_id": "sat-1", "site_id": "hallway",
                       "lang": "pt-PT"})
        self.assertNotIn("sat-1", SessionManager.sessions)
        live = self._inbound({"session_id": "sat-1"})
        self.assertIsNone(live.site_id)
        self.assertIsNone(live.lang)

    def test_stamping_cannot_resurrect_a_previous_round(self):
        # §2.2 forbids relying on the utterance cache as durable. A message
        # derived in round two must not come back carrying round one's state.
        self._inbound({"session_id": "sat-1", "site_id": "hallway",
                       "lang": "pt-PT"})
        fwd = Message("u", context={"session": {"session_id": "sat-1"}}
                      ).forward("x")
        self.assertEqual(fwd.context["session"], {"session_id": "sat-1"})

    def test_a_named_carrier_tolerates_a_malformed_field(self):
        # §2.5: field-level malformedness resolves field by field for every
        # consumer, named sessions included — one bad field must not cost the
        # Message its session.
        live = self._inbound({"session_id": "sat-1", "lang": 123,
                              "site_id": "hallway"})
        self.assertIsNone(live.lang)
        self.assertEqual(live.site_id, "hallway")

    def test_an_unusable_session_id_names_the_default_session(self):
        # §6 wants a non-empty string when session_id is set, so an empty or
        # wrong-typed one is malformed and reads as omitted (§2.1) — and an
        # omitted id IS the default (§3.1). Routing it anywhere else would
        # strand the arrival in a session no message can name.
        self._inbound({"session_id": "default", "site_id": "kitchen"})
        for unusable in ("", 0, [], {}, False, 123, 1.5, True, b"x"):
            with self.subTest(session_id=unusable):
                live = self._inbound({"session_id": unusable,
                                      "lang": "pt-PT"})
                self.assertIs(live, SessionManager.get_default_session())
                self.assertEqual(live.lang, "pt-PT")
                self.assertEqual(live.site_id, "kitchen")

    def test_named_session_stays_a_whole_snapshot(self):
        # §2.2 / §4.2: the orchestrator holds no cross-utterance state for a
        # named session, so a client resuming without intent_context enters
        # with a fresh context. The §5.1 merge must NOT leak to named ids.
        self._inbound({"session_id": "sat-1",
                       "intent_context": {"naptime:sleeping": {"value": True}},
                       "site_id": "hallway"})
        live = self._inbound({"session_id": "sat-1"})
        self.assertIsNone(live.intent_context)
        self.assertIsNone(live.site_id)

    def test_named_session_does_not_touch_the_default_store(self):
        self._inbound({"session_id": "default", "site_id": "kitchen"})
        self._inbound({"session_id": "sat-1", "site_id": "hallway"})
        self.assertEqual(SessionManager.get_default_session().site_id,
                         "kitchen")

    def test_subclass_that_serializes_unconditionally_survives_the_arrival(self):
        # ovos-bus-client's Session emits its extra keys unconditionally, so
        # every one of them looks present at its default value. Presence is
        # read off the carrier, never off a serialized object, so an
        # unconditional emitter cannot wipe a stored subclass field.
        class RicherSession(Session):
            def __init__(self, *args, unit_prefs=None, **kwargs):
                super().__init__(*args, **kwargs)
                self.unit_prefs = dict(unit_prefs) if unit_prefs else None

            def serialize(self):
                out = super().to_dict()
                out["unit_prefs"] = dict(self.unit_prefs) if self.unit_prefs else {}
                return out

            @classmethod
            def from_dict(cls, payload):
                payload = dict(payload or {})
                unit_prefs = payload.pop("unit_prefs", None)
                sess = super().from_dict(payload)
                sess.unit_prefs = dict(unit_prefs) if unit_prefs else None
                return sess

        SessionManager.session_cls = RicherSession
        try:
            live = self._inbound({"session_id": "default",
                                  "unit_prefs": {"system": "metric"}})
            self._inbound({"session_id": "default", "lang": "en-US"})
            self.assertEqual(live.unit_prefs, {"system": "metric"})
            self.assertEqual(live.lang, "en-US")
        finally:
            SessionManager.session_cls = Session

    def test_wrong_typed_list_counts_as_not_carried(self):
        # §2.5: a wrong-typed value has no reading, so it reads as omitted.
        # A string is the trap — iterating one yields characters, which would
        # silently install nonsense in a stored list.
        self.assertEqual(carried_fields({"pipeline": "abc"}), {})
        self.assertEqual(carried_fields({"blacklisted_skills": [1, 2]}), {})
        self.assertEqual(carried_fields({"audio_transformers": [None]}), {})
        self.assertEqual(carried_fields({"fallback_handlers": [{"a": 1}]}), {})
        self.assertEqual(carried_fields({"intent_context": "nope"}), {})

    def test_wrong_typed_list_leaves_the_store_intact(self):
        self._inbound({"session_id": "default",
                       "pipeline": ["stop_high", "converse"]})
        live = self._inbound({"session_id": "default", "pipeline": "abc"})
        self.assertEqual(live.pipeline, ["stop_high", "converse"])

    def test_location_carries_as_a_preference_field(self):
        # §3.5 / SESSION-2 §2.5: a preference field replaces the stored
        # value when carried, and an omission leaves it alone -- the same
        # merge rule as site_id.
        self._inbound({"session_id": "default",
                       "location": {"lat": 38.7, "tz": "Europe/Lisbon"}})
        live = self._inbound({"session_id": "default"})
        self.assertEqual(live.location, {"lat": 38.7, "tz": "Europe/Lisbon"})
        live = self._inbound({"session_id": "default",
                              "location": {"lat": 40.7}})
        self.assertEqual(live.location, {"lat": 40.7})

    def test_location_with_no_valid_key_counts_as_not_carried(self):
        self.assertEqual(carried_fields({"location": {"city": "Lisbon"}}), {})
        self.assertEqual(carried_fields({"location": "Lisbon"}), {})
        self.assertEqual(carried_fields({"location": []}), {})

    def test_non_object_carrier_is_malformed(self):
        # §2.5: a carrier that is not an object has no session identity to
        # key on; the default must not be substituted for it.
        with self.assertRaises(MalformedSession):
            self._inbound("[1, 2]")


class TestResolveSessionIdIsTypeAware(unittest.TestCase):
    def test_wrong_typed_ids_resolve_to_the_default(self):
        # §6 requires a non-empty string when session_id is set; a
        # wrong-typed value has no reading and so is malformed, reading as
        # omitted (§2.1) — and an omitted id IS the default (§3.1). A
        # falsiness-only check misclassified a truthy wrong-typed value
        # (e.g. 123) as naming some other session.
        for unusable in (123, 1.5, True, [], {}, b"x"):
            with self.subTest(session_id=unusable):
                self.assertEqual(resolve_session_id(
                    {"session_id": unusable}), DEFAULT_SESSION_ID)

    def test_usable_ids_resolve_to_themselves(self):
        self.assertEqual(resolve_session_id({"session_id": "abc"}), "abc")

    def test_absent_or_empty_or_literal_default_resolve_to_the_default(self):
        for carrier in ({}, {"session_id": None}, {"session_id": ""},
                        {"session_id": "default"}):
            with self.subTest(carrier=carrier):
                self.assertEqual(resolve_session_id(carrier),
                                 DEFAULT_SESSION_ID)


class TestSessionManagerGetIsARead(unittest.TestCase):
    """`get` resolves which session a Message refers to and writes nothing."""

    def setUp(self):
        SessionManager.sessions.clear()
        SessionManager.default_session = None

    def test_get_does_not_write_the_store(self):
        store = SessionManager.get_default_session()
        store.site_id = "kitchen"
        msg = Message("u", context={"session": {"session_id": "default",
                                                "site_id": "hallway"}})
        self.assertIs(SessionManager.get(msg), store)
        msg.context["session"]["site_id"] = "garage"
        self.assertIs(SessionManager.get(msg), store)
        self.assertEqual(store.site_id, "kitchen")

    def test_get_without_a_message_returns_the_store(self):
        self.assertIs(SessionManager.get(), SessionManager.get_default_session())

    def test_get_on_a_session_less_message_returns_the_store(self):
        self.assertIs(SessionManager.get(Message("u", context={})),
                      SessionManager.get_default_session())

    def test_get_on_a_named_session_builds_from_the_carrier(self):
        # §2.2: no orchestrator state for a named id, so the carrier is all
        # there is and the read builds from it.
        msg = Message("u", context={"session": {"session_id": "sat-1",
                                                "site_id": "hallway"}})
        first = SessionManager.get(msg)
        self.assertEqual(first.site_id, "hallway")
        self.assertNotIn("sat-1", SessionManager.sessions)

    def test_get_on_a_wrong_typed_session_id_resolves_to_the_store(self):
        # A wrong-typed session_id is malformed and reads as omitted
        # (§2.1), and an omitted id IS the default (§3.1) — it must not
        # fall through to a freshly minted uuid4 session.
        store = SessionManager.get_default_session()
        msg = Message("u", context={"session": {"session_id": 123,
                                                "lang": "pt-PT"}})
        live = SessionManager.get(msg)
        self.assertIs(live, store)
        self.assertEqual(live.resolved_session_id(), "default")


class TestDerivationChainWrite(unittest.TestCase):
    """`update` is the OVOS-SESSION-2 §2.6 write — object-shaped and whole."""

    def setUp(self):
        SessionManager.sessions.clear()
        SessionManager.default_session = None

    def test_update_replaces_the_stored_state(self):
        store = SessionManager.fold_inbound(
            Message("u", context={"session": {"session_id": "default",
                                              "site_id": "kitchen",
                                              "lang": "en-US"}}))
        SessionManager.update(Session("default", lang="pt-PT"))
        self.assertEqual(store.lang, "pt-PT")
        self.assertIsNone(store.site_id)

    def test_update_keeps_the_store_identity(self):
        store = SessionManager.get_default_session()
        self.assertIs(SessionManager.update(Session("default", lang="pt-PT")),
                      store)

    def test_lifecycle_mutation_reaches_the_store(self):
        # §5.1 third bullet: a session mutated at a handler boundary carries
        # the mutation into the store when the handler writes it back.
        store = SessionManager.fold_inbound(
            Message("u", context={"session": {"session_id": "default",
                                              "lang": "en-US"}}))
        working = SessionManager.get(
            Message("u", context={"session": {"session_id": "default"}}))
        working.site_id = "kitchen"
        working.intent_context = {"a:x": {"value": 1}}
        SessionManager.update(working)
        self.assertEqual(store.site_id, "kitchen")
        self.assertEqual(store.intent_context, {"a:x": {"value": 1}})

    def test_update_rejects_none(self):
        with self.assertRaises(ValueError):
            SessionManager.update(None)

    def test_named_session_is_not_cross_utterance_state(self):
        # §2.2: what `update` registers for a named id is the utterance-scoped
        # cache, not a store — a later arrival replaces it wholesale.
        SessionManager.update(Session("sat-1", site_id="hallway"))
        live = SessionManager.fold_inbound(
            Message("u", context={"session": {"session_id": "sat-1"}}))
        self.assertIsNone(live.site_id)

    def test_a_written_named_session_never_reaches_an_outbound_message(self):
        # §2.5: a named session is client-owned, so the outbound carrier is
        # exactly what the message was built with — the orchestrator has
        # nothing truer to replace it with, and anything it kept would
        # eventually be a past round's state.
        working = Session("sat-1", site_id="hallway", lang="pt-PT")
        working.add_active_handler("my.skill")
        SessionManager.update(working)
        fwd = Message("u", context={"session": {"session_id": "sat-1",
                                                "lang": "en-US"}}
                      ).forward("x")
        self.assertEqual(fwd.context["session"],
                         {"session_id": "sat-1", "lang": "en-US"})

    def test_a_written_named_session_cannot_reach_the_next_round(self):
        # the sharp edge: converse and stop route off active_handlers, so a
        # stamp carrying a previous round's list would re-activate a handler
        # the client deliberately dropped.
        round_one = SessionManager.fold_inbound(
            Message("u", context={"session": {
                "session_id": "sat-1", "site_id": "hallway",
                "intent_context": {"a:x": {"value": 1}}}}))
        round_one.add_active_handler("my.skill")
        SessionManager.update(round_one)
        SessionManager.fold_inbound(
            Message("u", context={"session": {"session_id": "sat-1",
                                              "lang": "en-US"}}))
        speak = Message("u", context={"session": {"session_id": "sat-1",
                                                  "lang": "en-US"}}
                        ).forward("ovos.utterance.speak")
        self.assertEqual(speak.context["session"],
                         {"session_id": "sat-1", "lang": "en-US"})


class TestSessionSync(unittest.TestCase):
    """OVOS-SESSION-2 §2.7 / §6.2 — `ovos.session.sync` consumer obligation."""

    def setUp(self):
        SessionManager.sessions.clear()
        SessionManager.default_session = None

    @staticmethod
    def _sync(payload, carrier=None):
        return SessionManager.handle_sync(
            Message("ovos.session.sync", data={"session": payload},
                    context={"session": carrier
                             if carrier is not None
                             else {"session_id": "default"}}))

    def test_sync_payload_merges_into_the_store(self):
        SessionManager.fold_inbound(
            Message("u", context={"session": {"session_id": "default",
                                              "site_id": "kitchen",
                                              "lang": "en-US"}}))
        live = self._sync({"lang": "pt-PT"})
        self.assertEqual(live.lang, "pt-PT")
        self.assertEqual(live.site_id, "kitchen")

    def test_sync_removes_an_intent_context_entry(self):
        # OVOS-CONTEXT-1 §5.3 names the sync payload as the removal path.
        SessionManager.fold_inbound(
            Message("u", context={"session": {
                "session_id": "default",
                "intent_context": {"a:x": {"value": 1},
                                   "b:y": {"value": 2}}}}))
        live = self._sync({"intent_context": {"a:x": None}})
        self.assertEqual(live.intent_context, {"b:y": {"value": 2}})

    def test_the_ambient_carrier_identifies_but_does_not_contribute(self):
        # §2.7: context.session identifies the session, data.session is the
        # content. Fields on the carrier are not part of the sync.
        live = self._sync({"lang": "pt-PT"},
                          carrier={"session_id": "default",
                                   "site_id": "kitchen"})
        self.assertEqual(live.lang, "pt-PT")
        self.assertIsNone(live.site_id)

    def test_sync_on_a_named_session_leaves_the_store_alone(self):
        # §2.2: no store for a named id; §2.7 aims the update at the
        # in-flight utterance session, which the orchestrator owns.
        SessionManager.fold_inbound(
            Message("u", context={"session": {"session_id": "default",
                                              "site_id": "kitchen"}}))
        self._sync({"site_id": "hallway"},
                   carrier={"session_id": "sat-1"})
        self.assertEqual(SessionManager.get_default_session().site_id,
                         "kitchen")


class TestHandlerWritesRideOnDerivations(unittest.TestCase):
    """OVOS-CONTEXT-1 §5.3 — read the session, mutate it, emit a derivation.

    §5.0 makes this the only write path there is: no participant announces a
    context change on a topic of its own, so a mutation that does not reach
    the wire on the handler's own emission does not reach the wire at all.
    """

    def setUp(self):
        SessionManager.sessions.clear()
        SessionManager.default_session = None

    @staticmethod
    def _dispatch(session_id="sat-1", **fields):
        return Message("my.skill:intent",
                       context={"session": dict(session_id=session_id,
                                                **fields),
                                "source": "A", "destination": "B"})

    def test_forward_carries_a_handler_write_on_a_named_session(self):
        msg = self._dispatch()
        sess = SessionManager.get(msg)
        sess.intent_context = {"my.skill:topic": {"value": "weather"}}
        self.assertEqual(
            msg.forward("ovos.utterance.speak").context["session"]["intent_context"],
            {"my.skill:topic": {"value": "weather"}})

    def test_reply_and_response_carry_a_handler_write(self):
        msg = self._dispatch()
        SessionManager.get(msg).intent_context = {"my.skill:t": {"value": 1}}
        for derived in (msg.reply("q.answer"), msg.response()):
            self.assertEqual(derived.context["session"]["intent_context"],
                             {"my.skill:t": {"value": 1}})
        # §5.2 routing reversal is untouched by the stamp
        self.assertEqual(msg.reply("q.answer").context["source"], "B")

    def test_a_removal_rides_out_as_a_null_entry(self):
        # §5.3: a removal is written into the handler's own copy exactly as
        # an addition is, and travels the same way — as a null entry, which
        # is what the entry-by-entry merge reads as "remove this key".
        msg = self._dispatch(intent_context={"my.skill:t": {"value": 1}})
        SessionManager.get(msg).intent_context = {"my.skill:t": None}
        self.assertEqual(
            msg.forward("ovos.utterance.speak").context["session"]["intent_context"],
            {"my.skill:t": None})

    def test_repeated_reads_of_one_message_give_one_session(self):
        msg = self._dispatch()
        self.assertIs(SessionManager.get(msg), SessionManager.get(msg))

    def test_two_messages_on_one_id_do_not_share_a_session(self):
        # §2.2: nothing is keyed on the id, so a second Message naming the
        # same session starts from its own carrier and sees no leakage.
        first, second = self._dispatch(), self._dispatch()
        SessionManager.get(first).intent_context = {"my.skill:t": {"value": 1}}
        self.assertIsNot(SessionManager.get(first), SessionManager.get(second))
        self.assertIsNone(SessionManager.get(second).intent_context)
        self.assertEqual(second.forward("x").context["session"],
                         {"session_id": "sat-1"})

    def test_a_handler_write_never_reaches_the_registry(self):
        msg = self._dispatch()
        SessionManager.get(msg).intent_context = {"my.skill:t": {"value": 1}}
        self.assertNotIn("sat-1", SessionManager.sessions)
        self.assertEqual(list(SessionManager.sessions), [])

    def test_an_unread_message_forwards_its_carrier_unchanged(self):
        carrier = {"session_id": "sat-1", "lang": "pt-PT",
                   "intent_context": {"a:x": {"value": 1}}}
        fwd = Message("u", context={"session": dict(carrier)}).forward("x")
        self.assertEqual(fwd.context["session"], carrier)

    def test_a_rewritten_carrier_drops_the_stale_binding(self):
        msg = self._dispatch()
        SessionManager.get(msg).intent_context = {"my.skill:t": {"value": 1}}
        msg.context["session"] = {"session_id": "sat-2"}
        rebound = SessionManager.get(msg)
        self.assertEqual(rebound.resolved_session_id(), "sat-2")
        self.assertIsNone(rebound.intent_context)

    def test_a_derivation_for_another_session_is_not_stamped(self):
        msg = self._dispatch()
        SessionManager.get(msg).intent_context = {"my.skill:t": {"value": 1}}
        msg.context["session"] = {"session_id": "other"}
        self.assertEqual(msg.forward("x").context["session"],
                         {"session_id": "other"})

    def test_the_bound_session_outranks_a_direct_carrier_edit(self):
        # once the session has been read off a Message, it is the authority
        # for everything derived from it — a field poked straight into the
        # carrier dict does not reach the derivation.
        msg = self._dispatch(lang="en-US")
        SessionManager.get(msg)
        msg.context["session"]["lang"] = "pt-PT"
        self.assertEqual(msg.forward("f").context["session"]["lang"], "en-US")

    def test_a_write_on_the_default_session_still_rides_the_store(self):
        msg = self._dispatch(session_id=DEFAULT_SESSION_ID)
        sess = SessionManager.get(msg)
        self.assertIs(sess, SessionManager.get_default_session())
        sess.intent_context = {"shared:t": {"value": 1}}
        self.assertEqual(msg.forward("x").context["session"]["intent_context"],
                         {"shared:t": {"value": 1}})


class TestSessionManagerBind(unittest.TestCase):
    """`bind` lets an orchestrator make its own round session THE session of
    a Message, so every later `get`/derivation in the round sees that one
    object rather than one lazily rebuilt from the carrier.
    """

    def setUp(self):
        SessionManager.sessions.clear()
        SessionManager.default_session = None

    def test_bind_makes_forward_stamp_the_bound_object(self):
        msg = Message("my.skill:intent",
                      context={"session": {"session_id": "sat-1"}})
        round_session = Session("sat-1")
        self.assertIs(SessionManager.bind(msg, round_session), round_session)
        round_session.intent_context = {"my.skill:t": {"value": 1}}
        self.assertEqual(
            msg.forward("x").context["session"]["intent_context"],
            {"my.skill:t": {"value": 1}})

    def test_bind_makes_reply_and_response_stamp_the_bound_object(self):
        msg = Message("my.skill:intent",
                      context={"session": {"session_id": "sat-1"},
                               "source": "A", "destination": "B"})
        round_session = Session("sat-1")
        SessionManager.bind(msg, round_session)
        round_session.intent_context = {"my.skill:t": {"value": 2}}
        for derived in (msg.reply("q.answer"), msg.response()):
            self.assertEqual(derived.context["session"]["intent_context"],
                             {"my.skill:t": {"value": 2}})

    def test_bind_replaces_a_prior_lazy_binding_from_get(self):
        msg = Message("my.skill:intent",
                      context={"session": {"session_id": "sat-1"}})
        lazy = SessionManager.get(msg)
        lazy.intent_context = {"my.skill:t": {"value": "stale"}}
        round_session = Session("sat-1")
        SessionManager.bind(msg, round_session)
        round_session.intent_context = {"my.skill:t": {"value": "fresh"}}
        self.assertIsNot(SessionManager.get(msg), lazy)
        self.assertIs(SessionManager.get(msg), round_session)
        self.assertEqual(
            msg.forward("x").context["session"]["intent_context"],
            {"my.skill:t": {"value": "fresh"}})

    def test_get_after_bind_returns_the_bound_object(self):
        msg = Message("u", context={"session": {"session_id": "sat-1"}})
        round_session = Session("sat-1")
        SessionManager.bind(msg, round_session)
        self.assertIs(SessionManager.get(msg), round_session)

    def test_bound_is_a_readonly_peek(self):
        msg = Message("u", context={"session": {"session_id": "sat-1"}})
        self.assertIsNone(SessionManager.bound(msg))
        round_session = Session("sat-1")
        SessionManager.bind(msg, round_session)
        self.assertIs(SessionManager.bound(msg), round_session)

    def test_bind_refuses_a_default_shaped_session_that_is_not_the_store(self):
        # a copy would make get() (returns the binding) and stamp_derived
        # (falls back to the live store for a default binding) disagree
        # about the very same Message.
        msg = Message("u", context={"session": {"session_id": "default"}})
        impostor = Session()
        with self.assertRaises(ValueError):
            SessionManager.bind(msg, impostor)

    def test_bind_accepts_the_registry_default_itself(self):
        msg = Message("u", context={"session": {"session_id": "default"}})
        store = SessionManager.get_default_session()
        self.assertIs(SessionManager.bind(msg, store), store)
        self.assertIs(SessionManager.get(msg), store)

    def test_bind_refuses_a_session_id_mismatch(self):
        msg = Message("u", context={"session": {"session_id": "sat-1"}})
        other = Session("sat-2")
        with self.assertRaises(ValueError) as cm:
            SessionManager.bind(msg, other)
        self.assertIn("sat-1", str(cm.exception))
        self.assertIn("sat-2", str(cm.exception))

    def test_bind_allows_any_id_on_a_carrier_less_message(self):
        # §2.1: absent, null, and {} all name nothing yet, so there is no
        # carrier claim for a bound named session to contradict.
        for ctx in ({}, {"session": None}, {"session": {}}):
            with self.subTest(ctx=ctx):
                msg = Message("u", context=dict(ctx))
                named = Session("sat-1")
                self.assertIs(SessionManager.bind(msg, named), named)
                self.assertIs(SessionManager.get(msg), named)

    def test_bind_on_a_carrier_less_message_rides_the_forward(self):
        # the caller declared the session by binding it; the derivation
        # must pick it up even though the source Message named no session
        # of its own to match against.
        msg = Message("my.skill:intent", context={})
        named = Session("sat-1")
        SessionManager.bind(msg, named)
        named.intent_context = {"my.skill:t": {"value": 1}}
        self.assertEqual(
            msg.forward("x").context["session"],
            {"session_id": "sat-1",
             "intent_context": {"my.skill:t": {"value": 1}}})


class TestWrongTypedSessionIdIsLogged(unittest.TestCase):
    def setUp(self):
        SessionManager.sessions.clear()
        SessionManager.default_session = None

    def test_wrong_typed_session_id_logs_a_warning_exactly_once(self):
        with self.assertLogs("ovos_spec_tools.session", level="WARNING") as cm:
            resolve_session_id({"session_id": 123})
        self.assertEqual(len(cm.output), 1)
        self.assertIn("session_id", cm.output[0])
        self.assertIn("int", cm.output[0])

    def test_wrong_typed_session_id_through_get_logs_once(self):
        msg = Message("u", context={"session": {"session_id": 123,
                                                "lang": "pt-PT"}})
        with self.assertLogs("ovos_spec_tools.session", level="WARNING") as cm:
            SessionManager.get(msg)
        warnings = [line for line in cm.output if "session_id" in line]
        self.assertEqual(len(warnings), 1)

    def test_absent_session_id_is_silent(self):
        with self.assertRaises(AssertionError):
            with self.assertLogs("ovos_spec_tools.session", level="WARNING"):
                resolve_session_id({})

    def test_none_session_id_is_silent(self):
        with self.assertRaises(AssertionError):
            with self.assertLogs("ovos_spec_tools.session", level="WARNING"):
                resolve_session_id({"session_id": None})

    def test_empty_string_session_id_is_silent(self):
        with self.assertRaises(AssertionError):
            with self.assertLogs("ovos_spec_tools.session", level="WARNING"):
                resolve_session_id({"session_id": ""})

    def test_wrong_typed_session_id_through_fold_inbound_logs_once(self):
        # fold_inbound resolves the id (routing) and then merges the
        # carrier (carried_fields), both of which used to independently
        # diagnose `session_id` -- resolve_session_id is now the only one
        # that does.
        msg = Message("recognizer_loop:utterance",
                      context={"session": {"session_id": 123,
                                          "lang": "pt-PT"}})
        with self.assertLogs("ovos_spec_tools.session", level="WARNING") as cm:
            SessionManager.fold_inbound(msg)
        warnings = [line for line in cm.output if "session_id" in line]
        self.assertEqual(len(warnings), 1)


if __name__ == "__main__":
    unittest.main()
