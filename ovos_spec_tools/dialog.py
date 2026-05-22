"""Reference dialog renderer for OVOS-INTENT-2 §4.2.

This is the reference implementation of the **Dialog renderer** conformance
role of OVOS-INTENT-1 §7. Rendering a dialog means: select one phrase from a
loaded ``.dialog``, expand its ``(a|b)`` / ``[x]`` variety to a single variant,
and fill every ``{name}`` slot with a caller-supplied value.

Two interfaces are provided:

- :func:`render` — a stateless one-shot function;
- :class:`DialogRenderer` — a stateful object that additionally avoids
  repeating the phrase it chose last time.

Only the single-brace slot form ``{name}`` is recognized; there is no ``{{ }}``
form (OVOS-INTENT-2 §4.2). Slots are filled by the caller; a chosen phrase with
a slot the caller did not fill raises :class:`UnfilledSlot`.
"""
from __future__ import annotations

import random as _random
import re
from typing import Dict, Optional, Sequence

from ovos_spec_tools.expansion import expand

__all__ = ["render", "DialogRenderer", "UnfilledSlot"]

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
    """Render one phrase from a loaded ``.dialog`` (stateless).

    Args:
        phrases: the phrase strings of a ``.dialog``.
        slots: caller-supplied values for the phrase's named slots, keyed by
            slot name. Values are converted to text.
        vocabularies: vocabularies for any ``<name>`` references in the phrase.
        rng: an object with a ``choice`` method, for phrase and variant
            selection; defaults to the :mod:`random` module.

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
    phrase = chooser.choice(list(phrases))
    return _render_phrase(phrase, slots or {}, vocabularies, chooser)


class DialogRenderer:
    """A stateful renderer for one loaded ``.dialog`` (OVOS-INTENT-2 §4.2).

    An object-oriented alternative to :func:`render`. It holds the dialog's
    phrases, the vocabularies, and the random source, and — unlike the bare
    function — **avoids repeating the phrase it chose on the previous call**,
    so a repeatedly-spoken response does not sound mechanical. Repetition
    avoidance is an implementation choice the spec explicitly allows (§4.2).
    """

    def __init__(self, phrases: Sequence[str],
                 vocabularies: Optional[Dict[str, Sequence[str]]] = None,
                 rng: Optional[object] = None):
        """
        Args:
            phrases: the phrase strings of a ``.dialog``.
            vocabularies: vocabularies for any ``<name>`` references.
            rng: an object with a ``choice`` method; defaults to :mod:`random`.
        """
        self.phrases = list(phrases)
        if not self.phrases:
            raise ValueError("a DialogRenderer needs at least one phrase")
        self.vocabularies = vocabularies
        self.rng = rng if rng is not None else _random
        self._last: Optional[str] = None

    @classmethod
    def from_resources(cls, resources, name: str,
                       rng: Optional[object] = None) -> "DialogRenderer":
        """Build a renderer for the ``.dialog`` named ``name``.

        ``resources`` is a
        :class:`~ovos_spec_tools.resources.LocaleResources`; its loaded dialog
        and its vocabularies are used.
        """
        return cls(resources.load_dialog(name),
                   vocabularies=resources.vocabularies(), rng=rng)

    def render(self, slots: Optional[Dict[str, object]] = None) -> str:
        """Render one phrase, avoiding the phrase chosen on the previous call.

        Args:
            slots: caller-supplied values for the phrase's named slots.

        Returns:
            One rendered phrase, ready for text-to-speech.

        Raises:
            UnfilledSlot: a slot in the chosen phrase has no value.
            MalformedTemplate: the chosen phrase is not a valid template.
        """
        choices = [p for p in self.phrases if p != self._last] or self.phrases
        phrase = self.rng.choice(choices)
        self._last = phrase
        return _render_phrase(phrase, slots or {}, self.vocabularies, self.rng)


def _render_phrase(phrase: str,
                   slots: Dict[str, object],
                   vocabularies: Optional[Dict[str, Sequence[str]]],
                   chooser: object) -> str:
    """Expand one phrase to a variant, then fill its slots.

    Expansion keeps slots opaque (OVOS-INTENT-1 §4), so it runs first and a
    slot value can never be parsed as grammar.
    """
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
