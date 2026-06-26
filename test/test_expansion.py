"""Conformance tests for the OVOS-INTENT-1 reference expander.

Each test cites the section of OVOS-INTENT-1 version 2 it exercises. Together
these form the conformance corpus for the Expander role (§7).
"""
import pytest

from ovos_spec_tools import MalformedTemplate, expand, inline_keywords


# --- §4.2 the worked example -------------------------------------------------

def test_worked_example():
    """§4.2 — the canonical 8-sentence expansion."""
    samples = expand("(turn|switch) [the] (light|fan)")
    assert sorted(samples) == [
        "switch fan", "switch light", "switch the fan", "switch the light",
        "turn fan", "turn light", "turn the fan", "turn the light",
    ]


# --- §3.2-§3.3 expansion -----------------------------------------------------

def test_literal_template_is_its_own_sample():
    assert expand("turn on the lights") == ["turn on the lights"]


def test_alternatives():
    assert sorted(expand("(turn on|switch on|enable) it")) == [
        "enable it", "switch on it", "turn on it",
    ]


def test_empty_branch_collapses_whitespace():
    """§3.2 — an empty branch leaves no double space (§4.1 step 4)."""
    assert sorted(expand("(please|) turn it on")) == [
        "please turn it on", "turn it on",
    ]


def test_optional_equals_empty_alternative():
    assert sorted(expand("turn on [the] lights")) == [
        "turn on lights", "turn on the lights",
    ]


def test_nested_groups():
    """§3.5 — groups nest without limit."""
    assert sorted(expand("turn on [(all|every) ]light[s]")) == [
        "turn on all light", "turn on all lights",
        "turn on every light", "turn on every lights",
        "turn on light", "turn on lights",
    ]


def test_duplicate_samples_are_removed():
    """§4.1 step 4 — the sample set is a set."""
    assert expand("(hi|hi) there") == ["hi there"]


# --- §3.4 / §5 named slots are opaque ---------------------------------------

def test_slots_are_carried_through_unchanged():
    assert sorted(expand("(buy|sell) {item}")) == ["buy {item}", "sell {item}"]


def test_slot_repeated_across_branches_is_valid():
    """A slot once per branch is once per sample — not a repeated slot."""
    assert sorted(expand("(buy {item}|sell {item})")) == [
        "buy {item}", "sell {item}",
    ]


def test_digit_in_slot_name():
    """§3.4 — slot names may contain digits."""
    assert expand("set channel {channel_2}") == ["set channel {channel_2}"]


# --- §3.4 dual-brace slot spelling: {name} == {{name}} ----------------------

def test_double_brace_slot_is_equivalent_to_single_brace():
    """§3.4 — ``{{name}}`` is an equivalent spelling of ``{name}``."""
    assert expand("(buy|sell) {{item}}") == expand("(buy|sell) {item}")
    assert sorted(expand("(buy|sell) {{item}}")) == ["buy {item}", "sell {item}"]


def test_double_brace_folds_to_single_brace_in_samples():
    """A ``{{name}}`` slot is emitted as the canonical single-brace ``{name}``."""
    assert expand("it is currently {{temperature}} degrees") == [
        "it is currently {temperature} degrees",
    ]


def test_double_brace_inside_groups():
    assert sorted(expand("(buy {{item}}|sell {{item}})")) == [
        "buy {item}", "sell {item}",
    ]
    assert sorted(expand("[really ]want {{item}}")) == [
        "really want {item}", "want {item}",
    ]


def test_mixed_single_and_double_brace_slots():
    """Both spellings may appear in one template and mean distinct slots."""
    assert expand("move {{from}} to {to}") == ["move {from} to {to}"]


def test_double_brace_slot_only_template_is_malformed():
    """§3.6 — a bare slot is malformed in either spelling."""
    with pytest.raises(MalformedTemplate):
        expand("{{name}}")


def test_double_brace_invalid_name_is_malformed():
    """§3.4 — the folded interior is name-checked exactly like a single slot."""
    for tpl in ("{{Name}} here", "{{1st}} here", "{{bad name}} here"):
        with pytest.raises(MalformedTemplate):
            expand(tpl)


def test_double_brace_repeated_slot_is_malformed():
    """§3.6 — repeating a slot is malformed across spellings too."""
    with pytest.raises(MalformedTemplate):
        expand("{{x}} and {x}")


def test_double_brace_adjacent_slots_is_malformed():
    """§3.6 — adjacent slots remain malformed after folding."""
    with pytest.raises(MalformedTemplate):
        expand("{{a}} {b}")


# --- §3.7 inline vocabulary references --------------------------------------

VOCAB = {"greeting": ["hello", "hi", "good morning"]}


def test_vocabulary_reference():
    """§3.7 — the worked example of an inline vocabulary reference."""
    samples = expand("<greeting> [there] {name}", VOCAB)
    assert sorted(samples) == [
        "good morning there {name}", "good morning {name}",
        "hello there {name}", "hello {name}",
        "hi there {name}", "hi {name}",
    ]


def test_single_member_vocabulary_substitutes_bare():
    assert expand("say <word>", {"word": ["yes"]}) == ["say yes"]


def test_vocabulary_member_is_itself_expanded():
    """A vocabulary member is a template — it is expanded too."""
    samples = expand("<day>", {"day": ["(mon|tues|wednes)day"]})
    assert sorted(samples) == ["monday", "tuesday", "wednesday"]


def test_recursive_vocabulary_reference():
    vocab = {"polite": ["please", "<courteous>"], "courteous": ["kindly"]}
    assert sorted(expand("<polite> stop", vocab)) == [
        "kindly stop", "please stop",
    ]


def test_undefined_vocabulary_reference_is_malformed():
    with pytest.raises(MalformedTemplate):
        expand("<missing> word")


def test_cyclic_vocabulary_reference_is_malformed():
    vocab = {"a": ["<b>"], "b": ["<a>"]}
    with pytest.raises(MalformedTemplate):
        expand("<a> word", vocab)


def test_vocabulary_with_a_slot_is_malformed():
    with pytest.raises(MalformedTemplate):
        expand("say <bad>", {"bad": ["{slot}"]})


# --- §3.6 malformed forms ----------------------------------------------------

@pytest.mark.parametrize("template", [
    "(unbalanced",
    "unbalanced)",
    "[unbalanced",
    "{unbalanced",
    "<unbalanced",
    "turn (on|off the lights",
])
def test_unbalanced_metacharacters(template):
    with pytest.raises(MalformedTemplate):
        expand(template)


@pytest.mark.parametrize("template", ["(word)", "()", "turn (on)"])
def test_single_branch_group(template):
    with pytest.raises(MalformedTemplate):
        expand(template)


@pytest.mark.parametrize("template", ["", "(|)", "[hello]"])
def test_empty_sample(template):
    with pytest.raises(MalformedTemplate):
        expand(template)


def test_slot_only_template():
    with pytest.raises(MalformedTemplate):
        expand("{name}")


@pytest.mark.parametrize("template", ["{a}{b}", "{a} {b}"])
def test_adjacent_slots(template):
    with pytest.raises(MalformedTemplate):
        expand(template)


def test_adjacent_slots_detected_after_expansion():
    """§3.6 — the adjacency check applies to every expanded sample."""
    with pytest.raises(MalformedTemplate):
        expand("{a} [foo] {b}")


def test_repeated_slot_name():
    with pytest.raises(MalformedTemplate):
        expand("{x} and {x}")


@pytest.mark.parametrize("template", ["{Name}", "{1st}", "{bad name}", "<Bad>"])
def test_invalid_names(template):
    with pytest.raises(MalformedTemplate):
        expand(template)


# --- edge cases --------------------------------------------------------------

def test_leading_trailing_and_repeated_whitespace_is_normalized():
    assert expand("  turn   on   the    lights  ") == ["turn on the lights"]


def test_tabs_count_as_whitespace():
    assert expand("turn\ton") == ["turn on"]


def test_vocabularies_argument_is_optional():
    assert expand("plain literal template") == ["plain literal template"]


def test_a_bare_vocabulary_reference_is_a_valid_template():
    assert sorted(expand("<g>", {"g": ["hello", "hi"]})) == ["hello", "hi"]


def test_vocabulary_member_may_be_multiple_words():
    assert expand("<g> there", {"g": ["good morning"]}) == ["good morning there"]


def test_empty_vocabulary_is_malformed():
    with pytest.raises(MalformedTemplate):
        expand("say <x>", {"x": []})


def test_expand_does_not_enforce_slot_consistency():
    """expand() works one template at a time; the cross-template slot rule
    (OVOS-INTENT-1 §5.5) is enforced elsewhere, not here."""
    assert sorted(expand("(buy {item}|leave)")) == ["buy {item}", "leave"]


def test_optional_around_a_slot():
    assert sorted(expand("[really ]want {item}")) == [
        "really want {item}", "want {item}",
    ]


def test_unicode_literal_words_pass_through():
    assert expand("ligar a televisão") == ["ligar a televisão"]


def test_duplicate_branches_collapse_to_one_sample():
    assert expand("(go|go) home") == ["go home"]


# --- inline_keywords ----------------------------------------------------------


def test_inline_keywords_basic():
    tpl = "<turn_on> [the] {name}"
    vocab = {"turn_on": ["turn on", "switch on"]}
    assert inline_keywords(tpl, vocab) == "(turn on|switch on) [the] {name}"


def test_inline_keywords_nested():
    tpl = "<broadcast> <everywhere>"
    vocab = {
        "broadcast": ["<a>ذع", "بلغ"],
        "a": ["آ", "أ"],
        "everywhere": ["كل مكان"],
    }
    result = inline_keywords(tpl, vocab)
    assert "بلغ" in result
    assert "كل مكان" in result
    assert "(آ|أ)" in result


def test_inline_keywords_empty_vocab():
    assert inline_keywords("<x> lights", {}) == "<x> lights"


def test_inline_keywords_none_vocab():
    assert inline_keywords("<x> lights", None) == "<x> lights"


def test_inline_keywords_strips_unresolved():
    # An unknown keyword is left as literal text with its angle brackets
    # stripped (the documented lenient behaviour), not raised on.
    vocab = {"known": ["yes"]}
    result = inline_keywords("<unknown> <known>", vocab)
    assert result == "unknown (yes)"


def test_inline_keywords_inlines_all_values_by_default():
    # No silent truncation: every value is inlined (OVOS-INTENT-1 §4.3 — a
    # limit is enforced by refusing, not by dropping).
    vocab = {"x": [str(i) for i in range(20)]}
    result = inline_keywords("<x>", vocab)
    for i in range(20):
        assert f"|{i}|" in f"|{result[1:-1]}|"
    assert result.count("|") == 19


def test_inline_keywords_max_values_refuses():
    # §4.3: an explicit bound, when exceeded, REFUSES (raises) — it never
    # silently truncates the value list.
    vocab = {"x": [str(i) for i in range(20)]}
    with pytest.raises(MalformedTemplate):
        inline_keywords("<x>", vocab, max_values=5)


def test_inline_keywords_max_values_within_bound():
    vocab = {"x": ["a", "b", "c"]}
    assert inline_keywords("<x>", vocab, max_values=5) == "(a|b|c)"


def test_inline_keywords_cycle_raises():
    # A reference cycle is rejected (OVOS-INTENT-1 §4.1), not cut off at an
    # arbitrary recursion depth.
    vocab = {"a": ["<b>"], "b": ["<a>"]}
    with pytest.raises(MalformedTemplate):
        inline_keywords("<a>", vocab)


def test_inline_keywords_no_refs():
    assert inline_keywords("hello world", {"x": ["y"]}) == "hello world"

