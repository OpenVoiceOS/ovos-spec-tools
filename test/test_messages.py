"""Tests for the spec bus-message registry."""
import unittest

from ovos_spec_tools import (
    MIGRATION_MAP,
    SPEC_TO_LEGACY,
    SpecMessage,
    migration_counterpart,
)


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
