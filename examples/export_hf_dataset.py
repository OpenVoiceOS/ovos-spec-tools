"""Export a hassil-locale tree (from convert_hassil_intents.py) into an
OVOS-compatible HuggingFace dataset with three configs per language:

  * ``{lang}-templates``  — one row per ``.intent`` line, with slot schema
  * ``{lang}-keywords``   — one row per ``.voc`` vocabulary set
  * ``{lang}-entities``   — one row per ``.entity`` value set
  * ``{lang}-test``       — expanded realisations (template × entity combinations)

The schema mirrors ``OpenVoiceOS/massive-templates`` and
``OpenVoiceOS/intents-for-eval`` so downstream training pipelines
(Padacioso, Adapt, m2v, …) can consume the data unchanged.

Usage::

    python export_hf_dataset.py /tmp/hassil-locale /tmp/hassil-dataset

The output directory receives one JSONL file per (lang, config) pair:

    /tmp/hassil-dataset/
      en-US-templates.jsonl
      en-US-keywords.jsonl
      en-US-entities.jsonl
      en-US-test.jsonl
      pt-PT-templates.jsonl
      ...

A minimal ``dataset_info.json`` is also written so the folder can be
uploaded directly with ``huggingface-cli upload-folder``.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Optional: use ovos-spec-tools expansion for bracket alternation / optionals
try:
    from ovos_spec_tools.expansion import expand, MalformedTemplate
except Exception:
    expand = None  # type: ignore[assignment]
    MalformedTemplate = Exception  # type: ignore[misc,assignment]


SLOT_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
VOC_RE = re.compile(r"<([a-zA-Z_][a-zA-Z0-9_]*)>")


def _extract_slots(template: str) -> list[str]:
    """Return ordered slot names from a template."""
    return SLOT_RE.findall(template)


def _extract_voc_refs(template: str) -> list[str]:
    """Return ordered vocabulary references from a template."""
    return VOC_RE.findall(template)


def _expand_alternations(template: str) -> list[str]:
    """Expand ``(a|b)`` and ``[opt]`` using ovos-spec-tools when available,
    otherwise return the template unchanged."""
    if expand is None:
        return [template]
    try:
        return expand(template)
    except MalformedTemplate:
        return [template]


def _load_locale_file(path: Path) -> list[str]:
    """Read a locale file, drop comments and blank lines."""
    lines: list[str] = []
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].strip()
            if line:
                lines.append(line)
    return lines


def _build_slot_schema(
    slot_names: list[str],
    entity_dir: Path,
) -> list[dict]:
    """For each slot name, try to find a matching ``.entity`` file and load
    example values."""
    schema: list[dict] = []
    for name in slot_names:
        entity_path = entity_dir / f"{name}.entity"
        examples: list[str] = []
        if entity_path.is_file():
            examples = _load_locale_file(entity_path)[:20]  # cap examples
        schema.append({"name": name, "examples": examples})
    return schema


def _realise_template(
    template: str,
    slot_names: list[str],
    entity_dir: Path,
    max_combos: int = 50,
) -> list[tuple[str, dict[str, str | None]]]:
    """Generate concrete utterances by filling slots with entity values.
    Returns ``(utterance, slot_map)`` pairs."""
    if not slot_names:
        return [(template, {})]

    # Load value pools for each slot
    pools: list[list[str]] = []
    for name in slot_names:
        entity_path = entity_dir / f"{name}.entity"
        if entity_path.is_file():
            values = _load_locale_file(entity_path)
            pools.append(values[:10])  # cap per slot
        else:
            pools.append([f"__{name}__"])  # placeholder when no entity file

    # Cartesian product capped
    from itertools import product
    results: list[tuple[str, dict[str, str | None]]] = []
    for combo in product(*pools):
        if len(results) >= max_combos:
            break
        utterance = template
        slot_map: dict[str, str | None] = {}
        for name, value in zip(slot_names, combo):
            utterance = utterance.replace("{" + name + "}", value, 1)
            slot_map[name] = value if not value.startswith("__") else None
        results.append((utterance, slot_map))
    return results


def export_templates(
    locale_dir: Path,
    lang: str,
    out_dir: Path,
) -> int:
    """Write ``{lang}-templates.jsonl`` — one row per ``.intent`` line."""
    lang_dir = locale_dir / lang
    if not lang_dir.is_dir():
        return 0

    entity_dir = lang_dir
    rows: list[dict] = []

    for intent_file in sorted(lang_dir.glob("*.intent")):
        intent_name = intent_file.stem
        # Domain is always "homeassistant" for this corpus
        domain = "homeassistant"
        for template in _load_locale_file(intent_file):
            slot_names = _extract_slots(template)
            slots = _build_slot_schema(slot_names, entity_dir)
            rows.append(
                {
                    "intent_id": f"{domain}:{intent_name}",
                    "domain": domain,
                    "template": template,
                    "slots": slots,
                }
            )

    out_path = out_dir / f"{lang}-templates.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def export_keywords(
    locale_dir: Path,
    lang: str,
    out_dir: Path,
) -> int:
    """Write ``{lang}-keywords.jsonl`` — one row per ``.voc`` file,
    packaged as an Adapt-style rule."""
    lang_dir = locale_dir / lang
    if not lang_dir.is_dir():
        return 0

    rows: list[dict] = []
    for voc_file in sorted(lang_dir.glob("*.voc")):
        vocab_name = voc_file.stem
        values = _load_locale_file(voc_file)
        # Package as a keyword rule (required vocab + optional vocab pattern)
        rows.append(
            {
                "intent_id": f"homeassistant:{vocab_name}",
                "domain": "homeassistant",
                "required_vocab": values,
                "optional_vocab": [],
                "excluded_vocab": [],
            }
        )

    out_path = out_dir / f"{lang}-keywords.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def export_entities(
    locale_dir: Path,
    lang: str,
    out_dir: Path,
) -> int:
    """Write ``{lang}-entities.jsonl`` — one row per ``.entity`` file."""
    lang_dir = locale_dir / lang
    if not lang_dir.is_dir():
        return 0

    rows: list[dict] = []
    for entity_file in sorted(lang_dir.glob("*.entity")):
        slot_name = entity_file.stem
        values = _load_locale_file(entity_file)
        rows.append(
            {
                "slot_name": slot_name,
                "values": values,
                "type": "closed" if values else "open",
            }
        )

    out_path = out_dir / f"{lang}-entities.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def export_test(
    locale_dir: Path,
    lang: str,
    out_dir: Path,
) -> int:
    """Write ``{lang}-test.jsonl`` — expanded realisations with gold intent + slots."""
    lang_dir = locale_dir / lang
    if not lang_dir.is_dir():
        return 0

    entity_dir = lang_dir
    rows: list[dict] = []
    seen_utterances: set[str] = set()

    for intent_file in sorted(lang_dir.glob("*.intent")):
        intent_name = intent_file.stem
        domain = "homeassistant"
        for template in _load_locale_file(intent_file):
            # First expand alternations/optionals
            expanded = _expand_alternations(template)
            for exp in expanded:
                slot_names = _extract_slots(exp)
                realised = _realise_template(exp, slot_names, entity_dir, max_combos=20)
                for utterance, slot_map in realised:
                    if utterance in seen_utterances:
                        continue
                    seen_utterances.add(utterance)
                    rows.append(
                        {
                            "utterance": utterance,
                            "expected_intent": f"{domain}:{intent_name}",
                            "expected_slots": slot_map,
                            "lang": lang,
                        }
                    )

    out_path = out_dir / f"{lang}-test.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def export_all(
    locale_dir: Path,
    out_dir: Path,
    langs: list[str] | None = None,
) -> dict[str, dict[str, int]]:
    """Export every language under ``locale_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if langs is None:
        langs = sorted(d.name for d in locale_dir.iterdir() if d.is_dir())

    stats: dict[str, dict[str, int]] = {}
    for lang in langs:
        print(f"[{lang}] exporting...")
        stats[lang] = {
            "templates": export_templates(locale_dir, lang, out_dir),
            "keywords": export_keywords(locale_dir, lang, out_dir),
            "entities": export_entities(locale_dir, lang, out_dir),
            "test": export_test(locale_dir, lang, out_dir),
        }
    return stats


def _write_dataset_info(out_dir: Path, stats: dict[str, dict[str, int]]) -> None:
    """Write a minimal dataset_info.json for HF upload."""
    configs: list[dict] = []
    for lang in sorted(stats):
        for suffix in ["templates", "keywords", "entities", "test"]:
            configs.append(
                {
                    "config_name": f"{lang}-{suffix}",
                    "data_files": f"{lang}-{suffix}.jsonl",
                    "num_examples": stats[lang][suffix],
                }
            )

    info = {
        "dataset_name": "hassil-ovos-locale",
        "description": "Home Assistant hassil intents exported to OVOS-INTENT-2 locale format",
        "configs": configs,
        "languages": sorted(stats),
    }
    with (out_dir / "dataset_info.json").open("w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=2, ensure_ascii=False)


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        print("Usage: python export_hf_dataset.py <locale_dir> <out_dir>")
        raise SystemExit(2)
    locale_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    stats = export_all(locale_dir, out_dir)
    _write_dataset_info(out_dir, stats)

    total_rows = sum(sum(v.values()) for v in stats.values())
    print(f"\nDone — {len(stats)} languages, {total_rows:,} total rows in {out_dir}")
    for lang, s in sorted(stats.items()):
        print(
            f"  {lang:6}: templates={s['templates']:>5}, keywords={s['keywords']:>4}, "
            f"entities={s['entities']:>3}, test={s['test']:>5}"
        )


if __name__ == "__main__":
    main()
