"""Tests for :mod:`ovos_spec_tools.datasets`."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from ovos_spec_tools.datasets import (
    SUPPORTED_DATASETS,
    expand_hf_template,
    export_to_locale,
    inline_keywords,
    load_dataset_templates,
    _normalize_rows,
    _resolve_config,
    _strip_domain,
)

# ---------------------------------------------------------------------------
# _resolve_config
# ---------------------------------------------------------------------------


class TestResolveConfig:
    def test_hassil_intents_plain_lang(self):
        assert _resolve_config("hassil-intents", "en") == "en"
        assert _resolve_config("hassil-intents", "pt_BR") == "pt_BR"

    def test_intents_for_eval_appends_templates(self):
        assert _resolve_config("intents-for-eval", "en-US") == "en-US-templates"

    def test_intents_for_eval_passthrough(self):
        assert _resolve_config("intents-for-eval", "en-US-templates") == "en-US-templates"

    def test_massive_templates_appends_templates(self):
        assert _resolve_config("massive-templates", "pt-PT") == "pt-PT-templates"


# ---------------------------------------------------------------------------
# _strip_domain
# ---------------------------------------------------------------------------


class TestStripDomain:
    def test_with_domain(self):
        assert _strip_domain("homeassistant:hass_turn_on") == "hass_turn_on"

    def test_without_domain(self):
        assert _strip_domain("hass_turn_on") == "hass_turn_on"

    def test_multiple_colons(self):
        assert _strip_domain("a:b:c") == "b:c"


# ---------------------------------------------------------------------------
# _normalize_rows
# ---------------------------------------------------------------------------


class TestNormalizeRows:
    def test_hassil_intents_style(self):
        rows = [
            {
                "intent_id": "homeassistant:hass_turn_on",
                "domain": "homeassistant",
                "template": "<turn_on> {name}",
                "slots": [{"name": "name", "examples": ["light"]}],
                "expansions": [{"keyword": "turn_on", "values": ["turn on"]}],
            }
        ]
        out = _normalize_rows(rows, "hassil-intents")
        assert out[0]["intent_id"] == "homeassistant:hass_turn_on"
        assert out[0]["expansions"] == [{"keyword": "turn_on", "values": ["turn on"]}]

    def test_massive_style_fallback(self):
        rows = [
            {
                "intent": "hass_turn_on",
                "template": "(turn on|switch on) {name}",
                "slots": [{"name": "name", "examples": ["light"]}],
                "text": "turn on the light",
            }
        ]
        out = _normalize_rows(rows, "massive-templates")
        assert out[0]["intent_id"] == "hass_turn_on"
        assert "expansions" not in out[0]
        assert out[0]["text"] == "turn on the light"


# ---------------------------------------------------------------------------
# expand_hf_template
# ---------------------------------------------------------------------------


class TestExpandHfTemplate:
    def test_with_expansions(self):
        tpl = "<turn_on> [the] {name}"
        exps = [{"keyword": "turn_on", "values": ["turn on", "switch on"]}]
        results = expand_hf_template(tpl, exps, max_samples=100)
        assert "turn on the {name}" in results
        assert "turn on {name}" in results
        assert "switch on the {name}" in results
        assert len(results) == 4

    def test_without_expansions_inline(self):
        tpl = "(turn on|switch on) [the] {name}"
        results = expand_hf_template(tpl, max_samples=100)
        assert results == [
            "turn on the {name}",
            "switch on the {name}",
            "turn on {name}",
            "switch on {name}",
        ]

    def test_max_samples_cap(self):
        tpl = "(a|b|c|d|e) (1|2|3|4|5) (x|y|z)"
        results = expand_hf_template(tpl, max_samples=5)
        assert len(results) == 5

    def test_no_grammar_passthrough(self):
        tpl = "hello world"
        results = expand_hf_template(tpl)
        assert results == ["hello world"]


# ---------------------------------------------------------------------------
# export_to_locale
# ---------------------------------------------------------------------------


class TestExportToLocale:
    def test_exports_structure(self):
        """Verify that export creates .intent / .voc / .entity files."""
        mock_rows = [
            {
                "intent_id": "test:greet",
                "template": "<hello> {name}",
                "slots": [{"name": "name", "examples": ["Alice", "Bob"]}],
                "expansions": [{"keyword": "hello", "values": ["hi", "hey"]}],
            },
            {
                "intent_id": "test:greet",
                "template": "<greet> [there] {name}",
                "slots": [],
                "expansions": [{"keyword": "greet", "values": ["hello", "good day"]}],
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp)

            with patch(
                "ovos_spec_tools.datasets.load_dataset_templates",
                return_value=mock_rows,
            ):
                count = export_to_locale("hassil-intents", "en", dst)

            locale_en = dst / "locale" / "en"
            assert count == 2
            assert (locale_en / "greet.intent").exists()
            assert (locale_en / "hello.voc").exists()
            assert (locale_en / "greet.voc").exists()
            assert (locale_en / "name.entity").exists()

            lines = (locale_en / "name.entity").read_text().splitlines()
            assert "Alice" in lines
            assert "Bob" in lines

    def test_round_trip_small(self):
        """Load a single row, export, verify the intent file has the template."""
        rows = load_dataset_templates("hassil-intents", lang="en", streaming=False)
        # Only keep first 3 rows to make it fast
        first = [rows[0], rows[1]]

        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp)
            with patch(
                "ovos_spec_tools.datasets.load_dataset_templates",
                return_value=first,
            ):
                count = export_to_locale("hassil-intents", "en", dst)
            assert count == 2

            # Check that first intent file has rows[0] template
            name = rows[0]["intent_id"].split(":")[-1]
            intent_path = dst / "locale" / "en" / f"{name}.intent"
            assert intent_path.exists()
            assert rows[0]["template"] in intent_path.read_text()


# ---------------------------------------------------------------------------
# inline_keywords
# ---------------------------------------------------------------------------


class TestInlineKeywords:
    def test_basic_inlining(self):
        tpl = "<turn_on> [the] {name}"
        exps = [{"keyword": "turn_on", "values": ["turn on", "switch on"]}]
        assert inline_keywords(tpl, exps) == "(turn on|switch on) [the] {name}"

    def test_nested_refs(self):
        tpl = "<broadcast> <everywhere>"
        exps = [
            {"keyword": "broadcast", "values": ["<a>ذع", "بلغ"]},
            {"keyword": "a", "values": ["آ", "أ"]},
            {"keyword": "everywhere", "values": ["كل مكان"]},
        ]
        result = inline_keywords(tpl, exps)
        assert "(آ|أ)ذع" in result or "(أ|آ)ذع" in result
        assert "بلغ" in result
        assert "كل مكان" in result

    def test_unresolvable_keyword(self):
        tpl = "<nope> lights"
        result = inline_keywords(tpl)
        assert result == "<nope> lights"  # no vocab → no change

    def test_flat_vocab(self):
        tpl = "<greet> world"
        result = inline_keywords(tpl, flat_vocab={"greet": ["hi", "hello"]})
        assert result == "(hi|hello) world"

    def test_max_values_cap(self):
        tpl = "<x>"
        exps = [{"keyword": "x", "values": [str(i) for i in range(20)]}]
        result = inline_keywords(tpl, exps, max_values=5)
        assert "|".join(str(i) for i in range(5)) in result
        assert "10" not in result

    def test_no_keyword_refs(self):
        tpl = "hello world"
        assert inline_keywords(tpl) == "hello world"

    def test_empty_expansions(self):
        tpl = "<x>"
        assert inline_keywords(tpl, []) == "<x>"


# ---------------------------------------------------------------------------
# SUPPORTED_DATASETS
# ---------------------------------------------------------------------------


class TestSupportedDatasets:
    def test_contains_three(self):
        assert "hassil-intents" in SUPPORTED_DATASETS
        assert "intents-for-eval" in SUPPORTED_DATASETS
        assert "massive-templates" in SUPPORTED_DATASETS

    def test_urls_valid(self):
        for url in SUPPORTED_DATASETS.values():
            assert "/" in url
            assert url.startswith("OpenVoiceOS/")
