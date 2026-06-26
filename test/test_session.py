"""OVOS-SESSION-1 conformance tests for :class:`ovos_spec_tools.Session`.

Every section heading below cites the spec section under test. The
handler-list sections additionally cite OVOS-PIPELINE-1 §7.1 and
OVOS-CONVERSE-1 §2.1 / §2.2 / §3, whose fields SESSION-1 §3 registers."""
import json
import unittest

from ovos_spec_tools import (
    DEFAULT_CONVERSE_HANDLERS_CAP, DEFAULT_SESSION_ID, MalformedSession,
    SESSION1_OWNED_FIELDS, SESSION1_REGISTERED_FIELDS, Session)


# --- §2 wire shape ---------------------------------------------------------

class TestWireShape(unittest.TestCase):
    def test_empty_session_is_wellformed(self):
        s = Session()
        self.assertEqual(s.to_dict(), {})
        self.assertEqual(s.serialize(), "{}")

    def test_only_session_id_is_wellformed(self):
        s = Session(session_id="abc")
        self.assertEqual(s.to_dict(), {"session_id": "abc"})

    def test_omitted_field_never_serializes_as_null(self):
        s = Session(session_id="abc", lang=None)
        self.assertNotIn("lang", s.to_dict())
        self.assertNotIn("null", s.serialize())

    def test_explicit_null_on_wire_is_logged_and_treated_as_omitted(self):
        with self.assertLogs("ovos_spec_tools.session", level="WARNING"):
            s = Session.from_dict({"session_id": "abc", "lang": None})
        self.assertIsNone(s.lang)
        self.assertEqual(s.session_id, "abc")

    def test_explicit_null_on_registered_other_spec_field_treated_as_omitted(self):
        # §2.1 — null on a field claimed by another spec is also omitted.
        with self.assertLogs("ovos_spec_tools.session", level="WARNING"):
            s = Session.from_dict({"session_id": "abc",
                                   "active_handlers": None,
                                   "response_mode": None})
        self.assertEqual(s.active_handlers, [])
        self.assertIsNone(s.response_mode)
        self.assertNotIn("active_handlers", s.to_dict())
        self.assertNotIn("response_mode", s.to_dict())

    def test_unknown_field_passes_through(self):
        # §2.4 unknown-field tolerance + §4 propagation
        s = Session.from_dict({"session_id": "abc",
                               "novel_future_field": 42})
        self.assertEqual(s.extras["novel_future_field"], 42)
        self.assertEqual(s.to_dict()["novel_future_field"], 42)

    def test_registered_other_spec_field_is_first_class(self):
        # §3 — `pipeline` is registered (owner OVOS-PIPELINE-1), so it
        # lands as a first-class attribute, not in `extras`.
        s = Session.from_dict({"pipeline": ["padatious_high"]})
        self.assertEqual(s.pipeline, ["padatious_high"])
        self.assertNotIn("pipeline", s.extras)
        self.assertEqual(s.to_dict()["pipeline"], ["padatious_high"])

    def test_non_dict_payload_is_malformed(self):
        with self.assertRaises(MalformedSession):
            Session.from_dict(["not", "an", "object"])  # type: ignore[arg-type]

    def test_unparsable_json_is_malformed(self):
        with self.assertRaises(MalformedSession):
            Session.deserialize("{not valid")

    def test_none_payload_yields_empty_session(self):
        # §2.1 — absent session ≡ empty object
        self.assertEqual(Session.deserialize(None), Session())
        self.assertEqual(Session.from_dict(None), Session())


# --- §3.1 session_id semantics --------------------------------------------

class TestSessionId(unittest.TestCase):
    def test_omitted_resolves_to_default(self):
        # §2.1 + §3.1 — three forms map to the same identity
        self.assertEqual(Session().resolved_session_id(), DEFAULT_SESSION_ID)
        self.assertEqual(
            Session.from_dict({}).resolved_session_id(), DEFAULT_SESSION_ID)
        self.assertEqual(
            Session(session_id=DEFAULT_SESSION_ID).resolved_session_id(),
            DEFAULT_SESSION_ID)

    def test_is_default_predicate(self):
        self.assertTrue(Session().is_default)
        self.assertTrue(Session(session_id=DEFAULT_SESSION_ID).is_default)
        self.assertFalse(Session(session_id="remote-42").is_default)

    def test_empty_session_id_rejected(self):
        with self.assertRaises(MalformedSession):
            Session(session_id="")

    def test_non_string_session_id_rejected(self):
        with self.assertRaises(MalformedSession):
            Session(session_id=123)  # type: ignore[arg-type]


# --- §3.2 language signals -------------------------------------------------

class TestLanguageSignals(unittest.TestCase):
    def test_all_six_lang_fields_round_trip(self):
        s = Session(
            lang="en-US", secondary_langs=["es-ES", "fr-FR"],
            output_lang="de-DE", stt_lang="en-GB",
            request_lang="en-US", detected_lang="fr-FR")
        self.assertEqual(Session.from_dict(s.to_dict()), s)

    def test_secondary_langs_must_not_contain_lang(self):
        # §3.2.2
        with self.assertRaises(MalformedSession):
            Session(lang="en-US", secondary_langs=["en-US", "fr-FR"])

    def test_secondary_langs_no_duplicates(self):
        with self.assertRaises(MalformedSession):
            Session(secondary_langs=["fr-FR", "fr-FR"])

    def test_secondary_langs_rejects_empty_string(self):
        with self.assertRaises(MalformedSession):
            Session(secondary_langs=[""])

    def test_lang_must_be_string(self):
        with self.assertRaises(MalformedSession):
            Session(lang=42)  # type: ignore[arg-type]


# --- §3.3 site_id ----------------------------------------------------------

class TestSiteId(unittest.TestCase):
    def test_site_id_round_trip(self):
        s = Session(site_id="kitchen")
        self.assertEqual(s.to_dict(), {"site_id": "kitchen"})
        self.assertEqual(Session.from_dict(s.to_dict()), s)

    def test_empty_site_id_rejected(self):
        with self.assertRaises(MalformedSession):
            Session(site_id="")

    def test_unknown_site_id_carries_no_meaning(self):
        # §3.3 — "unknown" is a normal opaque value, not reserved.
        s = Session(site_id="unknown")
        self.assertEqual(s.to_dict(), {"site_id": "unknown"})


# --- §3 / §3.4 other-spec override fields ----------------------------------

class TestOverrideFields(unittest.TestCase):
    def test_full_section_3_field_set_round_trips(self):
        payload = {
            "session_id": "abc",
            "lang": "en-US",
            "pipeline": ["stop_high", "converse", "adapt_high"],
            "intent_context": {"frame_stack": [], "timeout": 120},
            "blacklisted_skills": ["skill-a"],
            "blacklisted_intents": ["skill-b:foo"],
            "blacklisted_pipelines": ["fallback_low"],
            "audio_transformers": ["a"],
            "utterance_transformers": ["b"],
            "metadata_transformers": ["c"],
            "intent_transformers": ["d"],
            "dialog_transformers": ["e"],
            "tts_transformers": ["f"],
            "blacklisted_audio_transformers": ["ba"],
            "blacklisted_utterance_transformers": ["bb"],
            "blacklisted_metadata_transformers": ["bc"],
            "blacklisted_intent_transformers": ["bd"],
            "blacklisted_dialog_transformers": ["be"],
            "blacklisted_tts_transformers": ["bf"],
        }
        s = Session.from_dict(payload)
        self.assertEqual(s.to_dict(), payload)
        self.assertEqual(Session.deserialize(s.serialize()), s)

    def test_empty_list_override_is_wire_equivalent_to_omission(self):
        # §3.4 — an empty array on a list override is dropped.
        s = Session(pipeline=[], blacklisted_skills=[],
                    audio_transformers=[])
        self.assertEqual(s.to_dict(), {})
        self.assertEqual(s.pipeline, None)

    def test_intent_context_object_round_trips(self):
        s = Session(intent_context={"frame_stack": [["x", 1.0]]})
        self.assertEqual(s.to_dict()["intent_context"],
                         {"frame_stack": [["x", 1.0]]})

    def test_context_key_is_not_registered_passes_through_as_extra(self):
        # The spec field is `intent_context`, not `context`; a stray
        # `context` key is unknown and rides in `extras` (§2.4).
        s = Session.from_dict({"context": {"k": "v"}})
        self.assertEqual(s.extras["context"], {"k": "v"})
        self.assertEqual(s.to_dict()["context"], {"k": "v"})


# --- OVOS-PIPELINE-1 §7.1 active_handlers ----------------------------------

class TestActiveHandlers(unittest.TestCase):
    def test_add_active_handler_head_first(self):
        s = Session()
        s.add_active_handler("a", activated_at=1.0)
        s.add_active_handler("b", activated_at=2.0)
        self.assertEqual([h["skill_id"] for h in s.active_handlers],
                         ["b", "a"])

    def test_add_active_handler_dedup_promotes_to_head(self):
        # §7.1 — re-activation evicts the prior entry and re-inserts at head.
        s = Session()
        s.add_active_handler("a", activated_at=1.0)
        s.add_active_handler("b", activated_at=2.0)
        s.add_active_handler("a", activated_at=3.0)
        self.assertEqual([h["skill_id"] for h in s.active_handlers],
                         ["a", "b"])
        self.assertEqual(s.active_handlers[0]["activated_at"], 3.0)
        # no duplicate entry for "a"
        self.assertEqual(len([h for h in s.active_handlers
                              if h["skill_id"] == "a"]), 1)

    def test_remove_active_handler(self):
        s = Session()
        s.add_active_handler("a")
        s.add_active_handler("b")
        s.remove_active_handler("a")
        self.assertEqual([h["skill_id"] for h in s.active_handlers], ["b"])

    def test_active_predicate(self):
        s = Session()
        self.assertFalse(s.active)
        s.add_active_handler("a")
        self.assertTrue(s.active)

    def test_active_handlers_round_trip(self):
        s = Session()
        s.add_active_handler("a", activated_at=1.0)
        self.assertEqual(Session.from_dict(s.to_dict()), s)

    def test_legacy_pair_shape_rejected_object_shape_only(self):
        # PIPELINE-1 §7.1 / CONVERSE-1 §2.1 fix the wire type as an array
        # of {skill_id, activated_at} OBJECTS. No spec defines a pair
        # shape; the spec-adoption program forbids back-compat shims. A
        # pair entry is malformed and is dropped (not raised — §6).
        s = Session.from_dict({"active_handlers": [["a", 1.0], ["b", 2.0]]})
        self.assertEqual(s.active_handlers, [])

    def test_handler_missing_activated_at_is_dropped_not_timestamped(self):
        # PIPELINE-1 §7.1 — activated_at is orchestrator-stamped at
        # dispatch; the carrier MUST NOT fabricate it. An entry without a
        # valid activated_at is malformed and dropped — never minted with
        # time.time(), and the whole session is NOT rejected (§6).
        s = Session.from_dict({"active_handlers": [
            {"skill_id": "good", "activated_at": 5.0},
            {"skill_id": "no_stamp"},
            {"skill_id": "bad_stamp", "activated_at": "soon"},
        ]})
        self.assertEqual(s.active_handlers,
                         [{"skill_id": "good", "activated_at": 5.0}])

    def test_handler_bool_activated_at_is_dropped(self):
        # bool is a numeric subtype in Python but is not a valid timestamp.
        s = Session.from_dict({"active_handlers": [
            {"skill_id": "x", "activated_at": True}]})
        self.assertEqual(s.active_handlers, [])


# --- OVOS-CONVERSE-1 §2.1 converse_handlers --------------------------------

class TestConverseHandlers(unittest.TestCase):
    def test_default_cap_is_64(self):
        # The cap is the spec's §2.1 default for the add_converse_handler
        # argument — NOT a session field.
        self.assertEqual(DEFAULT_CONVERSE_HANDLERS_CAP, 64)

    def test_cap_is_not_session_state(self):
        # §2.1 — the cap is a deployment value the orchestrator applies at
        # insertion time, never an attribute carried on the session.
        s = Session()
        self.assertFalse(hasattr(s, "converse_handlers_cap"))
        self.assertNotIn("converse_handlers_cap", s.to_dict())

    def test_add_converse_handler_head_first_dedup(self):
        s = Session()
        s.add_converse_handler("a", activated_at=1.0)
        s.add_converse_handler("b", activated_at=2.0)
        s.add_converse_handler("a", activated_at=3.0)
        self.assertEqual([h["skill_id"] for h in s.converse_handlers],
                         ["a", "b"])

    def test_cap_evicts_tail(self):
        # §2.1 — when the cap would be exceeded, drop the least-recent tail.
        # The cap is supplied per insertion by the orchestrator.
        s = Session()
        for i in range(5):
            s.add_converse_handler(f"s{i}", activated_at=float(i), cap=3)
        self.assertEqual([h["skill_id"] for h in s.converse_handlers],
                         ["s4", "s3", "s2"])
        self.assertEqual(len(s.converse_handlers), 3)

    def test_not_capped_on_construction(self):
        # §2.1 — a constructed session with an over-cap converse_handlers
        # list is NOT auto-truncated on load; the cap applies only at the
        # next insertion.
        seed = [{"skill_id": f"s{i}", "activated_at": float(i)}
                for i in range(10)]
        s = Session(converse_handlers=seed)
        self.assertEqual(len(s.converse_handlers), 10)
        # the cap is enforced only on the next add_converse_handler.
        s.add_converse_handler("new", activated_at=99.0, cap=4)
        self.assertEqual(len(s.converse_handlers), 4)
        self.assertEqual(s.converse_handlers[0]["skill_id"], "new")

    def test_not_capped_on_deserialize(self):
        # §2.1 — a deserialized over-cap list is preserved verbatim; the
        # cap is applied only on the next capped insertion.
        seed = {"converse_handlers": [
            {"skill_id": f"s{i}", "activated_at": float(i)}
            for i in range(10)]}
        s = Session.deserialize(json.dumps(seed))
        self.assertEqual(len(s.converse_handlers), 10)

    def test_cap_unbounded_when_non_positive(self):
        s = Session()
        for i in range(100):
            s.add_converse_handler(f"s{i}", activated_at=float(i), cap=0)
        self.assertEqual(len(s.converse_handlers), 100)

    def test_cap_unbounded_when_none(self):
        s = Session()
        for i in range(100):
            s.add_converse_handler(f"s{i}", activated_at=float(i), cap=None)
        self.assertEqual(len(s.converse_handlers), 100)

    def test_prune_drops_stale_entries(self):
        # §3.2 — entries older than ttl are pruned at now - activated_at > ttl.
        s = Session()
        s.add_converse_handler("fresh", activated_at=100.0)
        s.add_converse_handler("stale", activated_at=10.0)
        s.prune_converse_handlers(ttl=50, now=100.0)
        self.assertEqual([h["skill_id"] for h in s.converse_handlers],
                         ["fresh"])

    def test_prune_noop_when_ttl_non_positive(self):
        s = Session()
        s.add_converse_handler("a", activated_at=1.0)
        s.prune_converse_handlers(ttl=0, now=1e9)
        self.assertEqual(len(s.converse_handlers), 1)

    def test_remove_converse_handler(self):
        s = Session()
        s.add_converse_handler("a")
        s.add_converse_handler("b")
        s.remove_converse_handler("a")
        self.assertEqual([h["skill_id"] for h in s.converse_handlers], ["b"])

    def test_converse_handlers_round_trip(self):
        s = Session()
        s.add_converse_handler("a", activated_at=1.0)
        self.assertEqual(Session.from_dict(s.to_dict()), s)


# --- OVOS-CONVERSE-1 §2.2 response_mode ------------------------------------

class TestResponseMode(unittest.TestCase):
    def test_absent_by_default(self):
        s = Session()
        self.assertIsNone(s.response_mode)
        self.assertNotIn("response_mode", s.to_dict())

    def test_set_response_mode_shape(self):
        s = Session()
        s.set_response_mode("skill-a", expires_at=123.0)
        self.assertEqual(s.response_mode,
                         {"skill_id": "skill-a", "expires_at": 123.0})

    def test_single_holder_overwrite(self):
        # §2.2 — setting while another holds overwrites silently.
        s = Session()
        s.set_response_mode("skill-a", expires_at=1.0)
        s.set_response_mode("skill-b", expires_at=2.0)
        self.assertEqual(s.response_mode["skill_id"], "skill-b")

    def test_clear_unconditional(self):
        s = Session()
        s.set_response_mode("skill-a", expires_at=1.0)
        s.clear_response_mode()
        self.assertIsNone(s.response_mode)

    def test_clear_only_own_holder(self):
        # a skill MUST NOT clear another's hold.
        s = Session()
        s.set_response_mode("skill-a", expires_at=1.0)
        s.clear_response_mode("skill-b")
        self.assertEqual(s.response_mode["skill_id"], "skill-a")
        s.clear_response_mode("skill-a")
        self.assertIsNone(s.response_mode)

    def test_malformed_response_mode_resolves_to_none(self):
        # §2.1 — a holder with no skill_id is not a valid window.
        self.assertIsNone(Session(response_mode={}).response_mode)
        self.assertIsNone(
            Session.from_dict({"response_mode": {"expires_at": 1}}).response_mode)

    def test_response_mode_missing_expires_at_drops_entry_no_default(self):
        # CONVERSE-1 §2.2 marks expires_at Required with NO default; the
        # carrier MUST NOT fabricate -1. A holder lacking a valid numeric
        # expires_at is not a valid window → None.
        self.assertIsNone(
            Session(response_mode={"skill_id": "a"}).response_mode)
        self.assertIsNone(
            Session.from_dict(
                {"response_mode": {"skill_id": "a"}}).response_mode)

    def test_response_mode_invalid_expires_at_drops_entry(self):
        # non-numeric or bool expires_at is not a valid window.
        self.assertIsNone(
            Session(response_mode={"skill_id": "a",
                                   "expires_at": "later"}).response_mode)
        self.assertIsNone(
            Session(response_mode={"skill_id": "a",
                                   "expires_at": True}).response_mode)

    def test_response_mode_never_fabricates_minus_one(self):
        # regression: the carrier used to default expires_at = -1.
        s = Session.from_dict({"response_mode": {"skill_id": "a"}})
        self.assertNotEqual(
            (s.response_mode or {}).get("expires_at"), -1)
        self.assertIsNone(s.response_mode)

    def test_response_mode_round_trip(self):
        s = Session()
        s.set_response_mode("skill-a", expires_at=99.0)
        self.assertEqual(Session.from_dict(s.to_dict()), s)


# --- §6 consume-vs-produce split: from_dict tolerates field values ---------

class TestConsumeTolerance(unittest.TestCase):
    """SESSION-1 §6: a consumer MUST NOT reject a Message because of the
    value of any single session field — an invalid value falls back to
    the field's deployment default (omission), never Message rejection.
    The constructor (PRODUCE path) still enforces producer MUSTs; only
    from_dict (CONSUME path) is tolerant."""

    def test_from_dict_tolerates_non_bcp47_lang(self):
        # #13 — a bad lang falls back, does NOT raise on consume.
        with self.assertLogs("ovos_spec_tools.session", level="WARNING"):
            s = Session.from_dict({"session_id": "x", "lang": "en US"})
        self.assertIsNone(s.lang)
        self.assertEqual(s.session_id, "x")

    def test_from_dict_tolerates_non_bcp47_other_lang_fields(self):
        with self.assertLogs("ovos_spec_tools.session", level="WARNING"):
            s = Session.from_dict({
                "output_lang": "  ", "stt_lang": 42,
                "request_lang": "", "detected_lang": "a\tb"})
        self.assertIsNone(s.output_lang)
        self.assertIsNone(s.stt_lang)
        self.assertIsNone(s.request_lang)
        self.assertIsNone(s.detected_lang)

    def test_from_dict_tolerates_empty_site_id(self):
        # #12 — §3.3 imposes no non-empty rule; empty falls back, no raise.
        with self.assertLogs("ovos_spec_tools.session", level="WARNING"):
            s = Session.from_dict({"site_id": ""})
        self.assertIsNone(s.site_id)

    def test_from_dict_tolerates_secondary_langs_duplicates(self):
        # #15 — §3.2.2 dup rule is a PRODUCER rule; consume drops dups.
        with self.assertLogs("ovos_spec_tools.session", level="WARNING"):
            s = Session.from_dict({"secondary_langs": ["fr-FR", "fr-FR"]})
        self.assertEqual(s.secondary_langs, ["fr-FR"])

    def test_from_dict_tolerates_secondary_langs_contains_lang(self):
        # #15 — secondary_langs containing `lang` is a PRODUCER rule; the
        # consumer drops the offending entry rather than rejecting.
        with self.assertLogs("ovos_spec_tools.session", level="WARNING"):
            s = Session.from_dict(
                {"lang": "en-US", "secondary_langs": ["en-US", "fr-FR"]})
        self.assertEqual(s.secondary_langs, ["fr-FR"])

    def test_from_dict_tolerates_non_list_secondary_langs(self):
        # #14 — wrong type falls back to omission, no raise.
        with self.assertLogs("ovos_spec_tools.session", level="WARNING"):
            s = Session.from_dict({"secondary_langs": "en-US"})
        self.assertIsNone(s.secondary_langs)

    def test_from_dict_tolerates_non_list_overrides(self):
        # #18 — non-list override fields fall back, no raise.
        with self.assertLogs("ovos_spec_tools.session", level="WARNING"):
            s = Session.from_dict({"pipeline": "adapt_high",
                                   "blacklisted_skills": {"a": 1},
                                   "intent_context": ["not", "an", "object"]})
        self.assertIsNone(s.pipeline)
        self.assertIsNone(s.blacklisted_skills)
        self.assertIsNone(s.intent_context)

    def test_from_dict_tolerates_empty_session_id(self):
        # #12-adjacent — empty session_id on the wire resolves to default,
        # not a rejection (§6 / §3.1).
        with self.assertLogs("ovos_spec_tools.session", level="WARNING"):
            s = Session.from_dict({"session_id": ""})
        self.assertIsNone(s.session_id)
        self.assertEqual(s.resolved_session_id(), DEFAULT_SESSION_ID)

    def test_from_dict_still_raises_on_non_object_root(self):
        # §5 — the one structural failure that stays a hard error.
        with self.assertRaises(MalformedSession):
            Session.from_dict(["not", "an", "object"])  # type: ignore[arg-type]

    def test_deserialize_still_raises_on_unparsable_json(self):
        # §5 — unparsable JSON is a hard error.
        with self.assertRaises(MalformedSession):
            Session.deserialize("{not valid")

    def test_produce_path_still_enforces_producer_musts(self):
        # The constructor (PRODUCE) still rejects producer-MUST violations:
        # non-empty session_id (§6), BCP-47 langs (§3.2), secondary_langs
        # producer rules (§3.2.2). Only from_dict (CONSUME) is tolerant.
        with self.assertRaises(MalformedSession):
            Session(session_id="")
        with self.assertRaises(MalformedSession):
            Session(lang="en US")
        with self.assertRaises(MalformedSession):
            Session(lang="en-US", secondary_langs=["en-US"])

    def test_good_values_survive_consume_unchanged(self):
        # tolerance must not corrupt valid input.
        payload = {"session_id": "x", "lang": "en-US",
                   "secondary_langs": ["es-ES", "fr-FR"], "site_id": "kitchen",
                   "pipeline": ["adapt_high"]}
        s = Session.from_dict(payload)
        self.assertEqual(s.to_dict(), payload)


# --- §4 propagation --------------------------------------------------------

class TestPropagation(unittest.TestCase):
    def test_propagate_is_deep_copy(self):
        s = Session(session_id="abc", pipeline=["padatious_high"])
        copy = s.propagate()
        self.assertEqual(copy, s)
        copy.pipeline.append("adapt_high")
        self.assertEqual(s.pipeline, ["padatious_high"])

    def test_propagate_carries_handlers(self):
        s = Session()
        s.add_active_handler("a", activated_at=1.0)
        s.add_converse_handler("b", activated_at=2.0)
        s.set_response_mode("c", expires_at=3.0)
        copy = s.propagate()
        self.assertEqual(copy, s)
        # the cap is not session state — nothing to carry across propagation.
        self.assertFalse(hasattr(copy, "converse_handlers_cap"))
        self.assertEqual(copy.active_handlers, s.active_handlers)
        # deep copy — mutating the twin does not touch the source
        copy.active_handlers[0]["activated_at"] = 999.0
        self.assertEqual(s.active_handlers[0]["activated_at"], 1.0)

    def test_unknown_field_survives_propagation(self):
        s = Session.from_dict({"session_id": "abc",
                               "novel_future_field": [1, 2, 3]})
        self.assertEqual(s.propagate().to_dict()["novel_future_field"],
                         [1, 2, 3])

    def test_materialize_default_sets_only_session_id(self):
        # §4.1
        s = Session.materialize_default()
        self.assertEqual(s.to_dict(), {"session_id": DEFAULT_SESSION_ID})


# --- §5 serialization ------------------------------------------------------

class TestSerialization(unittest.TestCase):
    def test_serialize_round_trip_via_json_str(self):
        s = Session(session_id="abc", lang="en-US",
                    pipeline=["padatious_high"])
        wire = s.serialize()
        self.assertEqual(Session.deserialize(wire), s)

    def test_serialize_rejects_nan(self):
        # §5 + OVOS-MSG-1 §6 — numbers MUST be finite
        s = Session(extras={"weird": float("nan")})
        with self.assertRaises(ValueError):
            s.serialize()

    def test_session_id_not_distinguished_from_other_strings(self):
        # §3.1 — "default" is a normal session value, structurally
        self.assertEqual(Session(session_id=DEFAULT_SESSION_ID).to_dict(),
                         {"session_id": "default"})

    def test_no_null_anywhere_on_a_fully_populated_session(self):
        # §2.1 — nothing serializes as null even when many fields set.
        s = Session(session_id="abc", lang="en-US", site_id="kitchen",
                    pipeline=["adapt_high"])
        s.add_active_handler("a", activated_at=1.0)
        s.set_response_mode("a", expires_at=2.0)
        self.assertNotIn("null", s.serialize())


# --- §6 conformance, registry --------------------------------------------

class TestRegistry(unittest.TestCase):
    def test_owned_fields_registry(self):
        # The fields whose semantics SESSION-1 itself owns: §3.1 session_id,
        # §3.2 the six language signals, §3.3 site_id.
        self.assertEqual(SESSION1_OWNED_FIELDS, frozenset({
            "session_id", "site_id", "lang", "secondary_langs", "output_lang",
            "stt_lang", "request_lang", "detected_lang",
        }))

    def test_registered_fields_superset_of_owned(self):
        self.assertTrue(SESSION1_OWNED_FIELDS.issubset(
            SESSION1_REGISTERED_FIELDS))
        # the full §3 roster includes the other-spec registered fields
        for f in ("pipeline", "intent_context", "active_handlers",
                  "converse_handlers", "response_mode",
                  "blacklisted_skills", "audio_transformers"):
            self.assertIn(f, SESSION1_REGISTERED_FIELDS)


if __name__ == "__main__":
    unittest.main()
