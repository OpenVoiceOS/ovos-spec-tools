"""Tests for :func:`ovos_spec_tools.find_lang_dir`."""
import os
import tempfile
import unittest
from pathlib import Path

from ovos_spec_tools import find_lang_dir


def _mkdirs(root, *names):
    for name in names:
        os.makedirs(os.path.join(root, name))


class TestFindLangDir(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="findlang_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_exact_uppercase_match(self):
        _mkdirs(self.root, "en-US", "de-DE")
        self.assertEqual(find_lang_dir(self.root, "en-US"),
                         Path(self.root) / "en-US")

    def test_exact_lowercase_match(self):
        _mkdirs(self.root, "en-us")
        self.assertEqual(find_lang_dir(self.root, "en-us"),
                         Path(self.root) / "en-us")

    def test_case_mismatch_resolves(self):
        """Request uppercase, dir is lowercase — closest_lang resolves
        through standardize_lang on both sides."""
        _mkdirs(self.root, "en-us")
        self.assertEqual(find_lang_dir(self.root, "en-US"),
                         Path(self.root) / "en-us")

    def test_subdialect_fallback(self):
        """Request en-AU, only en-US available — minor regional
        difference (langcodes distance ~4) is below the default max
        of 10."""
        _mkdirs(self.root, "en-US", "fr-FR")
        self.assertEqual(find_lang_dir(self.root, "en-AU"),
                         Path(self.root) / "en-US")

    def test_macro_fallback(self):
        """Request bare ``en``, en-US directory available — resolves."""
        _mkdirs(self.root, "en-US")
        self.assertEqual(find_lang_dir(self.root, "en"),
                         Path(self.root) / "en-US")

    def test_no_match_returns_none(self):
        _mkdirs(self.root, "pt-PT", "ja-JP")
        self.assertIsNone(find_lang_dir(self.root, "ko-KR"))

    def test_missing_base_path_returns_none(self):
        self.assertIsNone(
            find_lang_dir(os.path.join(self.root, "nope"), "en-US"))

    def test_max_distance_zero_requires_exact_normalized_match(self):
        """``max_distance=0`` disables smart fallback; only same-tag
        matches resolve."""
        _mkdirs(self.root, "en-US")
        self.assertEqual(
            find_lang_dir(self.root, "en-US", max_distance=0),
            Path(self.root) / "en-US")
        self.assertIsNone(
            find_lang_dir(self.root, "en-AU", max_distance=0))

    def test_custom_resolver_is_honoured(self):
        """A caller can swap the resolver — useful for tests or
        deployments that want a different fallback policy."""
        _mkdirs(self.root, "en-US", "de-DE")

        def _always_de(target, available, max_distance):
            return "de-DE" if "de-DE" in available else None

        self.assertEqual(
            find_lang_dir(self.root, "en-US", lang_resolver=_always_de),
            Path(self.root) / "de-DE")

    def test_ignores_non_directory_entries(self):
        """A regular file alongside lang dirs must not be considered a
        candidate."""
        _mkdirs(self.root, "en-US")
        Path(self.root, "stray.txt").write_text("noise")
        self.assertEqual(find_lang_dir(self.root, "en-US"),
                         Path(self.root) / "en-US")

    def test_accepts_path_or_str_base(self):
        _mkdirs(self.root, "en-US")
        self.assertEqual(find_lang_dir(Path(self.root), "en-US"),
                         Path(self.root) / "en-US")


if __name__ == "__main__":
    unittest.main()
