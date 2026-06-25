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
from enum import Enum
from typing import Dict, Optional


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

    # --- PIPELINE-1 (merged) ---
    UTTERANCE = "ovos.utterance.handle"
    SPEAK = "ovos.utterance.speak"
    UTTERANCE_HANDLED = "ovos.utterance.handled"
    UTTERANCE_CANCELLED = "ovos.utterance.cancelled"
    INTENT_MATCHED = "ovos.intent.matched"
    INTENT_UNMATCHED = "ovos.intent.unmatched"
    INTENT_HANDLER_START = "ovos.intent.handler.start"
    INTENT_HANDLER_COMPLETE = "ovos.intent.handler.complete"
    INTENT_HANDLER_ERROR = "ovos.intent.handler.error"

    # --- INTENT-4 (merged) ---
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

    # --- STOP-1 (merged) ---
    STOP_PING = "ovos.stop.ping"
    STOP_PONG = "ovos.stop.pong"
    STOP = "ovos.stop"

    # --- AUDIO-1 (provisional, PR #38) ---
    AUDIO_OUTPUT_STARTED = "ovos.audio.output.started"
    AUDIO_OUTPUT_ENDED = "ovos.audio.output.ended"
    MIC_LISTEN = "ovos.mic.listen"

    # --- AUDIO-IN-1 listening signals (provisional, PR #69) ---
    LISTENER_RECORD_STARTED = "ovos.listener.record.started"
    LISTENER_RECORD_ENDED = "ovos.listener.record.ended"
    LISTENER_SLEEP = "ovos.listener.sleep"
    LISTENER_AWOKEN = "ovos.listener.awoken"


# legacy topic -> SpecMessage that supersedes it, RESTRICTED to renames whose
# legacy payload already satisfies the new topic's consumers (so a transparent
# dual-emit is safe). Shape-changing renames are intentionally absent.
MIGRATION_MAP: Dict[str, SpecMessage] = {
    "recognizer_loop:utterance": SpecMessage.UTTERANCE,
    "speak": SpecMessage.SPEAK,
    "recognizer_loop:audio_output_start": SpecMessage.AUDIO_OUTPUT_STARTED,
    "recognizer_loop:audio_output_end": SpecMessage.AUDIO_OUTPUT_ENDED,
    "mycroft.mic.listen": SpecMessage.MIC_LISTEN,
    "recognizer_loop:record_begin": SpecMessage.LISTENER_RECORD_STARTED,
    "recognizer_loop:record_end": SpecMessage.LISTENER_RECORD_ENDED,
    "recognizer_loop:sleep": SpecMessage.LISTENER_SLEEP,
    "mycroft.awoken": SpecMessage.LISTENER_AWOKEN,
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
