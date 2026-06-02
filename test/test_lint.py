"""Tests for the locale resource linter (`ovos-spec-lint`)."""
import pytest

from ovos_spec_tools.lint import ERROR, WARNING, lint_locale, main


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


# --- slot consistency (OVOS-INTENT-1 §5.5) ----------------------------------

# .intent allows union slot sets — templates MAY declare different slots.

def test_inconsistent_slots_in_one_intent_is_accepted(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "p.intent", "play {query}\nstop {engine}\n")
    assert not any("slot sets" in f.message for f in _errors(lint_locale(locale)))


def test_mixing_slotted_and_slotless_lines_in_intent_is_accepted(tmp_path):
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
