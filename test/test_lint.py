"""Tests for the locale resource linter (`ovos-spec-lint`)."""
import pytest

from ovos_spec_tools.expansion import MalformedTemplate
from ovos_spec_tools.lint import (
    ERROR,
    WARNING,
    declared_slots,
    declared_slot_types,
    lint_locale,
    lint_skill_source,
    RX_SEVERITY,
    lint_required_slots,
    lint_slot_types,
    main,
    validate_required_slots,
    validate_slot_types,
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
    _write(locale / "en-US" / "old.value", "one\n")
    findings = lint_locale(locale)
    assert _errors(findings) == []
    assert any(".value" in f.message for f in _warnings(findings))


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


# --- OVOS-INTENT-1 §5.6 / OVOS-INTENT-4 §6.1 slot_types ---------------------

def test_declared_slot_types_reads_registered_prefixes():
    templates = ["play {query} for {duration:length}"]
    assert declared_slot_types(templates) == {"length": "duration"}


def test_declared_slot_types_ignores_unregistered_prefix():
    # An unregistered prefix degrades to an untyped slot (§3.6) and declares
    # no type — the derived map must not claim a type the grammar never keeps.
    templates = ["play {query} for {gizmo:length}"]
    assert declared_slot_types(templates) == {}


def test_declared_slot_types_folds_double_brace():
    assert declared_slot_types(["set {{color:shade}}"]) == {"shade": "color"}


def test_declared_slot_types_first_seen_wins_on_conflict():
    templates = ["set {number:x}", "set {color:x} please"]
    assert declared_slot_types(templates) == {"x": "number"}


def test_validate_slot_types_accepts_declared_registered_slot():
    validate_slot_types({"length": "duration"},
                        ["play {query} for {duration:length}"])


def test_validate_slot_types_rejects_undeclared_slot():
    with pytest.raises(MalformedTemplate):
        validate_slot_types({"length": "duration"}, ["play {query}"])


def test_validate_slot_types_rejects_unregistered_type():
    with pytest.raises(MalformedTemplate):
        validate_slot_types({"length": "gizmo"}, ["play {length}"])


def test_lint_slot_types_returns_an_error_finding():
    findings = lint_slot_types("play.intent", {"length": "gizmo"},
                              ["play {length}"])
    assert len(findings) == 1
    assert findings[0].severity == ERROR


def test_lint_slot_types_clean_returns_no_findings():
    findings = lint_slot_types("play.intent", {"length": "duration"},
                              ["play {duration:length}"])
    assert findings == []


# --- duplicate intent definitions (OVOS-INTENT-2 §4.1) ----------------------


@pytest.mark.parametrize("name", [
    "create_alarm_alt", "create_alarm_alias", "create_alarm_extra",
    "create_alarm_2",
])
def test_duplicate_suffix_intent_is_an_error(tmp_path, name):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "create_alarm.intent", "set an alarm\n")
    _write(locale / "en-US" / f"{name}.intent", "wake me up\n")
    errors = _errors(lint_locale(locale))
    assert len(errors) == 1
    assert f"{name}.intent" in errors[0].path
    assert "fold its templates into create_alarm.intent" in errors[0].message


def test_duplicate_suffix_without_a_base_file_still_errors(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "create_alarm_alt.intent", "wake me up\n")
    errors = _errors(lint_locale(locale))
    assert len(errors) == 1
    assert "there is no create_alarm.intent" in errors[0].message


def test_the_suffix_rule_only_applies_to_intent_files(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "colour_alt.voc", "colour\ncolor\n")
    assert _errors(lint_locale(locale)) == []


@pytest.mark.parametrize("name", [
    "alt", "alternative", "mp3", "altitude", "set_alarm", "x2y",
])
def test_an_ordinary_base_name_is_not_a_duplicate(tmp_path, name):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / f"{name}.intent", "do the thing\n")
    assert _errors(lint_locale(locale)) == []


def test_stacked_intent_handlers_are_an_error(tmp_path):
    source = tmp_path / "skill" / "__init__.py"
    _write(source, (
        "class S:\n"
        "    @intent_handler('create_alarm.intent')\n"
        "    @intent_handler('create_alarm_alt.intent')\n"
        "    def handle_create(self, message):\n"
        "        return 1\n"))
    errors = _errors(lint_skill_source(tmp_path))
    assert len(errors) == 1
    assert "stacked on handle_create()" in errors[0].message
    assert "create_alarm.intent" in errors[0].message
    assert "create_alarm_alt.intent" in errors[0].message


def test_a_handler_that_only_calls_another_is_an_error(tmp_path):
    source = tmp_path / "skill" / "__init__.py"
    _write(source, (
        "class S:\n"
        "    @intent_handler('create_alarm.intent')\n"
        "    def handle_create(self, message):\n"
        "        return self.do_work(message)\n"
        "\n"
        "    @intent_handler('create_alarm_alt.intent')\n"
        "    def handle_create_alt(self, message):\n"
        "        'Docstring only, then the call.'\n"
        "        return self.handle_create(message)\n"))
    errors = _errors(lint_skill_source(tmp_path))
    assert len(errors) == 1
    assert "handle_create_alt() does nothing but call handle_create()" \
        in errors[0].message
    assert "Fold the templates into create_alarm.intent" in errors[0].message


def test_a_handler_that_calls_a_non_handler_is_not_flagged(tmp_path):
    source = tmp_path / "skill" / "__init__.py"
    _write(source, (
        "class S:\n"
        "    @intent_handler('create_alarm.intent')\n"
        "    def handle_create(self, message):\n"
        "        return self.do_work(message)\n"
        "\n"
        "    def do_work(self, message):\n"
        "        return 1\n"))
    assert _errors(lint_skill_source(tmp_path)) == []


def test_a_handler_with_a_real_body_is_not_flagged(tmp_path):
    source = tmp_path / "skill" / "__init__.py"
    _write(source, (
        "class S:\n"
        "    @intent_handler('a.intent')\n"
        "    def handle_a(self, message):\n"
        "        return 1\n"
        "\n"
        "    @intent_handler('b.intent')\n"
        "    def handle_b(self, message):\n"
        "        self.speak('hi')\n"
        "        return self.handle_a(message)\n"))
    assert _errors(lint_skill_source(tmp_path)) == []


def test_a_decorated_function_without_a_resource_string_is_named_anyway(tmp_path):
    source = tmp_path / "skill" / "__init__.py"
    _write(source, (
        "class S:\n"
        "    @intent_handler(IntentBuilder('x'))\n"
        "    def handle_x(self, message):\n"
        "        return 1\n"
        "\n"
        "    @intent_handler('y.intent')\n"
        "    def handle_y(self, message):\n"
        "        return self.handle_x(message)\n"))
    errors = _errors(lint_skill_source(tmp_path))
    assert len(errors) == 1
    assert "the resource on handle_x()" in errors[0].message


def test_unparseable_python_warns_and_is_skipped(tmp_path):
    _write(tmp_path / "skill" / "broken.py", "def (:\n")
    findings = lint_skill_source(tmp_path)
    assert _errors(findings) == []
    assert any("cannot be parsed" in f.message for f in _warnings(findings))


def test_a_tree_with_no_python_yields_nothing(tmp_path):
    (tmp_path / "empty").mkdir()
    assert lint_skill_source(tmp_path / "empty") == []


def test_the_cli_checks_the_skill_source_beside_the_locale(tmp_path, capsys):
    _write(tmp_path / "locale" / "en-US" / "create_alarm.intent", "wake me\n")
    _write(tmp_path / "__init__.py", (
        "class S:\n"
        "    @intent_handler('create_alarm.intent')\n"
        "    @intent_handler('create_alarm_alt.intent')\n"
        "    def handle_create(self, message):\n"
        "        return 1\n"))
    assert main([str(tmp_path / "locale")]) == 1
    assert "stacked on handle_create()" in capsys.readouterr().out


def test_an_empty_skill_source_switches_the_binding_check_off(tmp_path, capsys):
    _write(tmp_path / "locale" / "en-US" / "create_alarm.intent", "wake me\n")
    _write(tmp_path / "__init__.py", (
        "class S:\n"
        "    @intent_handler('a.intent')\n"
        "    @intent_handler('b.intent')\n"
        "    def handle(self, message):\n"
        "        return 1\n"))
    assert main([str(tmp_path / "locale"), "--skill-source", ""]) == 0


# --- deprecated regex resources (Miro, 2026-09-25) --------------------------


def test_an_rx_file_is_reported_with_its_own_message(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "x.voc", "yes\n")
    _write(locale / "en-US" / "when.rx", ".*\n")
    findings = [f for f in lint_locale(locale) if f.path.endswith("when.rx")]
    assert len(findings) == 1
    assert findings[0].severity == RX_SEVERITY
    assert findings[0].message == (
        "regex resources are deprecated; model the slot in an .intent file "
        "(OVOS-INTENT-2 §1)")


def test_an_rx_file_is_a_warning_while_two_skills_still_ship_them():
    # Flip RX_SEVERITY to ERROR once the date-time and weather drop PRs merge.
    assert RX_SEVERITY == WARNING


def test_an_rx_file_does_not_also_raise_the_generic_legacy_warning(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "x.voc", "yes\n")
    _write(locale / "en-US" / "when.rx", ".*\n")
    assert not any("legacy file type" in f.message
                   for f in lint_locale(locale))


def test_strict_fails_a_tree_that_still_ships_an_rx(tmp_path, capsys):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "x.voc", "yes\n")
    _write(locale / "en-US" / "when.rx", ".*\n")
    assert main([str(locale), "--strict", "--skill-source", ""]) == 1
    assert "regex resources are deprecated" in capsys.readouterr().out
