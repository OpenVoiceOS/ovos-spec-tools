"""Re-export templates into per-language subdirectories with uniform
expansions as list<struct> instead of dynamic dict keys."""
from __future__ import annotations

import json
import re
from pathlib import Path
import sys


def _load_vocabs(locale_dir: Path, lang: str) -> dict[str, list[str]]:
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


def _extract_keyword_refs(template: str) -> list[str]:
    return re.findall(r"<([a-zA-Z_][a-zA-Z0-9_]*)>", template)


def reexport_uniform(locale_dir: Path, input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    langs = sorted(p.stem.replace("-templates", "") for p in input_dir.glob("*-templates.jsonl"))

    for lang in langs:
        in_path = input_dir / f"{lang}-templates.jsonl"
        lang_dir = output_dir / lang
        lang_dir.mkdir(parents=True, exist_ok=True)
        out_path = lang_dir / "templates.jsonl"

        vocabs = _load_vocabs(locale_dir, lang)
        written = 0
        with in_path.open(encoding="utf-8") as fin, out_path.open("w", encoding="utf-8") as fout:
            for line in fin:
                row = json.loads(line)
                # Remove old dict-style expansions if present
                row.pop("expansions", None)

                template = row.get("template", "")
                refs = _extract_keyword_refs(template)
                expansions: list[dict[str, object]] = []
                for ref in refs:
                    vals = vocabs.get(ref)
                    if vals:
                        expansions.append({"keyword": ref, "values": vals})
                if expansions:
                    row["expansions"] = expansions

                fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                written += 1

        print(f"[{lang}] wrote {written} rows -> {out_path}")


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: python reexport_uniform.py <locale_dir> <input_templates_dir> <output_dir>")
        raise SystemExit(2)
    reexport_uniform(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))


if __name__ == "__main__":
    main()
