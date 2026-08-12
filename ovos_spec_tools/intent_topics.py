"""Canonical ↔ legacy intent **dispatch topic** helpers (OVOS-MSG-1 / -INTENT-4).

OVOS-MSG-1 §2.1.1 assembles the per-intent dispatch topic from named
identifiers at runtime: ``<skill_id>:<intent_name>``. OVOS-PIPELINE-1 §4
dispatches a matched intent on that topic. The intent **name** is the skill
author's label for the intent; it is **not** the name of the file the samples
came from.

Older ``ovos-workshop`` releases built the topic straight from the padatious
resource **filename**, so a skill with a ``food.order.intent`` resource
registered and listened on ``<skill_id>:food.order.intent`` — the authoring
file extension leaked onto the wire. Current workshop is spec-pure: it strips
the extension and registers ``<skill_id>:food.order``.

Old skills still run: a containerized skill built against an old workshop
subscribes to the suffixed topic over the real bus, and a new core dispatching
the canonical topic would never reach it. This module is the **whole** compat
surface for that gap, and it is two pure functions:

- :func:`canonical_intent_topic` — remove the suffix;
- :func:`legacy_intent_topic` — add it back.

Both are total and idempotent, and neither holds state. A bus bridges the two
spellings with them alone: it sends the legacy twin of every canonical intent
topic it emits, and it dispatches the canonical form of every suffixed topic it
receives. No registry of who listens to what is necessary — an unheard twin
costs a few ignored bytes.

.. note::

   **Non-normative migration policy.** No OVOS specification mandates the
   suffixed topic or the re-emit. The suffixed form is historical leakage,
   and everything here is transitional tooling scoped to the migration
   period. New code MUST produce and consume canonical topics only.
"""
from __future__ import annotations

from typing import Optional

__all__ = [
    "INTENT_FILE_SUFFIX",
    "NON_SKILL_NAMESPACES",
    "RESERVED_INTENT_NAMES",
    "canonical_intent_topic",
    "intent_topic_counterpart",
    "is_intent_topic",
    "legacy_intent_topic",
]

#: The authoring-file extension that leaked onto the wire in old workshop
#: releases. Appended to the intent-name half of a dispatch topic only.
INTENT_FILE_SUFFIX = ".intent"


#: Topic prefixes that are **namespaces, not skill_ids**. OVOS-MSG-1 §2.1
#: gives several subsystems a ``<namespace>:<event>`` topic of their own —
#: ``recognizer_loop:utterance``, ``question:query``,
#: ``padatious:register_intent``, ``speak:b64_audio``, ``stop:global`` — and
#: the legacy CommonPlay topics (``play:query``, ``play:query.response``,
#: ``play:status.query``) add another. None of them is a per-intent dispatch,
#: and ``play:query.response`` fans out one frame per responding skill, so
#: twinning it doubles a burst. A topic under one of these prefixes is never
#: twinned.
NON_SKILL_NAMESPACES = frozenset({
    "recognizer_loop",
    "question",
    "padatious",
    "play",
    "speak",
    "mycroft",
    "ovos",
    "gui",
    "stop",
    "converse",
})

#: Intent names reserved by the specifications for a per-skill *control*
#: dispatch, not for an author-registered intent. ``<skill_id>:stop`` is
#: OVOS-STOP-1 §2 (and OVOS-INTENT-4 §5.3 forbids a skill registering it);
#: ``converse`` and ``common_query`` are the other reserved names in the
#: ``pipeline_id`` ≡ ``skill_id`` dispatch namespace. None of them ever came
#: from a ``.intent`` resource file, so none has a legacy twin.
#:
#: The set is deliberately minimal. Excluding a name here silently denies the
#: compat twin to any skill that ships a resource file of that name, which
#: brings back the very bug this module exists to fix — so a name earns its
#: place only by being reserved *and* colliding with a real colon topic.
RESERVED_INTENT_NAMES = frozenset({
    "stop",
    "converse",
    "common_query",
})


def is_intent_topic(msg_type: str) -> bool:
    """Whether ``msg_type`` is a per-intent dispatch topic.

    OVOS-MSG-1 §2.1.1 assembles the per-intent dispatch topic as
    ``<skill_id>:<intent_name>``. The colon is the structural separator, but it
    is **not** exclusive to intent dispatch: subsystem topics such as
    ``recognizer_loop:utterance`` and ``question:query`` share the shape, and
    several colon-bearing topics migrate through
    :data:`~ovos_spec_tools.messages.MIGRATION_MAP`. Treating every colon as an
    intent dispatch would twin the hottest topics on the bus and break the
    one-emit-one-frame invariant, so the test is deliberately narrow.

    A topic is an intent dispatch candidate only when **all** hold:

    - it contains ``:`` and both halves are non-empty — ``":foo"`` and
      ``"skill:"`` name no skill or no intent;
    - it is not a migrating topic (neither side of
      :data:`~ovos_spec_tools.messages.MIGRATION_MAP`), whose counterpart is
      the namespace bridge's business, not this one;
    - its leading segment is not one of :data:`NON_SKILL_NAMESPACES`;
    - its intent name (after the LAST colon, matching
      :func:`canonical_intent_topic`) is not one of
      :data:`RESERVED_INTENT_NAMES`.

    Args:
        msg_type: a bus topic string.

    Returns:
        ``True`` if ``msg_type`` is a per-intent dispatch topic.
    """
    if not msg_type or ":" not in msg_type:
        return False
    skill_id, _, intent_name = msg_type.rpartition(":")
    if not skill_id or not intent_name:
        return False
    # Imported lazily: ``messages`` imports this module for the mirror guard,
    # so a module-level import here would close the cycle.
    from ovos_spec_tools.messages import MIGRATION_MAP, SPEC_TO_LEGACY
    if msg_type in MIGRATION_MAP or msg_type in SPEC_TO_LEGACY:
        return False
    if skill_id.split(":", 1)[0] in NON_SKILL_NAMESPACES:
        return False
    if intent_name in RESERVED_INTENT_NAMES:
        return False
    # A suffixed reserved name (``<skill_id>:stop.intent``) is not a dispatch
    # either -- the reserved names never came from a resource file. Stripped
    # inline: ``canonical_intent_topic`` calls back into this function.
    if intent_name.endswith(INTENT_FILE_SUFFIX) \
            and intent_name[: -len(INTENT_FILE_SUFFIX)] in RESERVED_INTENT_NAMES:
        return False
    return True


def intent_topic_counterpart(msg_type: str) -> Optional[str]:
    """The other spelling of an intent dispatch topic, or ``None``.

    The intent-topic analogue of
    :func:`~ovos_spec_tools.messages.migration_counterpart`: canonical maps to
    suffixed and suffixed maps back, so a receive-side mirror guard can pair
    the two frames of a compat dual-emit.

    Args:
        msg_type: a bus topic string.

    Returns:
        The counterpart topic, or ``None`` when ``msg_type`` is not an intent
        dispatch topic or has no distinct counterpart (an intent name of
        exactly ``".intent"``, which :func:`canonical_intent_topic` leaves
        alone).
    """
    if not is_intent_topic(msg_type):
        return None
    canonical = canonical_intent_topic(msg_type)
    other = legacy_intent_topic(msg_type) if canonical == msg_type else canonical
    return other if other != msg_type else None


def canonical_intent_topic(msg_type: str) -> str:
    """Strip the legacy ``.intent`` suffix from an intent dispatch topic.

    Only the **intent-name** half is touched — the part after the LAST colon —
    so a skill_id that itself ends in ``.intent`` is never damaged. The
    function is idempotent and total: a topic that is already canonical, or is
    not an intent dispatch topic at all, is returned unchanged.

    A topic whose intent name is *exactly* ``".intent"`` is left alone too:
    stripping it would leave an empty intent name, which is not a valid topic.

    Args:
        msg_type: a bus topic string.

    Returns:
        The canonical ``<skill_id>:<intent_name>`` topic.
    """
    if not is_intent_topic(msg_type):
        return msg_type
    skill_id, _, intent_name = msg_type.rpartition(":")
    if not intent_name.endswith(INTENT_FILE_SUFFIX):
        return msg_type
    stripped = intent_name[: -len(INTENT_FILE_SUFFIX)]
    if not stripped:
        # "skill:.intent" — stripping would leave no intent name.
        return msg_type
    return f"{skill_id}:{stripped}"


def legacy_intent_topic(msg_type: str) -> str:
    """Append the legacy ``.intent`` suffix to an intent dispatch topic.

    The inverse of :func:`canonical_intent_topic`, and idempotent in the same
    way: an already-suffixed topic, and any non-intent topic, is returned
    unchanged.

    Args:
        msg_type: a bus topic string.

    Returns:
        The suffixed ``<skill_id>:<intent_name>.intent`` topic.
    """
    if not is_intent_topic(msg_type):
        return msg_type
    _, _, intent_name = msg_type.rpartition(":")
    if intent_name.endswith(INTENT_FILE_SUFFIX):
        return msg_type
    return f"{msg_type}{INTENT_FILE_SUFFIX}"
