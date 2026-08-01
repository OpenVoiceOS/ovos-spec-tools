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

__all__ = [
    "INTENT_FILE_SUFFIX",
    "canonical_intent_topic",
    "is_intent_topic",
    "legacy_intent_topic",
]

#: The authoring-file extension that leaked onto the wire in old workshop
#: releases. Appended to the intent-name half of a dispatch topic only.
INTENT_FILE_SUFFIX = ".intent"


def is_intent_topic(msg_type: str) -> bool:
    """Whether ``msg_type`` is a per-intent dispatch topic.

    OVOS-MSG-1 §2.1.1 reserves ``:`` as the structural separator of the
    ``<skill_id>:<intent_name>`` topic, and no other OVOS topic uses it. A
    colon anywhere in the topic therefore identifies an intent dispatch.

    Both halves must be non-empty: ``":foo"`` and ``"skill:"`` name no skill
    or no intent and are not dispatch topics.

    Args:
        msg_type: a bus topic string.

    Returns:
        ``True`` if ``msg_type`` is an intent dispatch topic.
    """
    if not msg_type or ":" not in msg_type:
        return False
    skill_id, _, intent_name = msg_type.rpartition(":")
    return bool(skill_id) and bool(intent_name)


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
