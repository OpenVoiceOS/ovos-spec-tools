"""Conformance tests for the OVOS-INTENT-1 reference expander.

Each test cites the section of OVOS-INTENT-1 version 2 it exercises. Together
these form the conformance corpus for the Expander role (§7).
"""
import pytest

from ovos_spec_tools import MalformedTemplate, expand


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
