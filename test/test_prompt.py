"""Conformance tests for the OVOS-INTENT-2 §4.4 reference prompt renderer.

A ``.prompt`` substitutes the **double-brace** ``{{name}}`` form only. A single
``{name}`` and any lone brace are literal pass-through text — a prompt is
free-form LLM text that routinely contains literal single braces (JSON, code).
"""
import pytest

from ovos_spec_tools import (
    LocaleResources,
    MalformedResource,
    PromptRenderer,
    render_prompt,
)


def _resources(tmp_path, files):
    """Build a LocaleResources over a locale with the given {relpath: text}."""
    locale = tmp_path / "locale"
    for relpath, text in files.items():
        path = locale / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return LocaleResources(str(locale))


# --- render_prompt() — double-brace substitution -----------------------------

def test_render_prompt_fills_a_double_brace_slot():
    assert render_prompt("Hello {{name}}.", {"name": "Sam"}) == "Hello Sam."


def test_single_brace_is_literal_and_never_substituted():
    """A single ``{name}`` is literal text in a .prompt — never substituted."""
    assert render_prompt("Hello {name}.", {"name": "Sam"}) == "Hello {name}."
    assert render_prompt("Hello {name}.", {}) == "Hello {name}."


def test_unfilled_double_brace_slot_is_left_literal():
    """A ``{{name}}`` slot is optional — unfilled means literal text, not error."""
    assert render_prompt("Hello {{name}}.", {}) == "Hello {{name}}."
    assert render_prompt("Hello {{name}}.") == "Hello {{name}}."


def test_partial_fill_leaves_the_rest_literal():
    out = render_prompt("{{greeting}} {{name}}", {"greeting": "Hi"})
    assert out == "Hi {{name}}"


def test_literal_json_stays_literal_while_double_brace_substitutes():
    """The motivating case: literal JSON single braces survive, {{name}} fills."""
    text = 'Reply as {"key": "val"} for {{name}}.'
    out = render_prompt(text, {"name": "Sam", "key": "K"})
    assert out == 'Reply as {"key": "val"} for Sam.'


@pytest.mark.parametrize("text", [
    'json {"key": 1}',            # JSON object braces (single)
    "empty {} and { } braces",    # not a name
    "code {x+1} here",            # not a valid name
    "single {name} stays",        # single-brace is literal in a prompt
    "upper {{Name}} stays",       # uppercase — outside the charset
    "digit {{1st}} stays",        # begins with a digit
    "empty double {{}} stays",    # no name
    "spaced double {{ }} stays",  # whitespace is not a name
])
def test_literal_braces_are_untouched(text):
    assert render_prompt(text, {"key": "K", "name": "N", "x": "X"}) == text


def test_no_substitution_inside_a_fenced_code_block():
    text = (
        "Fill {{greeting}} here.\n"
        "```\n"
        "{{greeting}} stays literal in the code block\n"
        "```\n"
        "And {{greeting}} again here.\n"
    )
    out = render_prompt(text, {"greeting": "HI"})
    assert out == (
        "Fill HI here.\n"
        "```\n"
        "{{greeting}} stays literal in the code block\n"
        "```\n"
        "And HI again here.\n"
    )


def test_fence_with_an_info_string_is_recognized():
    text = "```json\n{{x}}\n```\n{{x}}"
    assert render_prompt(text, {"x": "V"}) == "```json\n{{x}}\n```\nV"


def test_whole_file_is_verbatim_apart_from_substitution():
    """`#` lines and blank lines are kept — a prompt is not line-filtered."""
    text = "# A heading\n\nBody with {{slot}}.\n\n    indented line\n"
    out = render_prompt(text, {"slot": "X"})
    assert out == "# A heading\n\nBody with X.\n\n    indented line\n"


def test_html_comment_is_literal_pass_through():
    """A .prompt has no comment syntax — ``<!-- -->`` is literal text."""
    text = "<!-- author note --> Body for {{name}}."
    assert render_prompt(text, {"name": "Sam"}) == "<!-- author note --> Body for Sam."


def test_numeric_slot_value_is_stringified():
    assert render_prompt("count {{n}}", {"n": 0}) == "count 0"


def test_filled_value_is_not_re_scanned_for_slots():
    """A value containing `{{...}}` is inserted literally, not substituted again."""
    assert render_prompt("say {{x}}", {"x": "{{y}}"}) == "say {{y}}"


def test_text_with_no_trailing_newline_is_preserved():
    assert render_prompt("no newline {{x}}", {"x": "here"}) == "no newline here"


# --- PromptRenderer — stateful, multilingual ---------------------------------

def test_renderer_renders_from_resources(tmp_path):
    res = _resources(tmp_path, {"en-US/sys.prompt": "You are {{role}}."})
    renderer = PromptRenderer(res, "sys")
    assert renderer.render("en-US", {"role": "a helper"}) == "You are a helper."


def test_renderer_serves_multiple_languages(tmp_path):
    res = _resources(tmp_path, {
        "en-US/sys.prompt": "Answer in English.",
        "pt-PT/sys.prompt": "Responde em português.",
    })
    renderer = PromptRenderer(res, "sys")
    assert renderer.render("en-US") == "Answer in English."
    assert renderer.render("pt-PT") == "Responde em português."


def test_renderer_default_slots_are_reused(tmp_path):
    res = _resources(tmp_path, {"en-US/g.prompt": "You are {{assistant}}."})
    renderer = PromptRenderer(res, "g", slots={"assistant": "OVOS"})
    assert renderer.render("en-US") == "You are OVOS."
    assert renderer.render("en-US") == "You are OVOS."


def test_per_call_slot_overrides_a_default(tmp_path):
    res = _resources(tmp_path, {"en-US/g.prompt": "You are {{assistant}}."})
    renderer = PromptRenderer(res, "g", slots={"assistant": "OVOS"})
    assert renderer.render("en-US", {"assistant": "Mycroft"}) == "You are Mycroft."


def test_renderer_missing_prompt_raises(tmp_path):
    res = _resources(tmp_path, {"en-US/x.prompt": "hi"})
    renderer = PromptRenderer(res, "absent")
    with pytest.raises(FileNotFoundError):
        renderer.render("en-US")


# --- load_prompt() -----------------------------------------------------------

def test_load_prompt_returns_the_whole_file(tmp_path):
    text = "# Heading\n\nBody {{slot}} text.\n"
    res = _resources(tmp_path, {"en-US/p.prompt": text})
    assert res.load_prompt("p", "en-US") == text


def test_load_prompt_passes_single_brace_and_comments_verbatim(tmp_path):
    """read_prompt_file/load_prompt does no stripping — all text is literal."""
    text = '<!-- note --> {"json": 1} single {slot} double {{slot}}\n'
    res = _resources(tmp_path, {"en-US/p.prompt": text})
    assert res.load_prompt("p", "en-US") == text


def test_empty_prompt_is_malformed(tmp_path):
    res = _resources(tmp_path, {"en-US/p.prompt": "   \n\n"})
    with pytest.raises(MalformedResource):
        res.load_prompt("p", "en-US")


def test_load_prompt_missing_raises(tmp_path):
    res = _resources(tmp_path, {"en-US/other.prompt": "hi"})
    with pytest.raises(FileNotFoundError):
        res.load_prompt("p", "en-US")
