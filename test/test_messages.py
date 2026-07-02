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


#: The complete set of STATIC (non-templated) ``ovos.*`` topics the OVOS
#: architecture specs normatively define, each mapped to its owning spec +
#: section. This is the golden reference: ``SpecMessage`` MUST contain exactly
#: this set — every spec topic has a member (completeness) and every member is a
#: spec topic (spec-only-ness). Runtime-templated topics (MSG-1 §2.1.1:
#: ``<skill_id>:…`` / ``<pipeline_id>…`` / per-skill ping placeholders) are
#: deliberately excluded, as are bus-client internals no spec defines
#: (``ovos.session.update_default``, ``ovos.session.start``, ``ovos.context.*``).
SPEC_STATIC_TOPICS = {
    # OVOS-PIPELINE-1 §8/§9 utterance + intent layer
    "ovos.utterance.handle": "PIPELINE-1 §9.1",
    "ovos.utterance.speak": "PIPELINE-1 §9.6",
    "ovos.utterance.handled": "PIPELINE-1 §9.5",
    "ovos.intent.matched": "PIPELINE-1 §9.2",
    "ovos.intent.unmatched": "PIPELINE-1 §9.3",
    "ovos.intent.handler.start": "PIPELINE-1 §8.1",
    "ovos.intent.handler.complete": "PIPELINE-1 §8.1",
    "ovos.intent.handler.error": "PIPELINE-1 §8.1",
    # OVOS-TRANSFORM-1
    "ovos.utterance.cancelled": "TRANSFORM-1 §8.2",
    "ovos.transformer.audio.list": "TRANSFORM-1 §6",
    "ovos.transformer.audio.list.response": "TRANSFORM-1 §6",
    "ovos.transformer.utterance.list": "TRANSFORM-1 §6",
    "ovos.transformer.utterance.list.response": "TRANSFORM-1 §6",
    "ovos.transformer.metadata.list": "TRANSFORM-1 §6",
    "ovos.transformer.metadata.list.response": "TRANSFORM-1 §6",
    "ovos.transformer.intent.list": "TRANSFORM-1 §6",
    "ovos.transformer.intent.list.response": "TRANSFORM-1 §6",
    "ovos.transformer.dialog.list": "TRANSFORM-1 §6",
    "ovos.transformer.dialog.list.response": "TRANSFORM-1 §6",
    "ovos.transformer.tts.list": "TRANSFORM-1 §6",
    "ovos.transformer.tts.list.response": "TRANSFORM-1 §6",
    # OVOS-INTENT-4
    "ovos.intent.register.keyword": "INTENT-4 §5",
    "ovos.intent.register.template": "INTENT-4 §6",
    "ovos.entity.register": "INTENT-4 §7",
    "ovos.intent.deregister": "INTENT-4 §8.2",
    "ovos.entity.deregister": "INTENT-4 §8.3",
    "ovos.skill.deregister": "INTENT-4 §8.4",
    "ovos.intent.enable": "INTENT-4 §8.5",
    "ovos.intent.disable": "INTENT-4 §8.5",
    "ovos.intent.list": "INTENT-4 §10.1",
    "ovos.intent.list.response": "INTENT-4 §10.1",
    "ovos.intent.describe": "INTENT-4 §10.2",
    "ovos.intent.describe.response": "INTENT-4 §10.2",
    # OVOS-STOP-1
    "ovos.stop.ping": "STOP-1 §4.2",
    "ovos.stop.pong": "STOP-1 §4.2",
    "ovos.stop": "STOP-1 §5.3",
    # OVOS-AUDIO-1 (audio output)
    "ovos.utterance.speak.b64": "AUDIO-1 §3.4",
    "ovos.audio.speech": "AUDIO-1 §4.3",
    "ovos.audio.queue": "AUDIO-1 §4.1",
    "ovos.audio.play_sound": "AUDIO-1 §4.2",
    "ovos.audio.stop": "AUDIO-1 §6",
    "ovos.audio.is_speaking": "AUDIO-1 §5.3",
    "ovos.audio.output.started": "AUDIO-1 §5.1",
    "ovos.audio.output.ended": "AUDIO-1 §5.2",
    "ovos.mic.listen": "AUDIO-1 §4.4",
    # OVOS-AUDIO-IN-1 (listener)
    "ovos.listener.record.started": "AUDIO-IN-1 §6.1",
    "ovos.listener.record.ended": "AUDIO-IN-1 §6.2",
    "ovos.listener.sleep": "AUDIO-IN-1 §6.3",
    "ovos.listener.awoken": "AUDIO-IN-1 §6.4",
    # OVOS-SESSION-2
    "ovos.session.sync": "SESSION-2 §2.7",
    # OVOS-CONVERSE-1
    "ovos.converse.active.list": "CONVERSE-1 §6.1",
    "ovos.converse.active.list.response": "CONVERSE-1 §6.1",
    # OVOS-PERSONA-1 §11 bus surface
    "ovos.persona.query": "PERSONA-1 §8.5",
    "ovos.persona.answer": "PERSONA-1 §8.5",
    "ovos.persona.list": "PERSONA-1 §8.7",
    "ovos.persona.list.response": "PERSONA-1 §8.7",
    "ovos.persona.register": "PERSONA-1 §9",
    "ovos.persona.deregister": "PERSONA-1 §9",
    "ovos.persona.activated": "PERSONA-1 §11",
    "ovos.persona.dismissed": "PERSONA-1 §11",
    # OVOS-FALLBACK-1 §9 bus surface
    "ovos.fallback.register": "FALLBACK-1 §3.1",
    "ovos.fallback.deregister": "FALLBACK-1 §3.2",
    # OVOS-COMMON-QUERY-1 §13 bus surface
    "ovos.common_query.ping": "COMMON-QUERY-1 §6.1",
    "ovos.common_query.pong": "COMMON-QUERY-1 §6.2",
    # OVOS-OCP-1 §4 Virtual Media Player
    "ovos.common_play.play": "OCP-1 §4.2",
    "ovos.common_play.search": "OCP-1 §4.2",
    "ovos.common_play.pause": "OCP-1 §4.3",
    "ovos.common_play.resume": "OCP-1 §4.3",
    "ovos.common_play.stop": "OCP-1 §4.3",
    "ovos.common_play.next": "OCP-1 §4.3",
    "ovos.common_play.previous": "OCP-1 §4.3",
    "ovos.common_play.seek": "OCP-1 §4.3",
    "ovos.common_play.player.state": "OCP-1 §4.4",
    "ovos.common_play.media.state": "OCP-1 §4.4",
    "ovos.common_play.track.state": "OCP-1 §4.4",
}

#: Topics ``ovos-bus-client`` uses that NO spec defines, so they MUST NOT be
#: enum members (SESSION-2 §1 defers lifecycle topics; CONTEXT-1 §5 routes
#: context mutations through ``ovos.session.sync``, not ``ovos.context.*``).
NON_SPEC_BUS_CLIENT_TOPICS = {
    "ovos.session.update_default",
    "ovos.session.start",
    "ovos.context.set",
    "ovos.context.unset",
    "ovos.context.clear",
}


class TestSpecCompleteness(unittest.TestCase):
    """The enum is the single source of truth: spec-complete and spec-only."""

    def test_enum_covers_every_spec_static_topic(self):
        # Completeness: every normative static spec topic has an enum member.
        members = {m.value for m in SpecMessage}
        missing = set(SPEC_STATIC_TOPICS) - members
        self.assertFalse(missing, f"spec topics with no enum member: {missing}")

    def test_enum_is_spec_only(self):
        # Spec-only-ness: every enum member is a normative spec topic.
        members = {m.value for m in SpecMessage}
        extra = members - set(SPEC_STATIC_TOPICS)
        self.assertFalse(extra, f"enum members not traced to a spec: {extra}")

    def test_enum_matches_spec_set_exactly(self):
        self.assertEqual({m.value for m in SpecMessage},
                         set(SPEC_STATIC_TOPICS))

    def test_bus_client_internals_are_not_enum_members(self):
        # session.sync IS spec (SESSION-2 §2.7); update_default/start/context.*
        # are NOT and must stay out of the enum.
        members = {m.value for m in SpecMessage}
        for topic in NON_SPEC_BUS_CLIENT_TOPICS:
            self.assertNotIn(topic, members,
                             f"{topic} is not spec-defined; must not be a member")
        self.assertIn("ovos.session.sync", members)  # SESSION-2 §2.7

    def test_no_templated_topics_are_members(self):
        # Runtime-assembled topics (MSG-1 §2.1.1) are never static members.
        for m in SpecMessage:
            self.assertNotIn("<", m.value, m.value)
            self.assertNotIn(":", m.value, m.value)


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


class TestStopDispatchPattern(unittest.TestCase):
    """OVOS-STOP-1 §2: per-skill `<skill_id>:stop` bridges to `<skill_id>.stop`."""

    def setUp(self):
        self.t = NamespaceTranslator(modernize=True, emit_legacy=True)

    def test_counterpart_of_stop_dispatch(self):
        self.assertEqual(migration_counterpart("lights.skill:stop"),
                         "lights.skill.stop")

    def test_dotted_skill_id_preserved(self):
        self.assertEqual(migration_counterpart("ovos.skill.foo:stop"),
                         "ovos.skill.foo.stop")

    def test_non_stop_intent_not_matched(self):
        self.assertIsNone(migration_counterpart("lights.skill:turn_on"))

    def test_global_stop_not_matched(self):
        # `<pipeline_id>:global_stop` is the plugin's own self-dispatch, not a
        # per-skill `:stop`, so it must not bridge.
        self.assertIsNone(migration_counterpart("ovos-stop-pipeline-plugin:global_stop"))

    def test_static_map_takes_precedence(self):
        # `mycroft.stop` ends in `.stop` but is the global rename in the map.
        self.assertEqual(migration_counterpart("mycroft.stop"), "ovos.stop")

    def test_send_side_mirrors_legacy_stop(self):
        self.assertEqual(self.t.counterpart_topics("lights.skill:stop"),
                         ["lights.skill.stop"])

    def test_emit_legacy_off_no_mirror(self):
        t = NamespaceTranslator(modernize=True, emit_legacy=False)
        self.assertEqual(t.counterpart_topics("lights.skill:stop"), [])

    def test_is_migrated(self):
        self.assertTrue(self.t.is_migrated("lights.skill:stop"))
        self.assertFalse(self.t.is_migrated("lights.skill:turn_on"))


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
