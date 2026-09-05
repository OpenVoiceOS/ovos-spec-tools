"""Conformance tests for the OVOS-INTENT-4 keyword intent primitives."""
import pytest

from ovos_spec_tools import (
    Intent,
    IntentBuilder,
    LocaleResources,
    MalformedIntent,
    open_intent_envelope,
    voc_match,
)
from ovos_spec_tools.message import Message


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- IntentBuilder API surface (workshop/adapt-compatible) -------------------

def test_builder_accumulates_roles():
    b = (IntentBuilder("SetBrightness")
         .require("Set")
         .require("Brightness")
         .one_of("Up", "Down")
         .optionally("Politely")
         .exclude("Question"))
    assert b.name == "SetBrightness"
    assert b.requires == [("Set", "Set"), ("Brightness", "Brightness")]
    assert b.at_least_one == [("Up", "Down")]
    assert b.optional == [("Politely", "Politely")]
    assert b.excludes == ["Question"]


def test_builder_require_attribute_name():
    b = IntentBuilder("X").require("Color", "favourite_colour")
    assert b.requires == [("Color", "favourite_colour")]


def test_builder_require_optional_flag():
    # legacy signature: require(..., optional=True) routes to optional
    b = IntentBuilder("X").require("Y", optional=True)
    assert b.requires == []
    assert b.optional == [("Y", "Y")]


def test_builder_chaining_returns_self():
    b = IntentBuilder("X")
    assert b.require("A") is b
    assert b.optionally("B") is b
    assert b.one_of("C", "D") is b
    assert b.exclude("E") is b


def test_build_returns_intent_with_attributes():
    intent = IntentBuilder("Name").require("XKeyword").optionally("Y").build()
    assert isinstance(intent, Intent)
    assert intent.name == "Name"
    assert intent.requires == [("XKeyword", "XKeyword")]
    assert intent.optional == [("Y", "Y")]
    assert intent.at_least_one == []
    assert intent.excludes == []


# --- OVOS-INTENT-4 §5.2 keyword payload mapping ------------------------------

def test_to_keyword_payload_structure():
    intent = (IntentBuilder("SetBrightness")
              .require("Set")
              .require("Brightness")
              .one_of("Up", "Down")
              .optionally("Politely")
              .exclude("Question")
              .build())
    payload = intent.to_keyword_payload(skill_id="lighting.skill",
                                        lang="en-US")
    assert payload["skill_id"] == "lighting.skill"
    assert payload["intent_name"] == "SetBrightness"
    assert payload["lang"] == "en-US"
    assert payload["required"] == [{"name": "Set"}, {"name": "Brightness"}]
    assert payload["optional"] == [{"name": "Politely"}]
    assert payload["one_of"] == [[{"name": "Up"}, {"name": "Down"}]]
    assert payload["excluded"] == [{"name": "Question"}]


def test_to_keyword_payload_all_four_keys_present_when_empty():
    # §5.2: a producer MUST include all four role keys, even when empty.
    intent = IntentBuilder("Bare").require("Only").build()
    payload = intent.to_keyword_payload()
    for key in ("required", "optional", "one_of", "excluded"):
        assert key in payload
    assert payload["optional"] == []
    assert payload["one_of"] == []
    assert payload["excluded"] == []
    assert payload["intent_name"] == "Bare"
    # identity fields omitted when not provided
    assert "skill_id" not in payload
    assert "lang" not in payload


def test_to_keyword_payload_inlines_samples_when_supplied():
    intent = IntentBuilder("X").require("Set").one_of("Up", "Down").build()
    samples = {"Set": ["set", "change"], "Up": ["up", "higher"]}
    payload = intent.to_keyword_payload(samples=samples)
    assert payload["required"] == [{"name": "Set", "samples": ["set", "change"]}]
    assert payload["one_of"] == [[
        {"name": "Up", "samples": ["up", "higher"]},
        {"name": "Down"},  # no samples supplied -> name-only
    ]]


# --- open_intent_envelope round-trip -----------------------------------------

def test_open_intent_envelope_legacy_keys():
    intent = (IntentBuilder("Foo").require("A").optionally("B")
              .one_of("C", "D").exclude("E").build())
    # legacy serialization == Intent.__dict__ shape
    msg = Message("register_intent", {
        "name": intent.name,
        "requires": intent.requires,
        "at_least_one": [list(g) for g in intent.at_least_one],
        "optional": intent.optional,
        "excludes": intent.excludes,
    })
    rebuilt = open_intent_envelope(msg)
    assert rebuilt == intent


def test_open_intent_envelope_intent4_descriptors():
    intent = (IntentBuilder("Foo").require("A").optionally("B")
              .one_of("C", "D").exclude("E").build())
    payload = intent.to_keyword_payload(skill_id="s", lang="en-US")
    msg = Message("ovos.intent.register.keyword", payload)
    rebuilt = open_intent_envelope(msg)
    assert rebuilt == intent


def test_open_intent_envelope_accepts_raw_dict():
    rebuilt = open_intent_envelope({"intent_name": "Z",
                                    "required": [{"name": "A"}],
                                    "optional": [], "one_of": [],
                                    "excluded": []})
    assert rebuilt.name == "Z"
    assert rebuilt.requires == [("A", "A")]


# --- voc_match convenience ---------------------------------------------------

@pytest.fixture
def locale(tmp_path):
    _write(tmp_path / "locale" / "en-US" / "yes.voc",
           "yes\nyeah\nyep\nof course\n")
    return tmp_path / "locale"


def test_voc_match_whole_word_hit(locale):
    res = LocaleResources(str(locale))
    assert voc_match("yes, please", "yes", "en-US", res) is True


def test_voc_match_whole_word_no_substring(locale):
    res = LocaleResources(str(locale))
    # 'yes' must NOT match inside 'yesterday' (whole-word §4.3 semantics)
    assert voc_match("yesterday is gone", "yes", "en-US", res) is False


def test_voc_match_multiword_entry(locale):
    res = LocaleResources(str(locale))
    assert voc_match("well of course i will", "yes", "en-US", res) is True


def test_voc_match_accepts_path(locale):
    assert voc_match("yeah right", "yes", "en-US", str(locale)) is True


def test_voc_match_accepts_sequence_of_dirs(locale):
    assert voc_match("yep indeed", "yes", "en-US", [str(locale)]) is True


def test_voc_match_missing_voc_returns_false(locale):
    assert voc_match("anything", "nonexistent", "en-US", str(locale)) is False


# --- OVOS-INTENT-3 §4.2 well-formedness (validate raises; build/emit warn) ---

def test_validate_rejects_intent_with_no_required_and_no_one_of():
    """§4.2: a keyword intent MUST declare at least one required or one-of
    constraint — only optional + excluded "has nothing that must be present
    and is malformed". Explicit validate() enforces this."""
    intent = Intent("Bad", optional=[("Politely", "Politely")],
                    excludes=["Question"])
    with pytest.raises(MalformedIntent):
        intent.validate()


def test_build_warns_but_does_not_raise_on_malformed_intent(caplog):
    """build() stays backward-compatible: a §4.2-malformed builder logs a
    warning rather than raising. Enforcement is via explicit validate / lint."""
    builder = IntentBuilder("Bad").optionally("Politely").exclude("Question")
    with caplog.at_level("WARNING"):
        intent = builder.build()  # must NOT raise
    assert any("malformed" in r.message.lower() for r in caplog.records)
    with pytest.raises(MalformedIntent):  # explicit validation still rejects
        intent.validate()


def test_build_accepts_intent_with_only_one_of():
    """A single one-of group satisfies §4.2 (at least one of required/one-of)."""
    intent = IntentBuilder("OK").one_of("Up", "Down").build()
    assert intent.at_least_one == [("Up", "Down")]


def test_validate_rejects_same_vocab_under_two_roles():
    """§4.2: a vocabulary MUST appear under at most one role; required + excluded
    of the same vocab is contradictory and malformed."""
    intent = Intent("Bad", requires=[("Light", "Light")], excludes=["Light"])
    with pytest.raises(MalformedIntent):
        intent.validate()


def test_validate_rejects_vocab_required_and_one_of():
    intent = Intent("Bad", requires=[("Set", "Set")],
                    at_least_one=[("Set", "Down")])
    with pytest.raises(MalformedIntent):
        intent.validate()


def test_validate_returns_self_for_well_formed_intent():
    intent = Intent("Good", requires=[("Set", "Set")])
    assert intent.validate() is intent


def test_to_keyword_payload_warns_but_emits_malformed_intent(caplog):
    """Emitting a §4.2-malformed register payload warns rather than raising,
    keeping the producer backward-compatible."""
    intent = Intent("Bad", optional=[("Politely", "Politely")],
                    excludes=["Question"])
    with caplog.at_level("WARNING"):
        payload = intent.to_keyword_payload()  # must NOT raise
    assert payload["intent_name"] == "Bad"
    assert any("malformed" in r.message.lower() for r in caplog.records)


def test_raw_intent_construction_does_not_validate():
    """Raw ``Intent(...)`` construction stays permissive (the scaffold / wire
    round-trip path); validation happens at build()/emit. The empty-default
    Intent and open_intent_envelope reconstruction must not raise."""
    Intent()  # scaffold default, no raise
    rebuilt = open_intent_envelope({"intent_name": "Z"})
    assert rebuilt.name == "Z"
