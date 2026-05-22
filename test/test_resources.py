"""Conformance tests for the OVOS-INTENT-2 reference loader."""
import pytest

from ovos_spec_tools import (
    LocaleResources,
    MalformedResource,
    read_resource_file,
)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _skill(tmp_path, lang="en-US"):
    """A skill `locale/` directory rooted at tmp_path."""
    return tmp_path / "locale", (tmp_path / "locale" / lang)


# --- §3 common reader --------------------------------------------------------

def test_common_reader_skips_blanks_and_comments(tmp_path):
    f = tmp_path / "x.voc"
    _write(f, "# a comment\n\nyes\n  yeah  \n# another\nyep\n")
    assert read_resource_file(f) == ["yes", "yeah", "yep"]


def test_common_reader_accepts_crlf_and_bom(tmp_path):
    f = tmp_path / "x.voc"
    f.write_bytes(b"\xef\xbb\xbfyes\r\nyeah\r\n")  # BOM + CRLF
    assert read_resource_file(f) == ["yes", "yeah"]


# --- §4.1 .intent ------------------------------------------------------------

def test_load_intent_expands_and_keeps_slots(tmp_path):
    locale, lang = _skill(tmp_path)
    _write(lang / "play.intent", "(play|put on) {query}\n")
    res = LocaleResources("en-US", str(locale))
    assert sorted(res.load_intent("play")) == ["play {query}", "put on {query}"]


def test_load_intent_resolves_voc_references(tmp_path):
    locale, lang = _skill(tmp_path)
    _write(lang / "greeting.voc", "hello\nhi\n")
    _write(lang / "greet.intent", "<greeting> {name}\n")
    res = LocaleResources("en-US", str(locale))
    assert sorted(res.load_intent("greet")) == ["hello {name}", "hi {name}"]


# --- §4.2 .dialog ------------------------------------------------------------

def test_load_dialog_returns_unexpanded_phrases(tmp_path):
    locale, lang = _skill(tmp_path)
    _write(lang / "hi.dialog", "Hello {name}!\n(Hi|Hey) {name}.\n")
    res = LocaleResources("en-US", str(locale))
    assert res.load_dialog("hi") == ["Hello {name}!", "(Hi|Hey) {name}."]


# --- §4.3 slot-free roles ----------------------------------------------------

def test_load_entity_and_blacklist(tmp_path):
    locale, lang = _skill(tmp_path)
    _write(lang / "weekday.entity", "monday\n(tues|wednes)day\n")
    _write(lang / "play.blacklist", "trailer\n")
    res = LocaleResources("en-US", str(locale))
    assert sorted(res.load_entity("weekday")) == ["monday", "tuesday", "wednesday"]
    assert res.load_blacklist("play") == ["trailer"]


def test_slot_free_role_rejects_a_named_slot(tmp_path):
    locale, lang = _skill(tmp_path)
    _write(lang / "bad.voc", "a slot {here}\n")
    res = LocaleResources("en-US", str(locale))
    with pytest.raises(MalformedResource):
        res.load_vocabulary("bad")


# --- §2 layout ---------------------------------------------------------------

def test_subdirectories_are_searched_recursively(tmp_path):
    locale, lang = _skill(tmp_path)
    _write(lang / "intents" / "deep.intent", "do the thing\n")
    res = LocaleResources("en-US", str(locale))
    assert res.load_intent("deep") == ["do the thing"]


def test_language_tag_is_case_insensitive(tmp_path):
    locale, lang = _skill(tmp_path, lang="en-us")
    _write(lang / "x.intent", "hello world\n")
    res = LocaleResources("en-US", str(locale))  # requested with different case
    assert res.load_intent("x") == ["hello world"]


def test_duplicate_resource_in_one_tree_is_malformed(tmp_path):
    locale, lang = _skill(tmp_path)
    _write(lang / "a" / "dup.intent", "first\n")
    _write(lang / "b" / "dup.intent", "second\n")
    res = LocaleResources("en-US", str(locale))
    with pytest.raises(MalformedResource):
        res.load_intent("dup")


# --- §2.1 resolution precedence ---------------------------------------------

def test_user_override_wins_over_skill(tmp_path):
    skill_locale = tmp_path / "skill" / "locale"
    user_locale = tmp_path / "user" / "locale"
    _write(skill_locale / "en-US" / "x.intent", "skill version\n")
    _write(user_locale / "en-US" / "x.intent", "user version\n")
    res = LocaleResources("en-US", str(skill_locale), user_locale=str(user_locale))
    assert res.load_intent("x") == ["user version"]


# --- §5 empty files ----------------------------------------------------------

def test_empty_file_is_malformed(tmp_path):
    locale, lang = _skill(tmp_path)
    _write(lang / "empty.intent", "# only a comment\n\n")
    res = LocaleResources("en-US", str(locale))
    with pytest.raises(MalformedResource):
        res.load_intent("empty")


def test_missing_resource_raises(tmp_path):
    locale, _ = _skill(tmp_path)
    res = LocaleResources("en-US", str(locale))
    with pytest.raises(FileNotFoundError):
        res.load_intent("nope")
