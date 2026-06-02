"""Load, expand, and export HuggingFace datasets conforming to the
OVOS-INTENT-2 template syntax.

Supports three datasets:

- ``hassil-intents``  — ``OpenVoiceOS/hass-intent-templates`` (per-lang configs,
  ``template`` with full OVOS syntax, ``expansions`` column)
- ``intents-for-eval`` — ``OpenVoiceOS/intents-for-eval``
  (``{lang}-templates`` config, ``template`` has ``<keyword>`` inlined to ``(a|b|c)``)
- ``massive-templates`` — ``OpenVoiceOS/massive-templates``
  (``{lang}-templates`` config, same style as intents-for-eval)

Usage::

    from ovos_spec_tools.datasets import (
        load_dataset_templates,
        expand_hf_template,
        export_to_locale,
        SUPPORTED_DATASETS,
    )

    # Load English templates from hassil-intents
    templates = load_dataset_templates("hassil-intents", lang="en")

    # Expand a single template into concrete utterances
    results = expand_hf_template(
        template="<turn_on> [the] {name}",
        expansions=[{"keyword": "turn_on", "values": ["turn on", "switch on"]}],
    )

    # Export to OVOS-INTENT-2 locale directory
    export_to_locale("hassil-intents", lang="en", output_dir="/tmp/my-locale")
"""
from __future__ import annotations

import json
import re
import typing
from collections import defaultdict
from pathlib import Path

from ovos_spec_tools.expansion import expand as _expand_templates

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

SLOT_RE = re.compile(r"\{([^{}]+)\}")
VOC_RE = re.compile(r"<([^<>\s]+)>")

# ---------------------------------------------------------------------------
# Dataset registry
# ---------------------------------------------------------------------------

SUPPORTED_DATASETS: dict[str, str] = {
    "hassil-intents": "OpenVoiceOS/hassil-intents-locale",
    "intents-for-eval": "OpenVoiceOS/intents-for-eval",
    "massive-templates": "OpenVoiceOS/massive-templates",
}

_REQUIRED_EXTRAS = (
    "The `datasets` library is required; install it with:  pip install datasets"
)


def _resolve_config(dataset_id: str, lang: str) -> str:
    """Return the HF config name for ``dataset_id`` at ``lang``.

    * ``hassil-intents`` uses plain language tags (``en``, ``pt_BR``, …).
    * ``intents-for-eval`` and ``massive-templates`` use the form
      ``{lang}-templates`` (``en-US-templates``, ``pt-PT-templates``, …).

    Accepts either form as input for the latter two.
    """
    if dataset_id == "hassil-intents":
        return lang
    # intents-for-eval / massive-templates: accept short or full form
    if lang.endswith("-templates"):
        return lang
    # Normalize BCP-47 style: "en-US" -> "en-US-templates"
    return f"{lang}-templates"


def _normalize_rows(rows: list[dict], dataset_id: str) -> list[dict]:
    """Normalize rows from any supported dataset to a common schema::

        {"intent_id": str, "template": str, "slots": [{name, examples}],
         "expansions": [{keyword, values}]}

    For datasets that inline ``<keyword>`` refs into ``(a|b|c)`` groups,
    ``expansions`` is left empty and the template carries the alternations
    directly.
    """
    normalized: list[dict] = []
    for row in rows:
        out: dict = {
            "intent_id": row.get("intent_id") or row.get("intent") or "",
            "template": row.get("template") or "",
            "slots": row.get("slots") or [],
        }
        if "expansions" in row:
            out["expansions"] = row["expansions"] or []
        elif "text" in row:
            out["text"] = row["text"]
        normalized.append(out)
    return normalized


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_dataset_templates(
    dataset_id: str,
    lang: str = "en",
    *,
    split: str = "train",
    streaming: bool = True,
) -> list[dict]:
    """Load template rows from a supported HuggingFace dataset.

    Parameters
    ----------
    dataset_id
        One of ``"hassil-intents"``, ``"intents-for-eval"``,
        ``"massive-templates"``.
    lang
        Language tag.  For hassil-intents use plain codes (``en``, ``pt_BR``);
        for the others use BCP-47 (``en-US``, ``pt-PT``) — or the full config
        name (``en-US-templates``).  Default ``"en"``.
    split
        Dataset split to load.  Default ``"train"``.
    streaming
        If True (default) iterate in streaming mode.

    Returns
    -------
    list[dict]
        Normalized rows with keys ``intent_id``, ``template``, ``slots``,
        and (if available) ``expansions``.
    """
    try:
        from datasets import load_dataset
    except ImportError:
        raise ImportError(_REQUIRED_EXTRAS)

    repo = SUPPORTED_DATASETS.get(dataset_id)
    if repo is None:
        raise ValueError(
            f"Unknown dataset {dataset_id!r}; choose from {list(SUPPORTED_DATASETS)}"
        )

    config = _resolve_config(dataset_id, lang)
    ds = load_dataset(repo, config, split=split, streaming=streaming)
    rows: list[dict] = [dict(r) for r in ds]
    return _normalize_rows(rows, dataset_id)


def expand_hf_template(
    template: str,
    expansions: Sequence[dict] | None = None,
    max_samples: int = 2048,
) -> list[str]:
    """Expand an OVOS-INTENT-2 template into concrete utterances.

    ``<keyword>`` references are resolved from ``expansions`` (a list of
    ``{"keyword": str, "values": [str, ...]}`` dicts, as found in the
    hassil-intents dataset).  If ``expansions`` is empty or None, resolves
    ``<keyword>`` from inline ``(a|b|c)`` groups (as in intents-for-eval /
    massive-templates style).

    Then expands alternatives ``(a|b)``, optionals ``[x]``, and fills
    ``{slot}`` placeholders (which render as-fill since they are opaque
    to the grammar).

    Parameters
    ----------
    template
        An OVOS-INTENT-2 template string.
    expansions
        Optional list of ``{keyword, values}`` dicts providing the vocabulary
        for each ``<keyword>`` reference.
    max_samples
        Hard cap on the number of sample utterances to generate.

    Returns
    -------
    list[str]
        Concrete utterance strings.
    """
    if expansions:
        vocab: dict[str, list[str]] = {}
        for entry in expansions:
            kw = entry.get("keyword", "")
            vals = entry.get("values", [])
            if kw and vals:
                vocab[kw] = list(vals)
    else:
        vocab = None

    try:
        results = _expand_templates(template, vocabularies=vocab)
    except Exception:
        return [template]

    if max_samples and len(results) > max_samples:
        results = results[:max_samples]
    return results


def inline_keywords(
    template: str,
    expansions: Sequence[dict] | None = None,
    *,
    flat_vocab: dict[str, list[str]] | None = None,
    max_values: int = 10,
) -> str:
    """Inline ``<keyword>`` references as ``(v1|v2|…)`` alternation groups.

    Engines like Padatious don't look up ``.voc`` files at runtime — they
    need keywords inlined into the template body.  This utility replaces
    every ``<keyword>`` reference with its values in alternation syntax,
    handling nested references recursively.

    Parameters
    ----------
    template
        Template string with ``<keyword>`` references.
    expansions
        List of ``{"keyword", "values"}`` dicts (from the ``expansions``
        column of the hass-intent-templates dataset).
    flat_vocab
        Flat ``{keyword: [values]}`` mapping, alternative to ``expansions``.
    max_values
        Cap the number of values per keyword inlined.  Default 10.

    Returns
    -------
    str
        Template with all ``<keyword>`` references inlined.
    """
    vocab: dict[str, list[str]] = {}
    if flat_vocab:
        vocab.update(flat_vocab)
    if expansions:
        for entry in expansions:
            kw = entry.get("keyword", "")
            vals = entry.get("values") or []
            if kw and vals:
                vocab[kw] = list(vals)

    if not vocab:
        return template

    def _sub(m: re.Match[str]) -> str:
        vals = vocab.get(m.group(1))
        if vals:
            return "(" + "|".join(vals[:max_values]) + ")"
        return m.group(1)  # strip brackets for unresolvable keywords

    # Iterate until stable — handles nested refs like <a> inside <everywhere>
    for _ in range(8):
        new = VOC_RE.sub(_sub, template)
        if new == template:
            break
        template = new
    return template


def _strip_domain(intent_id: str) -> str:
    """Strip the ``domain:`` prefix from an intent ID to get the base name."""
    return intent_id.split(":", 1)[-1] if ":" in intent_id else intent_id


def export_to_locale(
    dataset_id: str,
    lang: str,
    output_dir: str | Path,
    *,
    split: str = "train",
    streaming: bool = True,
) -> int:
    """Export templates from a HuggingFace dataset to an OVOS-INTENT-2 locale
    directory tree.

    Writes::

        <output_dir>/
          locale/
            <lang>/
              <intent_name>.intent     # all template lines for each intent
              <keyword>.voc            # vocabulary expansions
              <slot>.entity            # slot example values

    Parameters
    ----------
    dataset_id
        Dataset to load (``"hassil-intents"``, ``"intents-for-eval"``,
        or ``"massive-templates"``).
    lang
        Language to export.
    output_dir
        Root directory for the locale tree.
    split
        Dataset split.  Default ``"train"``.
    streaming
        Whether to stream from HF.  Default True.

    Returns
    -------
    int
        Number of templates written.
    """
    rows = load_dataset_templates(
        dataset_id, lang=lang, split=split, streaming=streaming
    )
    out = Path(output_dir)
    locale = out / "locale" / lang
    locale.mkdir(parents=True, exist_ok=True)

    # Collect templates per intent
    intent_lines: dict[str, list[str]] = defaultdict(list)
    vocabs: dict[str, set[str]] = defaultdict(set)
    entities: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        name = _strip_domain(row["intent_id"])
        tpl = row["template"]
        intent_lines[name].append(tpl)

        # Collect slot examples from row["slots"]
        for slot in row.get("slots", []):
            slot_name = slot.get("name", "")
            for ex in slot.get("examples", []):
                entities[slot_name].add(ex)

        # Collect expansions from row["expansions"]
        for exp in row.get("expansions", []):
            kw = exp.get("keyword", "")
            for v in exp.get("values", []):
                vocabs[kw].add(v)

        # If no expansions but the template has <keyword> refs,
        # try to extract inline alternations
        if not row.get("expansions"):
            for m in VOC_RE.finditer(tpl):
                kw = m.group(1)
                # No expansion data available; carry on

    # Write .intent files
    written = 0
    for name, lines in sorted(intent_lines.items()):
        intent_path = locale / f"{name}.intent"
        with intent_path.open("w", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")
        written += len(lines)

    # Write .voc files
    for name, values in sorted(vocabs.items()):
        if not values:
            continue
        voc_path = locale / f"{name}.voc"
        with voc_path.open("w", encoding="utf-8") as fh:
            for v in sorted(values):
                fh.write(v + "\n")

    # Write .entity files
    for name, values in sorted(entities.items()):
        if not values:
            continue
        entity_path = locale / f"{name}.entity"
        with entity_path.open("w", encoding="utf-8") as fh:
            for v in sorted(values):
                fh.write(v + "\n")

    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Load templates from an OVOS HF dataset and export to locale."
    )
    parser.add_argument(
        "dataset",
        choices=list(SUPPORTED_DATASETS),
        help="Dataset to load",
    )
    parser.add_argument("lang", help="Language tag (e.g. en, en-US, pt_BR)")
    parser.add_argument("output", type=Path, help="Output directory")
    parser.add_argument(
        "--split", default="train", help="Dataset split (default: train)"
    )
    args = parser.parse_args(argv)

    count = export_to_locale(args.dataset, args.lang, args.output, split=args.split)
    print(
        f"Exported {count} template lines to {args.output}/locale/{args.lang}/"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
