"""Tests for the spec bus-message registry."""
import unittest

from ovos_spec_tools import (
    MIGRATION_MAP,
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


if __name__ == "__main__":
    unittest.main()
