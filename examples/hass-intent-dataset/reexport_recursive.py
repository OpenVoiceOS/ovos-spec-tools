"""Recursively resolve nested <keyword> references inside expansion values,
on a per-row basis.  A keyword is only expanded if it appears in the same
row's template (or in another expansion value that is itself being expanded)."""
from __future__ import annotations

import json
import re
from pathlib import Path
import sys


def _load_all_vocabs(locale_dir: Path, lang: str) -> dict[str, list[str]]:
    voc_dir = locale_dir / lang
    vocabs: dict[str, list[str]] = {}
    if not voc_dir.is_dir():
        return vocabs
    for voc_path in voc_dir.glob("*.voc"):
        stem = voc_path.stem
        vals = [ln.strip() for ln in voc_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if vals:
            vocabs[stem] = vals
    return vocabs


def _extract_refs(text: str) -> set[str]:
    return set(re.findall(r"<([a-zA-Z_][a-zA-Z0-9_]*)>", text))


def _resolve_value(value: str, vocabs: dict[str, list[str]], seen: set[str]) -> list[str]:
    """Recursively expand <keyword> references in a single value string.
    ``seen`` prevents cycles."""
    refs = _extract_refs(value)
    if not refs:
        return [value]

    # Pick the first ref that is available in vocabs and not already seen
    for ref in sorted(refs):
        if ref in seen or ref not in vocabs:
            continue
        sub_values = vocabs[ref]
        results: list[str] = []
        for sub in sub_values:
            new_val = value.replace(f"<{ref}>", sub, 1)
            results.extend(_resolve_value(new_val, vocabs, seen | {ref}))
        return results

    # Unresolvable refs remain as-is
    return [value]


def _resolve_expansions(template: str, vocabs: dict[str, list[str]]) -> list[dict[str, object]]:
    """For every <keyword> in ``template``, resolve its .voc values recursively."""
    refs = _extract_refs(template)
    if not refs:
        return []

    resolved: list[dict[str, object]] = []
    for ref in sorted(refs):
        if ref not in vocabs:
            continue
        raw_values = vocabs[ref]
        flat_values: list[str] = []
        for v in raw_values:
            flat_values.extend(_resolve_value(v, vocabs, {ref}))
        # Deduplicate while preserving order
        seen = set()
        deduped = [v for v in flat_values if not (v in seen or seen.add(v))]
        resolved.append({"keyword": ref, "values": deduped})
    return resolved


def reexport_recursive(locale_dir: Path, input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    langs = sorted(p.name for p in input_dir.iterdir() if p.is_dir())

    for lang in langs:
        in_path = input_dir / lang / "templates.jsonl"
        if not in_path.exists():
            continue
        lang_dir = output_dir / lang
        lang_dir.mkdir(parents=True, exist_ok=True)
        out_path = lang_dir / "templates.jsonl"

        vocabs = _load_all_vocabs(locale_dir, lang)
        written = 0
        with in_path.open(encoding="utf-8") as fin, out_path.open("w", encoding="utf-8") as fout:
            for line in fin:
                row = json.loads(line)
                template = row.get("template", "")
                expansions = _resolve_expansions(template, vocabs)
                if expansions:
                    row["expansions"] = expansions
                else:
                    row.pop("expansions", None)
                fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                written += 1

        print(f"[{lang}] wrote {written} rows -> {out_path}")


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: python reexport_recursive.py <locale_dir> <input_dir> <output_dir>")
        raise SystemExit(2)
    reexport_recursive(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))


if __name__ == "__main__":
    main()
