"""Tests for the language-tag utilities."""
import pytest

import ovos_spec_tools.language as language
from ovos_spec_tools import closest_lang, lang_distance, standardize_lang


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
