"""Tests for `iter_locale_dirs` — the canonical locale subdir walker."""
import pytest

from ovos_spec_tools import iter_locale_dirs


def _make_skill(tmp_path, *lang_dirs):
    """Create ``<tmp_path>/locale/<lang>/`` for each given lang."""
    for lang in lang_dirs:
        (tmp_path / "locale" / lang).mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_no_locale_dir_yields_nothing(tmp_path):
    assert list(iter_locale_dirs(tmp_path)) == []


def test_each_locale_subdir_is_yielded(tmp_path):
    root = _make_skill(tmp_path, "en-US", "pt-PT", "de-DE")
    langs = sorted(lang for lang, _ in iter_locale_dirs(root))
    assert langs == ["de-DE", "en-US", "pt-PT"]


def test_yields_subdir_path_as_second_item(tmp_path):
    root = _make_skill(tmp_path, "en-US")
    pairs = list(iter_locale_dirs(root))
    assert len(pairs) == 1
    lang, path = pairs[0]
    assert lang == "en-US"
    assert path == root / "locale" / "en-US"


def test_subdir_name_is_normalized(tmp_path):
    """``en_us/`` and ``EN-us/`` resolve to the same canonical tag."""
    root = _make_skill(tmp_path, "en_us")
    [(lang, _)] = list(iter_locale_dirs(root))
    assert lang.lower() == "en-us"


def test_files_in_locale_root_are_ignored(tmp_path):
    root = _make_skill(tmp_path, "en-US")
    (root / "locale" / "stray.txt").write_text("not a locale dir")
    langs = [lang for lang, _ in iter_locale_dirs(root)]
    assert langs == ["en-US"]


def test_native_filter_keeps_a_regional_subdir(tmp_path):
    """A skill that declares ``en`` as native still discovers ``en-US/``."""
    pytest.importorskip("langcodes")
    root = _make_skill(tmp_path, "en-US", "fr-FR")
    langs = sorted(lang for lang, _ in
                   iter_locale_dirs(root, native_langs=["en"]))
    assert langs == ["en-US"]


def test_native_filter_drops_unrelated_languages(tmp_path):
    pytest.importorskip("langcodes")
    root = _make_skill(tmp_path, "en-US", "fr-FR", "ja-JP")
    langs = sorted(lang for lang, _ in
                   iter_locale_dirs(root, native_langs=["en-GB", "fr"]))
    assert langs == ["en-US", "fr-FR"]


def test_native_filter_is_skipped_when_natives_none(tmp_path):
    """``native_langs=None`` (the default) yields every subdir, even ones
    no native would match — the caller asked for the full walk."""
    root = _make_skill(tmp_path, "en-US", "ja-JP")
    langs = sorted(lang for lang, _ in iter_locale_dirs(root))
    assert langs == ["en-US", "ja-JP"]
