"""Tests for the locale resource linter (`ovos-spec-lint`)."""
import pytest

from ovos_spec_tools.expansion import MalformedTemplate
from ovos_spec_tools.lint import (
    ERROR,
    WARNING,
    declared_slots,
    lint_locale,
    lint_required_slots,
    main,
    validate_required_slots,
)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _errors(findings):
    return [f for f in findings if f.severity == ERROR]


def _warnings(findings):
    return [f for f in findings if f.severity == WARNING]


def test_clean_locale_has_no_findings(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "play.intent", "(play|put on) {query}\n")
    _write(locale / "en-US" / "yes.voc", "yes\nyeah\n")
    _write(locale / "en-US" / "greet.dialog", "Hello {name}.\n")
    assert lint_locale(locale) == []


def test_malformed_template_is_an_error(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "bad.intent", "turn (on|off the lights\n")
    errors = _errors(lint_locale(locale))
    assert len(errors) == 1
    assert "bad.intent" in errors[0].path


def test_empty_file_is_an_error(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "empty.voc", "# just a comment\n")
    assert any("empty" in f.message for f in _errors(lint_locale(locale)))


def test_slot_in_slot_free_role_is_an_error(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "thing.voc", "the {slot}\n")
    assert any("slot-free" in f.message for f in _errors(lint_locale(locale)))


def test_bad_base_name_is_an_error(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "Bad-Name.intent", "hello world\n")
    assert any("base name" in f.message for f in _errors(lint_locale(locale)))


def test_entity_base_name_starting_with_digit_is_an_error(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "2nd.entity", "second\n")
    assert any("digit" in f.message for f in _errors(lint_locale(locale)))


def test_duplicate_resource_is_an_error(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "a" / "dup.intent", "first\n")
    _write(locale / "en-US" / "b" / "dup.intent", "second\n")
    assert any("duplicate" in f.message for f in _errors(lint_locale(locale)))


def test_legacy_extension_is_a_warning(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "x.voc", "yes\n")
    _write(locale / "en-US" / "old.rx", ".*\n")
    findings = lint_locale(locale)
    assert _errors(findings) == []
    assert any(".rx" in f.message for f in _warnings(findings))


def test_blacklist_paired_with_intent_has_no_warning(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "bright.intent", "make it (bright|light)\n")
    _write(locale / "en-US" / "bright.blacklist", "sunrise\n")
    assert not any("blacklist" in f.message
                   for f in _warnings(lint_locale(locale)))


def test_blacklist_paired_with_entity_has_no_warning(tmp_path):
    # §4.3 slot-value exclusion: a .blacklist pairs by base name with an
    # .entity whose values it excludes from filling the slot.
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "ask.intent", "who is {person}\n")
    _write(locale / "en-US" / "person.entity", "alice\nbob\n")
    _write(locale / "en-US" / "person.blacklist", "he\nshe\nthey\n")
    assert not any("blacklist" in f.message
                   for f in _warnings(lint_locale(locale)))


def test_blacklist_paired_with_inline_slot_has_no_warning(tmp_path):
    # The excluded slot may be declared only as an inline `{slot}` in a
    # template, with no sibling .entity (an open-vocabulary slot).
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "search.intent", "look up {query}\n")
    _write(locale / "en-US" / "query.blacklist", "it\nthat\n")
    assert not any("blacklist" in f.message
                   for f in _warnings(lint_locale(locale)))


def test_unpaired_blacklist_is_a_warning(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "x.voc", "yes\n")
    _write(locale / "en-US" / "orphan.blacklist", "nope\n")
    assert any("blacklist" in f.message
               for f in _warnings(lint_locale(locale)))


def test_file_outside_a_language_directory_is_a_warning(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "stray.intent", "hello world\n")
    assert any("language directory" in f.message
               for f in _warnings(lint_locale(locale)))


def test_non_bcp47_language_directory_is_a_warning(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "english" / "x.intent", "hello world\n")
    assert any("BCP-47" in f.message for f in _warnings(lint_locale(locale)))


def test_unresolved_vocabulary_reference_is_an_error(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "greet.intent", "<missing> {name}\n")
    assert _errors(lint_locale(locale))


def test_can_point_at_a_single_language_directory(tmp_path):
    lang = tmp_path / "en-US"
    _write(lang / "play.intent", "(play|stop) {query}\n")
    assert lint_locale(lang) == []


# --- the CLI -----------------------------------------------------------------

def test_main_returns_zero_for_a_clean_locale(tmp_path, capsys):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "play.intent", "play {query}\n")
    assert main([str(locale)]) == 0


def test_main_returns_one_on_errors(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "bad.intent", "{a}{b}\n")
    assert main([str(locale)]) == 1


def test_main_strict_fails_on_warnings(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "old.list", "a\n")
    assert main([str(locale)]) == 0
    assert main([str(locale), "--strict"]) == 1


# --- edge cases --------------------------------------------------------------

def test_lint_nonexistent_path_is_an_error():
    findings = lint_locale("/no/such/locale/path")
    assert any(f.severity == ERROR for f in findings)


def test_lint_empty_locale_warns(tmp_path):
    locale = tmp_path / "locale"
    locale.mkdir()
    assert any("no language" in f.message for f in lint_locale(locale))


def test_unknown_extension_is_ignored(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "notes.txt", "ignore me\n")
    _write(locale / "en-US" / "ok.intent", "hello world\n")
    assert lint_locale(locale) == []


def test_lint_accepts_a_single_language_directory(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "ok.intent", "hello world\n")
    assert lint_locale(locale / "en-US") == []


# --- slot consistency: .dialog ONLY (OVOS-INTENT-2 §4.2) ---------------------

# .intent templates MAY declare different slot sets — the engine extracts only
# the matched template's slots and the intent's slot set is their union
# (OVOS-INTENT-2 §4.1, OVOS-INTENT-3 §5.1). A tool MUST NOT reject .intent for
# divergent slots, so divergence is NOT flagged for the .intent role.

def test_divergent_slots_in_one_intent_is_allowed(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "p.intent", "play {query}\nstop {engine}\n")
    assert not any("slot sets" in f.message for f in _errors(lint_locale(locale)))


def test_mixing_slotted_and_slotless_lines_in_intent_is_allowed(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "p.intent", "play {query}\njust stop\n")
    assert not any("slot sets" in f.message for f in _errors(lint_locale(locale)))


def test_consistent_slots_across_an_intent_is_clean(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "p.intent",
           "(play|put on) {query}\ni want {query}\n")
    assert lint_locale(locale) == []


# .dialog still requires identical slot sets.

def test_inconsistent_slots_in_one_dialog_is_an_error(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "greet.dialog",
           "Hello {name}.\nNice to meet you, {title} and {surname}.\n")
    assert any("slot sets" in f.message for f in _errors(lint_locale(locale)))


def test_mixing_slotted_and_slotless_lines_in_dialog_is_an_error(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "greet.dialog",
           "Hello {name}.\nWelcome back.\n")
    assert any("slot sets" in f.message for f in _errors(lint_locale(locale)))


# --- robustness --------------------------------------------------------------

def test_non_utf8_file_is_reported_not_crashed(tmp_path):
    lang = tmp_path / "locale" / "en-US"
    lang.mkdir(parents=True)
    (lang / "bad.intent").write_bytes(b"\xff\xfe not valid utf-8\n")
    findings = lint_locale(tmp_path / "locale")
    assert any("cannot read" in f.message for f in findings)


def test_empty_language_directory_warns(tmp_path):
    locale = tmp_path / "locale"
    (locale / "en-US").mkdir(parents=True)
    assert any("no resource files" in f.message
               for f in _warnings(lint_locale(locale)))


# --- .blacklist pairing (OVOS-INTENT-2 §4.3) --------------------------------

def test_orphan_blacklist_warns(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "ghost.blacklist", "spam words\n")
    assert any("no matching" in f.message
               for f in _warnings(lint_locale(locale)))


def test_blacklist_with_a_matching_intent_is_clean(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "play.intent", "play music\n")
    _write(locale / "en-US" / "play.blacklist", "trailer\n")
    assert lint_locale(locale) == []


# --- the --spec-version flag -------------------------------------------------

def test_spec_version_0_flags_the_blacklist_role(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "play.intent", "play music\n")
    _write(locale / "en-US" / "play.blacklist", "trailer\n")
    findings = lint_locale(locale, spec_version=0)
    assert any("requires spec version" in f.message for f in findings)


def test_spec_version_1_flags_a_vocabulary_reference(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "greeting.voc", "hello\nhi\n")
    _write(locale / "en-US" / "greet.intent", "<greeting> there\n")
    errors = _errors(lint_locale(locale, spec_version=1))
    assert any("vocabulary reference" in f.message for f in errors)


def test_default_spec_version_flags_neither(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "greeting.voc", "hello\nhi\n")
    _write(locale / "en-US" / "greet.intent", "<greeting> there\n")
    _write(locale / "en-US" / "greet.blacklist", "spam\n")
    findings = lint_locale(locale)  # default spec-version 2
    assert not any("spec version" in f.message for f in findings)


def test_main_honors_spec_version(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "greeting.voc", "hello\nhi\n")
    _write(locale / "en-US" / "greet.intent", "<greeting> there\n")
    assert main([str(locale)]) == 0                          # v3 — fine
    assert main([str(locale), "--spec-version", "1"]) == 1   # <name> is v2


# --- the .prompt role (OVOS-INTENT-2 §4.4) ----------------------------------

def test_prompt_file_is_a_recognized_role(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "system.prompt", "You are {assistant}.\n")
    assert lint_locale(locale) == []


def test_empty_prompt_is_an_error(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "system.prompt", "   \n\n")
    assert any("empty" in f.message for f in _errors(lint_locale(locale)))


def test_prompt_is_not_template_checked(tmp_path):
    """A `.prompt` is plain text — content that would be a malformed template
    if it were one is perfectly valid."""
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "sys.prompt", "turn (on|off the lights {a}{b}\n")
    assert lint_locale(locale) == []


def test_non_utf8_prompt_is_reported_not_crashed(tmp_path):
    lang = tmp_path / "locale" / "en-US"
    lang.mkdir(parents=True)
    (lang / "sys.prompt").write_bytes(b"\xff\xfe not valid utf-8")
    assert any("cannot read" in f.message
               for f in lint_locale(tmp_path / "locale"))


def test_spec_version_2_flags_the_prompt_role(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "system.prompt", "You are helpful.\n")
    findings = lint_locale(locale, spec_version=2)
    assert any("requires spec version 3" in f.message for f in findings)


def test_default_spec_version_does_not_flag_prompt(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "system.prompt", "You are helpful.\n")
    assert not any("spec version" in f.message for f in lint_locale(locale))


# --- required_slots validation (OVOS-INTENT-3 §5.3) ----------------------

def test_declared_slots_is_the_union_across_templates():
    templates = [
        "(play|put on) {query}",
        "(play|put on) {query} (on|using) {engine}",
        "i want to listen to {query}",
    ]
    assert declared_slots(templates) == frozenset({"query", "engine"})


def test_declared_slots_folds_double_brace_spelling():
    # {{name}} and {name} are the same slot (OVOS-INTENT-1 §3.4).
    assert declared_slots(["say {{name}}", "say {name}!"]) == frozenset({"name"})


def test_required_slot_declared_by_a_template_is_accepted():
    templates = [
        "(play|put on) {query}",
        "(play|put on) {query} (on|using) {engine}",
    ]
    # both required slots are declared by at least one template — no raise.
    validate_required_slots(["query", "engine"], templates)


def test_required_slot_declared_by_no_template_is_rejected():
    templates = ["(play|put on) {query}"]
    with pytest.raises(MalformedTemplate) as exc:
        validate_required_slots(["query", "engine"], templates)
    assert "engine" in str(exc.value)
    assert "§5.3" in str(exc.value)


def test_required_slot_in_only_one_of_several_templates_is_accepted():
    # the engine extracts only the matched template's slots, so a required slot
    # declared by a *single* template still satisfies §5.3 (it can fire).
    templates = [
        "i want to listen to {query}",
        "(play|put on) {query} (on|using) {engine}",
    ]
    validate_required_slots(["engine"], templates)


def test_no_required_slots_is_always_accepted():
    validate_required_slots([], ["(play|put on) {query}"])


def test_required_slot_against_slotless_templates_is_rejected():
    with pytest.raises(MalformedTemplate):
        validate_required_slots(["query"], ["just hello", "say hi"])


def test_required_slot_declared_only_in_double_brace_is_accepted():
    # {{engine}} declares the slot just as {engine} would (§3.4 fold).
    validate_required_slots(["engine"], ["play {query} on {{engine}}"])


def test_lint_required_slots_returns_an_error_finding():
    findings = lint_required_slots(
        "play.intent", ["query", "engine"], ["(play|put on) {query}"])
    assert len(findings) == 1
    assert findings[0].severity == ERROR
    assert findings[0].path == "play.intent"
    assert "engine" in findings[0].message


def test_lint_required_slots_clean_returns_no_findings():
    findings = lint_required_slots(
        "play.intent", ["query"], ["(play|put on) {query}"])
    assert findings == []
