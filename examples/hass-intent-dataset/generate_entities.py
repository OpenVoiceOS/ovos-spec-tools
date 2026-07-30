"""Generate .entity files for all slots that lack them across the
hassil-locale tree.  Sources localized values from the bundled
``base_locale/`` directory — the single source of truth for
translated slot values.

Numeric slots (brightness, percentage, temperature, …) are still
generated programmatically since they are language-agnostic."""
from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Numeric ranges — same digits in every language (not "strings")
# ---------------------------------------------------------------------------

NUMERIC_SLOTS: dict[str, range] = {
    "brightness": range(0, 101),
    "percentage": range(0, 101),
    "position": range(0, 101),
    "volume_level": range(0, 101),
    "volume_step": range(1, 21),
    "temperature": range(0, 101),
    "hours": range(0, 24),
    "minutes": range(0, 60),
    "seconds": range(0, 60),
    "start_hours": range(0, 24),
    "start_minutes": range(0, 60),
}

# ---------------------------------------------------------------------------
# Base locale loader
# ---------------------------------------------------------------------------


def _base_locale_dir() -> Path:
    return Path(__file__).resolve().parent / "base_locale"


def _read_entity(lang: str, slot: str) -> list[str] | None:
    """Read values from ``base_locale/<lang>/<slot>.entity``.
    Returns ``None`` if the file doesn't exist."""
    path = _base_locale_dir() / lang / f"{slot}.entity"
    if not path.is_file():
        return None
    return [
        ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]


def _get_values(slot: str, lang: str) -> list[str] | None:
    """Return a value list for ``slot`` in ``lang``.

    Resolution order:
    1. ``base_locale/<lang>/<slot>.entity``
    2. ``base_locale/en/<slot>.entity`` (English fallback for HA constants)
    3. Programmatic numeric range (if applicable)
    4. ``None`` (free-form / wildcard slot)
    """
    # 1. Language-specific
    values = _read_entity(lang, slot)
    if values is not None:
        return values

    # 2. English fallback (for HA internal constants)
    if lang != "en":
        values = _read_entity("en", slot)
        if values is not None:
            return values

    # 3. Numeric range
    if slot in NUMERIC_SLOTS:
        return [str(n) for n in NUMERIC_SLOTS[slot]]

    # 4. Unknown — leave as wildcard
    return None


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def generate_missing_entities(locale_dir: Path) -> dict[str, int]:
    """Walk the locale tree and write ``.entity`` files for every slot that
    appears in ``.intent`` files but has no matching ``.entity`` file.

    Values are sourced from ``base_locale/``; slots with no translation
    data are left as wildcards (no file written)."""
    stats: dict[str, int] = {}

    for lang_dir in sorted(locale_dir.iterdir()):
        if not lang_dir.is_dir():
            continue
        lang = lang_dir.name
        intent_files = list(lang_dir.glob("*.intent"))
        if not intent_files:
            continue

        # Discover which slots are used
        used_slots: set[str] = set()
        for intent_file in intent_files:
            with intent_file.open(encoding="utf-8") as fh:
                for line in fh:
                    for match in re.finditer(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", line):
                        used_slots.add(match.group(1))

        written = 0
        for slot in sorted(used_slots):
            entity_path = lang_dir / f"{slot}.entity"
            if entity_path.exists():
                continue
            values = _get_values(slot, lang)
            if values is None:
                continue
            with entity_path.open("w", encoding="utf-8") as fh:
                for v in values:
                    fh.write(v + "\n")
            written += 1

        if written:
            stats[lang] = written

    return stats


def main() -> None:
    import sys
    if len(sys.argv) != 2:
        print("Usage: python generate_entities.py <locale_dir>")
        raise SystemExit(2)
    locale_dir = Path(sys.argv[1])
    stats = generate_missing_entities(locale_dir)
    total = sum(stats.values())
    print(f"Wrote {total} .entity files across {len(stats)} languages.")
    for lang, count in sorted(stats.items()):
        print(f"  {lang:8}: {count} files")


if __name__ == "__main__":
    main()
