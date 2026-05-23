"""Tests for the language-tag utilities."""
import pytest

import ovos_spec_tools.language as language
from ovos_spec_tools import closest_lang, lang_distance, lang_matches, standardize_lang


# --- standardize_lang --------------------------------------------------------

def test_standardize_normalizes_underscores_and_case():
    assert standardize_lang("en_us").lower() == "en-us"


def test_standardize_keeps_tagalog_as_tl():
    """langcodes folds `tl` into `fil`; OVOS keeps it distinct."""
    assert standardize_lang("tl") == "tl"
    assert standardize_lang("tgl") == "tl"


# --- lang_distance -----------------------------------------------------------

def test_distance_is_zero_for_identical_tags():
    assert lang_distance("en-US", "en_us") == 0


def test_distance_is_large_for_different_languages():
    assert lang_distance("en-US", "fr-FR") >= 10


def test_distance_measures_a_bare_tag_from_its_norm_region():
    """`pt` is identical to `pt-PT` and merely regional to `pt-BR`."""
    assert lang_distance("pt", "pt-PT") == 0
    assert lang_distance("pt", "pt-BR") > 0


# --- closest_lang ------------------------------------------------------------

def test_closest_lang_exact_match():
    assert closest_lang("en-US", ["pt-BR", "en-US", "de-DE"]) == "en-US"


def test_closest_lang_exact_match_after_standardization():
    assert closest_lang("en_US", ["en-US"]) == "en-US"


def test_closest_lang_returns_the_original_string():
    """The returned value is the entry from `available`, verbatim."""
    assert closest_lang("EN-us", ["en-US"]) == "en-US"


def test_closest_lang_no_match_returns_none():
    assert closest_lang("zz-ZZ", ["en-US", "pt-BR"]) is None


def test_closest_lang_disabled_with_zero_distance():
    assert closest_lang("en-AU", ["en-US"], max_distance=0) is None


def test_closest_lang_regional_fallback():
    pytest.importorskip("langcodes")
    assert closest_lang("en-AU", ["pt-BR", "en-US"]) == "en-US"


def test_closest_lang_skips_a_distant_language():
    pytest.importorskip("langcodes")
    # fr-FR is a different language and beyond the distance cap; en-GB is near.
    assert closest_lang("en-AU", ["fr-FR", "en-GB"]) == "en-GB"


def test_closest_lang_prefers_the_norm_region_for_a_bare_tag():
    """langcodes makes bare `pt` closest to pt-BR; the norm region pt-PT wins."""
    assert closest_lang("pt", ["pt-BR", "pt-PT"]) == "pt-PT"
    assert closest_lang("pt", ["pt-PT", "pt-BR"]) == "pt-PT"  # order-independent


def test_explicit_region_is_respected_over_the_norm_preference():
    assert closest_lang("pt-BR", ["pt-PT", "pt-BR"]) == "pt-BR"


def test_bare_tag_falls_back_when_norm_region_absent():
    pytest.importorskip("langcodes")
    assert closest_lang("pt", ["pt-BR"]) == "pt-BR"


# --- the langcodes-absent path ----------------------------------------------

def test_distance_without_langcodes_shares_primary_subtag(monkeypatch):
    """With no langcodes distance, a shared primary subtag still resolves."""
    monkeypatch.setattr(language, "_langcodes_distance", lambda a, b: None)
    assert closest_lang("en-AU", ["pt-BR", "en-GB", "fr-FR"]) == "en-GB"


def test_distance_without_langcodes_prefers_the_generic_tag(monkeypatch):
    monkeypatch.setattr(language, "_langcodes_distance", lambda a, b: None)
    assert closest_lang("en-AU", ["en-US", "en", "en-GB"]) == "en"


def test_distance_without_langcodes_no_shared_subtag(monkeypatch):
    monkeypatch.setattr(language, "_langcodes_distance", lambda a, b: None)
    assert closest_lang("en-AU", ["pt-BR", "fr-FR"]) is None


# --- edge cases --------------------------------------------------------------

def test_closest_lang_empty_available_is_none():
    assert closest_lang("en-US", []) is None


def test_standardize_lang_empty_string():
    assert standardize_lang("") == ""


def test_lang_distance_is_symmetric_enough_for_identity():
    assert lang_distance("en-US", "en-US") == 0
    assert lang_distance("EN_us", "en-US") == 0


def test_lang_distance_regional_versus_different_language():
    pytest.importorskip("langcodes")
    assert lang_distance("de-DE", "de-AT") < 10    # a usable regional match
    assert lang_distance("de-DE", "nl-NL") >= 10   # a different language


def test_closest_lang_regioned_request_falls_back_to_a_sibling(tmp_path):
    pytest.importorskip("langcodes")
    assert closest_lang("pt-MZ", ["en-US", "pt-BR"]) == "pt-BR"


# --- lang_matches ------------------------------------------------------------

def test_lang_matches_identical_tags():
    assert lang_matches("en-US", "en_us") is True


def test_lang_matches_different_languages():
    pytest.importorskip("langcodes")
    assert lang_matches("en-US", "fr-FR") is False


def test_lang_matches_regional_sibling_within_default_threshold():
    pytest.importorskip("langcodes")
    assert lang_matches("de-DE", "de-AT") is True


def test_lang_matches_exact_only_when_max_distance_zero():
    from ovos_spec_tools import lang_matches as lm
    assert lm("en-US", "en-US", max_distance=0) is True
    assert lm("en-US", "en-GB", max_distance=0) is False
