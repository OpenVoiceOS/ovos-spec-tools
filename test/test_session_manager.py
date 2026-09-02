"""SessionManager (singleton registry) + forward/reply session stamping.

SessionManager is an implementation detail enforcing the OVOS-SESSION-1 §4
value-passing contract; these tests pin its core invariants.
"""
import json
import unittest

from ovos_spec_tools.session import (MalformedSession, Session,
                                     SessionManager)
from ovos_spec_tools.message import Message


class TestSessionManagerRegistry(unittest.TestCase):
    def setUp(self):
        SessionManager.sessions.clear()
        SessionManager.default_session = None

    def test_one_live_object_per_id(self):
        a = SessionManager.update(Session("s1"))
        b = SessionManager.get(Message("x", context={"session": {"session_id": "s1"}}))
        self.assertIs(a, b)  # same live object, folded not replaced

    def test_held_reference_observes_later_fold(self):
        held = SessionManager.update(Session("s2"))
        # a later snapshot for the same id is folded onto the held object
        snap = {"session_id": "s2", "active_handlers": [{"skill_id": "k", "activated_at": 1.0}]}
        SessionManager.get(Message("x", context={"session": snap}))
        self.assertEqual([h["skill_id"] for h in held.active_handlers], ["k"])

    def test_default_folds_like_any_session(self):
        # the default session is a normal session per §4 — no owner-only
        # reservation; a message carrying it folds onto the live default.
        d = SessionManager.get_default_session()
        SessionManager.get(Message("x", context={"session": {"session_id": "default",
                                                             "lang": "pt-PT"}}))
        self.assertEqual(d.lang, "pt-PT")
        self.assertIs(d, SessionManager.get_default_session())


class TestForwardReplyStamping(unittest.TestCase):
    def setUp(self):
        SessionManager.sessions.clear()
        SessionManager.default_session = None

    def test_forward_refreshes_to_live_session(self):
        # get -> mutate -> forward: the derived message carries the live state,
        # not the originating message's pre-mutation snapshot.
        live = SessionManager.update(Session("123"))
        live.add_active_handler("my.skill")
        orig = Message("utt", context={"session": {"session_id": "123"}})
        fwd = orig.forward("my.skill.activate")
        ah = fwd.context["session"]["active_handlers"]
        self.assertEqual([h["skill_id"] for h in ah], ["my.skill"])

    def test_reply_refreshes_to_live_session(self):
        live = SessionManager.update(Session("123"))
        live.add_active_handler("my.skill")
        orig = Message("ask", context={"session": {"session_id": "123"},
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
        live = SessionManager.update(Session("123"))
        live.add_active_handler("live.skill")
        orig = Message("ask", context={"session": {"session_id": "123"},
                                       "source": "A"})
        # context= overrides routing only -> session still refreshed
        rep = orig.reply("ask.response", context={"destination": "X"})
        ah = rep.context["session"]["active_handlers"]
        self.assertEqual([h["skill_id"] for h in ah], ["live.skill"])

    def test_unowned_id_left_untouched(self):
        # a session id this process never folded is carried verbatim (§5)
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
        live = SessionManager.update(Session("123"))
        live.add_active_handler("a")
        orig = Message("u", context={"session": live.to_dict()})
        fwd = orig.forward("x")
        self.assertEqual([h["skill_id"] for h in fwd.context["session"]["active_handlers"]],
                         ["a"])


if __name__ == "__main__":
    unittest.main()


class TestDefaultSessionStoreMerge(unittest.TestCase):
    """OVOS-SESSION-2 §5.1 — writes into the default-session store are a
    field merge, not a whole-object replace.

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
        return SessionManager.get(Message("recognizer_loop:utterance",
                                          context={"session": snap}))

    def test_omitted_field_leaves_stored_value_unchanged(self):
        self._inbound({"session_id": "default", "lang": "en-US",
                       "intent_context": {"naptime:sleeping": {"value": True}},
                       "site_id": "kitchen"})
        # a second turn from the same device carries only what the client
        # knows; server-owned state it never saw must survive the write
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

    def test_session_naming_no_id_writes_the_default_store(self):
        # §4.1/§4.3: a session carrying no session_id IS the default session,
        # so it takes the §5.1 merge too.
        self._inbound({"session_id": "default", "site_id": "kitchen"})
        live = self._inbound({"lang": "en-US"})
        self.assertEqual(live.site_id, "kitchen")

    def test_subclass_only_fields_survive_the_fold(self):
        # a downstream Session (ovos-bus-client) models fields beyond
        # SESSION1_REGISTERED_FIELDS; the merge projects both sides through
        # serialize so those fields merge instead of resetting to defaults.
        class RicherSession(Session):
            def __init__(self, *args, location=None, **kwargs):
                super().__init__(*args, **kwargs)
                self.location = dict(location) if location else None

            def serialize(self):
                # bus-client's Session overrides serialize (not to_dict) to
                # emit its extra keys, returns a dict rather than a string,
                # and emits them UNCONDITIONALLY — no omit-when-empty guard,
                # so every one of them looks present at its default value
                out = super().to_dict()
                out["location"] = dict(self.location) if self.location else {}
                return out

            @classmethod
            def from_dict(cls, payload):
                payload = dict(payload or {})
                location = payload.pop("location", None)
                sess = super().from_dict(payload)
                sess.location = dict(location) if location else None
                return sess

        SessionManager.session_cls = RicherSession
        try:
            live = self._inbound({"session_id": "default",
                                  "location": {"city": "Lisbon"}})
            self._inbound({"session_id": "default", "lang": "en-US"})
            self.assertEqual(live.location, {"city": "Lisbon"})
        finally:
            SessionManager.session_cls = Session

    def test_subclass_field_mutated_after_arrival_reaches_the_store(self):
        # the mirror of the above: a subclass field the message did not carry
        # still applies when something set it after arrival.
        class RicherSession(Session):
            def __init__(self, *args, location=None, **kwargs):
                super().__init__(*args, **kwargs)
                self.location = dict(location) if location else None

            def serialize(self):
                out = super().to_dict()
                out["location"] = dict(self.location) if self.location else {}
                return out

            @classmethod
            def from_dict(cls, payload):
                payload = dict(payload or {})
                location = payload.pop("location", None)
                sess = super().from_dict(payload)
                sess.location = dict(location) if location else None
                return sess

        SessionManager.session_cls = RicherSession
        try:
            live = self._inbound({"session_id": "default", "lang": "en-US"})
            inbound = RicherSession.deserialize({"session_id": "default",
                                                 "lang": "en-US"})
            inbound.location = {"city": "Porto"}
            SessionManager.update(inbound)
            self.assertEqual(live.location, {"city": "Porto"})
        finally:
            SessionManager.session_cls = Session

    def test_malformed_field_does_not_wipe_the_stored_value(self):
        # §2.1 tolerates a malformed field by treating it as omitted, and
        # §5.1 leaves an omitted field's stored value standing. A field the
        # payload named but deserialization dropped was never carried.
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

    def test_consumed_session_does_not_replay_its_clears(self):
        # _store consumes the arrival snapshot; re-folding the same object
        # must not replay its clears against a store that has moved on.
        live = self._inbound({"session_id": "default", "site_id": "kitchen"})
        inbound = Session.deserialize({"session_id": "default",
                                       "site_id": "kitchen"})
        inbound.site_id = None
        SessionManager.update(inbound)
        self.assertIsNone(live.site_id)
        self._inbound({"session_id": "default", "site_id": "hallway"})
        SessionManager.update(inbound)
        self.assertEqual(live.site_id, "hallway")

    def test_lifecycle_mutation_reaches_the_store(self):
        # §5.1: "session mutations during the lifecycle propagate into the
        # store". A session deserialized from a minimal message and then
        # mutated at a handler boundary must carry the mutation in, not the
        # state it arrived with.
        live = self._inbound({"session_id": "default", "lang": "en-US"})
        inbound = Session.deserialize({"session_id": "default",
                                       "lang": "en-US"})
        inbound.site_id = "kitchen"
        inbound.intent_context = {"a:x": {"value": 1}}
        SessionManager.update(inbound)
        self.assertEqual(live.site_id, "kitchen")
        self.assertEqual(live.intent_context, {"a:x": {"value": 1}})

    def test_field_cleared_after_arrival_is_cleared_in_the_store(self):
        # the arrival snapshot tells an omission apart from a clear: the
        # message carried site_id and the object no longer presents it.
        live = self._inbound({"session_id": "default", "site_id": "kitchen"})
        inbound = Session.deserialize({"session_id": "default",
                                       "site_id": "kitchen"})
        inbound.site_id = None
        SessionManager.update(inbound)
        self.assertIsNone(live.site_id)

    def test_folded_session_keeps_no_arrival_snapshot(self):
        # a deserialize round-trip inside update_from is not an arrival; a
        # folded session must not claim a snapshot no message ever sent.
        live = self._inbound({"session_id": "default", "site_id": "kitchen"})
        self.assertIsNone(live.wire_payload)
        self._inbound({"session_id": "default", "lang": "en-US"})
        self.assertIsNone(live.wire_payload)

    def test_merged_lang_conflict_resolves_instead_of_raising(self):
        # §3.2.2 forbids secondary_langs to contain lang. Both messages below
        # are legal on their own; the merge must not synthesize the illegal
        # pair, which would be sticky — the store would keep it and raise on
        # every later fold.
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

    def test_subclass_that_records_no_arrival_gets_overwrite_not_clear(self):
        # ovos-bus-client's Session.deserialize is a staticmethod building a
        # fresh instance, so wire_payload is never set. Such a session takes
        # the own-baseline branch: it overwrites what it serializes — including
        # fields it emits unconditionally at their defaults — but an omission
        # of its still never clears a stored field.
        class UnstampedSession(Session):
            def __init__(self, *args, location=None, **kwargs):
                super().__init__(*args, **kwargs)
                self.location = dict(location) if location else None

            def serialize(self):
                out = super().to_dict()
                out["location"] = dict(self.location) if self.location else {}
                return out

            @staticmethod
            def deserialize(payload):
                payload = dict(json.loads(payload)
                               if isinstance(payload, str) else payload or {})
                location = payload.pop("location", None)
                sess = UnstampedSession(**payload)
                sess.location = dict(location) if location else None
                return sess

        SessionManager.session_cls = UnstampedSession
        try:
            live = self._inbound({"session_id": "default",
                                  "location": {"city": "Lisbon"},
                                  "site_id": "kitchen"})
            self.assertIsNone(live.wire_payload)
            self._inbound({"session_id": "default"})
            # unconditionally-emitted field is overwritten by its default...
            self.assertIsNone(live.location)
            # ...but a field the subclass omits when empty still stands
            self.assertEqual(live.site_id, "kitchen")
        finally:
            SessionManager.session_cls = Session

    def test_deserialize_records_the_arrival_when_from_dict_does_not(self):
        # a subclass may replace from_dict without recording the arrival;
        # inheriting deserialize still stamps it, so the merge stays
        # presence-aware.
        class OwnFromDict(Session):
            def __init__(self, *args, location=None, **kwargs):
                super().__init__(*args, **kwargs)
                self.location = dict(location) if location else None

            def serialize(self):
                out = super().to_dict()
                out["location"] = dict(self.location) if self.location else {}
                return out

            @classmethod
            def from_dict(cls, payload):
                payload = dict(payload or {})
                return cls(**{k: v for k, v in payload.items()
                              if k in ("session_id", "lang", "location")})

        SessionManager.session_cls = OwnFromDict
        try:
            live = self._inbound({"session_id": "default",
                                  "location": {"city": "Lisbon"}})
            self._inbound({"session_id": "default", "lang": "en-US"})
            self.assertEqual(live.location, {"city": "Lisbon"})
        finally:
            SessionManager.session_cls = Session

    def test_subclass_that_records_the_arrival_merges_fully(self):
        # the remedy: a subclass that records wire_payload where it parses a
        # payload gets the full presence-aware merge.
        class StampedSession(Session):
            def __init__(self, *args, location=None, **kwargs):
                super().__init__(*args, **kwargs)
                self.location = dict(location) if location else None

            def serialize(self):
                out = super().to_dict()
                out["location"] = dict(self.location) if self.location else {}
                return out

            @staticmethod
            def deserialize(payload):
                payload = dict(json.loads(payload)
                               if isinstance(payload, str) else payload or {})
                location = payload.pop("location", None)
                sess = StampedSession(**payload)
                sess.location = dict(location) if location else None
                sess.wire_payload = dict(payload,
                                         **({"location": location}
                                            if location is not None else {}))
                return sess

        SessionManager.session_cls = StampedSession
        try:
            live = self._inbound({"session_id": "default",
                                  "location": {"city": "Lisbon"},
                                  "site_id": "kitchen"})
            self._inbound({"session_id": "default"})
            self.assertEqual(live.location, {"city": "Lisbon"})
            self.assertEqual(live.site_id, "kitchen")
        finally:
            SessionManager.session_cls = Session

    def test_empty_list_does_not_clear_the_stored_value(self):
        # §3.4 makes an empty list wire-equivalent to omission, so it reads as
        # "no opinion" here, not as a clear. This is a behaviour change from
        # the whole-object replace, which dropped the stored value.
        self._inbound({"session_id": "default",
                       "blacklisted_skills": ["skill.a"]})
        live = self._inbound({"session_id": "default",
                              "blacklisted_skills": []})
        self.assertEqual(live.blacklisted_skills, ["skill.a"])

    def test_reserializing_a_cleared_entry_cannot_remove_it(self):
        # the carrier limitation (module docstring): to_dict never emits a
        # null, so an out-of-process component that deletes an entry and
        # re-serializes leaves the store's entry standing. Removal needs the
        # explicit OVOS-CONTEXT-1 §5.3 null entry on the wire.
        self._inbound({"session_id": "default",
                       "intent_context": {"a:x": {"value": 1}}})
        cleared = Session.deserialize({"session_id": "default",
                                       "intent_context": {"a:x": {"value": 1}}})
        cleared.intent_context = {}
        live = self._inbound(json.loads(cleared.serialize()))
        self.assertEqual(live.intent_context, {"a:x": {"value": 1}})
        live = self._inbound({"session_id": "default",
                              "intent_context": {"a:x": None}})
        self.assertIsNone(live.intent_context)

    def test_non_object_carrier_is_malformed(self):
        with self.assertRaises(MalformedSession):
            self._inbound("[1, 2]")

    def test_programmatic_update_cannot_drop_stored_fields(self):
        # §5.1: an omission never drops a stored default-session field. A
        # Session built programmatically has no arrival snapshot, so it is its
        # own baseline — it can overwrite, never clear by omitting.
        live = self._inbound({"session_id": "default",
                              "intent_context": {"a:x": {"value": 1}},
                              "site_id": "kitchen"})
        SessionManager.update(Session("default"))
        self.assertEqual(live.intent_context, {"a:x": {"value": 1}})
        self.assertEqual(live.site_id, "kitchen")
        SessionManager.update(Session("default", site_id="hallway"))
        self.assertEqual(live.site_id, "hallway")
