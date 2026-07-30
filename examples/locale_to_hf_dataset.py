"""Convert any OVOS-INTENT-2 locale tree into a HuggingFace dataset in
the style of https://huggingface.co/datasets/OpenVoiceOS/intents-for-eval.

Works on any directory containing `<lang>/*.intent` resource files —
the converter's `examples/hassil-locale/`, a single skill's `locale/`,
a multi-skill workspace, etc. The script auto-detects whether the
input path is the locale parent (`<src>/locale/<lang>/…`) or already
the locale root (`<src>/<lang>/…`).

Emits a single flat JSONL plus a README:

    <out>/train_templates.jsonl
    <out>/README.md

Per-row schema (`domain` is only emitted if a domain is supplied):

    {intent_id, lang, template, slots: [{name, examples}]}
    {intent_id, domain, lang, template, slots: [{name, examples}]}

Run:
    python examples/locale_to_hf_dataset.py <src> <out> [domain]

    # default — no domain field on rows
    python examples/locale_to_hf_dataset.py examples/hassil-locale examples/hf-dataset

    # add a constant domain to every row
    python examples/locale_to_hf_dataset.py examples/hassil-locale out smarthome
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SLOT_RE = re.compile(r"\{([^{}]+)\}")
VOC_RE = re.compile(r"<([^<>\s]+)>")

# ---------------------------------------------------------------------------
# Locale loading
# ---------------------------------------------------------------------------


def _load_lines(path: Path) -> list[str]:
    return [
        ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def _load_locale(lang_dir: Path):
    """Return (vocabs, entities, intents) for one language directory.

    `vocabs` and `entities` map name → list[str]; `intents` maps base
    name → list[str] (the template lines)."""
    vocabs: dict[str, list[str]] = {}
    entities: dict[str, list[str]] = {}
    intents: dict[str, list[str]] = {}
    for path in sorted(lang_dir.iterdir()):
        if path.suffix == ".voc":
            vocabs[path.stem] = _load_lines(path)
        elif path.suffix == ".entity":
            entities[path.stem] = _load_lines(path)
        elif path.suffix == ".intent":
            intents[path.stem] = _load_lines(path)
    return vocabs, entities, intents


# ---------------------------------------------------------------------------
# Template processing
# ---------------------------------------------------------------------------


def _expand_vocab_inline(template: str, vocabs: dict[str, list[str]]) -> str:
    """Replace `<voc>` references with `(v1|v2|v3)` alternations so the
    output template carries only `{slot}` placeholders and OVOS-INTENT-1
    alternation/optional syntax — matching the intents-for-eval style."""

    def _sub(m: re.Match[str]) -> str:
        name = m.group(1)
        values = vocabs.get(name)
        if not values:
            return m.group(0)
        return "(" + "|".join(values) + ")"

    # Resolve up to a few levels — a .voc could in principle reference
    # another vocabulary; in practice that doesn't happen in the
    # hassil-derived corpus, but cap iterations defensively.
    for _ in range(4):
        new = VOC_RE.sub(_sub, template)
        if new == template:
            break
        template = new
    return template


def _slots_for_template(
    template: str, entities: dict[str, list[str]]
) -> list[dict]:
    seen: dict[str, dict] = {}
    for slot in SLOT_RE.findall(template):
        if slot in seen:
            continue
        seen[slot] = {"name": slot, "examples": entities.get(slot, [])[:64]}
    return list(seen.values())


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _json_line(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ": "))


def export_lang(
    lang_dir: Path, lang: str, f_tpl, domain: str | None
) -> int:
    vocabs, entities, intents = _load_locale(lang_dir)
    count = 0
    for intent_name in sorted(intents):
        intent_id = f"{domain}:{intent_name}" if domain else intent_name
        for tpl in intents[intent_name]:
            expanded = _expand_vocab_inline(tpl, vocabs)
            row: dict = {"intent_id": intent_id}
            if domain:
                row["domain"] = domain
            row["lang"] = lang
            row["template"] = expanded
            row["slots"] = _slots_for_template(expanded, entities)
            f_tpl.write(_json_line(row) + "\n")
            count += 1
    return count


_README = """\
# OVOS-INTENT-2 derived intents dataset

Mechanically converted from an OVOS-INTENT-2 locale tree
(`<lang>/*.intent`, `*.voc`, `*.entity` files) into the
[OpenVoiceOS/intents-for-eval][src] templates schema.

[src]: https://huggingface.co/datasets/OpenVoiceOS/intents-for-eval

## Layout

    train_templates.jsonl   # all languages interleaved; `lang` selects

## Row schema

    {
      "intent_id": "turn_on",
      "lang": "en",
      "template": "(turn on|switch on) [the] {name}",
      "slots": [
        {"name": "name", "examples": ["kitchen light", "..."]}
      ]
    }

If a domain was supplied at conversion time, every row carries a
`domain` field (`intent_id` is prefixed as `<domain>:<intent_id>`).

## What the converter does

  * One row per template line in `<lang>/<intent>.intent`.
  * `<vocab>` references are expanded inline into `(a|b|c)`
    alternations from the matching `<vocab>.voc` file.
  * `{slot}` references survive verbatim; their `examples` come from
    `<slot>.entity` (empty list if the slot is free-form).
  * `[opt]` optionals and `(a|b)` alternations are preserved.

## Caveats vs intents-for-eval

  * Templates are mechanically derived from the source locale —
    alternations and optionals reflect what the source authored,
    not paraphrase-style native-speaker authoring.
  * No test set is included. Evaluation buckets (`paraphrase`,
    `near_ood`, `far_ood`, `asr_noise`, `typos`) require human
    authoring and are out of scope for this conversion.
"""


def _resolve_locale_root(src: Path) -> Path:
    """Return the directory whose children are `<lang>/` dirs. Accepts
    either the dataset root (`<src>/locale/<lang>/…`) or the locale root
    itself (`<src>/<lang>/…`)."""
    if (src / "locale").is_dir():
        return src / "locale"
    # Otherwise expect `<src>/<lang>/…`; the heuristic is that at least
    # one child contains a .intent file.
    for child in src.iterdir():
        if child.is_dir() and any(child.glob("*.intent")):
            return src
    raise SystemExit(f"no `<lang>/*.intent` resources found under {src}")


def main() -> None:
    if len(sys.argv) not in (3, 4):
        print(__doc__)
        raise SystemExit(2)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    domain = sys.argv[3] if len(sys.argv) == 4 else None
    locale_root = _resolve_locale_root(src)
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "README.md").write_text(_README, encoding="utf-8")

    out_path = dst / "train_templates.jsonl"
    total = 0
    langs = 0
    with out_path.open("w", encoding="utf-8") as f_tpl:
        for lang_dir in sorted(p for p in locale_root.iterdir() if p.is_dir()):
            if not any(lang_dir.glob("*.intent")):
                continue
            lang = lang_dir.name
            count = export_lang(lang_dir, lang, f_tpl, domain)
            print(f"[{lang}] templates: {count:>5}")
            total += count
            langs += 1
    print(f"total: {langs} languages, {total} rows — at {out_path}")


if __name__ == "__main__":
    main()
