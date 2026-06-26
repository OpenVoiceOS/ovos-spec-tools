"""Conformance tests for the OVOS-INTENT-2 §4.2 reference dialog renderer."""
import pytest

from ovos_spec_tools import DialogRenderer, LocaleResources, UnfilledSlot, render


class _FixedRng:
    """A deterministic stand-in for `random`: always picks a chosen index."""

    def __init__(self, index=0):
        self.index = index

    def choice(self, seq):
        seq = list(seq)
        return seq[self.index % len(seq)]


def _resources(tmp_path, files):
    """Build a LocaleResources over a locale with the given {relpath: text}."""
    locale = tmp_path / "locale"
    for relpath, text in files.items():
        path = locale / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return LocaleResources(str(locale))


# --- render() — the stateless function ---------------------------------------

def test_render_fills_slots():
    out = render(["It is {temperature} degrees."],
                 slots={"temperature": 21})
    assert out == "It is 21 degrees."


def test_render_fills_double_brace_slots():
    """OVOS-INTENT-1 §3.4 — ``{{name}}`` is an equivalent slot spelling."""
    out = render(["It is {{temperature}} degrees."],
                 slots={"temperature": 21})
    assert out == "It is 21 degrees."


def test_render_mixed_brace_spellings_share_values():
    out = render(["{{a}} and {b}"], slots={"a": "X", "b": "Y"})
    assert out == "X and Y"


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


# --- DialogRenderer — stateful, multilingual ---------------------------------

def test_renderer_fills_slots(tmp_path):
    res = _resources(tmp_path, {"en-US/t.dialog": "It is {temperature} degrees."})
    renderer = DialogRenderer(res, "t")
    assert renderer.render("en-US", {"temperature": 21}) == "It is 21 degrees."


def test_renderer_serves_multiple_languages(tmp_path):
    res = _resources(tmp_path, {
        "en-US/hi.dialog": "Hello.",
        "pt-BR/hi.dialog": "Ola.",
    })
    renderer = DialogRenderer(res, "hi")
    assert renderer.render("en-US") == "Hello."
    assert renderer.render("pt-BR") == "Ola."


def test_renderer_avoids_repeating_the_last_phrase(tmp_path):
    """With two phrases, consecutive renders must alternate (§4.2)."""
    res = _resources(tmp_path, {"en-US/c.dialog": "alpha\nbeta\n"})
    renderer = DialogRenderer(res, "c")
    first = renderer.render("en-US")
    second = renderer.render("en-US")
    third = renderer.render("en-US")
    assert first != second
    assert second != third
    assert {first, second} == {"alpha", "beta"}


def test_repetition_avoidance_is_per_language(tmp_path):
    """The 'last phrase' is tracked separately for each language."""
    res = _resources(tmp_path, {
        "en-US/c.dialog": "alpha\nbeta\n",
        "pt-BR/c.dialog": "um\ndois\n",
    })
    renderer = DialogRenderer(res, "c")
    renderer.render("en-US")
    # the pt-BR render is unconstrained by the en-US history
    assert renderer.render("pt-BR") in {"um", "dois"}


def test_renderer_unfilled_slot_raises(tmp_path):
    res = _resources(tmp_path, {"en-US/s.dialog": "say {name}"})
    renderer = DialogRenderer(res, "s")
    with pytest.raises(UnfilledSlot):
        renderer.render("en-US")


def test_renderer_missing_dialog_for_language_raises(tmp_path):
    res = _resources(tmp_path, {"en-US/hi.dialog": "Hello."})
    renderer = DialogRenderer(res, "hi")
    with pytest.raises(FileNotFoundError):
        renderer.render("de-DE")


# --- default slots and .entity fallback --------------------------------------

def test_renderer_default_slots_are_reused(tmp_path):
    res = _resources(tmp_path, {"en-US/g.dialog": "Hello {name}."})
    renderer = DialogRenderer(res, "g", slots={"name": "Sam"})
    assert renderer.render("en-US") == "Hello Sam."
    assert renderer.render("en-US") == "Hello Sam."


def test_per_call_slot_overrides_a_default(tmp_path):
    res = _resources(tmp_path, {"en-US/g.dialog": "Hello {name}."})
    renderer = DialogRenderer(res, "g", slots={"name": "Sam"})
    assert renderer.render("en-US", {"name": "Max"}) == "Hello Max."


def test_unfilled_slot_falls_back_to_entity(tmp_path):
    res = _resources(tmp_path, {
        "en-US/today.dialog": "today is {day}",
        "en-US/day.entity": "monday\n",
    })
    renderer = DialogRenderer(res, "today")
    assert renderer.render("en-US") == "today is monday"


def test_slot_precedence_call_then_default_then_entity(tmp_path):
    res = _resources(tmp_path, {
        "en-US/v.dialog": "value {x}",
        "en-US/x.entity": "from_entity\n",
    })
    renderer = DialogRenderer(res, "v", slots={"x": "from_default"})
    # default beats the .entity fallback
    assert renderer.render("en-US") == "value from_default"
    # a per-call value beats both
    assert renderer.render("en-US", {"x": "from_call"}) == "value from_call"


# --- edge cases --------------------------------------------------------------

def test_renderer_with_one_phrase_repeats_it(tmp_path):
    res = _resources(tmp_path, {"en-US/one.dialog": "the only phrase"})
    renderer = DialogRenderer(res, "one")
    assert renderer.render("en-US") == "the only phrase"
    assert renderer.render("en-US") == "the only phrase"


def test_render_phrase_with_no_slots():
    assert render(["a fixed phrase"]) == "a fixed phrase"


def test_render_slot_value_with_braces_stays_literal():
    """The filled value is inserted verbatim — never re-parsed as a slot."""
    out = render(["you said {echo}"], slots={"echo": "{not a slot}"})
    assert out == "you said {not a slot}"


def test_render_numeric_slot_value_is_stringified():
    assert render(["count {n}"], slots={"n": 0}) == "count 0"


def test_renderer_missing_dialog_raises(tmp_path):
    res = _resources(tmp_path, {"en-US/x.dialog": "hello"})
    renderer = DialogRenderer(res, "absent")
    with pytest.raises(FileNotFoundError):
        renderer.render("en-US")
