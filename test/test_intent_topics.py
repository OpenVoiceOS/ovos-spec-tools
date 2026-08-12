"""Tests for the canonical/legacy intent dispatch topic helpers."""
import unittest

from ovos_spec_tools import (
    INTENT_FILE_SUFFIX,
    canonical_intent_topic,
    intent_topic_counterpart,
    is_intent_topic,
    legacy_intent_topic,
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


if __name__ == "__main__":
    unittest.main()


class TestIsIntentTopicNarrowness(unittest.TestCase):
    """The predicate must not claim subsystem topics (bus-client#271, F2/C3)."""

    #: Every one of these carries a colon and none is a per-intent dispatch.
    NOT_INTENT_TOPICS = [
        "recognizer_loop:utterance",
        "recognizer_loop:record_begin",
        "recognizer_loop:record_end",
        "recognizer_loop:audio_output_start",
        "recognizer_loop:audio_output_end",
        "recognizer_loop:wakeword",
        "question:query",
        "question:action",
        "question:query.response",
        "padatious:register_intent",
        "padatious:register_entity",
        "stop:global",
        "speak:b64_audio",
        "skill-fake.jarbas:stop",
        "skill-fake.jarbas:converse",
        "skill-fake.jarbas:common_query",
        "play:query",
        "play:query.response",
        "play:status.query",
        "mycroft:something",
        "ovos:something",
        "gui:page_gained_focus",
    ]

    def test_subsystem_and_reserved_topics_are_not_intent_topics(self):
        for topic in self.NOT_INTENT_TOPICS:
            with self.subTest(topic=topic):
                self.assertFalse(is_intent_topic(topic))

    def test_suffixed_subsystem_topics_are_not_intent_topics_either(self):
        # a twin must never be manufactured for these, in either direction
        for topic in self.NOT_INTENT_TOPICS:
            with self.subTest(topic=topic):
                self.assertFalse(is_intent_topic(topic + ".intent"))

    def test_migrating_topics_belong_to_the_namespace_bridge(self):
        from ovos_spec_tools.messages import MIGRATION_MAP, SPEC_TO_LEGACY
        colon_topics = [t for t in list(MIGRATION_MAP) + list(SPEC_TO_LEGACY)
                        if ":" in t]
        self.assertTrue(colon_topics, "expected colon-bearing migrating topics")
        for topic in colon_topics:
            with self.subTest(topic=topic):
                self.assertFalse(is_intent_topic(topic))

    def test_ping_and_pong_are_not_reserved(self):
        # a skill may ship a ``ping.intent`` resource; excluding the name would
        # silently deny it the compat twin. No colon ``<skill_id>:ping`` topic
        # exists in the ecosystem -- the CommonQuery ones are dotted
        # (``ovos.common_query.ping``) and never reach this predicate.
        self.assertTrue(is_intent_topic("skill-fake.jarbas:ping"))
        self.assertTrue(is_intent_topic("skill-fake.jarbas:pong"))
        self.assertEqual(intent_topic_counterpart("skill-fake.jarbas:ping"),
                         "skill-fake.jarbas:ping.intent")

    def test_real_intent_dispatch_topics(self):
        for topic in ["skill-food.jarbas:food.order",
                      "skill-x:handle_thing",
                      "skill-x:Some Thing",
                      "skill-x:handle.some.thing.v2",
                      "ovos-skill-hello-world.openvoiceos:HelloWorldIntent"]:
            with self.subTest(topic=topic):
                self.assertTrue(is_intent_topic(topic))
                self.assertTrue(is_intent_topic(topic + ".intent"))

    def test_a_skill_id_starting_with_a_namespace_word_is_still_a_skill(self):
        # the guard is on the exact leading segment, not a prefix match
        self.assertTrue(is_intent_topic("questionnaire.jarbas:answer"))
        self.assertTrue(is_intent_topic("ovos-skill-stop.jarbas:halt"))

    def test_halves_must_be_non_empty(self):
        self.assertFalse(is_intent_topic(":foo"))
        self.assertFalse(is_intent_topic("skill:"))
        self.assertFalse(is_intent_topic("nocolon"))
        self.assertFalse(is_intent_topic(""))


class TestIntentTopicCounterpart(unittest.TestCase):

    def test_canonical_maps_to_suffixed(self):
        self.assertEqual(
            intent_topic_counterpart("skill-food.jarbas:food.order"),
            "skill-food.jarbas:food.order.intent")

    def test_suffixed_maps_back_to_canonical(self):
        self.assertEqual(
            intent_topic_counterpart("skill-food.jarbas:food.order.intent"),
            "skill-food.jarbas:food.order")

    def test_pairing_is_an_involution(self):
        topic = "skill-x:handle_thing"
        twin = intent_topic_counterpart(topic)
        self.assertEqual(intent_topic_counterpart(twin), topic)

    def test_non_intent_topics_have_no_counterpart(self):
        for topic in TestIsIntentTopicNarrowness.NOT_INTENT_TOPICS + ["nocolon", ""]:
            with self.subTest(topic=topic):
                self.assertIsNone(intent_topic_counterpart(topic))

    def test_a_bare_dot_intent_name_has_no_distinct_counterpart(self):
        self.assertIsNone(intent_topic_counterpart("skill-x:.intent"))
