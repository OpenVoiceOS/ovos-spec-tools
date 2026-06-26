"""Canonical OVOS-spec bus-message topics and the legacy↔``ovos.*`` bridge.

Specs implemented
-----------------
This module is the vocabulary and migration map for the OVOS bus-namespace
move from the historical Mycroft topics to the ``ovos.*`` namespace. Each
:class:`SpecMessage` member names a topic an OVOS specification defines, and
is tied to its owning spec section in the per-member comments below:

- **OVOS-PIPELINE-1** — §8 handler-lifecycle trio
  (``ovos.intent.handler.{start,complete,error}``) and §9 utterance-layer
  topics (``ovos.utterance.{handle,speak,handled,cancelled}``,
  ``ovos.intent.{matched,unmatched}``);
- **OVOS-INTENT-4** — registration / deregistration / enable-disable /
  introspection topics (§§5–8, §10);
- **OVOS-STOP-1** — §4.2 ping/pong and §5 global-stop broadcast
  (``ovos.stop.*``);
- **OVOS-AUDIO-IN-1** — listener / mic / audio-output signals
  (``ovos.mic.listen``, ``ovos.listener.*``, ``ovos.audio.output.*``).
  These topic *names* are settled (memory: listening signals → AUDIO-IN-1
  ``ovos.listener.*``); the owning spec prose is still landing, so they are
  flagged **provisional** at their definitions.

Why an enum
-----------
Referencing ``SpecMessage.SPEAK`` instead of the raw
``"ovos.utterance.speak"`` makes downstream code self-documenting: a
``SpecMessage`` member is provably spec-defined, while a bare string is
visibly legacy or implementation-specific. The enum is the *vocabulary* half
of the migration; :data:`MIGRATION_MAP` is the *rename* half.

The transparent bridge (``MIGRATION_MAP`` / :class:`NamespaceTranslator`)
------------------------------------------------------------------------
``MIGRATION_MAP`` maps each legacy topic to the ``SpecMessage`` that replaces
it. The bridge is **payload-compatible and transparent**: a producer emits
only the spec topic, and the bus dual-emit (``ovos-bus-client``'s
``MessageBusClient`` and ``ovos_utils.fakebus.FakeBus``, both driven by
:class:`NamespaceTranslator`) *also* delivers the **same payload** under the
counterpart topic, so consumers still subscribed to the legacy name during
the migration window keep working without code changes. The receive side
deduplicates the mirror (see :meth:`NamespaceTranslator.new_mirror_guard`) so
a handler subscribed to both names runs once.

Because the bridge mirrors the payload **verbatim**, only renames that need
no payload transformation can live in the map. The two deliberate exclusions
are documented at :data:`MIGRATION_MAP`: the OVOS-INTENT-4 registration
*consolidation* (an N→1 restructure the bus cannot synthesize) and the
per-skill placeholder ``ovos.stop.*`` ping topics (not static strings).

Out of enum / map scope (OVOS-MSG-1 §2.1.1 runtime-assembled topics)
--------------------------------------------------------------------
Topics whose ``type`` is assembled at runtime from identifiers are neither
enum members nor static-mappable: ``ovos.pipeline.<pipeline_id>.intents.list``
(PIPELINE-1 §10), the ``<skill_id>:<intent_name>`` dispatch topic
(PIPELINE-1 §7), and the per-skill ``<skill_id>.stop.ping`` / ``<skill_id>.stop``
placeholders (STOP-1).
"""
import json as _json
import time
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple


class SpecMessage(str, Enum):
    """Canonical ``ovos.*`` bus topics defined by the OVOS specifications.

    Every member's value is a literal topic string a specification assigns to
    the ``ovos.*`` namespace; the per-member comments cite the owning spec
    section. Members subclass ``str`` (OVOS-MSG-1 §2.1 topics are strings) so
    they can be used directly as topics::

        bus.on(SpecMessage.SPEAK, handler)
        bus.emit(Message(SpecMessage.UTTERANCE, {...}))

    The enum grows as specs are catalogued/merged; absence of a topic here
    does not imply it is not spec-defined. Topics from specs still landing are
    flagged *provisional* in the comments.
    """

    def __str__(self) -> str:
        # Behave like py3.11 ``StrEnum``: ``str()`` / f-string yield the bare
        # topic ("ovos.utterance.speak"), not "SpecMessage.SPEAK", so a member
        # is interchangeable with the OVOS-MSG-1 §2.1 wire ``type`` string.
        return self.value

    # --- OVOS-PIPELINE-1 §9 utterance-layer topics ---
    #: §9.1 — utterance-layer entry point; producer→orchestrator (also the
    #: AUDIO-IN-1 §5 emission target).
    UTTERANCE = "ovos.utterance.handle"
    #: §9.6 — natural-language output exit point; handler→output layer.
    SPEAK = "ovos.utterance.speak"
    #: §9.5 — universal end-marker, exactly one per entry Message.
    UTTERANCE_HANDLED = "ovos.utterance.handled"
    #: §6.4 terminal event — utterance cancelled before a match was acted on.
    UTTERANCE_CANCELLED = "ovos.utterance.cancelled"
    #: §9.2 — match notification (NOT a dispatch), broadcast.
    INTENT_MATCHED = "ovos.intent.matched"
    #: §9.3 — emitted when pipeline iteration claimed no match, broadcast.
    INTENT_UNMATCHED = "ovos.intent.unmatched"
    # §8 handler-lifecycle trio — orchestrator-emitted around each dispatch,
    # each ``forward``-derived from the dispatch Message (§8, MSG-1 §5.1).
    INTENT_HANDLER_START = "ovos.intent.handler.start"      # §8.1 before invoke
    INTENT_HANDLER_COMPLETE = "ovos.intent.handler.complete"  # §8.1 normal return
    INTENT_HANDLER_ERROR = "ovos.intent.handler.error"       # §8.1 raised/timeout

    # --- OVOS-INTENT-4 registration / management / introspection topics ---
    #: §5 — register a keyword intent (vocab descriptors inlined, §5.1/§5.2).
    INTENT_REGISTER_KEYWORD = "ovos.intent.register.keyword"
    #: §6 — register a template intent.
    INTENT_REGISTER_TEMPLATE = "ovos.intent.register.template"
    #: §8.2 — remove one intent (the (skill_id, intent_name[, lang]) triple).
    INTENT_DEREGISTER = "ovos.intent.deregister"
    #: §8.5 — re-arm a previously disabled intent.
    INTENT_ENABLE = "ovos.intent.enable"
    #: §8.5 — suppress an intent without removing its definition.
    INTENT_DISABLE = "ovos.intent.disable"
    #: §7 — register an ``.entity`` value-set hint.
    ENTITY_REGISTER = "ovos.entity.register"
    #: §8.3 — remove one entity.
    ENTITY_DEREGISTER = "ovos.entity.deregister"
    #: §8.4 — remove everything owned by a skill_id.
    SKILL_DEREGISTER = "ovos.skill.deregister"
    #: §10.1 — query the orchestrator-owned manifest (observer→orchestrator).
    INTENT_LIST = "ovos.intent.list"
    #: §10.1 — the ``.response`` reply to ``ovos.intent.list`` (MSG-1 §5.3).
    INTENT_LIST_RESPONSE = "ovos.intent.list.response"
    #: §10.2 — query the full definition of one intent.
    INTENT_DESCRIBE = "ovos.intent.describe"
    #: §10.2 — the ``.response`` reply to ``ovos.intent.describe`` (MSG-1 §5.3).
    INTENT_DESCRIBE_RESPONSE = "ovos.intent.describe.response"

    # --- OVOS-STOP-1 stop cascade topics ---
    #: §4.2 — broadcast stoppability query. The per-skill ``<skill_id>.stop.ping``
    #: placeholder form is NOT static-mappable (see MIGRATION_MAP).
    STOP_PING = "ovos.stop.ping"
    #: §4.2 — shared stoppability reply topic; pong is ``reply``-derived (MSG-1 §5.2).
    STOP_PONG = "ovos.stop.pong"
    #: §5.3 — universal stop broadcast; ``ovos.stop.*`` namespace is reserved by STOP-1.
    STOP = "ovos.stop"

    # --- OVOS-AUDIO-IN-1 listener / mic / audio-output signals (provisional) ---
    # Topic names settled; owning AUDIO-IN-1 prose still landing (see module docstring).
    AUDIO_OUTPUT_STARTED = "ovos.audio.output.started"
    AUDIO_OUTPUT_ENDED = "ovos.audio.output.ended"
    MIC_LISTEN = "ovos.mic.listen"
    LISTENER_RECORD_STARTED = "ovos.listener.record.started"
    LISTENER_RECORD_ENDED = "ovos.listener.record.ended"
    LISTENER_SLEEP = "ovos.listener.sleep"
    LISTENER_AWOKEN = "ovos.listener.awoken"


#: Legacy (Mycroft-era) topic -> the :class:`SpecMessage` that supersedes it.
#: This is the single source of truth for the legacy↔``ovos.*`` renames that
#: the bus bridges transparently. ``NamespaceTranslator`` reads it (and its
#: reverse, :data:`SPEC_TO_LEGACY`) so a producer emits only the spec topic and
#: the bus dual-emits the legacy counterpart carrying the **same payload** —
#: consumers still on a legacy topic during the migration window keep receiving
#: data. Every entry here is a rename the bus can bridge **without transforming
#: the payload**; the two deliberate exclusions are documented at the bottom.
#:
#: For the renames marked "payload restructured" below (the handler trio and the
#: INTENT-4 management topics), the *bridge itself* still does not transform
#: anything: once the **producer** has adopted the spec payload shape
#: ({skill_id, intent_name}), the mirror carries that already-modern payload on
#: the legacy topic too. The restructure is a producer-side adoption, the bridge
#: is the topic rename — they compose, but the map only owns the rename.
MIGRATION_MAP: Dict[str, SpecMessage] = {
    # --- AUDIO-IN-1 / PIPELINE-1 §9 (payload-compatible 1:1 renames) ---
    "recognizer_loop:utterance": SpecMessage.UTTERANCE,        # PIPELINE-1 §9.1
    "speak": SpecMessage.SPEAK,                                # PIPELINE-1 §9.6
    "recognizer_loop:audio_output_start": SpecMessage.AUDIO_OUTPUT_STARTED,  # AUDIO-IN-1 (provisional)
    "recognizer_loop:audio_output_end": SpecMessage.AUDIO_OUTPUT_ENDED,      # AUDIO-IN-1 (provisional)
    "mycroft.mic.listen": SpecMessage.MIC_LISTEN,             # AUDIO-IN-1 (provisional)
    "recognizer_loop:record_begin": SpecMessage.LISTENER_RECORD_STARTED,  # AUDIO-IN-1 (provisional)
    "recognizer_loop:record_end": SpecMessage.LISTENER_RECORD_ENDED,      # AUDIO-IN-1 (provisional)
    "recognizer_loop:sleep": SpecMessage.LISTENER_SLEEP,     # AUDIO-IN-1 (provisional)
    "mycroft.awoken": SpecMessage.LISTENER_AWOKEN,           # AUDIO-IN-1 (provisional)
    # --- PIPELINE-1 §8 handler-lifecycle trio (rename; payload adopted by the
    #     producer to {skill_id, intent_name} — bridge mirrors verbatim) ---
    "mycroft.skill.handler.start": SpecMessage.INTENT_HANDLER_START,        # §8.1
    "mycroft.skill.handler.complete": SpecMessage.INTENT_HANDLER_COMPLETE,  # §8.1
    "mycroft.skill.handler.error": SpecMessage.INTENT_HANDLER_ERROR,        # §8.1
    # --- STOP-1 (1:1 renames) ---
    "skill.stop.pong": SpecMessage.STOP_PONG,   # STOP-1 §4.2 stoppability reply
    "mycroft.stop": SpecMessage.STOP,           # STOP-1 §5.3 universal stop broadcast
    # --- PIPELINE-1 §9.3 intent outcome (1:1 rename) ---
    "complete_intent_failure": SpecMessage.INTENT_UNMATCHED,
    # --- INTENT-4 §8 intent management (renames; producer adopts the
    #     {skill_id, intent_name} payload — bridge mirrors verbatim) ---
    "detach_intent": SpecMessage.INTENT_DEREGISTER,            # §8.2
    "detach_skill": SpecMessage.SKILL_DEREGISTER,              # §8.4
    "mycroft.skill.enable_intent": SpecMessage.INTENT_ENABLE,  # §8.5
    "mycroft.skill.disable_intent": SpecMessage.INTENT_DISABLE,  # §8.5
    #
    # ---- DELIBERATE EXCLUSION 1: INTENT-4 §5–§7 *registration* ----
    # ovos.intent.register.keyword / .register.template / ovos.entity.register
    # are NOT mappable, because the rename is not 1:1. Adapt emits N legacy
    # `register_vocab` messages + one `register_intent` (the intent references
    # its vocab by name); INTENT-4 §5.2 consolidates all of that into ONE
    # register.keyword Message with the vocab descriptors INLINED (§5.1). A
    # transparent bus bridge cannot synthesize that N→1 consolidation — it would
    # have to buffer and join messages it has no schema for — so registration
    # requires INTENT-4 *adoption* in the producer (ovos_workshop/intents.py) and
    # consumers (the pipeline plugins), not a static topic rename here.
    #
    # ---- DELIBERATE EXCLUSION 2: STOP-1 per-skill ping placeholders ----
    # The legacy stoppability handshake used per-skill topics shaped
    # `{skill_id}.stop.ping` / `{skill_id}.stop` (OVOS-MSG-1 §2.1.1 runtime-
    # assembled topics). STOP-1 §4.2/§5.3 replace them with the single broadcast
    # topics ovos.stop.ping / ovos.stop. A `{skill_id}.*` placeholder is not a
    # static string, so it cannot be a dict key; the migration there is handled by
    # producers/consumers subscribing on both forms, not by this map.
}

#: Reverse index: spec topic (plain ``str``) -> the legacy topic it replaces.
#: Derived from :data:`MIGRATION_MAP`; keys are ``SpecMessage.value`` strings so
#: lookups work with either an enum member (via its ``str`` value) or a raw topic.
SPEC_TO_LEGACY: Dict[str, str] = {v.value: k for k, v in MIGRATION_MAP.items()}


def migration_counterpart(topic: str) -> Optional[str]:
    """Return the other-namespace counterpart of a migrating topic, else ``None``.

    The bridge is symmetric: a legacy topic maps to its ``ovos.*`` replacement,
    and a spec topic maps back to the legacy name it replaces. This is the
    lookup the dual-emit (:meth:`NamespaceTranslator.counterpart_topics`) and
    the receive-side dedup (:meth:`NamespaceTranslator.new_mirror_guard`) both
    rest on.

    Args:
        topic: a bus topic string (legacy or ``ovos.*``).

    Returns:
        The counterpart topic as a plain ``str`` (a ``SpecMessage.value``, never
        the enum member itself), or ``None`` if ``topic`` does not migrate.
    """
    if topic in MIGRATION_MAP:
        # legacy -> spec; ``.value`` so the return is a plain str, not a member
        return MIGRATION_MAP[topic].value
    return SPEC_TO_LEGACY.get(topic)  # spec -> legacy, or None when unmapped


class NamespaceTranslator:
    """Shared legacy↔``ovos.*`` bus-namespace migration logic (OVOS bus bridge).

    This is the **reference implementation of the transparent dual-emit bridge**
    that ``ovos-bus-client``'s ``MessageBusClient`` and ``ovos_utils``'
    ``FakeBus`` both delegate to, so the real websocket bus and the
    test/satellite double behave identically. It carries no I/O and no config:
    the two direction flags are passed in (the caller reads env/config),
    keeping ``ovos-spec-tools`` dependency-free.

    The bridge has two halves, matching the two halves of a dual-emit bus:

    - **send side** — :meth:`counterpart_topics` tells the bus which extra
      topic to mirror an emission onto, so a producer that emits only the spec
      topic still reaches legacy subscribers (and vice-versa). The payload is
      copied verbatim (only renames that need no payload transformation are in
      :data:`MIGRATION_MAP`).
    - **receive side** — :meth:`new_mirror_guard` lets a handler subscribed to
      *both* names run exactly once, by recognising the mirror re-delivery and
      dropping it. :meth:`is_migrated` is the cheap pre-check ("does this topic
      participate at all?").

    Args:
        modernize: when ``True``, emitting a **legacy** topic also emits its
            ``ovos.*`` spec counterpart (carries the migration forward).
        emit_legacy: when ``True``, emitting an ``ovos.*`` **spec** topic also
            emits the legacy counterpart (keeps un-migrated consumers working).
        window: length, in ``clock`` seconds, of the **mirror window** — the
            interval within which a counterpart re-delivery of the same
            payload+context is treated as the mirror of a just-seen Message
            (and so suppressed) rather than a genuine second event.
    """

    def __init__(self, modernize: bool = True, emit_legacy: bool = True,
                 window: float = 1.0) -> None:
        self.modernize: bool = modernize
        self.emit_legacy: bool = emit_legacy
        self.window: float = window

    def counterpart_topics(self, msg_type: str) -> List[str]:
        """Extra topic(s) the bus should ALSO emit ``msg_type`` on (0 or 1).

        The result is the **send-side** half of the dual-emit: the bus emits the
        original Message, then re-emits the same payload on each returned topic.

        Args:
            msg_type: the topic the producer asked to emit.

        Returns:
            ``[spec_topic]`` when ``msg_type`` is a legacy topic and
            ``modernize`` is set; ``[legacy_topic]`` when ``msg_type`` is a spec
            topic and ``emit_legacy`` is set; ``[]`` otherwise (non-migrating
            topic, or the relevant direction disabled). At most one entry — a
            topic has exactly one counterpart.
        """
        if self.modernize and msg_type in MIGRATION_MAP:
            return [MIGRATION_MAP[msg_type].value]
        if self.emit_legacy and msg_type in SPEC_TO_LEGACY:
            return [SPEC_TO_LEGACY[msg_type]]
        return []

    def is_migrated(self, topic: str) -> bool:
        """Whether ``topic`` participates in the migration (so needs dedup).

        Args:
            topic: a bus topic string (legacy or ``ovos.*``).

        Returns:
            ``True`` if ``topic`` appears on either side of :data:`MIGRATION_MAP`
            — i.e. it has a counterpart and a handler subscribed to both names
            should run it through :meth:`new_mirror_guard`.
        """
        return topic in MIGRATION_MAP or topic in SPEC_TO_LEGACY

    def new_mirror_guard(self,
                         clock: Optional[Callable[[], float]] = None
                         ) -> Callable[[object], bool]:
        """Build a stateful ``is_mirror(message) -> bool`` for receive-side dedup.

        Each call returns a **fresh closure with its own private ``seen`` state**,
        so one guard is created per handler (or per subscription) and guards do
        not cross-talk. The returned predicate answers: *is this Message the
        dual-emit mirror of one this guard already let through?* — and a bus
        that subscribes a handler to both namespaces calls it to run the handler
        exactly once.

        Mirror-window semantics:

        - A Message is a **mirror** iff a previously-seen Message had the same
          payload+context fingerprint, a **different** ``msg_type``, and that
          earlier type's :func:`migration_counterpart` equals this one — i.e.
          it is the same event re-delivered on the counterpart topic. Mirrors
          return ``True`` (drop).
        - Two genuine events on the **same** topic are never suppressed
          (``prev[0] != mtype`` guards this): identical repeats on one topic
          are real repeats, not a mirror.
        - Entries older than ``window`` (per ``clock``) are evicted before each
          check, so a counterpart that arrives *after* the window is treated as
          a new event — the bridge only ever collapses a near-simultaneous
          dual-emit pair, never two deliberate emissions spaced apart.

        Args:
            clock: a monotonic seconds source; defaults to ``time.monotonic``,
                resolved **per call** so it stays monkeypatchable in tests.

        Returns:
            A predicate ``is_mirror(message) -> bool``. It is defensive: any
            message lacking ``msg_type`` / ``data`` / ``context``, or whose
            payload is not JSON-fingerprintable, returns ``False`` (never drop
            what we cannot prove is a mirror).
        """
        # Per-guard private state: fingerprint -> (msg_type, timestamp). Scoped
        # to this closure so distinct handlers never share dedup history.
        seen: Dict[str, Tuple[str, float]] = {}
        window = self.window

        def is_mirror(message: object) -> bool:
            try:
                mtype = message.msg_type  # type: ignore[attr-defined]
                # Fingerprint payload+context, order-independent (MSG-1 §6: key
                # order is not significant). ``default=str`` tolerates carrier
                # objects (e.g. Session) that are not natively JSON-encodable.
                fingerprint = _json.dumps([message.data, message.context],  # type: ignore[attr-defined]
                                          sort_keys=True, default=str)
            except Exception:
                # Not a Message-shaped object — cannot prove a mirror, so keep it.
                return False
            now = (clock or time.monotonic)()
            # Evict entries past the mirror window before matching.
            for key in [k for k, (_, ts) in seen.items() if now - ts >= window]:
                seen.pop(key, None)
            prev = seen.get(fingerprint)
            # Mirror iff same payload, DIFFERENT topic, and the topics are
            # registered counterparts of each other (a true dual-emit pair).
            if prev is not None and prev[0] != mtype \
                    and migration_counterpart(prev[0]) == mtype:
                return True
            seen[fingerprint] = (mtype, now)
            return False

        return is_mirror
