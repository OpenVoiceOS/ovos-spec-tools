"""A locale tree rewritten at the same path is read again.

``voc_match`` shares one ``LocaleResources`` per installed locale tree
(#152), which is what keeps a per-utterance caller off a full re-expansion.
``LocaleResources`` snapshots a skill or core tree at construction and never
re-reads the disk, so a cache keyed on the path alone serves the old
vocabulary for the life of the process: a reinstall, a skill update or a
translation edit is invisible until restart.

The key therefore carries a fingerprint of the tree. These tests drive the
four ways a tree changes, and the one way it does not.
"""
import os
import pathlib
import tempfile
import time
import unittest

from ovos_spec_tools import voc_match
from ovos_spec_tools.intent import _static_locale_resources, _tree_fingerprint


def _tree(files):
    root = tempfile.mkdtemp(prefix="t4046-")
    loc = pathlib.Path(root) / "en-us"
    loc.mkdir(parents=True)
    for name, text in files.items():
        (loc / name).write_text(text, encoding="utf-8")
    return root, loc


class TestARewrittenTreeIsReadAgain(unittest.TestCase):

    def setUp(self):
        _static_locale_resources.cache_clear()

    def test_a_voc_file_rewritten_in_place_takes_effect(self):
        root, loc = _tree({"yes.voc": "yes\nyeah\n"})
        self.assertTrue(voc_match("yes", "yes", "en-us", locale=root))

        time.sleep(0.01)
        (loc / "yes.voc").write_text("nope\n", encoding="utf-8")

        self.assertFalse(
            voc_match("yes", "yes", "en-us", locale=root),
            "the old vocabulary is still being served")
        self.assertTrue(voc_match("nope", "yes", "en-us", locale=root))

    def test_a_new_file_takes_effect(self):
        root, loc = _tree({"yes.voc": "yes\n"})
        self.assertFalse(voc_match("maybe", "later", "en-us", locale=root))

        time.sleep(0.01)
        (loc / "later.voc").write_text("maybe\n", encoding="utf-8")

        self.assertTrue(voc_match("maybe", "later", "en-us", locale=root))

    def test_a_deleted_file_takes_effect(self):
        """The deleted file is NOT the newest, so the newest mtime is
        unchanged by the delete. The file count is what catches it."""
        root, loc = _tree({"yes.voc": "yes\n"})
        time.sleep(0.01)
        (loc / "later.voc").write_text("maybe\n", encoding="utf-8")
        self.assertTrue(voc_match("yes", "yes", "en-us", locale=root))

        newest_before = _tree_fingerprint(root)[2]
        os.remove(loc / "yes.voc")
        self.assertEqual(_tree_fingerprint(root)[2], newest_before,
                         "this test is not driving the count branch")

        self.assertFalse(voc_match("yes", "yes", "en-us", locale=root))


class TestTheFingerprintItself(unittest.TestCase):

    def test_the_directory_mtime_alone_would_not_be_enough(self):
        """The negative result the fingerprint exists for.

        Rewriting a file in place does not change the mtime of the directory
        that holds it, so a cache keyed on the directory's own mtime would
        still serve the old vocabulary.
        """
        root, loc = _tree({"yes.voc": "yes\n"})
        dir_mtime_before = os.stat(loc).st_mtime_ns

        time.sleep(0.01)
        (loc / "yes.voc").write_text("nope\n", encoding="utf-8")

        self.assertEqual(os.stat(loc).st_mtime_ns, dir_mtime_before,
                         "the directory mtime moved; this platform would "
                         "not show the trap")
        # and the fingerprint does move for the same edit
        self.assertTrue(voc_match("nope", "yes", "en-us", locale=root))

    def test_the_fingerprint_moves_for_each_kind_of_change(self):
        root, loc = _tree({"yes.voc": "yes\n"})
        start = _tree_fingerprint(root)

        time.sleep(0.01)
        (loc / "yes.voc").write_text("nope\n", encoding="utf-8")
        rewritten = _tree_fingerprint(root)
        self.assertNotEqual(rewritten, start, "a rewrite must move it")

        (loc / "extra.voc").write_text("x\n", encoding="utf-8")
        added = _tree_fingerprint(root)
        self.assertNotEqual(added, rewritten, "an added file must move it")

        os.remove(loc / "yes.voc")
        removed = _tree_fingerprint(root)
        self.assertNotEqual(removed, added, "a deleted file must move it")

    def test_an_unchanged_tree_keeps_its_key(self):
        """The control. If the fingerprint moved on its own, the cache
        would never hit and #152's whole point would be gone."""
        root, _loc = _tree({"yes.voc": "yes\n"})
        first = _tree_fingerprint(root)
        for _ in range(5):
            self.assertEqual(_tree_fingerprint(root), first)

        _static_locale_resources.cache_clear()
        voc_match("yes", "yes", "en-us", locale=root)
        size_after_first = _static_locale_resources.cache_info().currsize
        for _ in range(10):
            voc_match("yes", "yes", "en-us", locale=root)
        self.assertEqual(
            _static_locale_resources.cache_info().currsize, size_after_first,
            "an unchanged tree minted a new cache entry per call")
        self.assertGreater(_static_locale_resources.cache_info().hits, 0)


if __name__ == "__main__":
    unittest.main()
