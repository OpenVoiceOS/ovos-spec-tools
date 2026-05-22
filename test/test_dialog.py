"""Conformance tests for the OVOS-INTENT-2 §4.2 reference dialog renderer."""
import pytest

from ovos_intent_primitives import UnfilledSlot, render


class _FixedRng:
    """A deterministic stand-in for `random`: always picks a chosen index."""

    def __init__(self, index=0):
        self.index = index

    def choice(self, seq):
        seq = list(seq)
        return seq[self.index % len(seq)]


def test_render_fills_slots():
    out = render(["It is {temperature} degrees."],
                 slots={"temperature": 21})
    assert out == "It is 21 degrees."


def test_render_selects_a_phrase():
    phrases = ["first phrase", "second phrase"]
    assert render(phrases, rng=_FixedRng(0)) == "first phrase"
    assert render(phrases, rng=_FixedRng(1)) == "second phrase"


def test_render_expands_variety_then_fills():
    out = render(["(Currently|At the moment) it is {t} degrees"],
                 slots={"t": 5}, rng=_FixedRng(0))
    assert out == "Currently it is 5 degrees"


def test_unfilled_slot_raises():
    with pytest.raises(UnfilledSlot):
        render(["It is {temperature} degrees."], slots={})


def test_slot_value_is_never_parsed_as_grammar():
    """Expansion happens before fill, so a value with metacharacters is safe."""
    out = render(["you said {echo}"], slots={"echo": "(a|b)"})
    assert out == "you said (a|b)"


def test_render_resolves_vocabulary_references():
    out = render(["<greet> {name}"], slots={"name": "Sam"},
                 vocabularies={"greet": ["hello"]}, rng=_FixedRng(0))
    assert out == "hello Sam"


def test_empty_phrase_list_raises():
    with pytest.raises(ValueError):
        render([])
