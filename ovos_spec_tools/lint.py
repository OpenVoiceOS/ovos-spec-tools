"""Locale resource linter for the OVOS specifications.

Validates the **syntax** (OVOS-INTENT-1) and the **naming and layout**
(OVOS-INTENT-2) of every resource file under a locale directory, and reports
every problem found rather than stopping at the first. Each finding is phrased
to point at the exact spec clause it enforces, so a failing lint tells the
author which MUST they violated.

Clause map (which spec rule each rule enforces):

- *empty file* → OVOS-INTENT-2 §5 step 5 — "Reject an empty file … every file
  MUST contribute at least one template" (and for ``.prompt``, content).
- *duplicate (role, base name)* → OVOS-INTENT-2 §2 — "Two files with the same
  extension MUST NOT share a base name anywhere within one language directory
  tree".
- *base-name / ``.entity`` charset* → OVOS-INTENT-2 §2 + OVOS-INTENT-1 §3.4 —
  base names are lowercase letters/digits/underscores; an ``.entity`` name also
  obeys the slot-name rule (not beginning with a digit).
- *not-a-BCP-47 directory* → OVOS-INTENT-2 §2 — "Language directories are named
  with BCP-47 language tags".
- *``.rx`` regex resource* → deprecated — a regex resource is not one of the
  defined roles, and the slot it captures belongs in an ``.intent`` template.
  Reported at :data:`RX_SEVERITY`, a WARNING while skills still ship them, an
  ERROR once they do not.
- *legacy extension / unknown role* → OVOS-INTENT-2 §1 + §5 — only the six
  defined roles exist; a loader "MUST NOT introduce additional resource file
  roles". Legacy Mycroft types are flagged, not parsed.
- *named slot in a slot-free role* → OVOS-INTENT-2 §4.3 — ``.entity`` / ``.voc``
  / ``.blacklist`` are slot-free.
- *template syntax* → OVOS-INTENT-1 §3.6 (delegated to
  :func:`~ovos_spec_tools.expansion.expand`).
- *slot-set consistency* → OVOS-INTENT-2 §4.2 (``.dialog`` only): a ``.dialog``
  whose phrases declare different slot sets is an ERROR (the caller fills the
  slots of the rendered phrase, so all phrases must expose the same slots).
  ``.intent`` templates MAY declare different slot sets — their union is the
  intent's slot set (OVOS-INTENT-2 §4.1, OVOS-INTENT-3 §5.1) — and are NOT
  flagged.
- *duplicate intent definition* → two shapes, and they rest on different
  authority. The file rule (in :func:`lint_locale`) flags an ``.intent`` base
  name ending in ``_alt``, ``_alias``, ``_extra`` or ``_2``..``_9``: a project
  policy that keeps one intent's phrasings in one file. No clause forbids the
  second file — under OVOS-INTENT-2 §4.1 the base name is the intent name, so
  the two files are two conformant intent names. The source rule (in
  :func:`lint_skill_source`) flags a second template registration on one
  method — several resource-naming ``@intent_handler`` decorators, or a
  handler whose whole body calls another handler — which OVOS-INTENT-3 §8
  refuses: "at most one registration per method per intent".
- *unpaired ``.blacklist``* → OVOS-INTENT-2 §4.3 — a ``.blacklist`` pairs
  by base name with either an ``.intent`` (match suppression: "paired by base
  name with exactly one ``.intent``") or an ``.entity`` / ``{slot}`` /
  vocabulary (slot-value exclusion: "its phrase set lists values that MUST
  NOT fill that slot"). A ``.blacklist`` that matches neither is inert and
  is flagged; ``{slot}`` names declared inline in an ``.intent`` template
  count as a pairing target.
- *required slot declared by no template* → OVOS-INTENT-3 §5.3 — "A required
  slot MUST be declared by at least one template in the intent … a tool MUST
  reject the definition at registration time." This is an intent-**definition**
  rule, not a single-file rule: ``required_slots`` lives above the raw
  ``.intent`` file. The locale linter (which sees only files) cannot enforce
  it; the check is exposed as :func:`validate_required_slots` (raises) and
  :func:`lint_required_slots` (returns a :class:`Finding`) for the
  registration/loading path that has both the ``required_slots`` list and the
  templates in hand.

Exposed as the ``ovos-spec-lint`` command::

    ovos-spec-lint path/to/locale

The argument may be a ``locale/`` directory (every language subdirectory is
checked) or a single ``<lang>/`` directory. The parent of that target is also
read as the skill's Python source, for the duplicate-binding rule; give
``--skill-source`` another path, or an empty one to switch that rule off.

The ``--spec-version`` option additionally flags features newer than a target
OVOS spec version, for skills that must run on older deployments:

- **0** — the legacy, undocumented Mycroft/OVOS de-facto behaviour;
- **1** — the formalized specs; adds the ``.blacklist`` role;
- **2** — adds ``<name>`` inline vocabulary references;
- **3** — adds the ``.prompt`` role.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ovos_spec_tools.expansion import (
    REGISTERED_TYPES,
    MalformedTemplate,
    expand,
    fold_double_braces,
    strip_type_prefixes,
    bare_pipe_reason,
    BARE_PIPE_ROLES,
)
from ovos_spec_tools.resources import (
    PROMPT_ROLE,
    SLOT_BEARING_ROLES,
    SLOT_FREE_ROLES,
    read_prompt_file,
    read_resource_file,
    read_resource_file_numbered,
)

__all__ = [
    "Finding",
    "lint_locale",
    "lint_skill_source",
    "RX_SEVERITY",
    "declared_slots",
    "declared_slot_types",
    "validate_required_slots",
    "lint_required_slots",
    "validate_slot_types",
    "lint_slot_types",
    "main",
]

# The six OVOS-INTENT-2 resource roles.
ROLE_EXTENSIONS = SLOT_BEARING_ROLES + SLOT_FREE_ROLES + (PROMPT_ROLE,)
# File types OVOS-INTENT-2 deliberately does not define — flagged, not parsed.
LEGACY_EXTENSIONS = (".rx", ".value", ".list", ".word", ".template", ".qml")

# The OVOS spec version that introduced each feature. This ladder is a *tooling*
# concept, not a clause in any single spec: it lets a skill target an older
# deployment by flagging roles/tokens that a runtime predating their
# introduction will silently ignore (a forward-compatibility lint, not a
# conformance check). Mapping: V1 = the formalized OVOS-INTENT-1/2 (adds the
# `.blacklist` role over the legacy V0 set), V2 = the `<name>` inline vocabulary
# reference (OVOS-INTENT-1 §3.7), V3 = the `.prompt` role (OVOS-INTENT-2 §4.4).
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
# A base name that ends this way names a SECOND definition of an intent the
# tree already defines: `create_alarm_alt.intent` beside `create_alarm.intent`.
# This is a project policy and not a spec rule. OVOS-INTENT-2 §4.1 makes the
# base name the intent name, so both files are conformant intent names, and no
# clause of OVOS-INTENT-1 to -4 forbids the second one. The policy keeps one
# intent's phrasings in one file, where a reader finds them.
#
# The suffix list is closed on purpose, and it is NOT widened to "any base
# that is another intent's base plus a suffix". A name alone cannot tell a
# second spelling of one intent from a related but distinct intent:
# `set_alarm_recurring`, `play_music_playlist` and `create_reminder_recurring`
# are all well-formed intent names. A wider rule would make every such pair an
# error and would be wrong more often than right.
#
# What decides those cases is not the name but the binding: if both files
# resolve to one handler, `lint_skill_source` reports it under OVOS-INTENT-3
# §8. The source rule is the instrument for that shape, and the file rule
# keeps the suffixes that can only mean "another copy".
_DUPLICATE_SUFFIX_RE = re.compile(r"^(?P<base>[a-z0-9_]*[a-z0-9])"
                                  r"_(?:alt|alias|extra|[2-9])$")
_TYPED_SLOT_RE = re.compile(r"\{([a-z][a-z0-9_]*):([a-z][a-z0-9_]*)\}")

ERROR = "error"
WARNING = "warning"

# The severity of a `.rx` regex resource. A regex resource is deprecated: a
# skill models the slot in an `.intent` file instead.
#
# It stays a WARNING while skills still ship regex resources, so the rule does
# not fail a build for files the author cannot drop in the same commit. Two
# repositories hold them: ovos-skill-weather, 24 files, and
# ovos-skill-easter-eggs, 1 file. Change this to ERROR when no skill ships a
# `.rx`, and re-count the org first rather than trusting this line. The census
# is in knowledge/wiki/audits/ci/rx-files.md. `--strict` fails on it either
# way.
RX_SEVERITY = WARNING


@dataclass
class Finding:
    """One problem found by the linter.

    Severity is :data:`ERROR` for a spec **MUST** violation (a malformed
    template, a duplicate ``(role, base name)``, an empty file, a slot in a
    slot-free role) and :data:`WARNING` for a **SHOULD**/advisory issue (a
    legacy file type, a non-BCP-47 directory name, an unpaired ``.blacklist``).
    Only errors fail a non-``--strict`` run.

    Attributes:
        severity: :data:`ERROR` or :data:`WARNING`.
        path: the offending file or directory, as a string.
        message: a human-readable description, citing the spec clause violated.
        line: the 1-based file line the finding points at, when the finding is
            about one template rather than the file as a whole. Optional and
            last, so every existing caller and every existing ``Finding(...)``
            keeps working unchanged.
    """

    severity: str  # ERROR or WARNING
    path: str
    message: str
    line: Optional[int] = None

    def __str__(self) -> str:
        where = self.path if self.line is None else f"{self.path}:{self.line}"
        return f"{where}: {self.severity}: {self.message}"


def declared_slots(templates: Sequence[str]) -> frozenset:
    """The union of the named slots declared across ``templates``.

    An intent's slot set is the **union** of the slots declared by its
    templates (OVOS-INTENT-2 §4.1, OVOS-INTENT-3 §5.1): the engine extracts
    only the slots of whichever template matched, so a slot the intent can
    ever fill is one declared by *some* template. Both equivalent spellings
    ``{name}`` and ``{{name}}`` (OVOS-INTENT-1 §3.4) count, so each template is
    folded to the single-brace canonical form before its slots are read.

    Args:
        templates: the template lines of one ``.intent`` definition.

    Returns:
        The frozen union of every named slot any template declares.
    """
    slots: set = set()
    for template in templates:
        bare = strip_type_prefixes(fold_double_braces(template))
        slots.update(_SLOT_RE.findall(bare))
    return frozenset(slots)


def validate_required_slots(
        required_slots: Sequence[str],
        templates: Sequence[str]) -> None:
    """Verify every required slot is declared by at least one template (§5.3).

    OVOS-INTENT-3 §5.3 makes this a **MUST** at registration time: "A required
    slot MUST be declared by at least one template in the intent. Declaring a
    required slot that no template mentions is malformed: the intent can never
    match, and a tool MUST reject the definition at registration time."

    ``required_slots`` is an intent-**definition** field — it lives above the
    raw ``.intent`` file, alongside the templates. This validator is the place
    that sees both together; call it when registering or loading an intent
    definition so a malformed one (a required slot no template can fill) is
    rejected before it can silently never fire.

    Args:
        required_slots: the slot names the intent declares as required.
        templates: the intent's template lines (its ``.intent`` samples).

    Raises:
        MalformedTemplate: a required slot is declared by no template, so the
            intent can never match (OVOS-INTENT-3 §5.3).
    """
    available = declared_slots(templates)
    missing = [name for name in required_slots if name not in available]
    if missing:
        have = "{" + ", ".join(sorted(available)) + "}" if available else "{}"
        raise MalformedTemplate(
            f"required slot(s) {{{', '.join(missing)}}} declared by no "
            f"template — the intent's templates declare only {have}, so the "
            "intent can never match. A required slot MUST be declared by at "
            "least one template (OVOS-INTENT-3 §5.3)")


def lint_required_slots(
        path: str,
        required_slots: Sequence[str],
        templates: Sequence[str]) -> List[Finding]:
    """Lint an intent's ``required_slots`` against its templates (§5.3).

    A :class:`Finding`-returning wrapper over :func:`validate_required_slots`,
    for callers that lint intent definitions (where ``required_slots`` metadata
    is available alongside the templates) and want findings rather than an
    exception. Each undeclared required slot is an :data:`ERROR` (a §5.3 MUST).

    Args:
        path: the offending intent's identifier (file path or name), reported
            on the finding.
        required_slots: the slot names the intent declares as required.
        templates: the intent's template lines.

    Returns:
        One :data:`ERROR` finding if any required slot is undeclared, else an
        empty list.
    """
    try:
        validate_required_slots(required_slots, templates)
    except MalformedTemplate as exc:
        return [Finding(ERROR, path, str(exc))]
    return []


def declared_slot_types(templates: Sequence[str]) -> Dict[str, str]:
    """The ``slot_types`` map declared by ``templates`` (OVOS-INTENT-4 §6.1).

    Reads every registered type prefix (OVOS-INTENT-1 §3.4, §5.6) off
    ``templates`` and maps each slot's bare name to its declared type. Only
    registered types (:data:`~ovos_spec_tools.expansion.REGISTERED_TYPES`) are
    reported — an unregistered prefix degrades to an untyped slot (§3.6) and
    so declares no type. When two templates disagree on a slot's type, the
    first-seen prefix wins.

    Args:
        templates: the template lines of one intent definition.

    Returns:
        A ``slot name -> type name`` map, for the optional ``slot_types``
        field of the OVOS-INTENT-4 §6.1 registration payload.
    """
    slot_types: Dict[str, str] = {}
    for template in templates:
        for slot_type, name in _TYPED_SLOT_RE.findall(fold_double_braces(template)):
            if slot_type in REGISTERED_TYPES:
                slot_types.setdefault(name, slot_type)
    return slot_types


def validate_slot_types(
        slot_types: Dict[str, str],
        templates: Sequence[str]) -> None:
    """Validate a ``slot_types`` map against its templates (§6.1, §5.6).

    Each key MUST name a slot the templates declare (§5.5: a type prefix does
    not change which slot set a template declares) and each value MUST be a
    registered type (§5.6): an unregistered type cannot be declared, since the
    grammar itself degrades an unregistered prefix to an untyped slot.

    Args:
        slot_types: the ``slot name -> type name`` map to validate.
        templates: the intent's template lines.

    Raises:
        MalformedTemplate: a key names a slot declared by no template, or a
            value is not a registered type.
    """
    available = declared_slots(templates)
    for name, slot_type in slot_types.items():
        if name not in available:
            raise MalformedTemplate(
                f"slot_types names {name!r}, which no template declares "
                f"(OVOS-INTENT-1 §5.5, OVOS-INTENT-4 §6.1)")
        if slot_type not in REGISTERED_TYPES:
            raise MalformedTemplate(
                f"slot_types[{name!r}] = {slot_type!r} is not a registered "
                f"type; registered types are {REGISTERED_TYPES} "
                f"(OVOS-INTENT-1 §5.6)")


def lint_slot_types(
        path: str,
        slot_types: Dict[str, str],
        templates: Sequence[str]) -> List[Finding]:
    """Lint an intent's ``slot_types`` against its templates (§6.1, §5.6).

    A :class:`Finding`-returning wrapper over :func:`validate_slot_types`,
    mirroring :func:`lint_required_slots`.

    Args:
        path: the offending intent's identifier (file path or name).
        slot_types: the ``slot name -> type name`` map to validate.
        templates: the intent's template lines.

    Returns:
        One :data:`ERROR` finding if ``slot_types`` is invalid, else an empty
        list.
    """
    try:
        validate_slot_types(slot_types, templates)
    except MalformedTemplate as exc:
        return [Finding(ERROR, path, str(exc))]
    return []


def lint_locale(path, spec_version: int = DEFAULT_SPEC_VERSION) -> List[Finding]:
    """Lint a locale directory, or a single language directory.

    The argument is dispatched by its name: a directory whose name matches the
    BCP-47 shape (OVOS-INTENT-2 §2) is treated as a single ``<lang>/`` tree;
    anything else is treated as the ``locale/`` root and each immediate
    subdirectory is linted as a language tree. This lets the linter accept
    either ``locale`` or ``locale/en-US`` as its target.

    Args:
        path: a ``locale/`` directory or a single ``<lang>/`` directory.
        spec_version: the target OVOS spec version; a resource using a feature
            newer than it is flagged (see the module docstring's version ladder).

    Returns:
        Every :class:`Finding`, in file order — never short-circuiting, so one
        run surfaces all problems. A non-directory ``path`` yields a single
        :data:`ERROR` finding.
    """
    root = Path(path)
    if not root.is_dir():
        return [Finding(ERROR, str(root), "not a directory")]

    if _LANG_TAG_RE.fullmatch(root.name):
        return _lint_language_tree(root, spec_version)

    findings: List[Finding] = []
    for child in sorted(root.iterdir()):
        if child.is_file() and child.suffix in ROLE_EXTENSIONS:
            # §2: resources live under locale/<lang>/, never loose at the root.
            findings.append(Finding(
                WARNING, str(child),
                "resource file is not inside a language directory "
                "(OVOS-INTENT-2 §2)"))
    language_dirs = [c for c in sorted(root.iterdir()) if c.is_dir()]
    if not language_dirs:
        findings.append(Finding(
            WARNING, str(root),
            "no language directories found (OVOS-INTENT-2 §2)"))
    for language_dir in language_dirs:
        findings.extend(_lint_language_tree(language_dir, spec_version))
    return findings


def _lint_language_tree(language_dir: Path, spec_version: int) -> List[Finding]:
    """Lint one ``<lang>/`` directory and all its subdirectories."""
    findings: List[Finding] = []
    if not _LANG_TAG_RE.fullmatch(language_dir.name):
        # §2: "Language directories are named with BCP-47 language tags."
        findings.append(Finding(
            WARNING, str(language_dir),
            f"directory name {language_dir.name!r} is not a BCP-47 "
            f"language tag (OVOS-INTENT-2 §2)"))

    role_files: List[Path] = []
    for path in sorted(language_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix in ROLE_EXTENSIONS:
            role_files.append(path)
        elif path.suffix == ".rx":
            # A regex resource is deprecated: the slot it captures belongs in
            # an .intent template, which every engine reads. See RX_SEVERITY.
            findings.append(Finding(
                RX_SEVERITY, str(path),
                "regex resources are deprecated; model the slot in an "
                ".intent file (OVOS-INTENT-2 §1)"))
        elif path.suffix in LEGACY_EXTENSIONS:
            # §1 defines exactly six roles; §5 forbids a loader inventing more.
            # Legacy Mycroft types are flagged (not parsed) so an author knows
            # the file will be silently ignored by a conformant loader.
            findings.append(Finding(
                WARNING, str(path),
                f"{path.suffix} is a legacy file type, not an "
                f"OVOS-INTENT-2 resource role (OVOS-INTENT-2 §1)"))

    if not role_files:
        findings.append(Finding(
            WARNING, str(language_dir),
            "language directory contains no resource files "
            "(OVOS-INTENT-2 §2)"))

    # Duplicate (role, base name) within one language tree (OVOS-INTENT-2 §2).
    first_seen: Dict[tuple, Path] = {}
    for path in role_files:
        key = (path.suffix, path.stem)
        if key in first_seen:
            findings.append(Finding(
                ERROR, str(path),
                f"duplicate {path.suffix} resource {path.stem!r} — also at "
                f"{first_seen[key]} (OVOS-INTENT-2 §2: a (role, base name) "
                f"must be unique per language tree)"))
        else:
            first_seen[key] = path

    # A duplicate intent definition: a second .intent file for an intent the
    # tree already defines. A project policy; see _DUPLICATE_SUFFIX_RE.
    intent_stems = {stem for (ext, stem) in first_seen if ext == ".intent"}
    for path in role_files:
        if path.suffix != ".intent":
            continue
        match = _DUPLICATE_SUFFIX_RE.fullmatch(path.stem)
        if match is None:
            continue
        base = match.group("base")
        target = f"{base}.intent"
        if base in intent_stems:
            where = f"fold its templates into {target} and delete this file"
        else:
            where = (f"there is no {target} in this tree: rename this file to "
                     f"the intent it defines, or fold it into the file that "
                     f"defines it")
        findings.append(Finding(
            ERROR, str(path),
            f"duplicate intent definition: {path.name} names a second "
            f"definition of {base!r} — {where}. One intent has one .intent "
            f"file and its alternatives are its templates"))

    # Per-role spec-version gate (a role newer than the target is flagged),
    # plus the `.blacklist` pairing check (§4.3).
    intent_names = {stem for (ext, stem) in first_seen if ext == ".intent"}
    # §4.3: a .blacklist pairs by base name with EITHER an .intent (match
    # suppression) OR an .entity / vocabulary (slot-value exclusion). Slot
    # names may also be declared inline as `{slot}` in an .intent template.
    slot_names = {stem for (ext, stem) in first_seen if ext in (".entity", ".voc")}
    for (ext, stem), path in first_seen.items():
        if ext == ".intent":
            try:
                slot_names.update(declared_slots(read_resource_file(path)))
            except (OSError, UnicodeError):
                pass
    for path in role_files:
        since = _ROLE_SINCE.get(path.suffix)
        if since is not None and spec_version < since:
            findings.append(Finding(
                WARNING, str(path),
                f"the {path.suffix} role requires spec version {since}; a "
                f"version-{spec_version} runtime ignores it"))
        if (path.suffix == ".blacklist"
                and path.stem not in intent_names
                and path.stem not in slot_names):
            # §4.3: an unpaired .blacklist — matching neither an .intent to
            # suppress nor an .entity/{slot}/vocabulary to exclude — is inert.
            findings.append(Finding(
                WARNING, str(path),
                f"blacklist {path.stem!r} has no matching {path.stem}.intent "
                f"to suppress nor {path.stem}.entity/{{{path.stem}}} slot to "
                f"exclude (OVOS-INTENT-2 §4.3)"))

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
    """Lint one resource file: naming, then the syntax of every template.

    Order mirrors the loader steps of OVOS-INTENT-2 §5: naming (§2), then the
    common reader (§3), then the per-format rule (§4) — for templated roles via
    a conformant expander (OVOS-INTENT-1), for ``.prompt`` as a whole-file
    non-empty check (§4.4).

    Args:
        path: the resource file to lint.
        vocabularies: every ``.voc`` in this language tree, so a ``<name>``
            reference (OVOS-INTENT-1 §3.7) resolves during expansion instead of
            being mis-reported as undefined.
        spec_version: the target spec version, for the feature gates.

    Returns:
        Every :class:`Finding` for this file.
    """
    findings: List[Finding] = []
    extension = path.suffix
    base_name = path.stem

    # --- naming (OVOS-INTENT-2 §2) ------------------------------------------
    if not _BASE_NAME_RE.fullmatch(base_name):
        findings.append(Finding(
            ERROR, str(path),
            f"base name {base_name!r} must be lowercase ASCII letters, "
            f"digits and underscores only (OVOS-INTENT-2 §2)"))
    if extension == ".entity" and not _SLOT_NAME_RE.fullmatch(base_name):
        # §2: where a base name names a slot (an .entity names its {slot}), it
        # additionally obeys the slot-name rule of OVOS-INTENT-1 §3.4.
        findings.append(Finding(
            ERROR, str(path),
            f".entity base name {base_name!r} names a slot and must not "
            f"begin with a digit (OVOS-INTENT-2 §2 / OVOS-INTENT-1 §3.4)"))
    if path.name != path.name.lower():
        # §2: base names and extensions are lowercase. Reported as a warning
        # (not an error) because the casefold is recoverable on case-insensitive
        # filesystems; on case-sensitive ones it will fail lookup.
        findings.append(Finding(
            WARNING, str(path),
            "file name should be lowercase (OVOS-INTENT-2 §2)"))

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

    # --- §3.6 malformed form: a pipe outside a group -------------------------
    # OVOS-INTENT-1 §3.6 names the form: a `|` inside no group, where a group
    # is `( ... )` or `[ ... ]`. `plata|argent` in an .entity is malformed,
    # and the author means two lines or one group. The four input-direction
    # roles are held to it under §2, and .dialog with them, because
    # OVOS-INTENT-2 §4.2 makes a .dialog line a template whose metacharacters
    # are structural. Reported with the line, because the author has to open
    # it.
    bare_pipe_lines = set()
    if extension in BARE_PIPE_ROLES:
        for number, line in read_resource_file_numbered(path):
            reason = bare_pipe_reason(line)
            if reason is not None:
                bare_pipe_lines.add(line)
                findings.append(Finding(
                    ERROR, str(path), f"{reason}  [in: {line!r}]", number))

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
        if template in bare_pipe_lines:
            # Already reported above, with the line number this loop does not
            # have. ``expand`` raises for the same fault (OVOS-INTENT-1 §3.6),
            # and one fault must not be reported twice.
            continue
        try:
            samples = expand(template, vocabularies)
        except MalformedTemplate as exc:
            findings.append(Finding(
                ERROR, str(path), f"{exc}  [in: {template!r}]"))
            continue
        if slot_free and any("{" in sample for sample in samples):
            # §4.3: .entity/.voc/.blacklist are the slot-free format — no {name}.
            findings.append(Finding(
                ERROR, str(path),
                f"{extension} is slot-free but a template contains a named "
                f"slot (OVOS-INTENT-2 §4.3)  [in: {template!r}]"))
        if slot_bearing:
            # Fold ``{{name}}`` to ``{name}`` and strip any type prefix first
            # (OVOS-INTENT-1 §3.4, §5.5) so the equivalent slot spellings yield
            # the identical slot set and a template mixing them is not
            # mis-flagged as slot-inconsistent.
            bare = strip_type_prefixes(fold_double_braces(template))
            slot_sets.append(frozenset(_SLOT_RE.findall(bare)))

    # --- slot consistency: `.dialog` ONLY -----------------------------------
    # `.dialog` phrases MUST all declare the same slot set: the caller fills the
    # slots of whichever phrase is rendered, so every phrase must expose the
    # identical slots (OVOS-INTENT-2 §4.2; OVOS-INTENT-1 §5.5). A `.dialog`
    # whose phrases diverge is malformed — ERROR.
    #
    # `.intent` is the deliberate OPPOSITE: its templates MAY declare different
    # slot sets, and the intent's slot set is their union — the engine extracts
    # only the slots of the template that matched (OVOS-INTENT-2 §4.1,
    # OVOS-INTENT-3 §5.1). A tool MUST NOT reject a `.intent` for divergent
    # slots, so divergence is NOT flagged for the `.intent` role.
    if extension == ".dialog" and len(set(slot_sets)) > 1:
        findings.append(Finding(
            ERROR, str(path),
            "a .dialog's phrases declare different slot sets — every phrase in "
            "one .dialog MUST declare the same {slots} (OVOS-INTENT-2 §4.2; "
            "OVOS-INTENT-1 §5.5)"))

    return findings


_HANDLER_DECORATORS = ("intent_handler", "intent_file_handler")
# A directory whose Python is not the skill's own source: a checked-out
# virtual environment, vendored third-party code, or the skill's test tree.
# A finding in any of them is about somebody else's file.
_SKIPPED_DIRS = {".git", ".venv", "venv", "env", ".env", "virtualenv",
                 ".direnv", "site-packages", "test", "tests", "build", "dist",
                 "node_modules", "__pycache__", ".tox", ".eggs"}


def _decorator_name(node: ast.expr) -> Optional[str]:
    """The bare name of a decorator, whether it is called or not."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _decorator_resource(node: ast.expr) -> Optional[str]:
    """The resource string an ``@intent_handler("x.intent")`` names."""
    if isinstance(node, ast.Call) and node.args:
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    return None


def _intent_decorators(func: ast.AST) -> List[ast.expr]:
    """Every ``@intent_handler``-family decorator on ``func``."""
    return [d for d in getattr(func, "decorator_list", [])
            if _decorator_name(d) in _HANDLER_DECORATORS]


def _delegates_to(func: ast.AST) -> Optional[str]:
    """The method name ``func`` does nothing but call, if that is all it does.

    A handler whose whole body is ``return self.other(message)`` (or the bare
    call) is not a second intent: it is a second binding to the first one.
    A docstring before the call is ignored, and nothing else is allowed.
    """
    body = list(getattr(func, "body", []))
    if body and isinstance(body[0], ast.Expr) \
            and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    if len(body) != 1:
        return None
    statement = body[0]
    if isinstance(statement, ast.Return):
        call = statement.value
    elif isinstance(statement, ast.Expr):
        call = statement.value
    else:
        return None
    if not isinstance(call, ast.Call):
        return None
    target = call.func
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) \
            and target.value.id == "self":
        return target.attr
    return None


def _handler_scopes(tree: ast.Module) -> List[List[ast.stmt]]:
    """Every name scope that can hold intent handlers.

    A method name is only a name inside its own class, so two classes in one
    module may each define ``handle_play`` without defining one intent twice.
    The module body is a scope of its own, for a plain decorated function.
    """
    scopes = [tree.body]
    scopes.extend(node.body for node in ast.walk(tree)
                  if isinstance(node, ast.ClassDef))
    return scopes


def lint_skill_source(path) -> List[Finding]:
    """Lint the Python source of a skill for duplicate intent definitions.

    The locale linter sees files and cannot see a binding: two ``.intent``
    files stacked on one method, or a handler that only calls another, define
    one intent twice as surely as an ``_alt`` resource does. This reads the
    decorators instead, with :mod:`ast`, and imports nothing.

    Args:
        path: a directory to walk, or a single ``.py`` file.

    Returns:
        Every :class:`Finding`, in file order. A file that does not parse
        yields one :data:`WARNING` and is skipped — a syntax error is the
        business of a Python linter, not of this one.
    """
    root = Path(path)
    if root.is_file():
        sources = [root]
    elif root.is_dir():
        sources = [f for f in sorted(root.rglob("*.py"))
                   if not _SKIPPED_DIRS & set(f.relative_to(root).parts)]
    else:
        return [Finding(ERROR, str(root), "not a file or a directory")]

    findings: List[Finding] = []
    for source in sources:
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, SyntaxError) as exc:
            findings.append(Finding(
                WARNING, str(source), f"cannot be parsed, so it was not "
                                      f"checked for duplicate intents: {exc}"))
            continue

        for scope in _handler_scopes(tree):
            handlers: Dict[str, List[ast.expr]] = {}
            functions: Dict[str, ast.AST] = {}
            for node in scope:
                if not isinstance(node, (ast.FunctionDef,
                                         ast.AsyncFunctionDef)):
                    continue
                decorators = _intent_decorators(node)
                if not decorators:
                    continue
                functions[node.name] = node
                handlers[node.name] = decorators
                # Only a decorator that names a template resource counts. A
                # keyword registration beside a template one is the pair
                # OVOS-INTENT-3 §2 permits: "An intent MAY carry one
                # registration per method — two training-data representations
                # of the same handler".
                templates = [r for r in
                             (_decorator_resource(d) for d in decorators) if r]
                if len(templates) > 1:
                    listed = ", ".join(templates)
                    findings.append(Finding(
                        ERROR, str(source),
                        f"duplicate intent definition: {len(templates)} "
                        f"template registrations are stacked on "
                        f"{node.name}() ({listed}) — OVOS-INTENT-3 §8 allows "
                        f"at most one registration per method per intent. "
                        f"Fold the templates into one .intent file and keep "
                        f"one decorator"))

            for name, node in functions.items():
                delegate = _delegates_to(node)
                if delegate is None or delegate not in handlers \
                        or delegate == name:
                    continue
                mine = next((r for r in
                             (_decorator_resource(d) for d in handlers[name])
                             if r), f"the resource on {name}()")
                theirs = next((r for r in
                               (_decorator_resource(d)
                                for d in handlers[delegate])
                               if r), f"the resource on {delegate}()")
                findings.append(Finding(
                    ERROR, str(source),
                    f"duplicate intent definition: {name}() does nothing but "
                    f"call {delegate}(), so {mine} and {theirs} define one "
                    f"intent twice. Fold the templates into {theirs} and "
                    f"delete {name}() (OVOS-INTENT-3 §8)"))
    return findings


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the ``ovos-spec-lint`` command.

    Lints the target, prints every :class:`Finding`, then a count summary.

    Args:
        argv: command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        ``0`` on success; ``1`` if any error was found, or — with ``--strict``
        — if any warning was found (so a CI step can gate on locale health).
    """
    parser = argparse.ArgumentParser(
        prog="ovos-spec-lint",
        description="Validate OVOS locale resource files against "
                    "OVOS-INTENT-1 (syntax) and OVOS-INTENT-2 (naming).")
    parser.add_argument(
        "locale", help="path to a locale/ directory, or a <lang>/ directory")
    parser.add_argument(
        "--skill-source", default=None,
        help="path to the skill's Python source, checked for duplicate "
             "intent bindings. Default: the parent of the locale target, "
             "when it holds Python files. Pass an empty value to skip.")
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

    source = args.skill_source
    if source is None:
        # The fleet runs `ovos-spec-lint locale`, from the skill root. Take
        # that root, so the binding check needs no workflow change; a tree
        # with no Python in it is not a skill and is left alone.
        parent = Path(args.locale).resolve().parent
        if parent.is_dir() and any(parent.rglob("*.py")):
            source = str(parent)
    if source:
        findings.extend(lint_skill_source(source))
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
