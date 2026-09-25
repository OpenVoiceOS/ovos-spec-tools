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
                                       BARE_PIPE_ROLES, INPUT_DIRECTION_ROLES,
                                       MalformedTemplate)
from ovos_spec_tools.lint import ERROR, lint_locale
from ovos_spec_tools.resources import (LocaleResources, MalformedResource,
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
                # §3.6 states the rule in one bullet and is cited first; the
                # three-clause derivation stays as background
                self.assertIn("§3.6", reason)
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

    def test_the_expander_rejects_the_form_like_every_other_malformed_one(self):
        # §3.6: "a tool MUST reject any template that contains one". expand()
        # is the entry point every other consumer calls, and the eight other
        # bullets already raise from it, so this one does too.
        with self.assertRaises(MalformedTemplate) as caught:
            expand("plata|argent")
        self.assertIn("pipe outside a group", str(caught.exception))

    def test_every_malformed_form_raises_from_the_same_entry_point(self):
        # the sibling forms, asserted beside it: a bullet that raises only
        # from the linter is the hole this fix closes
        for template in ("plata|argent", "()", "{a}{b}", "{x}", "(|)",
                         "{x} and {x}", "<Greeting>", "a(b|c", "a)b|c"):
            with self.subTest(template=template):
                with self.assertRaises(MalformedTemplate):
                    expand(template)

    def test_a_well_formed_template_still_expands(self):
        # the control: a checker that raised on everything would pass the
        # test above without reading the template
        self.assertEqual(expand("a (b|c) d"), ["a b d", "a c d"])

    def test_the_roles_the_rule_applies_to(self):
        # INPUT_DIRECTION_ROLES stays the §2 fact it names
        self.assertEqual(INPUT_DIRECTION_ROLES,
                         (".intent", ".entity", ".voc", ".blacklist"))
        self.assertNotIn(".dialog", INPUT_DIRECTION_ROLES)
        # the bare-pipe rule reaches .dialog as well: OVOS-INTENT-2 §4.2 makes
        # its metacharacters structural, so a pipe there is not punctuation.
        # .prompt is a whole-file document under §4.4, not a template.
        self.assertIn(".dialog", BARE_PIPE_ROLES)
        self.assertNotIn(".prompt", BARE_PIPE_ROLES)
        for role in INPUT_DIRECTION_ROLES:
            self.assertIn(role, BARE_PIPE_ROLES)


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
    (lang / "greet.dialog").write_text("hello | hi there\nwelcome back\n")
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

    def test_a_dialog_pipe_is_skipped_too(self):
        # OVOS-INTENT-2 §4.2: a .dialog line is a template and its
        # metacharacters are structural, so the bare pipe is malformed there
        # as well. The bad line is skipped and the rest of the file loads.
        with tempfile.TemporaryDirectory() as tmp:
            loader = LocaleResources(str(_tree(tmp)))
            self.assertEqual(loader.load_dialog("greet", "en-US"),
                             ["welcome back"])

    def test_a_dialog_with_nothing_left_says_so(self):
        # skipping every phrase and returning [] would fail at render time,
        # far from the cause
        from ovos_spec_tools.resources import MalformedResource
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lang = root / "en-us"
            lang.mkdir(parents=True)
            (lang / "only.dialog").write_text("a|b\n")
            loader = LocaleResources(str(root))
            with self.assertRaises(MalformedResource) as caught:
                loader.load_dialog("only", "en-US")
        self.assertIn("§3.6", str(caught.exception))

    def test_a_clean_dialog_is_returned_whole(self):
        # the control for both dialog tests above
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lang = root / "en-us"
            lang.mkdir(parents=True)
            (lang / "ok.dialog").write_text("hello there\nwelcome back\n")
            loader = LocaleResources(str(root))
            self.assertEqual(loader.load_dialog("ok", "en-US"),
                             ["hello there", "welcome back"])


class TestNothingLeftAfterTheSkipRaisesForEveryRole(unittest.TestCase):
    """The skip empties a file: every ``BARE_PIPE_ROLES`` role rejects it.

    Round 2 gave ``load_dialog`` this rejection and left the expanded roles
    returning ``[]``. An empty file already raises under §5, "every file must
    contribute at least one template", and a file whose every line the skip
    removed ends in that same state, so the two cannot answer differently:
    a caller cannot tell an empty list from a file that legitimately has
    nothing to give, and the only trace would be a WARN line nobody reads at
    install time. §3.6 puts the duty to reject on the tool, and an empty list
    is not a rejection.

    The scenario the reviewer named: a skill ships ``confirm.voc`` whose every
    line reads ``yes|yeah``. The loader used to return ``[]``, nothing raised,
    and the intent that needs that vocabulary simply never matched.
    """

    #: one file per role whose every line carries a bare pipe, with the loader
    #: that reads it and the word its message uses
    ROLES = (("confirm", ".voc", "load_vocabulary", "template"),
             ("greet", ".intent", "load_intent", "template"),
             ("colour", ".entity", "load_entity", "template"),
             ("banned", ".blacklist", "load_blacklist", "template"),
             ("answer", ".dialog", "load_dialog", "phrase"))

    def _loader(self, tmp, base_name, extension, body):
        root = Path(tmp)
        lang = root / "en-us"
        lang.mkdir(parents=True, exist_ok=True)
        (lang / f"{base_name}{extension}").write_text(body, encoding="utf-8")
        return LocaleResources(str(root))

    def test_every_role_raises_when_the_skip_leaves_nothing(self):
        for base_name, extension, method, unit in self.ROLES:
            with self.subTest(role=extension):
                with tempfile.TemporaryDirectory() as tmp:
                    loader = self._loader(tmp, base_name, extension,
                                          "yes|yeah\nsure|ok\n")
                    with self.assertRaises(MalformedResource) as caught:
                        getattr(loader, method)(base_name, "en-US")
                message = str(caught.exception)
                self.assertIn("§3.6", message)
                self.assertIn(f"every {unit} in", message)
                self.assertIn(f"{base_name}{extension}", message)

    def test_the_message_is_the_one_the_empty_file_gets_pointed_at(self):
        """Both states raise the same class, and each says which rule it is.

        §5 for the file that was always empty, §3.6 for the file the skip
        emptied. Same exception, different sentence, so a reader of the error
        knows which fault to fix.
        """
        with tempfile.TemporaryDirectory() as tmp:
            loader = self._loader(tmp, "confirm", ".voc", "\n\n")
            with self.assertRaises(MalformedResource) as empty:
                loader.load_vocabulary("confirm", "en-US")
        with tempfile.TemporaryDirectory() as tmp:
            loader = self._loader(tmp, "confirm", ".voc", "yes|yeah\n")
            with self.assertRaises(MalformedResource) as skipped:
                loader.load_vocabulary("confirm", "en-US")
        self.assertIn("§5", str(empty.exception))
        self.assertIn("empty resource file", str(empty.exception))
        self.assertIn("§3.6", str(skipped.exception))
        self.assertNotIn("§5", str(skipped.exception))

    def test_one_good_line_is_enough_and_the_rest_is_still_skipped(self):
        """The control. The raise is for a file with NOTHING left, not for a
        file that holds one bad line: that one still loads, minus the line."""
        for base_name, extension, method, _unit in self.ROLES:
            with self.subTest(role=extension):
                with tempfile.TemporaryDirectory() as tmp:
                    loader = self._loader(tmp, base_name, extension,
                                          "yes|yeah\nplain words\n")
                    kept = getattr(loader, method)(base_name, "en-US")
                self.assertEqual(kept, ["plain words"])

    def test_a_role_outside_the_set_is_untouched(self):
        """The second control: the raise is reached through the skip alone.

        A role outside ``BARE_PIPE_ROLES`` takes no skip, so its file cannot be
        emptied this way. ``.prompt`` is deliberately out, being a whole-file
        document under OVOS-INTENT-2 §4.4, and it keeps its pipe.
        """
        with tempfile.TemporaryDirectory() as tmp:
            loader = self._loader(tmp, "ask", ".prompt", "yes|yeah\n")
            self.assertIn("yes|yeah", loader.load_prompt("ask", "en-US"))

    def test_the_two_roles_share_one_error(self):
        """The asymmetry this round closes, asserted rather than described.

        The expanded roles and ``.dialog`` reach the same sentence, so the file
        cannot drift back into saying one thing for one role and another for
        the rest.
        """
        messages = {}
        for base_name, extension, method, unit in self.ROLES:
            with tempfile.TemporaryDirectory() as tmp:
                loader = self._loader(tmp, base_name, extension, "a|b\n")
                with self.assertRaises(MalformedResource) as caught:
                    getattr(loader, method)(base_name, "en-US")
            messages[extension] = str(caught.exception).replace(
                f"every {unit} in", "every UNIT in").replace(
                f"{base_name}{extension}", "FILE")
        shapes = set(m.split("FILE", 1)[1] for m in messages.values())
        self.assertEqual(len(shapes), 1, messages)


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
            (lang / "greet.dialog").write_text(
                "hello | hi there\nwelcome back\n")
            (lang / "long.prompt").write_text("a | b, read as one document\n")
            findings = [f for f in lint_locale(root)
                        if "pipe outside a group" in f.message]

        self.assertEqual(len(findings), 3, [str(f) for f in findings])
        by_name = {Path(f.path).name: f for f in findings}
        self.assertEqual(by_name["colour.entity"].line, 4)
        self.assertEqual(by_name["start.intent"].line, 2)
        # the .dialog is among them now (OVOS-INTENT-2 §4.2)
        self.assertEqual(by_name["greet.dialog"].line, 1)
        for finding in findings:
            self.assertEqual(finding.severity, ERROR)
            self.assertIn("§3.6", finding.message)
        # the .prompt is not: §4.4 makes it a document, not a template
        self.assertNotIn("long.prompt", by_name)

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
