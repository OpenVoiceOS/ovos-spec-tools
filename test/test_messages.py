"""Tests for the spec bus-message registry."""
import unittest

from ovos_spec_tools import (
    MIGRATION_MAP,
    MIGRATION_PAYLOAD_TRANSFORMS,
    SPEC_TO_LEGACY,
    NamespaceTranslator,
    SpecMessage,
    migration_counterpart,
)


class _Msg:
    def __init__(self, msg_type, data=None, context=None):
        self.msg_type = msg_type
        self.data = data or {}
        self.context = context or {}


class TestNamespaceTranslator(unittest.TestCase):
    def test_counterpart_topics_directions(self):
        t = NamespaceTranslator(modernize=True, emit_legacy=True)
        self.assertEqual(t.counterpart_topics("speak"), ["ovos.utterance.speak"])
        self.assertEqual(t.counterpart_topics("ovos.utterance.handle"),
                         ["recognizer_loop:utterance"])
        self.assertEqual(t.counterpart_topics("some.topic"), [])

    def test_flags_gate_each_direction(self):
        only_mod = NamespaceTranslator(modernize=True, emit_legacy=False)
        self.assertEqual(only_mod.counterpart_topics("speak"), ["ovos.utterance.speak"])
        self.assertEqual(only_mod.counterpart_topics("ovos.utterance.speak"), [])
        only_leg = NamespaceTranslator(modernize=False, emit_legacy=True)
        self.assertEqual(only_leg.counterpart_topics("speak"), [])
        self.assertEqual(only_leg.counterpart_topics("ovos.utterance.speak"), ["speak"])

    def test_is_migrated(self):
        t = NamespaceTranslator()
        self.assertTrue(t.is_migrated("speak"))
        self.assertTrue(t.is_migrated("ovos.utterance.speak"))
        self.assertFalse(t.is_migrated("random.topic"))

    def test_mirror_guard_drops_counterpart_pair(self):
        guard = NamespaceTranslator().new_mirror_guard()
        data = {"utterance": "hi"}
        self.assertFalse(guard(_Msg("speak", data)))
        self.assertTrue(guard(_Msg("ovos.utterance.speak", data)))  # mirror

    def test_mirror_guard_keeps_same_topic_repeats(self):
        guard = NamespaceTranslator().new_mirror_guard()
        data = {"utterance": "ok"}
        self.assertFalse(guard(_Msg("speak", data)))
        self.assertFalse(guard(_Msg("speak", data)))  # genuine repeat, same topic

    def test_mirror_guard_distinct_context_not_collapsed(self):
        guard = NamespaceTranslator().new_mirror_guard()
        data = {"utterance": "hi"}
        self.assertFalse(guard(_Msg("speak", data, {"session": {"session_id": "A"}})))
        self.assertFalse(guard(_Msg("ovos.utterance.speak", data,
                                    {"session": {"session_id": "B"}})))

    def test_mirror_guard_window_expiry(self):
        clk = {"t": 0.0}
        guard = NamespaceTranslator(window=1.0).new_mirror_guard(clock=lambda: clk["t"])
        data = {"utterance": "hi"}
        self.assertFalse(guard(_Msg("speak", data)))
        clk["t"] = 2.0
        self.assertFalse(guard(_Msg("ovos.utterance.speak", data)))  # window passed


class TestSpecMessage(unittest.TestCase):
    def test_members_are_ovos_namespaced_strings(self):
        for m in SpecMessage:
            self.assertTrue(m.value.startswith("ovos."), m.value)

    def test_usable_as_plain_string(self):
        self.assertEqual(SpecMessage.SPEAK, "ovos.utterance.speak")
        self.assertEqual(f"{SpecMessage.UTTERANCE}", "ovos.utterance.handle")

    def test_no_duplicate_values(self):
        values = [m.value for m in SpecMessage]
        self.assertEqual(len(values), len(set(values)))

    def test_audio1_bus_surface_members(self):
        # OVOS-AUDIO-1 §7 bus surface members.
        self.assertEqual(SpecMessage.SPEAK_B64, "ovos.utterance.speak.b64")  # §3.4
        self.assertEqual(SpecMessage.AUDIO_SPEECH, "ovos.audio.speech")      # §4.3
        self.assertEqual(SpecMessage.AUDIO_QUEUE, "ovos.audio.queue")        # §4.1
        self.assertEqual(SpecMessage.AUDIO_PLAY_SOUND, "ovos.audio.play_sound")  # §4.2
        self.assertEqual(SpecMessage.AUDIO_STOP, "ovos.audio.stop")          # §6
        self.assertEqual(SpecMessage.AUDIO_IS_SPEAKING, "ovos.audio.is_speaking")  # §5.3

    def test_audio1_output_topics_are_payload_compatible_renames(self):
        # The AUDIO-1 §7 output topics are payload-compatible 1:1 renames of the
        # Mycroft-era handler names (verified against ovos-audio
        # register_handlers), so they migrate via MIGRATION_MAP with no payload
        # transform (identity).
        expected = {
            "speak:b64_audio": SpecMessage.SPEAK_B64,
            "speak:b64_audio.response": SpecMessage.AUDIO_SPEECH,
            "mycroft.audio.queue": SpecMessage.AUDIO_QUEUE,
            "mycroft.audio.play_sound": SpecMessage.AUDIO_PLAY_SOUND,
            "mycroft.audio.speak.status": SpecMessage.AUDIO_IS_SPEAKING,
            "mycroft.audio.speech.stop": SpecMessage.AUDIO_STOP,
        }
        for legacy, spec in expected.items():
            self.assertEqual(MIGRATION_MAP[legacy], spec)
            # payload-compatible: identity transform (no per-topic entry)
            self.assertNotIn(legacy, MIGRATION_PAYLOAD_TRANSFORMS)

    def test_audio1_output_topics_round_trip(self):
        # legacy -> spec -> legacy and spec -> legacy round-trip.
        for legacy in ("speak:b64_audio", "speak:b64_audio.response",
                       "mycroft.audio.queue", "mycroft.audio.play_sound",
                       "mycroft.audio.speak.status", "mycroft.audio.speech.stop"):
            spec = migration_counterpart(legacy)
            self.assertIsNotNone(spec)
            self.assertEqual(migration_counterpart(spec), legacy)


class TestMigrationMap(unittest.TestCase):
    def test_maps_legacy_to_specmessage(self):
        self.assertEqual(MIGRATION_MAP["speak"], SpecMessage.SPEAK)
        self.assertEqual(MIGRATION_MAP["recognizer_loop:utterance"],
                         SpecMessage.UTTERANCE)

    def test_reverse_is_consistent(self):
        for legacy, spec in MIGRATION_MAP.items():
            self.assertEqual(SPEC_TO_LEGACY[str(spec)], legacy)

    def test_values_are_spec_members(self):
        for spec in MIGRATION_MAP.values():
            self.assertIsInstance(spec, SpecMessage)


class TestMigrationCounterpart(unittest.TestCase):
    def test_legacy_returns_spec(self):
        self.assertEqual(migration_counterpart("speak"), "ovos.utterance.speak")

    def test_spec_returns_legacy(self):
        self.assertEqual(migration_counterpart("ovos.utterance.speak"), "speak")

    def test_unmapped_returns_none(self):
        self.assertIsNone(migration_counterpart("some.random.topic"))

    def test_roundtrip(self):
        for legacy in MIGRATION_MAP:
            spec = migration_counterpart(legacy)
            self.assertEqual(migration_counterpart(spec), legacy)


class TestPayloadTransforms(unittest.TestCase):
    """Per-topic payload translation (MIGRATION_PAYLOAD_TRANSFORMS)."""

    def setUp(self):
        self.t = NamespaceTranslator()

    # --- structure invariants ---
    def test_transform_keys_are_legacy_topics(self):
        for legacy in MIGRATION_PAYLOAD_TRANSFORMS:
            self.assertIn(legacy, MIGRATION_MAP,
                          f"{legacy} is not a known legacy topic")

    def test_only_shape_changing_topics_have_transforms(self):
        # The 3 shape-changing entries: detach + enable/disable. The handler
        # trio is orchestrator-owned and intentionally NOT migrated, so it has
        # no transform (see MIGRATION_MAP).
        self.assertEqual(set(MIGRATION_PAYLOAD_TRANSFORMS), {
            "detach_intent",
            "mycroft.skill.enable_intent",
            "mycroft.skill.disable_intent",
        })

    def test_transforms_do_not_mutate_input(self):
        for legacy, (l2s, s2l) in MIGRATION_PAYLOAD_TRANSFORMS.items():
            src = {"intent_name": "a:b", "handler": "h", "skill_id": "s",
                   "duration": 1, "traceback": "tb", "exception": "ex",
                   "lang": "en-US"}
            before = dict(src)
            l2s(src)
            s2l(src)
            self.assertEqual(src, before, f"{legacy} mutated its input")

    # --- detach_intent: cleanly bidirectional ---
    def test_detach_spec_to_legacy_joins(self):
        out = self.t.translate_payload(
            "ovos.intent.deregister", "detach_intent",
            {"skill_id": "music.skill", "intent_name": "play", "lang": "en-US"})
        self.assertEqual(out, {"intent_name": "music.skill:play"})

    def test_detach_legacy_to_spec_splits(self):
        out = self.t.translate_payload(
            "detach_intent", "ovos.intent.deregister",
            {"intent_name": "music.skill:play"})
        self.assertEqual(out, {"skill_id": "music.skill",
                               "intent_name": "play"})

    def test_detach_roundtrip_spec_legacy_spec(self):
        spec = {"skill_id": "music.skill", "intent_name": "play"}
        legacy = self.t.translate_payload(
            "ovos.intent.deregister", "detach_intent", spec)
        back = self.t.translate_payload(
            "detach_intent", "ovos.intent.deregister", legacy)
        self.assertEqual(back, spec)

    def test_detach_split_on_first_colon_only(self):
        out = self.t.translate_payload(
            "detach_intent", "ovos.intent.deregister",
            {"intent_name": "skill:a:b"})
        self.assertEqual(out, {"skill_id": "skill", "intent_name": "a:b"})

    # --- handler trio: orchestrator-owned, intentionally NOT migrated ---
    def test_handler_trio_is_not_migrated(self):
        # PIPELINE-1 §8: the orchestrator emits the spec trio authoritatively;
        # the skill framework keeps the legacy topics as a private done-signal.
        # They must NOT bridge — bridging would double-emit and reshape a
        # shape-changing event.
        for legacy, spec in (
            ("mycroft.skill.handler.start", "ovos.intent.handler.start"),
            ("mycroft.skill.handler.complete", "ovos.intent.handler.complete"),
            ("mycroft.skill.handler.error", "ovos.intent.handler.error"),
        ):
            self.assertNotIn(legacy, MIGRATION_MAP)
            self.assertNotIn(legacy, MIGRATION_PAYLOAD_TRANSFORMS)
            self.assertFalse(self.t.is_migrated(legacy))
            self.assertFalse(self.t.is_migrated(spec))
            self.assertFalse(self.t.counterpart_topics(legacy))
            self.assertFalse(self.t.counterpart_topics(spec))

    # --- enable/disable: documented loss (no skill_id on legacy side) ---
    def test_toggle_spec_to_legacy_drops_skill_and_lang(self):
        out = self.t.translate_payload(
            "ovos.intent.enable", "mycroft.skill.enable_intent",
            {"skill_id": "music.skill", "intent_name": "play", "lang": "en-US"})
        self.assertEqual(out, {"intent_name": "play"})

    def test_toggle_legacy_to_spec_cannot_recover_skill_id(self):
        out = self.t.translate_payload(
            "mycroft.skill.disable_intent", "ovos.intent.disable",
            {"intent_name": "play"})
        # documented limitation: no skill_id / lang available.
        self.assertEqual(out, {"intent_name": "play"})
        self.assertNotIn("skill_id", out)


class TestTranslatePayload(unittest.TestCase):
    """translate_payload direction selection + identity behaviour."""

    def setUp(self):
        self.t = NamespaceTranslator()

    def test_identity_for_payload_compatible_rename(self):
        data = {"utterances": ["hello"], "lang": "en-US"}
        # speak <-> ovos.utterance.speak has no transform entry -> identity.
        self.assertEqual(
            self.t.translate_payload("speak", "ovos.utterance.speak", data),
            data)
        self.assertEqual(
            self.t.translate_payload("ovos.utterance.speak", "speak", data),
            data)

    def test_identity_returns_new_dict(self):
        data = {"a": 1}
        out = self.t.translate_payload("speak", "ovos.utterance.speak", data)
        self.assertIsNot(out, data)

    def test_non_migrating_topic_returns_copy(self):
        data = {"x": 1}
        out = self.t.translate_payload("random.a", "random.b", data)
        self.assertEqual(out, data)
        self.assertIsNot(out, data)

    def test_direction_legacy_source_uses_legacy_to_spec(self):
        # from_topic legacy -> applies legacy_to_spec (split form).
        out = self.t.translate_payload(
            "detach_intent", "ovos.intent.deregister",
            {"intent_name": "s:n"})
        self.assertEqual(out, {"skill_id": "s", "intent_name": "n"})

    def test_direction_spec_source_uses_spec_to_legacy(self):
        # from_topic spec -> applies spec_to_legacy (join form).
        out = self.t.translate_payload(
            "ovos.intent.deregister", "detach_intent",
            {"skill_id": "s", "intent_name": "n"})
        self.assertEqual(out, {"intent_name": "s:n"})

    def test_handles_empty_data(self):
        self.assertEqual(
            self.t.translate_payload("detach_intent",
                                     "ovos.intent.deregister", {}),
            {})


if __name__ == "__main__":
    unittest.main()
