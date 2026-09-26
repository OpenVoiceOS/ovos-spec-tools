"""A pipe outside a group is malformed in an input-direction template.

Three clauses give the rule and no single clause states it, which is why
nothing applied it before.

OVOS-INTENT-1 §3.2:

    Parentheses enclose **branches** separated by the pipe `|`. A group's
    branches are its `|`-separated segments

OVOS-INTENT-1 §3.1:

    Any run of characters that is not a grammar token is literal text.

OVOS-INTENT-1 §2, on the input-direction templates `.intent`, `.entity`,
`.voc` and `.blacklist`:

    The grammar metacharacters `( ) [ ] { } | < >` **cannot occur as literal
    input**

OVOS-INTENT-1 §6.2, engine obligations, step 2:

    Verify the templates conform to §2-§3 (normalized form, valid tokens).

So `plata|argent` in an `.entity` is a malformed template a conformant
engine must reject, and the author means two lines or one group.

The loader reports it and skips the line rather than raising: a skill whose
locale holds one bad line must still load the rest of its resources.
"""
import logging
import tempfile
import unittest
from pathlib import Path

from ovos_spec_tools.expansion import (bare_pipe_reason, expand,
                                       INPUT_DIRECTION_ROLES)
from ovos_spec_tools.lint import ERROR, lint_locale
from ovos_spec_tools.resources import (LocaleResources,
                                       read_resource_file_numbered)


class TestTheVerifier(unittest.TestCase):

    def test_a_bare_pipe_is_named(self):
        for template in ("plata|argent",
                         "set the color to plata|argent",
                         "a|",
                         "(a)|b",                 # degenerate group, then bare
                         "set to <colors>|x"):    # after a vocabulary ref
            with self.subTest(template=template):
                reason = bare_pipe_reason(template)
                self.assertIsNotNone(reason, f"{template!r} not flagged")
                self.assertIn("§3.2", reason)

    def test_a_pipe_inside_a_group_is_grammar(self):
        # §3.2 inside (), and §3.3: "[x] is exactly equivalent to the
        # alternative group (x|)", so a pipe inside [] is grammar too
        for template in ("(plata|argent)",
                         "a (b|c) d",
                         "a [b|c] d",
                         "((a|b)|c)",
                         "plain words with no pipe"):
            with self.subTest(template=template):
                self.assertIsNone(bare_pipe_reason(template),
                                  f"{template!r} wrongly flagged")

    def test_a_pipe_in_a_name_is_left_to_the_name_rule(self):
        # §3.4 and §3.7 already reject these with a better message; reporting
        # the same fault twice would send the author to the wrong rule
        self.assertIsNone(bare_pipe_reason("{slot|x}"))
        self.assertIsNone(bare_pipe_reason("<voc|x>"))

    def test_the_expander_still_keeps_it_whole(self):
        # the verifier is a separate judgement, not a change to expansion:
        # §3.1 still makes the bare pipe literal text
        self.assertEqual(expand("plata|argent"), ["plata|argent"])

    def test_dialog_is_not_an_input_direction_role(self):
        self.assertEqual(INPUT_DIRECTION_ROLES,
                         (".intent", ".entity", ".voc", ".blacklist"))
        self.assertNotIn(".dialog", INPUT_DIRECTION_ROLES)


class TestTheNumberedReader(unittest.TestCase):

    def test_the_number_is_the_file_line_not_the_template_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "colour.entity"
            path.write_text("# a comment\n\nred\nplata|argent\ngreen\n")
            numbered = read_resource_file_numbered(path)
            self.assertEqual(numbered,
                             [(3, "red"), (4, "plata|argent"), (5, "green")])


def _tree(tmp: str) -> Path:
    root = Path(tmp)
    lang = root / "en-us"
    lang.mkdir(parents=True)
    (lang / "colour.entity").write_text(
        "# a comment\n\nred\nplata|argent\n(azul|blue)\ngreen\n")
    (lang / "greet.dialog").write_text("hello | hi there\n")
    return root


class TestTheLoaderWarnsAndSkips(unittest.TestCase):

    def test_the_bad_line_is_skipped_and_the_rest_still_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            loader = LocaleResources(str(_tree(tmp)))
            self.assertEqual(loader.load_entity("colour", "en-US"),
                             ["red", "azul", "blue", "green"])

    def test_the_warning_names_the_file_and_the_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(tmp)
            loader = LocaleResources(str(root))
            with self.assertLogs("ovos_spec_tools.resources",
                                 level=logging.WARNING) as caught:
                loader.load_entity("colour", "en-US")
        joined = "\n".join(caught.output)
        self.assertIn("colour.entity:4", joined)
        self.assertIn("plata|argent", joined)

    def test_a_clean_file_logs_nothing(self):
        # the control: a warning that fires on every load would make the test
        # above pass without the check doing any work
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lang = root / "en-us"
            lang.mkdir(parents=True)
            (lang / "colour.entity").write_text("red\n(azul|blue)\n")
            loader = LocaleResources(str(root))
            logger = logging.getLogger("ovos_spec_tools.resources")
            with self.assertLogs(logger, level=logging.WARNING) as caught:
                logger.warning("canary")  # assertLogs needs at least one record
                loader.load_entity("colour", "en-US")
            self.assertEqual([r for r in caught.output if "canary" not in r], [])

    def test_a_dialog_pipe_is_untouched(self):
        # output-direction: §2's normalized form does not apply, so a pipe in
        # a phrase meant for a person is ordinary punctuation
        with tempfile.TemporaryDirectory() as tmp:
            loader = LocaleResources(str(_tree(tmp)))
            self.assertEqual(loader.load_dialog("greet", "en-US"),
                             ["hello | hi there"])


class TestTheLinterReportsFileAndLine(unittest.TestCase):

    def test_an_entity_and_an_intent_are_both_flagged_with_their_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lang = root / "locale" / "en-us"
            lang.mkdir(parents=True)
            (lang / "colour.entity").write_text(
                "# c\n\nred\nplata|argent\n(azul|blue)\n")
            (lang / "start.intent").write_text(
                "begin the (thing|job)\nrun|start it\n")
            (lang / "greet.dialog").write_text("hello | hi there\n")
            findings = [f for f in lint_locale(root)
                        if "pipe outside a group" in f.message]

        self.assertEqual(len(findings), 2, [str(f) for f in findings])
        by_name = {Path(f.path).name: f for f in findings}
        self.assertEqual(by_name["colour.entity"].line, 4)
        self.assertEqual(by_name["start.intent"].line, 2)
        for finding in findings:
            self.assertEqual(finding.severity, ERROR)
            self.assertIn("§2", finding.message)
        # the .dialog is not among them
        self.assertNotIn("greet.dialog", by_name)

    def test_the_rendered_finding_carries_the_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lang = root / "locale" / "en-us"
            lang.mkdir(parents=True)
            (lang / "colour.entity").write_text("red\nplata|argent\n")
            rendered = [str(f) for f in lint_locale(root)
                        if "pipe outside a group" in f.message]
        self.assertEqual(len(rendered), 1)
        self.assertIn("colour.entity:2: error:", rendered[0])


if __name__ == "__main__":
    unittest.main()
