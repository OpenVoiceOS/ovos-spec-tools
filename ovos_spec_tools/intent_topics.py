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
surface for that gap. It has two halves, mirroring
:class:`~ovos_spec_tools.messages.NamespaceTranslator`:

- **inbound / registration** — :func:`canonical_intent_topic` normalizes a
  suffixed name to its canonical form, and :class:`IntentAliasRegistry`
  records the alias pair so a consumer that binds both forms can collapse
  them and fire once (the alias-collapse-at-registration pattern of
  OVOS-INTENT-4 §5 / §8);
- **outbound** — :func:`legacy_reemit_targets` tells a bus which extra topic
  to mirror an intent dispatch onto, gated by the same ``emit_legacy``
  convention the namespace bridge uses.

.. note::

   **Non-normative migration policy.** No OVOS specification mandates the
   suffixed topic or the re-emit. The suffixed form is historical leakage,
   and everything here is transitional tooling scoped to the migration
   period. New code MUST produce and consume canonical topics only.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

__all__ = [
    "INTENT_FILE_SUFFIX",
    "IntentAliasRegistry",
    "canonical_intent_topic",
    "is_intent_topic",
    "legacy_intent_topic",
    "legacy_reemit_targets",
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


class IntentAliasRegistry:
    """Record of which registered intents also answer to a legacy alias.

    A consumer registers an intent under whatever name it was authored with.
    The registry normalizes that name to its canonical form and remembers
    whether the caller used the legacy suffixed spelling. Two questions are
    then answerable:

    - *which canonical intent does this topic mean?* — :meth:`canonical`,
      used at registration and on receive to collapse both spellings onto one
      key, so a consumer bound to both forms runs the handler once;
    - *does an old consumer expect the suffixed twin of this dispatch?* —
      :meth:`has_legacy_alias`, which gates the outbound re-emit so the bus
      invents no topic nobody listens on.

    The registry holds names only. It carries no handlers, no bus, and no
    state beyond the alias table, so a core, a bus client, or a test double
    can all share one.
    """

    def __init__(self) -> None:
        #: canonical topic -> legacy alias (only for intents registered with one)
        self._aliases: Dict[str, str] = {}
        #: canonical topics seen at registration, alias or not
        self._registered: set = set()

    def register(self, msg_type: str) -> str:
        """Record a registration and return the canonical topic for it.

        Calling this twice with the two spellings of one intent is the
        collapse: both calls return the same canonical topic, and the legacy
        alias is remembered from the suffixed call.

        Args:
            msg_type: the topic the consumer registered, in either spelling.

        Returns:
            The canonical topic the intent is keyed under. Non-intent topics
            are returned unchanged and are not recorded.
        """
        if not is_intent_topic(msg_type):
            return msg_type
        canonical = canonical_intent_topic(msg_type)
        self._registered.add(canonical)
        if msg_type != canonical:
            self._aliases[canonical] = msg_type
        return canonical

    def deregister(self, msg_type: str) -> None:
        """Forget an intent, in either spelling. Unknown topics are ignored."""
        canonical = canonical_intent_topic(msg_type)
        self._registered.discard(canonical)
        self._aliases.pop(canonical, None)

    def canonical(self, msg_type: str) -> str:
        """The canonical topic ``msg_type`` refers to (registered or not)."""
        return canonical_intent_topic(msg_type)

    def is_registered(self, msg_type: str) -> bool:
        """Whether either spelling of ``msg_type`` was registered."""
        return canonical_intent_topic(msg_type) in self._registered

    def has_legacy_alias(self, msg_type: str) -> bool:
        """Whether a consumer registered ``msg_type`` with the legacy suffix."""
        return canonical_intent_topic(msg_type) in self._aliases

    def legacy_alias(self, msg_type: str) -> Optional[str]:
        """The recorded legacy alias of ``msg_type``, or ``None``."""
        return self._aliases.get(canonical_intent_topic(msg_type))

    def aliases(self) -> Iterable[Tuple[str, str]]:
        """Iterate the recorded ``(canonical, legacy)`` pairs."""
        return tuple(self._aliases.items())

    def clear(self) -> None:
        """Drop every recorded intent and alias."""
        self._aliases.clear()
        self._registered.clear()


def legacy_reemit_targets(msg_type: str,
                          registry: Optional[IntentAliasRegistry] = None,
                          blanket: bool = False) -> List[str]:
    """Extra topic(s) an intent dispatch should ALSO be emitted on (0 or 1).

    This is the send-side hook, the intent-topic counterpart of
    :meth:`~ovos_spec_tools.messages.NamespaceTranslator.counterpart_topics`.
    A bus calls it while emitting and mirrors the dispatch onto whatever it
    returns, so an old containerized skill that subscribed to the suffixed
    topic still receives the intent.

    Two modes:

    - **alias-driven** (default, ``blanket=False``) — re-emit only when
      ``registry`` recorded a legacy alias for the intent. The registry knows
      an old consumer really did subscribe to the suffixed name, so nothing is
      invented.
    - **blanket** (``blanket=True``) — re-emit the suffixed twin of *every*
      intent dispatch, registry or not. This exists for pure-bus legacy
      listeners that subscribe without ever registering, and it **invents
      topics nobody may listen on**: every dispatch doubles in traffic and any
      handler bound to both spellings needs receive-side dedup. Keep it off
      unless such a listener is known to be present.

    Already-suffixed topics and non-intent topics never produce a target, so
    the mirror cannot cascade.

    Args:
        msg_type: the topic being emitted.
        registry: alias table from registration; required for alias-driven mode.
        blanket: enable the blanket rule described above.

    Returns:
        ``[legacy_topic]``, or ``[]`` when no re-emit applies. At most one
        entry — a topic has exactly one legacy twin.
    """
    if not is_intent_topic(msg_type):
        return []
    if canonical_intent_topic(msg_type) != msg_type:
        # Already the legacy spelling — do not mirror a mirror.
        return []
    if blanket:
        return [legacy_intent_topic(msg_type)]
    if registry is not None and registry.has_legacy_alias(msg_type):
        return [registry.legacy_alias(msg_type) or legacy_intent_topic(msg_type)]
    return []
