"""iter_expand: lazy sample generation identical to expand()."""
import itertools
import time
import unittest

from ovos_spec_tools import MalformedTemplate, expand, iter_expand


class TestIterExpand(unittest.TestCase):
    def test_identical_output_and_order(self):
        for tmpl in ("(hi|hello) [dear] {name}",
                     "turn (on|off) the (light|lamp|fan) [please]",
                     "plain sentence {slot}"):
            self.assertEqual(list(iter_expand(tmpl)), expand(tmpl))

    def test_lazy_on_combinatorial_template(self):
        opts = "(" + "|".join(f"w{i}" for i in range(30)) + ")"
        tmpl = f"{opts} {opts} {opts} {opts} {opts} {opts}"  # 30^6 = 729M
        t0 = time.monotonic()
        first = list(itertools.islice(iter_expand(tmpl), 100))
        self.assertLess(time.monotonic() - t0, 2.0)
        self.assertEqual(len(first), 100)
        self.assertEqual(first[0], "w0 w0 w0 w0 w0 w0")

    def test_template_level_errors_raise_before_first_yield(self):
        with self.assertRaises(MalformedTemplate):
            next(iter_expand("{slot}"))
        with self.assertRaises(MalformedTemplate):
            next(iter_expand("broken (group"))

    def test_dedup_matches_expand(self):
        tmpl = "(a|a|b) thing"
        self.assertEqual(list(iter_expand(tmpl)), expand(tmpl))


if __name__ == "__main__":
    unittest.main()
