"""The ``.required`` role (OVOS-INTENT-2 §4.5) and required slots (OVOS-INTENT-3 §5.3).

Every expected value below is written by hand from the clause, not read back
from the code under test.
"""
import pytest

from ovos_spec_tools import (
    LocaleResources,
    MalformedResource,
    derive_required_slots,
    required_keywords_reject,
)
from ovos_spec_tools.expansion import INPUT_DIRECTION_ROLES
from ovos_spec_tools.lint import ERROR, ROLE_EXTENSIONS, WARNING, lint_locale
from ovos_spec_tools.resources import SLOT_FREE_ROLES

PHILOSOPHER_KEYWORDS = [
    "aristotle",
    "aristoteles",
    "the stagirite",
    "the philosopher of stagira",
]


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _philosopher_locale(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "philosopher_dates.intent",
           "when was aristotle (born|alive)\n"
           "when did {person} die\n")
    _write(locale / "en-US" / "philosopher_dates.required",
           "# the name forms of one philosopher\n"
           "aristotle\n"
           "aristoteles\n"
           "(the stagirite|the philosopher of stagira)\n")
    return locale


# --- the role --------------------------------------------------------------

def test_required_is_a_slot_free_input_direction_role():
    assert ".required" in SLOT_FREE_ROLES
    assert ".required" in INPUT_DIRECTION_ROLES
    assert ".required" in ROLE_EXTENSIONS


# --- loading (§4.5 "Loads as") ---------------------------------------------

def test_required_loads_as_the_union_of_its_sample_sets(tmp_path):
    res = LocaleResources(str(_philosopher_locale(tmp_path)))
    assert res.load_required_keywords("philosopher_dates", "en-US") == \
        PHILOSOPHER_KEYWORDS


def test_a_named_slot_in_required_is_malformed_on_load(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "ask.intent", "ask about {person}\n")
    _write(locale / "en-US" / "ask.required", "about {person}\n")
    res = LocaleResources(str(locale))
    with pytest.raises(MalformedResource):
        res.load_required_keywords("ask", "en-US")


# --- the occurrence rule, inverted (§4.5 Role) ------------------------------

@pytest.mark.parametrize("utterance, rejected", [
    ("when was einstein born", True),
    ("when was plato born", True),
    ("when was aristotle born", False),
    ("When was Aristotle born?", False),
    ("when did aristoteles die", False),
    ("what did the stagirite write", False),
    ("what did the philosopher of stagira write", False),
    # whole words only: "aristotle" does not occur within "aristotelian"
    ("explain aristotelian logic", True),
    # a contiguous sequence: the words of "the stagirite" apart do not occur
    ("the man from stagirite", True),
    ("", True),
])
def test_required_keywords_reject_follows_the_occurrence_rule(
        utterance, rejected):
    assert required_keywords_reject(utterance, PHILOSOPHER_KEYWORDS) is rejected


@pytest.mark.parametrize("utterance, keywords, rejected", [
    # OVOS-INTENT-2 §4.3: "the phrase art does not occur within the word start"
    ("start the timer", ["art"], True),
    ("show me some art", ["art"], False),
    ("explain platonic love", ["plato"], True),
    ("what did plato write", ["plato"], False),
])
def test_a_keyword_inside_a_longer_word_does_not_occur(
        utterance, keywords, rejected):
    assert required_keywords_reject(utterance, keywords) is rejected


def test_no_required_keywords_is_no_requirement():
    # OVOS-INTENT-4 §6.1: "An empty required_keywords means no keyword
    # requirement, never a requirement that cannot be met."
    assert required_keywords_reject("when was einstein born", []) is False


# --- required slots (OVOS-INTENT-3 §5.3) ------------------------------------

@pytest.mark.parametrize("templates, expected", [
    # the OVOS-INTENT-4 §6.1 example payload
    (["(play|put on) {query}",
      "(play|put on) {query} (on|using) {engine}",
      "i want to listen to {query}",
      "play {query} for {duration:length}"], {"query"}),
    # a slot inside an optional group is not required
    (["play {query} [on {engine}]"], {"query"}),
    # a slot in only one branch of an alternative is not required
    (["(play {query}|stop the music)"], set()),
    # a slot in only some templates is not required
    (["who was {person}", "who was the stagirite"], set()),
    # every template declares it
    (["who was {person}", "when was {person} born"], {"person"}),
    # double-brace and typed spellings name the bare slot
    (["set {{label}} for {duration:length}"], {"label", "length"}),
    # an inline vocabulary is slot-free and does not change the slot set
    (["convert {amount} <unit>"], {"amount"}),
    # no templates, no required slots
    ([], set()),
])
def test_derive_required_slots(templates, expected):
    assert derive_required_slots(templates) == frozenset(expected)


# --- lint ------------------------------------------------------------------

def test_lint_paired_required_is_clean(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "philosopher_dates.intent",
           "when was aristotle born\nwhen did {person} die\n")
    _write(locale / "en-US" / "philosopher_dates.required", "aristotle\n")
    assert lint_locale(locale) == []


def test_lint_required_with_no_intent_warns(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "person.entity", "aristotle\n")
    _write(locale / "en-US" / "person.required", "aristotle\n")
    warnings = [f for f in lint_locale(locale) if f.severity == WARNING]
    assert [(f.path.endswith("person.required"), "person.intent" in f.message)
            for f in warnings] == [(True, True)]


def test_lint_named_slot_in_required_is_an_error(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "ask.intent", "ask about {person}\n")
    _write(locale / "en-US" / "ask.required", "about {person}\n")
    errors = [f for f in lint_locale(locale) if f.severity == ERROR]
    assert len(errors) == 1
    assert errors[0].path.endswith("ask.required")
    assert "slot-free" in errors[0].message


def test_lint_flags_each_slot_free_sample_with_no_required_keyword(tmp_path):
    locale = _philosopher_locale(tmp_path)
    _write(locale / "en-US" / "philosopher_dates.intent",
           "when was aristotle born\n"
           "when was (plato|socrates) born\n"
           "when did {person} die\n"
           "tell me about the stagirite\n")
    findings = lint_locale(locale)
    assert all(f.severity == WARNING for f in findings)
    flagged = sorted((f.line, f.message.split("[in: ")[1]) for f in findings)
    assert flagged == [(2, "'when was plato born']"),
                       (2, "'when was socrates born']")]


def test_spec_version_3_flags_the_required_role(tmp_path):
    locale = _philosopher_locale(tmp_path)
    findings = lint_locale(locale, spec_version=3)
    assert [f.path.endswith("philosopher_dates.required")
            for f in findings if "requires spec version 4" in f.message] == [True]
