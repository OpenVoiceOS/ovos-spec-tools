"""Tests for the canonical/legacy intent dispatch topic helpers."""
import unittest

from ovos_spec_tools import (
    INTENT_FILE_SUFFIX,
    IntentAliasRegistry,
    canonical_intent_topic,
    is_intent_topic,
    legacy_intent_topic,
    legacy_reemit_targets,
)


class TestIsIntentTopic(unittest.TestCase):
    def test_colon_topic_is_an_intent_topic(self):
        self.assertTrue(is_intent_topic("skill.foo:play"))
        self.assertTrue(is_intent_topic("skill.foo:play.intent"))

    def test_dotted_topic_without_colon_is_not(self):
        self.assertFalse(is_intent_topic("ovos.intent.register.keyword"))
        self.assertFalse(is_intent_topic("speak"))
        # a dotted topic that merely ends in the suffix is NOT a dispatch
        self.assertFalse(is_intent_topic("some.topic.intent"))

    def test_empty_halves_are_not_topics(self):
        self.assertFalse(is_intent_topic(""))
        self.assertFalse(is_intent_topic(":play"))
        self.assertFalse(is_intent_topic("skill.foo:"))
        self.assertFalse(is_intent_topic(":"))

    def test_multiple_colons_split_on_the_last(self):
        self.assertTrue(is_intent_topic("a:b:c"))


class TestCanonicalIntentTopic(unittest.TestCase):
    def test_strips_the_suffix(self):
        self.assertEqual(canonical_intent_topic("skill.foo:food.order.intent"),
                         "skill.foo:food.order")

    def test_idempotent(self):
        once = canonical_intent_topic("skill.foo:play.intent")
        self.assertEqual(canonical_intent_topic(once), once)
        self.assertEqual(once, "skill.foo:play")

    def test_already_canonical_unchanged(self):
        self.assertEqual(canonical_intent_topic("skill.foo:play"),
                         "skill.foo:play")

    def test_non_intent_topics_unchanged(self):
        for topic in ("speak", "ovos.intent.register.keyword",
                      "some.topic.intent", "", ":play", "skill:"):
            self.assertEqual(canonical_intent_topic(topic), topic)

    def test_only_the_last_colon_half_is_stripped(self):
        # a skill_id ending in the suffix must survive intact
        self.assertEqual(canonical_intent_topic("weird.intent:play.intent"),
                         "weird.intent:play")
        self.assertEqual(canonical_intent_topic("weird.intent:play"),
                         "weird.intent:play")
        self.assertEqual(canonical_intent_topic("a:b.intent:c.intent"),
                         "a:b.intent:c")

    def test_bare_suffix_intent_name_is_left_alone(self):
        # stripping would leave an empty intent name -> not a valid topic
        self.assertEqual(canonical_intent_topic("skill.foo:.intent"),
                         "skill.foo:.intent")

    def test_suffix_inside_the_name_is_not_stripped(self):
        self.assertEqual(canonical_intent_topic("skill.foo:play.intent.now"),
                         "skill.foo:play.intent.now")


class TestLegacyIntentTopic(unittest.TestCase):
    def test_appends_the_suffix(self):
        self.assertEqual(legacy_intent_topic("skill.foo:food.order"),
                         "skill.foo:food.order.intent")

    def test_idempotent(self):
        once = legacy_intent_topic("skill.foo:play")
        self.assertEqual(legacy_intent_topic(once), once)

    def test_non_intent_topics_unchanged(self):
        for topic in ("speak", "some.topic", "", ":play", "skill:"):
            self.assertEqual(legacy_intent_topic(topic), topic)

    def test_round_trip_is_lossless(self):
        for canonical in ("skill.foo:play", "weird.intent:play", "a:b:c"):
            self.assertEqual(
                canonical_intent_topic(legacy_intent_topic(canonical)),
                canonical)

    def test_suffix_constant(self):
        self.assertEqual(INTENT_FILE_SUFFIX, ".intent")


class TestIntentAliasRegistry(unittest.TestCase):
    def setUp(self):
        self.reg = IntentAliasRegistry()

    def test_canonical_registration_records_no_alias(self):
        self.assertEqual(self.reg.register("skill.foo:play"), "skill.foo:play")
        self.assertTrue(self.reg.is_registered("skill.foo:play"))
        self.assertFalse(self.reg.has_legacy_alias("skill.foo:play"))
        self.assertIsNone(self.reg.legacy_alias("skill.foo:play"))

    def test_legacy_registration_records_the_alias(self):
        self.assertEqual(self.reg.register("skill.foo:play.intent"),
                         "skill.foo:play")
        self.assertTrue(self.reg.has_legacy_alias("skill.foo:play"))
        self.assertEqual(self.reg.legacy_alias("skill.foo:play"),
                         "skill.foo:play.intent")

    def test_both_spellings_collapse_onto_one_key(self):
        a = self.reg.register("skill.foo:play")
        b = self.reg.register("skill.foo:play.intent")
        self.assertEqual(a, b)
        self.assertEqual(len(tuple(self.reg.aliases())), 1)
        # queried by either spelling, the answer is the same
        self.assertTrue(self.reg.is_registered("skill.foo:play.intent"))
        self.assertTrue(self.reg.has_legacy_alias("skill.foo:play.intent"))

    def test_unregistered_topic(self):
        self.assertFalse(self.reg.is_registered("skill.foo:play"))
        self.assertFalse(self.reg.has_legacy_alias("skill.foo:play"))

    def test_deregister_by_either_spelling(self):
        self.reg.register("skill.foo:play.intent")
        self.reg.deregister("skill.foo:play")
        self.assertFalse(self.reg.is_registered("skill.foo:play"))
        self.assertFalse(self.reg.has_legacy_alias("skill.foo:play"))
        # deregistering twice, or an unknown topic, is a no-op
        self.reg.deregister("skill.foo:play")
        self.reg.deregister("never.seen:x")

    def test_non_intent_topics_are_not_recorded(self):
        self.assertEqual(self.reg.register("speak"), "speak")
        self.assertFalse(self.reg.is_registered("speak"))
        self.assertEqual(tuple(self.reg.aliases()), ())

    def test_canonical_query_needs_no_registration(self):
        self.assertEqual(self.reg.canonical("skill.foo:play.intent"),
                         "skill.foo:play")

    def test_clear(self):
        self.reg.register("skill.foo:play.intent")
        self.reg.clear()
        self.assertEqual(tuple(self.reg.aliases()), ())
        self.assertFalse(self.reg.is_registered("skill.foo:play"))


class TestLegacyReemitTargets(unittest.TestCase):
    def setUp(self):
        self.reg = IntentAliasRegistry()

    def test_alias_driven_reemit(self):
        self.reg.register("skill.foo:play.intent")
        self.assertEqual(legacy_reemit_targets("skill.foo:play", self.reg),
                         ["skill.foo:play.intent"])

    def test_no_alias_no_reemit(self):
        self.reg.register("skill.foo:play")
        self.assertEqual(legacy_reemit_targets("skill.foo:play", self.reg), [])

    def test_no_registry_no_reemit(self):
        self.assertEqual(legacy_reemit_targets("skill.foo:play"), [])

    def test_blanket_reemits_every_intent_topic(self):
        self.assertEqual(
            legacy_reemit_targets("skill.foo:play", blanket=True),
            ["skill.foo:play.intent"])
        self.assertEqual(
            legacy_reemit_targets("skill.foo:play", self.reg, blanket=True),
            ["skill.foo:play.intent"])

    def test_blanket_still_ignores_non_intent_topics(self):
        self.assertEqual(legacy_reemit_targets("speak", blanket=True), [])
        self.assertEqual(
            legacy_reemit_targets("ovos.intent.register.keyword", blanket=True),
            [])

    def test_the_mirror_never_cascades(self):
        self.reg.register("skill.foo:play.intent")
        self.assertEqual(
            legacy_reemit_targets("skill.foo:play.intent", self.reg), [])
        self.assertEqual(
            legacy_reemit_targets("skill.foo:play.intent", blanket=True), [])

    def test_at_most_one_target(self):
        self.reg.register("skill.foo:play.intent")
        self.assertEqual(len(legacy_reemit_targets("skill.foo:play", self.reg,
                                                   blanket=True)), 1)


if __name__ == "__main__":
    unittest.main()
