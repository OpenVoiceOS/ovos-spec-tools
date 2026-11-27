"""A repeated slot name: malformed in an input template, well formed in a dialog.

OVOS-INTENT-1 §3.6, "Repeated slot name": in an input-direction template the
rule holds and the comparison is on the slot name, so ``{x} and {date:x}``
repeats a name. The rule does not reach an output-direction template, where
the caller gives one value per name and every occurrence takes it.
"""
import pytest

from ovos_spec_tools import (DialogRenderer, LocaleResources, MalformedTemplate,
                             declared_slots, derive_required_slots, expand,
                             render)
from ovos_spec_tools.lint import ERROR, lint_locale

LIMIT = "You may roll at most {number} dice. {number} is the limit."


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize("template", [
    "{x} and {x}",
    "{x} and {date:x}",
    "{{x}} and {x}",
    "{number:x} and {date:x}",
])
def test_input_direction_rejects_a_repeated_name(template):
    with pytest.raises(MalformedTemplate, match="repeated slot name"):
        expand(template)
    with pytest.raises(MalformedTemplate, match="repeated slot name"):
        expand(template, direction="input")


@pytest.mark.parametrize("template, expected", [
    ("{x} and {x}", ["{x} and {x}"]),
    ("{x} and {date:x}", ["{x} and {x}"]),
    (LIMIT, [LIMIT]),
    ("[{x} and] {x}", ["{x} and {x}", "{x}"]),
])
def test_output_direction_accepts_a_repeated_name(template, expected):
    assert expand(template, direction="output") == expected


def test_output_direction_still_applies_the_slot_name_rule():
    # OVOS-INTENT-1 §3.4: the slot-name rule holds in both directions
    with pytest.raises(MalformedTemplate):
        expand("{Number} and {Number}", direction="output")


def test_declared_slots_lists_a_repeated_name_once():
    assert declared_slots([LIMIT]) == frozenset({"number"})
    assert declared_slots(["{x} and {date:x}"]) == frozenset({"x"})


def test_required_slots_are_derived_from_an_intent_so_a_repeat_is_rejected():
    # derive_required_slots reads an .intent, an input-direction role
    with pytest.raises(MalformedTemplate, match="repeated slot name"):
        derive_required_slots(["roll {n} dice", "roll {n} dice and {n}"])
    assert derive_required_slots(["roll {n} dice", "roll {n} times"]) \
        == frozenset({"n"})


def test_render_fills_every_occurrence_with_the_same_value():
    assert render([LIMIT], slots={"number": 6}) == \
        "You may roll at most 6 dice. 6 is the limit."


def test_a_dialog_renderer_fills_a_repeated_name_everywhere(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "limit.dialog", LIMIT + "\n")
    renderer = DialogRenderer(LocaleResources(str(locale)), "limit")
    assert renderer.render("en-US", {"number": 6}) == \
        "You may roll at most 6 dice. 6 is the limit."


def test_lint_accepts_a_repeated_name_in_a_dialog(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "limit.dialog", LIMIT + "\n")
    assert lint_locale(locale) == []


@pytest.mark.parametrize("template", ["{x} and {x}", "{x} and {date:x}"])
def test_lint_rejects_a_repeated_name_in_an_intent(tmp_path, template):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "pair.intent", template + "\n")
    errors = [f for f in lint_locale(locale) if f.severity == ERROR]
    assert len(errors) == 1
    assert "repeated slot name" in errors[0].message
