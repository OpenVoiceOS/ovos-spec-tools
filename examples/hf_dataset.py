"""Load templates from an OVOS HuggingFace dataset, expand them, and export
to an OVOS-INTENT-2 locale directory.

Usage::

    # Export English hassil intents to locale
    python examples/hf_dataset.py hassil-intents en /tmp/my-locale

    # Expand a few templates to see concrete utterances
    python examples/hf_dataset.py hassil-intents en /tmp/my-locale --expand

    # Export massive-templates for Portuguese
    python examples/hf_dataset.py massive-templates pt-PT /tmp/pt-locale
"""
from __future__ import annotations

import sys
from pathlib import Path

from ovos_spec_tools.datasets import (
    SUPPORTED_DATASETS,
    expand_hf_template,
    export_to_locale,
    load_dataset_templates,
)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dataset",
        choices=list(SUPPORTED_DATASETS),
        help="HF dataset to load",
    )
    parser.add_argument(
        "lang",
        help="Language tag (e.g. en, pt_BR, en-US, pt-PT)",
    )
    parser.add_argument(
        "output",
        type=Path,
        help="Output directory for locale tree",
    )
    parser.add_argument(
        "--expand",
        action="store_true",
        help="Show expanded utterances for first 3 templates",
    )
    parser.add_argument(
        "--split",
        default="train",
        help="Dataset split (default: train)",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=10,
        help="Max samples to show per expanded template (default: 10)",
    )
    args = parser.parse_args(argv)

    print(f"Loading {args.dataset} ({SUPPORTED_DATASETS[args.dataset]}) / {args.lang} ...")
    templates = load_dataset_templates(
        args.dataset, lang=args.lang, split=args.split
    )
    print(f"Loaded {len(templates)} templates")

    if args.expand and templates:
        print("\n--- Template expansion samples ---")
        for i, row in enumerate(templates[:3]):
            tpl = row["template"]
            exps = row.get("expansions", [])
            results = expand_hf_template(tpl, exps, max_samples=args.max_samples)
            print(f"\n  [{i}] intent_id={row['intent_id']}")
            print(f"      template: {tpl}")
            if exps:
                print(f"      expansions: {len(exps)} keywords")
            if results:
                print(f"      sample utterances ({len(results)} total):")
                for r in results[:args.max_samples]:
                    print(f"        - {r}")

    count = export_to_locale(
        args.dataset, lang=args.lang, output_dir=args.output, split=args.split
    )
    loc = args.output / "locale" / args.lang
    print(f"\nExported {count} template lines to {loc}/")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
