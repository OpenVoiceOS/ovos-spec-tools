"""Canonical OVOS spec bus-message topics and the legacy→spec migration map.

``SpecMessage`` is a string enum of the bus topics the OVOS specifications
define under the ``ovos.*`` namespace. Referencing ``SpecMessage.SPEAK`` instead
of the raw ``"ovos.utterance.speak"`` makes downstream code self-documenting: a
``SpecMessage`` member is provably spec-defined, while a bare string is visibly
legacy or implementation-specific.

``MIGRATION_MAP`` maps each legacy topic to the ``SpecMessage`` that replaces it,
**only for renames where the legacy payload already satisfies the new topic's
consumers** (identical, empty, or superset payloads). Renames that also change
the payload *shape* (e.g. the handler-lifecycle trio, the INTENT-4 registration
restructure) are deliberately excluded — those need per-site payload
transformation, not a transparent topic rename, since a transparent dual-emit
would deliver legacy-shaped data on the new topic.

Topics with placeholders (``ovos.pipeline.<pipeline_id>.intents.list``,
``<skill_id>:<intent_name>``) are not enum members.
"""
import json as _json
import time
from enum import Enum
from typing import Callable, Dict, List, Optional


class SpecMessage(str, Enum):
    """Canonical ``ovos.*`` bus topics defined by the OVOS specifications.

    Members are ``str`` so they can be used directly as topics::

        bus.on(SpecMessage.SPEAK, handler)
        bus.emit(Message(SpecMessage.UTTERANCE, {...}))

    The enum grows as specs are catalogued/merged; absence of a topic here does
    not imply it is not spec-defined. Topics from specs still in open PRs are
    marked provisional.
    """

    def __str__(self) -> str:
        # behave like py3.11 StrEnum: str()/f-string yield the topic, not
        # "SpecMessage.SPEAK"
        return self.value

    # --- PIPELINE-1 ---
    UTTERANCE = "ovos.utterance.handle"
    SPEAK = "ovos.utterance.speak"
    UTTERANCE_HANDLED = "ovos.utterance.handled"
    UTTERANCE_CANCELLED = "ovos.utterance.cancelled"
    INTENT_MATCHED = "ovos.intent.matched"
    INTENT_UNMATCHED = "ovos.intent.unmatched"
    INTENT_HANDLER_START = "ovos.intent.handler.start"
    INTENT_HANDLER_COMPLETE = "ovos.intent.handler.complete"
    INTENT_HANDLER_ERROR = "ovos.intent.handler.error"

    # --- INTENT-4 ---
    INTENT_REGISTER_KEYWORD = "ovos.intent.register.keyword"
    INTENT_REGISTER_TEMPLATE = "ovos.intent.register.template"
    INTENT_DEREGISTER = "ovos.intent.deregister"
    INTENT_ENABLE = "ovos.intent.enable"
    INTENT_DISABLE = "ovos.intent.disable"
    ENTITY_REGISTER = "ovos.entity.register"
    ENTITY_DEREGISTER = "ovos.entity.deregister"
    SKILL_DEREGISTER = "ovos.skill.deregister"
    INTENT_LIST = "ovos.intent.list"
    INTENT_LIST_RESPONSE = "ovos.intent.list.response"
    INTENT_DESCRIBE = "ovos.intent.describe"
    INTENT_DESCRIBE_RESPONSE = "ovos.intent.describe.response"

    # --- STOP-1 ---
    STOP_PING = "ovos.stop.ping"
    STOP_PONG = "ovos.stop.pong"
    STOP = "ovos.stop"

    # --- AUDIO-1 ---
    AUDIO_OUTPUT_STARTED = "ovos.audio.output.started"
    AUDIO_OUTPUT_ENDED = "ovos.audio.output.ended"
    MIC_LISTEN = "ovos.mic.listen"
    LISTENER_RECORD_STARTED = "ovos.listener.record.started"
    LISTENER_RECORD_ENDED = "ovos.listener.record.ended"
    LISTENER_SLEEP = "ovos.listener.sleep"
    LISTENER_AWOKEN = "ovos.listener.awoken"


# legacy topic -> SpecMessage that supersedes it. This is the single source of
# truth for the legacy<->ovos.* topic renames; the bus (NamespaceTranslator) reads
# it to bridge BOTH namespaces transparently, so producers emit only the spec topic
# (from SpecMessage) and never hand-roll a dual-emit. Producers emit the spec
# payload; the bridged legacy message carries that same payload (consumers still on
# a legacy topic during the migration window receive the spec-shaped data — for the
# shape-changing renames below, e.g. the handler trio, that means the new
# skill_id/intent_name fields rather than the old `name`).
#
# Only 1:1 static renames live here. Per-instance topics with placeholders
# (``{skill_id}.stop.ping``, ``{skill_id}.stop`` -> the broadcast ``ovos.stop.ping``
# / ``ovos.stop``) cannot be expressed as a static map and are handled by
# producers/consumers subscribing on both forms.
MIGRATION_MAP: Dict[str, SpecMessage] = {
    # --- AUDIO-IN-1 / PIPELINE-1 (payload-compatible) ---
    "recognizer_loop:utterance": SpecMessage.UTTERANCE,
    "speak": SpecMessage.SPEAK,
    "recognizer_loop:audio_output_start": SpecMessage.AUDIO_OUTPUT_STARTED,
    "recognizer_loop:audio_output_end": SpecMessage.AUDIO_OUTPUT_ENDED,
    "mycroft.mic.listen": SpecMessage.MIC_LISTEN,
    "recognizer_loop:record_begin": SpecMessage.LISTENER_RECORD_STARTED,
    "recognizer_loop:record_end": SpecMessage.LISTENER_RECORD_ENDED,
    "recognizer_loop:sleep": SpecMessage.LISTENER_SLEEP,
    "mycroft.awoken": SpecMessage.LISTENER_AWOKEN,
    # --- PIPELINE-1 §8 handler-lifecycle trio (payload restructured to
    #     {skill_id, intent_name}; bridged transparently per the note above) ---
    "mycroft.skill.handler.start": SpecMessage.INTENT_HANDLER_START,
    "mycroft.skill.handler.complete": SpecMessage.INTENT_HANDLER_COMPLETE,
    "mycroft.skill.handler.error": SpecMessage.INTENT_HANDLER_ERROR,
    # --- STOP-1 §4.2/§5.3 (1:1 renames) ---
    "skill.stop.pong": SpecMessage.STOP_PONG,
    "mycroft.stop": SpecMessage.STOP,
}

# reverse: spec topic (plain str) -> the legacy topic it replaces
SPEC_TO_LEGACY: Dict[str, str] = {v.value: k for k, v in MIGRATION_MAP.items()}


def migration_counterpart(topic: str) -> Optional[str]:
    """Return the other-namespace topic for a migrating topic, else ``None``.

    A legacy topic returns its ``ovos.*`` replacement; a spec topic returns the
    legacy name it replaces; an unmapped topic returns ``None``. Always a plain
    ``str``.
    """
    if topic in MIGRATION_MAP:
        return MIGRATION_MAP[topic].value
    return SPEC_TO_LEGACY.get(topic)


class NamespaceTranslator:
    """Shared legacy<->``ovos.*`` bus-namespace migration logic.

    Used by both ``ovos_bus_client.MessageBusClient`` and
    ``ovos_utils.fakebus.FakeBus`` so the real bus and the test/satellite double
    behave identically. Pure logic: the two flags are passed in (the caller reads
    env/config), keeping ``ovos-spec-tools`` dependency-free.

    Args:
        modernize: emitting a legacy topic also emits the ``ovos.*`` spec topic.
        emit_legacy: emitting an ``ovos.*`` spec topic also emits the legacy topic.
        window: seconds within which a counterpart re-delivery is a "mirror".
    """

    def __init__(self, modernize: bool = True, emit_legacy: bool = True,
                 window: float = 1.0):
        self.modernize = modernize
        self.emit_legacy = emit_legacy
        self.window = window

    def counterpart_topics(self, msg_type: str) -> List[str]:
        """Topic(s) a producer should ALSO emit for ``msg_type`` (0 or 1)."""
        if self.modernize and msg_type in MIGRATION_MAP:
            return [MIGRATION_MAP[msg_type].value]
        if self.emit_legacy and msg_type in SPEC_TO_LEGACY:
            return [SPEC_TO_LEGACY[msg_type]]
        return []

    def is_migrated(self, topic: str) -> bool:
        """Whether ``topic`` participates in the migration (needs dedup)."""
        return topic in MIGRATION_MAP or topic in SPEC_TO_LEGACY

    def new_mirror_guard(self,
                         clock: Optional[Callable[[], float]] = None
                         ) -> Callable[[object], bool]:
        """Return a per-handler ``is_mirror(message) -> bool`` with private state.

        Returns True when ``message`` is the legacy/``ovos.*`` mirror of one just
        handled — same payload+context re-delivered via the COUNTERPART topic
        within the window — so the handler runs once. Two genuine events on the
        SAME topic are never suppressed. ``clock`` defaults to
        ``time.monotonic`` (resolved per call, so it stays monkeypatchable).
        """
        seen: Dict[str, tuple] = {}
        window = self.window

        def is_mirror(message) -> bool:
            try:
                mtype = message.msg_type
                fingerprint = _json.dumps([message.data, message.context],
                                          sort_keys=True, default=str)
            except Exception:
                return False
            now = (clock or time.monotonic)()
            for key in [k for k, (_, ts) in seen.items() if now - ts >= window]:
                seen.pop(key, None)
            prev = seen.get(fingerprint)
            if prev is not None and prev[0] != mtype \
                    and migration_counterpart(prev[0]) == mtype:
                return True
            seen[fingerprint] = (mtype, now)
            return False

        return is_mirror
