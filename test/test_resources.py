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
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "play.intent", "(play|put on) {query}\n")
    res = LocaleResources(str(locale))
    assert sorted(res.load_intent("play", "en-US")) == [
        "play {query}", "put on {query}",
    ]


def test_load_intent_resolves_voc_references(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "greeting.voc", "hello\nhi\n")
    _write(locale / "en-US" / "greet.intent", "<greeting> {name}\n")
    res = LocaleResources(str(locale))
    assert sorted(res.load_intent("greet", "en-US")) == [
        "hello {name}", "hi {name}",
    ]


# --- one instance, many languages -------------------------------------------

def test_one_instance_serves_multiple_languages(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "hi.intent", "hello\n")
    _write(locale / "pt-BR" / "hi.intent", "ola\n")
    res = LocaleResources(str(locale))
    assert res.load_intent("hi", "en-US") == ["hello"]
    assert res.load_intent("hi", "pt-BR") == ["ola"]


# --- §4.2 .dialog ------------------------------------------------------------

def test_load_dialog_returns_unexpanded_phrases(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "hi.dialog", "Hello {name}!\n(Hi|Hey) {name}.\n")
    res = LocaleResources(str(locale))
    assert res.load_dialog("hi", "en-US") == ["Hello {name}!", "(Hi|Hey) {name}."]


# --- §4.3 slot-free roles ----------------------------------------------------

def test_load_entity_and_blacklist(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "weekday.entity", "monday\n(tues|wednes)day\n")
    _write(locale / "en-US" / "play.blacklist", "trailer\n")
    res = LocaleResources(str(locale))
    assert sorted(res.load_entity("weekday", "en-US")) == [
        "monday", "tuesday", "wednesday",
    ]
    assert res.load_blacklist("play", "en-US") == ["trailer"]


def test_slot_free_role_rejects_a_named_slot(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "bad.voc", "a slot {here}\n")
    res = LocaleResources(str(locale))
    with pytest.raises(MalformedResource):
        res.load_vocabulary("bad", "en-US")


# --- §2 layout ---------------------------------------------------------------

def test_subdirectories_are_searched_recursively(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "intents" / "deep.intent", "do the thing\n")
    res = LocaleResources(str(locale))
    assert res.load_intent("deep", "en-US") == ["do the thing"]


def test_language_tag_is_case_insensitive(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-us" / "x.intent", "hello world\n")
    res = LocaleResources(str(locale))
    assert res.load_intent("x", "en-US") == ["hello world"]


def test_underscore_tag_matches_hyphen_tag(tmp_path):
    """Tags are standardized before comparison, so en_US finds en-US."""
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "x.intent", "hello world\n")
    res = LocaleResources(str(locale))
    assert res.load_intent("x", "en_US") == ["hello world"]


def test_duplicate_resource_in_one_tree_is_malformed(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "a" / "dup.intent", "first\n")
    _write(locale / "en-US" / "b" / "dup.intent", "second\n")
    res = LocaleResources(str(locale))
    with pytest.raises(MalformedResource):
        res.load_intent("dup", "en-US")


# --- §2.1 resolution precedence ---------------------------------------------

def test_user_override_wins_over_skill(tmp_path):
    skill_locale = tmp_path / "skill" / "locale"
    user_locale = tmp_path / "user" / "locale"
    _write(skill_locale / "en-US" / "x.intent", "skill version\n")
    _write(user_locale / "en-US" / "x.intent", "user version\n")
    res = LocaleResources(str(skill_locale), user_locale=str(user_locale))
    assert res.load_intent("x", "en-US") == ["user version"]


# --- §5 empty files ----------------------------------------------------------

def test_empty_file_is_malformed(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "empty.intent", "# only a comment\n\n")
    res = LocaleResources(str(locale))
    with pytest.raises(MalformedResource):
        res.load_intent("empty", "en-US")


def test_missing_resource_raises(tmp_path):
    locale = tmp_path / "locale"
    locale.mkdir()
    res = LocaleResources(str(locale))
    with pytest.raises(FileNotFoundError):
        res.load_intent("nope", "en-US")


# --- §2.2 smart language fallback -------------------------------------------

def test_fallback_resolves_a_near_language(tmp_path):
    pytest.importorskip("langcodes")
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "x.intent", "hello world\n")
    res = LocaleResources(str(locale))
    assert res.load_intent("x", "en-AU") == ["hello world"]


def test_fallback_rejects_a_too_distant_language(tmp_path):
    pytest.importorskip("langcodes")
    locale = tmp_path / "locale"
    _write(locale / "fr-FR" / "x.intent", "bonjour\n")
    res = LocaleResources(str(locale))
    with pytest.raises(FileNotFoundError):
        res.load_intent("x", "en-US")


def test_fallback_disabled_with_zero_max_distance(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "x.intent", "hello\n")
    res = LocaleResources(str(locale), max_language_distance=0)
    with pytest.raises(FileNotFoundError):
        res.load_intent("x", "en-AU")


def test_fallback_resolved_per_query_not_once(tmp_path):
    """One instance: an exact tag and a fallback tag resolve independently."""
    pytest.importorskip("langcodes")
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "x.intent", "us text\n")
    res = LocaleResources(str(locale))
    assert res.load_intent("x", "en-US") == ["us text"]   # exact
    assert res.load_intent("x", "en-AU") == ["us text"]   # fallback


def test_custom_lang_resolver_is_honored(tmp_path):
    """A caller may inject its own language resolver."""
    locale = tmp_path / "locale"
    _write(locale / "en-GB" / "x.intent", "british\n")

    def resolver(target, available, max_distance):
        return "en-GB" if "en-GB" in available else None

    res = LocaleResources(str(locale), lang_resolver=resolver)
    assert res.load_intent("x", "zz-ZZ") == ["british"]
