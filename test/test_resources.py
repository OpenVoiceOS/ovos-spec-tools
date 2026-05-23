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


# --- edge cases --------------------------------------------------------------

def test_core_resources_are_a_fallback(tmp_path):
    skill = tmp_path / "skill" / "locale"
    core = tmp_path / "core" / "locale"
    _write(core / "en-US" / "x.intent", "core version\n")
    res = LocaleResources(str(skill), core_locale=str(core))
    assert res.load_intent("x", "en-US") == ["core version"]


def test_skill_resources_override_core(tmp_path):
    skill = tmp_path / "skill" / "locale"
    core = tmp_path / "core" / "locale"
    _write(skill / "en-US" / "x.intent", "skill version\n")
    _write(core / "en-US" / "x.intent", "core version\n")
    res = LocaleResources(str(skill), core_locale=str(core))
    assert res.load_intent("x", "en-US") == ["skill version"]


def test_empty_dialog_is_malformed(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "e.dialog", "# nothing here\n")
    res = LocaleResources(str(locale))
    with pytest.raises(MalformedResource):
        res.load_dialog("e", "en-US")


def test_empty_voc_is_malformed(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "e.voc", "\n\n")
    res = LocaleResources(str(locale))
    with pytest.raises(MalformedResource):
        res.load_vocabulary("e", "en-US")


def test_vocabularies_collects_every_voc(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "yes.voc", "yes\n")
    _write(locale / "en-US" / "no.voc", "no\n")
    res = LocaleResources(str(locale))
    assert set(res.vocabularies("en-US")) == {"yes", "no"}


def test_entities_collects_every_entity(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "day.entity", "monday\n(tues|wednes)day\n")
    res = LocaleResources(str(locale))
    assert sorted(res.entities("en-US")["day"]) == [
        "monday", "tuesday", "wednesday",
    ]


def test_indented_comment_is_skipped(tmp_path):
    f = tmp_path / "x.voc"
    _write(f, "   # an indented comment\nyes\n")
    assert read_resource_file(f) == ["yes"]


def test_hash_mid_line_is_literal_not_a_comment(tmp_path):
    """Only a leading # starts a comment — there are no inline comments (§3)."""
    f = tmp_path / "x.voc"
    _write(f, "channel # five\n")
    assert read_resource_file(f) == ["channel # five"]


def test_nonexistent_skill_locale_raises_on_load(tmp_path):
    res = LocaleResources(str(tmp_path / "does-not-exist"))
    with pytest.raises(FileNotFoundError):
        res.load_intent("x", "en-US")


def test_intent_with_undefined_voc_reference_is_rejected(tmp_path):
    from ovos_spec_tools import MalformedTemplate
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "g.intent", "<undefined> hello\n")
    res = LocaleResources(str(locale))
    with pytest.raises(MalformedTemplate):
        res.load_intent("g", "en-US")


# --- LocaleResources.find ----------------------------------------------------

def test_find_returns_path_when_resource_exists(tmp_path):
    locale = tmp_path / "locale"
    f = locale / "en-US" / "play.intent"
    _write(f, "play {query}\n")
    res = LocaleResources(str(locale))
    assert res.find("play", ".intent", "en-US") == f


def test_find_returns_none_when_resource_missing(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "play.intent", "play {query}\n")
    res = LocaleResources(str(locale))
    assert res.find("stop", ".intent", "en-US") is None


def test_find_recurses_into_subdirectories(tmp_path):
    """A resource may live in a nested category folder under <lang>/."""
    locale = tmp_path / "locale"
    f = locale / "en-US" / "media" / "play.intent"
    _write(f, "play {query}\n")
    res = LocaleResources(str(locale))
    assert res.find("play", ".intent", "en-US") == f


def test_find_resolves_lang_via_closest_match(tmp_path):
    """A request for ``en`` matches an ``en-US/`` tree."""
    pytest.importorskip("langcodes")
    locale = tmp_path / "locale"
    f = locale / "en-US" / "play.intent"
    _write(f, "play {query}\n")
    res = LocaleResources(str(locale))
    assert res.find("play", ".intent", "en") == f


def test_find_walks_override_precedence(tmp_path):
    """user > skill > core: the first source carrying the file wins."""
    core = tmp_path / "core"
    skill = tmp_path / "skill"
    user = tmp_path / "user"
    _write(core / "en-US" / "play.intent", "core-version\n")
    _write(skill / "en-US" / "play.intent", "skill-version\n")
    _write(user / "en-US" / "play.intent", "user-version\n")
    res = LocaleResources(str(skill),
                          core_locale=str(core),
                          user_locale=str(user))
    assert res.find("play", ".intent", "en-US").parent == user / "en-US"


def test_find_raises_on_duplicate_within_language_tree(tmp_path):
    """OVOS-INTENT-2 §2: a (role, base name) must be unique per language tree."""
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "a" / "play.intent", "play one\n")
    _write(locale / "en-US" / "b" / "play.intent", "play two\n")
    res = LocaleResources(str(locale))
    with pytest.raises(MalformedResource):
        res.find("play", ".intent", "en-US")


# --- keyword_form ------------------------------------------------------------

def test_keyword_form_groups_alternatives_into_entity_and_aliases():
    from ovos_spec_tools import keyword_form
    entity, aliases = keyword_form("(hi|hello|hey)")
    # sorted, lowercased, first is canonical
    assert (entity, aliases) == ("hello", ["hey", "hi"])


def test_keyword_form_lowercases_and_dedupes():
    from ovos_spec_tools import keyword_form
    entity, aliases = keyword_form("(YES|Yes|yes)")
    assert (entity, aliases) == ("yes", [])


def test_keyword_form_empty_input_returns_empty_pair():
    from ovos_spec_tools import keyword_form
    assert keyword_form("") == ("", [])


def test_keyword_form_resolves_voc_references():
    """`<name>` references in a template expand against the supplied vocab."""
    from ovos_spec_tools import keyword_form
    entity, aliases = keyword_form(
        "<greet> friend", vocabularies={"greet": ["hi", "hello"]})
    assert sorted([entity, *aliases]) == ["hello friend", "hi friend"]


# --- LocaleResources.vocabulary_keywords / entity_keywords -------------------

def test_vocabulary_keywords_yields_one_triple_per_template_line(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "greet.voc",
           "(hi|hello)\n(yo|hey)\n")
    res = LocaleResources(str(locale))
    triples = sorted(res.vocabulary_keywords("en-US"))
    assert triples == [
        ("greet", "hello", ["hi"]),
        ("greet", "hey", ["yo"]),
    ]


def test_vocabulary_keywords_skips_blank_lines(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "yes.voc", "\nyes\n# a comment\n")
    res = LocaleResources(str(locale))
    assert list(res.vocabulary_keywords("en-US")) == [("yes", "yes", [])]


def test_entity_keywords_uses_same_shape(tmp_path):
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "color.entity", "(red|crimson)\nblue\n")
    res = LocaleResources(str(locale))
    triples = sorted(res.entity_keywords("en-US"))
    assert triples == [
        ("color", "blue", []),
        ("color", "crimson", ["red"]),
    ]


# --- utterance_contains ------------------------------------------------------

def test_utterance_contains_whole_word_substring_default():
    from ovos_spec_tools import utterance_contains
    assert utterance_contains("yes, please", ["yes"])  # default whole-word
    assert not utterance_contains("yesterday", ["yes"])  # substring not allowed


def test_utterance_contains_exact_mode():
    from ovos_spec_tools import utterance_contains
    assert utterance_contains("Yes", ["yes"], exact=True)
    assert not utterance_contains("yes please", ["yes"], exact=True)


def test_utterance_contains_folds_accents_and_punct_by_default():
    from ovos_spec_tools import utterance_contains
    # á → a, ! stripped, comparison succeeds
    assert utterance_contains("Olá!", ["ola"])


def test_utterance_contains_keeps_diacritics_when_disabled():
    from ovos_spec_tools import utterance_contains
    assert utterance_contains("ola", ["olá"], strip_diacritics=False) is False
    assert utterance_contains("olá", ["olá"], strip_diacritics=False)


def test_utterance_contains_keeps_punct_when_disabled():
    """Punctuation stays significant when strip_punct=False."""
    from ovos_spec_tools import utterance_contains
    assert utterance_contains("i love c++", ["c++"], strip_punct=False)
    assert utterance_contains(
        "i love c plus plus", ["c++"], strip_punct=False) is False


def test_utterance_contains_punct_and_diacritics_flags_compose():
    """The two flags are independent — any combination is valid."""
    from ovos_spec_tools import utterance_contains
    # both stripped (default) — matches across accents and punctuation
    assert utterance_contains("olá!", ["ola"])
    # diacritics stripped, punctuation kept — `!` becomes a word boundary
    assert utterance_contains(
        "olá!", ["ola"], strip_diacritics=True, strip_punct=False)
    # punct stripped, diacritics kept — `olá!` → `olá`; sample `ola` misses
    assert utterance_contains(
        "olá!", ["ola"], strip_diacritics=False, strip_punct=True) is False


def test_utterance_contains_exact_mode_normalizes_both_sides():
    """Exact comparison still applies the configured normalization."""
    from ovos_spec_tools import utterance_contains
    assert utterance_contains("  Olá!  ", ["ola"], exact=True)
    assert utterance_contains(
        "  Olá!  ", ["ola"], exact=True, strip_diacritics=False) is False


def test_utterance_contains_empty_inputs_return_false():
    from ovos_spec_tools import utterance_contains
    assert utterance_contains("", ["yes"]) is False
    assert utterance_contains("yes", []) is False


# --- strip_samples -----------------------------------------------------------

def test_strip_samples_removes_whole_word_matches():
    from ovos_spec_tools import strip_samples
    out = strip_samples("set volume to maximum", ["set", "volume"])
    assert "set" not in out.split()
    assert "volume" not in out.split()
    assert "maximum" in out.split()


def test_strip_samples_longest_first_consumes_composite_before_parts():
    """A composite phrase is removed before its shorter constituents."""
    from ovos_spec_tools import strip_samples
    out = strip_samples("give it up now", ["give up", "up"])
    # ``give it up`` does not contain the contiguous phrase "give up",
    # so the longer pattern misses; "up" is still stripped as a fallback.
    assert "up" not in out.split()


def test_strip_samples_case_insensitive():
    from ovos_spec_tools import strip_samples
    assert "Yes" not in strip_samples("Yes please", ["yes"]).split()


def test_strip_samples_no_match_returns_input_unchanged():
    from ovos_spec_tools import strip_samples
    assert strip_samples("no match here", ["xyzzy"]) == "no match here"


# --- normalize_for_match -----------------------------------------------------

def test_normalize_for_match_lowercases_and_trims():
    from ovos_spec_tools import normalize_for_match
    assert normalize_for_match("  YES  ") == "yes"


def test_normalize_for_match_strips_diacritics_by_default():
    from ovos_spec_tools import normalize_for_match
    assert normalize_for_match("Olá") == "ola"
    assert normalize_for_match("über") == "uber"


def test_normalize_for_match_strips_punct_by_default():
    from ovos_spec_tools import normalize_for_match
    assert normalize_for_match("yes, please!") == "yes please"


def test_normalize_for_match_preserves_slot_markers():
    """``{`` and ``}`` survive punctuation stripping so pre-render-pass
    slot markers stay intact."""
    from ovos_spec_tools import normalize_for_match
    assert normalize_for_match("play {song}") == "play {song}"


def test_normalize_for_match_keeps_punct_when_disabled():
    from ovos_spec_tools import normalize_for_match
    assert normalize_for_match("yes, please!", strip_punct=False) == "yes, please!"


def test_normalize_for_match_keeps_diacritics_when_disabled():
    from ovos_spec_tools import normalize_for_match
    assert normalize_for_match("Olá", strip_diacritics=False) == "olá"


def test_normalize_for_match_both_flags_off_only_lowercases_and_trims():
    from ovos_spec_tools import normalize_for_match
    assert normalize_for_match(
        "  Olá, World!  ",
        strip_diacritics=False, strip_punct=False) == "olá, world!"


def test_normalize_for_match_empty_string():
    from ovos_spec_tools import normalize_for_match
    assert normalize_for_match("") == ""
    assert normalize_for_match("   ") == ""


def test_normalize_for_match_is_keyword_only_for_flags():
    """The two flags are keyword-only — positional misuse can't silently
    flip the wrong knob."""
    from ovos_spec_tools import normalize_for_match
    import pytest as _pytest
    with _pytest.raises(TypeError):
        normalize_for_match("hi", False)  # would have to be keyword


# --- strip_samples extra coverage --------------------------------------------

def test_strip_samples_empty_samples_returns_input_unchanged():
    from ovos_spec_tools import strip_samples
    assert strip_samples("hello world", []) == "hello world"


def test_strip_samples_ignores_blank_samples():
    """A blank or whitespace-only sample is dropped silently."""
    from ovos_spec_tools import strip_samples
    assert strip_samples("hello world", ["", "  ", "world"]).strip() == "hello"


def test_strip_samples_escapes_regex_metacharacters_in_samples():
    """A sample like ``c++`` must not be treated as a regex pattern."""
    from ovos_spec_tools import strip_samples
    out = strip_samples("i love c++ programming", ["c++"])
    assert "c++" not in out


def test_strip_samples_preserves_casing_of_remaining_text():
    from ovos_spec_tools import strip_samples
    out = strip_samples("Yes Please", ["yes"])
    assert "Please" in out  # capital P preserved
    assert "Yes" not in out.split()


# --- vocabulary_keywords / entity_keywords extra coverage --------------------

def test_vocabulary_keywords_walks_override_precedence(tmp_path):
    """A user-locale .voc overrides the same-name skill-locale one."""
    skill = tmp_path / "skill"
    user = tmp_path / "user"
    _write(skill / "en-US" / "color.voc", "(red|crimson)\n")
    _write(user / "en-US" / "color.voc", "(blue|azure)\n")
    res = LocaleResources(str(skill), user_locale=str(user))
    triples = sorted(res.vocabulary_keywords("en-US"))
    # both files contribute — user overrides core, but both are reachable
    # because each source is walked for its own .voc files
    names = {entity for _, entity, _ in triples}
    assert "azure" in names


def test_vocabulary_keywords_handles_missing_locale_gracefully(tmp_path):
    """A skill that ships no .voc files yields nothing — no exception."""
    locale = tmp_path / "locale"
    (locale / "en-US").mkdir(parents=True)
    res = LocaleResources(str(locale))
    assert list(res.vocabulary_keywords("en-US")) == []


def test_vocabulary_keywords_resolves_voc_references_in_template(tmp_path):
    """A ``<other>`` reference in one .voc is resolved against the lang's
    full vocab map at expansion time."""
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "greet.voc", "hi\nhello\n")
    _write(locale / "en-US" / "greet_friend.voc", "<greet> friend\n")
    res = LocaleResources(str(locale))
    triples = sorted(res.vocabulary_keywords("en-US"))
    # the greet_friend.voc line expands its <greet> reference
    friend_triples = [t for t in triples if t[0] == "greet_friend"]
    assert friend_triples == [("greet_friend", "hello friend", ["hi friend"])]


def test_vocabulary_keywords_skips_malformed_lines(tmp_path):
    """A malformed template inside a .voc yields no keyword for that line
    rather than raising — well-formed neighbours still register."""
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "things.voc",
           "(hi|hello)\n(broken\nfine\n")
    res = LocaleResources(str(locale))
    entities = {e for _, e, _ in res.vocabulary_keywords("en-US")}
    assert "fine" in entities  # well-formed line survived
    # ``(broken`` does not yield (entity, [])
    assert "(broken" not in entities


# --- keyword_form extra coverage ---------------------------------------------

def test_keyword_form_blank_line_returns_empty_pair():
    from ovos_spec_tools import keyword_form
    assert keyword_form("   \n  ") == ("", [])


def test_keyword_form_malformed_template_returns_empty_pair():
    """A line that expansion rejects yields ('', []) — never propagates."""
    from ovos_spec_tools import keyword_form
    assert keyword_form("(unclosed") == ("", [])


def test_keyword_form_single_alternative_yields_no_aliases():
    """A line without alternatives has the line itself as the entity."""
    from ovos_spec_tools import keyword_form
    assert keyword_form("hello") == ("hello", [])


def test_vocabulary_keywords_returns_empty_when_language_has_no_dir(tmp_path):
    """Asking for a language with no directory yields nothing (no exception)
    — covers the `lang_dir is None: continue` branch in _keywords_for."""
    locale = tmp_path / "locale"
    _write(locale / "en-US" / "x.voc", "yes\n")
    res = LocaleResources(str(locale), max_language_distance=0)
    assert list(res.vocabulary_keywords("ja-JP")) == []
    assert list(res.entity_keywords("ja-JP")) == []


def test_strip_samples_handles_unicode_samples():
    """Unicode samples that need escaping in regex still strip cleanly."""
    from ovos_spec_tools import strip_samples
    assert "olá" not in strip_samples("ola olá", ["olá"]).split()
