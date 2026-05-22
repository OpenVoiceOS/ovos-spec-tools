"""Locale resource linter for the OVOS specifications.

Validates the **syntax** (OVOS-INTENT-1) and the **naming and layout**
(OVOS-INTENT-2) of every resource file under a locale directory, and reports
every problem found rather than stopping at the first.

Exposed as the ``ovos-spec-lint`` command::

    ovos-spec-lint path/to/locale

The argument may be a ``locale/`` directory (every language subdirectory is
checked) or a single ``<lang>/`` directory.

The ``--spec-version`` option additionally flags features newer than a target
OVOS spec version, for skills that must run on older deployments:

- **0** — the legacy, undocumented Mycroft/OVOS de-facto behaviour;
- **1** — the formalized specs; adds the ``.blacklist`` role;
- **2** — adds ``<name>`` inline vocabulary references;
- **3** — adds the ``.prompt`` role.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ovos_spec_tools.expansion import MalformedTemplate, expand
from ovos_spec_tools.resources import (
    PROMPT_ROLE,
    SLOT_BEARING_ROLES,
    SLOT_FREE_ROLES,
    read_prompt_file,
    read_resource_file,
)

__all__ = ["Finding", "lint_locale", "main"]

# The six OVOS-INTENT-2 resource roles.
ROLE_EXTENSIONS = SLOT_BEARING_ROLES + SLOT_FREE_ROLES + (PROMPT_ROLE,)
# File types OVOS-INTENT-2 deliberately does not define — flagged, not parsed.
LEGACY_EXTENSIONS = (".rx", ".value", ".list", ".word", ".template", ".qml")

# The OVOS spec version that introduced each feature.
DEFAULT_SPEC_VERSION = 3
_BLACKLIST_SINCE = 1        # the `.blacklist` role
_VOCABULARY_REFERENCE_SINCE = 2  # the `<name>` inline vocabulary reference
_PROMPT_ROLE_SINCE = 3      # the `.prompt` role
# Roles introduced after V0, by the spec version that added them.
_ROLE_SINCE = {".blacklist": _BLACKLIST_SINCE, PROMPT_ROLE: _PROMPT_ROLE_SINCE}

_BASE_NAME_RE = re.compile(r"[a-z0-9_]+")
_SLOT_NAME_RE = re.compile(r"[a-z][a-z0-9_]*")
_LANG_TAG_RE = re.compile(r"[a-z]{2,3}(-[A-Za-z0-9]+)*")
_SLOT_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")

ERROR = "error"
WARNING = "warning"


@dataclass
class Finding:
    """One problem found by the linter."""

    severity: str  # ERROR or WARNING
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.severity}: {self.message}"


def lint_locale(path, spec_version: int = DEFAULT_SPEC_VERSION) -> List[Finding]:
    """Lint a locale directory, or a single language directory.

    Returns every :class:`Finding`, in file order. A path whose name is a
    BCP-47 tag is treated as a single language tree; otherwise it is treated as
    a ``locale/`` directory and each language subdirectory is checked.

    ``spec_version`` is the target OVOS spec version: a resource using a
    feature newer than it is flagged (see the module docstring).
    """
    root = Path(path)
    if not root.is_dir():
        return [Finding(ERROR, str(root), "not a directory")]

    if _LANG_TAG_RE.fullmatch(root.name):
        return _lint_language_tree(root, spec_version)

    findings: List[Finding] = []
    for child in sorted(root.iterdir()):
        if child.is_file() and child.suffix in ROLE_EXTENSIONS:
            findings.append(Finding(
                WARNING, str(child),
                "resource file is not inside a language directory"))
    language_dirs = [c for c in sorted(root.iterdir()) if c.is_dir()]
    if not language_dirs:
        findings.append(Finding(
            WARNING, str(root), "no language directories found"))
    for language_dir in language_dirs:
        findings.extend(_lint_language_tree(language_dir, spec_version))
    return findings


def _lint_language_tree(language_dir: Path, spec_version: int) -> List[Finding]:
    """Lint one ``<lang>/`` directory and all its subdirectories."""
    findings: List[Finding] = []
    if not _LANG_TAG_RE.fullmatch(language_dir.name):
        findings.append(Finding(
            WARNING, str(language_dir),
            f"directory name {language_dir.name!r} is not a BCP-47 "
            f"language tag"))

    role_files: List[Path] = []
    for path in sorted(language_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix in ROLE_EXTENSIONS:
            role_files.append(path)
        elif path.suffix in LEGACY_EXTENSIONS:
            findings.append(Finding(
                WARNING, str(path),
                f"{path.suffix} is a legacy file type, not an "
                f"OVOS-INTENT-2 resource role"))

    if not role_files:
        findings.append(Finding(
            WARNING, str(language_dir),
            "language directory contains no resource files"))

    # Duplicate (role, base name) within one language tree (OVOS-INTENT-2 §2).
    first_seen: Dict[tuple, Path] = {}
    for path in role_files:
        key = (path.suffix, path.stem)
        if key in first_seen:
            findings.append(Finding(
                ERROR, str(path),
                f"duplicate {path.suffix} resource {path.stem!r} — also at "
                f"{first_seen[key]}"))
        else:
            first_seen[key] = path

    # Per-role spec-version gate (a role newer than the target is flagged),
    # plus the `.blacklist` pairing check (§4.3).
    intent_names = {stem for (ext, stem) in first_seen if ext == ".intent"}
    for path in role_files:
        since = _ROLE_SINCE.get(path.suffix)
        if since is not None and spec_version < since:
            findings.append(Finding(
                WARNING, str(path),
                f"the {path.suffix} role requires spec version {since}; a "
                f"version-{spec_version} runtime ignores it"))
        if path.suffix == ".blacklist" and path.stem not in intent_names:
            findings.append(Finding(
                WARNING, str(path),
                f"blacklist {path.stem!r} has no matching "
                f"{path.stem}.intent to suppress"))

    # Vocabularies, for resolving <name> references during expansion.
    vocabularies: Dict[str, List[str]] = {}
    for path in role_files:
        if path.suffix == ".voc":
            try:
                vocabularies[path.stem] = read_resource_file(path)
            except (OSError, UnicodeError):
                pass  # _lint_file reports the read error below

    for path in role_files:
        findings.extend(_lint_file(path, vocabularies, spec_version))
    return findings


def _lint_file(path: Path,
               vocabularies: Dict[str, Sequence[str]],
               spec_version: int) -> List[Finding]:
    """Lint one resource file: naming, then the syntax of every template."""
    findings: List[Finding] = []
    extension = path.suffix
    base_name = path.stem

    # --- naming (OVOS-INTENT-2 §2) ------------------------------------------
    if not _BASE_NAME_RE.fullmatch(base_name):
        findings.append(Finding(
            ERROR, str(path),
            f"base name {base_name!r} must be lowercase ASCII letters, "
            f"digits and underscores only"))
    if extension == ".entity" and not _SLOT_NAME_RE.fullmatch(base_name):
        findings.append(Finding(
            ERROR, str(path),
            f".entity base name {base_name!r} names a slot and must not "
            f"begin with a digit"))
    if path.name != path.name.lower():
        findings.append(Finding(
            WARNING, str(path), "file name should be lowercase"))

    # --- `.prompt` — a whole-file document, not a template list (§4.4) ------
    if extension == PROMPT_ROLE:
        try:
            text = read_prompt_file(path)
        except (OSError, UnicodeError) as exc:
            findings.append(Finding(
                ERROR, str(path), f"cannot read file: {exc}"))
        else:
            if not text.strip():
                findings.append(Finding(
                    ERROR, str(path),
                    "empty file — every resource file must contribute "
                    "content (OVOS-INTENT-2 §5)"))
        return findings

    # --- read (OVOS-INTENT-2 §3) --------------------------------------------
    try:
        templates = read_resource_file(path)
    except (OSError, UnicodeError) as exc:
        findings.append(Finding(ERROR, str(path), f"cannot read file: {exc}"))
        return findings
    if not templates:
        findings.append(Finding(
            ERROR, str(path),
            "empty file — every resource file must contribute at least one "
            "template (OVOS-INTENT-2 §5)"))
        return findings

    # --- syntax (OVOS-INTENT-1) ---------------------------------------------
    slot_free = extension in SLOT_FREE_ROLES
    slot_bearing = extension in SLOT_BEARING_ROLES
    slot_sets: List[frozenset] = []
    for template in templates:
        if spec_version < _VOCABULARY_REFERENCE_SINCE and "<" in template:
            findings.append(Finding(
                ERROR, str(path),
                f"an inline vocabulary reference <…> requires spec version "
                f"{_VOCABULARY_REFERENCE_SINCE}; a version-{spec_version} "
                f"runtime will not expand this template  [in: {template!r}]"))
        try:
            samples = expand(template, vocabularies)
        except MalformedTemplate as exc:
            findings.append(Finding(
                ERROR, str(path), f"{exc}  [in: {template!r}]"))
            continue
        if slot_free and any("{" in sample for sample in samples):
            findings.append(Finding(
                ERROR, str(path),
                f"{extension} is slot-free but a template contains a named "
                f"slot  [in: {template!r}]"))
        if slot_bearing:
            slot_sets.append(frozenset(_SLOT_RE.findall(template)))

    # --- slot consistency (OVOS-INTENT-1 §5.5) ------------------------------
    if slot_bearing and len(set(slot_sets)) > 1:
        findings.append(Finding(
            ERROR, str(path),
            f"templates declare different slot sets — every template in one "
            f"{extension} must use the same {{slots}} (OVOS-INTENT-1 §5.5)"))

    return findings


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the ``ovos-spec-lint`` command."""
    parser = argparse.ArgumentParser(
        prog="ovos-spec-lint",
        description="Validate OVOS locale resource files against "
                    "OVOS-INTENT-1 (syntax) and OVOS-INTENT-2 (naming).")
    parser.add_argument(
        "locale", help="path to a locale/ directory, or a <lang>/ directory")
    parser.add_argument(
        "--strict", action="store_true",
        help="exit non-zero if there are warnings as well as errors")
    parser.add_argument(
        "--spec-version", type=int, choices=(0, 1, 2, 3),
        default=DEFAULT_SPEC_VERSION,
        help="target OVOS spec version; flags features newer than it "
             "(0: legacy, 1: adds .blacklist, 2: adds <name> references, "
             f"3: adds the .prompt role). Default {DEFAULT_SPEC_VERSION}.")
    args = parser.parse_args(argv)

    findings = lint_locale(args.locale, spec_version=args.spec_version)
    errors = [f for f in findings if f.severity == ERROR]
    warnings = [f for f in findings if f.severity == WARNING]

    for finding in findings:
        print(finding)
    if findings:
        print()
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")

    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
