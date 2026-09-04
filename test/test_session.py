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

    def test_unknown_field_is_not_rejected(self):
        # §2.4 unknown-field tolerance: constructing/parsing does not raise.
        # This class does not model unknown fields (no catch-all attribute);
        # real §4 propagation of them happens at the Message level via
        # Message.forward/reply deep-copying the raw wire context, not
        # through Session.from_dict/to_dict.
        s = Session.from_dict({"session_id": "abc",
                               "novel_future_field": 42})
        self.assertEqual(s.session_id, "abc")
        self.assertNotIn("novel_future_field", s.to_dict())

    def test_registered_other_spec_field_is_first_class(self):
        # §3 — `pipeline` is registered (owner OVOS-PIPELINE-1), so it
        # lands as a first-class attribute.
        s = Session.from_dict({"pipeline": ["padatious_high"]})
        self.assertEqual(s.pipeline, ["padatious_high"])
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


# --- §3.5 location -----------------------------------------------------

class TestLocation(unittest.TestCase):
    def test_full_location_round_trips(self):
        s = Session(location={"lat": 38.7, "lon": -9.1, "tz": "Europe/Lisbon"})
        self.assertEqual(s.to_dict(),
                          {"location": {"lat": 38.7, "lon": -9.1,
                                        "tz": "Europe/Lisbon"}})
        self.assertEqual(Session.from_dict(s.to_dict()), s)

    def test_malformed_lat_type_dropped_alone(self):
        s = Session(location={"lat": "x", "lon": -9.1, "tz": "Europe/Lisbon"})
        self.assertEqual(s.to_dict(),
                          {"location": {"lon": -9.1, "tz": "Europe/Lisbon"}})

    def test_lat_out_of_range_dropped_alone(self):
        s = Session(location={"lat": 95, "lon": -9.1, "tz": "Europe/Lisbon"})
        self.assertEqual(s.to_dict(),
                          {"location": {"lon": -9.1, "tz": "Europe/Lisbon"}})

    def test_lon_out_of_range_dropped_alone(self):
        s = Session(location={"lat": 38.7, "lon": -181, "tz": "Europe/Lisbon"})
        self.assertEqual(s.to_dict(),
                          {"location": {"lat": 38.7, "tz": "Europe/Lisbon"}})

    def test_tz_wrong_type_dropped_alone(self):
        s = Session(location={"lat": 38.7, "lon": -9.1, "tz": 123})
        self.assertEqual(s.to_dict(), {"location": {"lat": 38.7, "lon": -9.1}})

    def test_tz_empty_string_dropped_alone(self):
        s = Session(location={"lat": 38.7, "lon": -9.1, "tz": ""})
        self.assertEqual(s.to_dict(), {"location": {"lat": 38.7, "lon": -9.1}})

    def test_unlisted_key_is_tolerated_but_not_reemitted(self):
        s = Session(location={"lat": 38.7, "city": "Lisbon"})
        self.assertEqual(s.to_dict(), {"location": {"lat": 38.7}})

    def test_none_of_three_present_is_wire_equivalent_to_omission(self):
        s = Session(location={"city": "Lisbon"})
        self.assertEqual(s.to_dict(), {})

    def test_none_is_omitted(self):
        s = Session(location=None)
        self.assertEqual(s.to_dict(), {})

    def test_non_dict_string_is_omitted(self):
        s = Session(location="Lisbon")
        self.assertEqual(s.to_dict(), {})

    def test_non_dict_list_is_omitted(self):
        s = Session(location=[])
        self.assertEqual(s.to_dict(), {})

    def test_location_is_registered_and_owned(self):
        self.assertIn("location", SESSION1_REGISTERED_FIELDS)
        self.assertIn("location", SESSION1_OWNED_FIELDS)

    def test_explicit_null_location_treated_as_omitted(self):
        s = Session.from_dict({"location": None})
        self.assertEqual(s.to_dict(), {})


# --- OVOS-PERSONA-1 registered persona_id ----------------------------------

class TestPersonaId(unittest.TestCase):
    def test_persona_id_round_trip(self):
        s = Session(persona_id="default")
        self.assertEqual(s.to_dict(), {"persona_id": "default"})
        self.assertEqual(Session.from_dict(s.to_dict()), s)

    def test_persona_id_omitted_not_null_when_none(self):
        # §2.1 omission-not-null: absent persona_id never serializes.
        s = Session()
        self.assertIsNone(s.persona_id)
        self.assertNotIn("persona_id", s.to_dict())
        self.assertNotIn("persona_id", s.serialize())

    def test_persona_id_is_registered_not_owned(self):
        # OVOS-PERSONA-1 registers it; OVOS-SESSION-1 does not own it.
        self.assertIn("persona_id", SESSION1_REGISTERED_FIELDS)
        self.assertNotIn("persona_id", SESSION1_OWNED_FIELDS)

    def test_persona_id_is_first_class(self):
        # Registered ⇒ lands as a first-class attribute.
        s = Session.from_dict({"persona_id": "assistant"})
        self.assertEqual(s.persona_id, "assistant")

    def test_empty_persona_id_rejected(self):
        with self.assertRaises(MalformedSession):
            Session(persona_id="")

    def test_explicit_null_persona_id_treated_as_omitted(self):
        # §2.1: explicit null on a registered field ⇒ omitted, not error.
        s = Session.from_dict({"persona_id": None})
        self.assertIsNone(s.persona_id)
        self.assertNotIn("persona_id", s.to_dict())


class TestFallbackHandlers(unittest.TestCase):
    """OVOS-SESSION-1 §3 registers ``fallback_handlers`` (array of string,
    owner OVOS-FALLBACK-1 §4). It is an array-of-string override field —
    same bucket / wire rules as the blacklists and transformer chains."""

    def test_fallback_handlers_round_trip(self):
        s = Session(fallback_handlers=["skill-a", "skill-b"])
        self.assertEqual(s.to_dict(),
                         {"fallback_handlers": ["skill-a", "skill-b"]})
        self.assertEqual(Session.from_dict(s.to_dict()), s)
        self.assertEqual(Session.deserialize(s.serialize()), s)

    def test_fallback_handlers_omitted_not_null_when_none(self):
        # §2.1 omission-not-null: absent fallback_handlers never serializes.
        s = Session()
        self.assertIsNone(s.fallback_handlers)
        self.assertNotIn("fallback_handlers", s.to_dict())
        self.assertNotIn("fallback_handlers", s.serialize())

    def test_empty_fallback_handlers_is_wire_equivalent_to_omission(self):
        # §3.4 — an empty array on a list override is dropped to omission.
        s = Session(fallback_handlers=[])
        self.assertIsNone(s.fallback_handlers)
        self.assertEqual(s.to_dict(), {})

    def test_fallback_handlers_is_registered_not_owned(self):
        # OVOS-FALLBACK-1 registers it; OVOS-SESSION-1 does not own it.
        self.assertIn("fallback_handlers", SESSION1_REGISTERED_FIELDS)
        self.assertNotIn("fallback_handlers", SESSION1_OWNED_FIELDS)

    def test_fallback_handlers_is_first_class(self):
        # Registered ⇒ lands as a first-class attribute.
        s = Session.from_dict({"fallback_handlers": ["skill-x"]})
        self.assertEqual(s.fallback_handlers, ["skill-x"])

    def test_explicit_null_fallback_handlers_treated_as_omitted(self):
        # §2.1: explicit null on a registered field ⇒ omitted, not error.
        s = Session.from_dict({"fallback_handlers": None})
        self.assertIsNone(s.fallback_handlers)
        self.assertNotIn("fallback_handlers", s.to_dict())

    def test_non_list_fallback_handlers_rejected(self):
        # Wrong wire type for an array-of-string override is malformed,
        # same as the blacklists / transformer chains (§3).
        with self.assertRaises(MalformedSession):
            Session(fallback_handlers="not-a-list")


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

    def test_context_key_is_not_registered_is_dropped_not_rejected(self):
        # The spec field is `intent_context`, not `context`; a stray
        # `context` key is unknown. §2.4 forbids rejecting it, which
        # from_dict honours (no raise); this class does not model it,
        # so it does not resurface from to_dict().
        s = Session.from_dict({"context": {"k": "v"}})
        self.assertEqual(s.to_dict(), {})


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

    def test_legacy_pair_shape_coerced_on_deserialize(self):
        # tolerant input — the legacy [skill_id, ts] pair shape coerces
        # into the spec object shape.
        s = Session.from_dict({"active_handlers": [["a", 1.0], ["b", 2.0]]})
        self.assertEqual(s.active_handlers,
                         [{"skill_id": "a", "activated_at": 1.0},
                          {"skill_id": "b", "activated_at": 2.0}])


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

    def test_response_mode_round_trip(self):
        s = Session()
        s.set_response_mode("skill-a", expires_at=99.0)
        self.assertEqual(Session.from_dict(s.to_dict()), s)


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

    def test_unknown_field_is_not_carried_by_session_propagate(self):
        # This class does not model unknown fields, so Session.propagate()
        # (a from_dict(to_dict()) round-trip) does not carry them. Real §4
        # propagation of unknown session keys happens at the Message level:
        # Message.forward/reply deep-copy the raw wire context instead of
        # reconstructing it through Session, so unknown keys DO survive
        # there (see test_message.py / test_messages.py for that path).
        s = Session.from_dict({"session_id": "abc",
                               "novel_future_field": [1, 2, 3]})
        self.assertNotIn("novel_future_field", s.propagate().to_dict())

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
        # §5 + OVOS-MSG-1 §6 — numbers MUST be finite. `intent_context` is
        # an opaque object-valued override field, a convenient carrier for
        # a non-finite number reaching serialize().
        s = Session(intent_context={"weird": float("nan")})
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
        # §3.2 the six language signals, §3.3 site_id, §3.5 location.
        self.assertEqual(SESSION1_OWNED_FIELDS, frozenset({
            "session_id", "site_id", "lang", "secondary_langs", "output_lang",
            "stt_lang", "request_lang", "detected_lang", "location",
        }))

    def test_registered_fields_superset_of_owned(self):
        self.assertTrue(SESSION1_OWNED_FIELDS.issubset(
            SESSION1_REGISTERED_FIELDS))
        # the full §3 roster includes the other-spec registered fields
        for f in ("pipeline", "intent_context", "active_handlers",
                  "converse_handlers", "response_mode",
                  "blacklisted_skills", "audio_transformers"):
            self.assertIn(f, SESSION1_REGISTERED_FIELDS)


# --- hashability (library-usefulness; not a spec rule) ---------------------

class TestHashable(unittest.TestCase):
    def test_equal_sessions_hash_equal(self):
        a = Session(session_id="abc", lang="en-US")
        b = Session(session_id="abc", lang="en-US")
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))

    def test_usable_as_dict_key_and_set_member(self):
        a = Session(session_id="abc")
        b = Session(session_id="abc")
        c = Session(session_id="xyz")
        d = {a: "value"}
        self.assertEqual(d[b], "value")
        self.assertEqual(len({a, b, c}), 2)

    def test_usable_in_lru_cache(self):
        import functools

        calls = []

        @functools.lru_cache(maxsize=None)
        def resolve(sess):
            calls.append(sess.session_id)
            return sess.session_id

        s1 = Session(session_id="abc", lang="en-US")
        s2 = Session(session_id="abc", lang="en-US")  # equal to s1
        self.assertEqual(resolve(s1), "abc")
        self.assertEqual(resolve(s2), "abc")
        self.assertEqual(calls, ["abc"])  # cached: only one underlying call

    def test_nested_override_fields_hash(self):
        s = Session(session_id="abc",
                    secondary_langs=["pt-PT", "es-ES"],
                    pipeline=["padatious_high"])
        self.assertEqual(hash(s), hash(s))  # stable, must not raise

    def test_mutation_then_rehash_changes_hash(self):
        # documented behavior: the hash snapshots the mutable Session at the
        # moment of hashing; mutating a field afterwards changes the hash.
        s = Session(session_id="abc")
        h1 = hash(s)
        s.lang = "en-US"
        self.assertNotEqual(hash(s), h1)


if __name__ == "__main__":
    unittest.main()
