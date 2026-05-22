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
from typing import Dict, Optional, Protocol, Sequence

from ovos_spec_tools.expansion import expand

__all__ = ["render", "DialogRenderer", "Chooser", "UnfilledSlot"]

_SLOT_TOKEN_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")


class Chooser(Protocol):
    """A source of random selection: anything with a ``choice`` method.

    The :mod:`random` module and a :class:`random.Random` instance both
    satisfy it. Inject a seeded ``random.Random`` for deterministic output.
    """

    def choice(self, seq: Sequence[str]) -> str:
        ...


class UnfilledSlot(ValueError):
    """A chosen dialog phrase has a named slot the caller did not fill.

    Per OVOS-INTENT-1 §5.1 the caller must supply a value for every slot in the
    chosen phrase; a phrase with an unfilled slot must not be sent to TTS.
    """


def render(phrases: Sequence[str],
           slots: Optional[Dict[str, object]] = None,
           vocabularies: Optional[Dict[str, Sequence[str]]] = None,
           rng: Optional[Chooser] = None) -> str:
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
                 rng: Optional[Chooser] = None,
                 slots: Optional[Dict[str, object]] = None,
                 entities: Optional[Dict[str, Sequence[str]]] = None):
        """
        Args:
            phrases: the phrase strings of a ``.dialog``.
            vocabularies: vocabularies for any ``<name>`` references.
            rng: an object with a ``choice`` method; defaults to :mod:`random`.
            slots: **default** slot values, held for the renderer's lifetime
                and reused on every :meth:`render` call. Use this for slots
                that do not change per render (a unit preference, a name). A
                per-call value passed to :meth:`render` overrides a default.
            entities: ``.entity`` value sets, keyed by slot name. A slot that
                is neither passed per call nor a default is filled with a
                random value from its entity set, if one is given here.
        """
        self.phrases = list(phrases)
        if not self.phrases:
            raise ValueError("a DialogRenderer needs at least one phrase")
        self.vocabularies = vocabularies
        self.rng = rng if rng is not None else _random
        self.default_slots: Dict[str, object] = dict(slots or {})
        self.entities: Dict[str, Sequence[str]] = dict(entities or {})
        self._last: Optional[str] = None

    @classmethod
    def from_resources(cls, resources, name: str,
                       rng: Optional[Chooser] = None,
                       slots: Optional[Dict[str, object]] = None
                       ) -> "DialogRenderer":
        """Build a renderer for the ``.dialog`` named ``name``.

        ``resources`` is a
        :class:`~ovos_spec_tools.resources.LocaleResources`; its loaded dialog,
        its vocabularies, and its ``.entity`` value sets are all used — so a
        slot left unfilled falls back to its ``.entity``. ``slots`` supplies
        default slot values.
        """
        return cls(resources.load_dialog(name),
                   vocabularies=resources.vocabularies(),
                   entities=resources.entities(),
                   rng=rng, slots=slots)

    def render(self, slots: Optional[Dict[str, object]] = None) -> str:
        """Render one phrase, avoiding the phrase chosen on the previous call.

        A slot is filled, in order of precedence, from: the per-call ``slots``;
        then the renderer's default slots; then a random value from the slot's
        ``.entity`` set. A slot none of these supply raises :class:`UnfilledSlot`.

        Args:
            slots: per-call slot values; each overrides a default of the
                same name.

        Returns:
            One rendered phrase, ready for text-to-speech.

        Raises:
            UnfilledSlot: a slot in the chosen phrase has no value from any
                source.
            MalformedTemplate: the chosen phrase is not a valid template.
        """
        effective = dict(self.default_slots)
        if slots:
            effective.update(slots)
        choices = [p for p in self.phrases if p != self._last] or self.phrases
        phrase = self.rng.choice(choices)
        self._last = phrase
        return _render_phrase(phrase, effective, self.vocabularies, self.rng,
                              self.entities)


def _render_phrase(phrase: str,
                   slots: Dict[str, object],
                   vocabularies: Optional[Dict[str, Sequence[str]]],
                   chooser: Chooser,
                   entities: Optional[Dict[str, Sequence[str]]] = None) -> str:
    """Expand one phrase to a variant, then fill its slots.

    Expansion keeps slots opaque (OVOS-INTENT-1 §4), so it runs first and a
    slot value can never be parsed as grammar.
    """
    variant = chooser.choice(expand(phrase, vocabularies))
    return _fill_slots(variant, slots, entities, chooser)


def _fill_slots(variant: str,
                slots: Dict[str, object],
                entities: Optional[Dict[str, Sequence[str]]],
                chooser: Chooser) -> str:
    """Replace every ``{name}`` in ``variant`` with a value.

    A value is taken from ``slots``; failing that, a random valid value from
    the slot's ``.entity`` set in ``entities``; failing that, the slot has no
    value and :class:`UnfilledSlot` is raised.
    """

    def replace(match: "re.Match") -> str:
        name = match.group(1)
        if name in slots:
            return str(slots[name])
        if entities and entities.get(name):
            return str(chooser.choice(list(entities[name])))
        raise UnfilledSlot(
            f"dialog slot {{{name}}} has no value: it was not filled by the "
            f"caller and has no .entity fallback")

    return _SLOT_TOKEN_RE.sub(replace, variant)
