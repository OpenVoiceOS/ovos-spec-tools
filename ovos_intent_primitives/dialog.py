"""Reference dialog renderer for OVOS-INTENT-2 §4.2.

This is the reference implementation of the **Dialog renderer** conformance
role of OVOS-INTENT-1 §7. To render a dialog, :func:`render` selects one phrase
from a loaded ``.dialog``, expands its ``(a|b)`` / ``[x]`` variety to a single
variant, and fills every ``{name}`` slot with a caller-supplied value.

Only the single-brace slot form ``{name}`` is recognized; there is no ``{{ }}``
form (OVOS-INTENT-2 §4.2). Slots are filled by the caller; a chosen phrase with
a slot the caller did not fill raises :class:`UnfilledSlot` and is not rendered.
"""
from __future__ import annotations

import random as _random
import re
from typing import Dict, Optional, Sequence

from ovos_intent_primitives.expansion import expand

__all__ = ["render", "UnfilledSlot"]

_SLOT_TOKEN_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")


class UnfilledSlot(ValueError):
    """A chosen dialog phrase has a named slot the caller did not fill.

    Per OVOS-INTENT-1 §5.1 the caller must supply a value for every slot in the
    chosen phrase; a phrase with an unfilled slot must not be sent to TTS.
    """


def render(phrases: Sequence[str],
           slots: Optional[Dict[str, object]] = None,
           vocabularies: Optional[Dict[str, Sequence[str]]] = None,
           rng: Optional[object] = None) -> str:
    """Render one phrase from a loaded ``.dialog``.

    Args:
        phrases: the phrase strings of a ``.dialog``, as returned by
            :meth:`~ovos_intent_primitives.resources.LocaleResources.load_dialog`.
        slots: caller-supplied values for the phrase's named slots, keyed by
            slot name. Values are converted to text.
        vocabularies: vocabularies for any ``<name>`` references in the phrase.
        rng: an object with a ``choice`` method, for phrase and variant
            selection; defaults to the :mod:`random` module. Inject a seeded
            generator for deterministic output.

    Returns:
        One rendered phrase, ready for text-to-speech.

    Raises:
        UnfilledSlot: a slot in the chosen phrase has no caller-supplied value.
        ValueError: ``phrases`` is empty.
        MalformedTemplate: the chosen phrase is not a valid template.
    """
    if not phrases:
        raise ValueError("no dialog phrases to render")
    chooser = rng if rng is not None else _random
    slots = slots or {}

    # Expansion keeps slots opaque (OVOS-INTENT-1 §4): expand first, pick a
    # variant, then fill — so a slot value can never be parsed as grammar.
    phrase = chooser.choice(list(phrases))
    variant = chooser.choice(expand(phrase, vocabularies))
    return _fill_slots(variant, slots)


def _fill_slots(variant: str, slots: Dict[str, object]) -> str:
    """Replace every ``{name}`` in ``variant`` with its caller-supplied value."""

    def replace(match: "re.Match") -> str:
        name = match.group(1)
        if name not in slots:
            raise UnfilledSlot(
                f"dialog slot {{{name}}} was not filled by the caller")
        return str(slots[name])

    return _SLOT_TOKEN_RE.sub(replace, variant)
