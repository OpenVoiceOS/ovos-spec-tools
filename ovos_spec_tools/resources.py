"""Reference loader for OVOS-INTENT-2 — Locale Resource Formats.

This module is the reference implementation of the loader of OVOS-INTENT-2: it
discovers a skill's locale resource files, reads them with the common reader
(§3), and loads each of the five resource roles per its format (§4).

The five roles, by extension:

- ``.intent`` — slot-bearing intent training samples;
- ``.dialog`` — slot-bearing spoken-response phrases;
- ``.entity`` — slot-free example values for a slot;
- ``.voc`` — slot-free vocabulary;
- ``.blacklist`` — slot-free intent-suppression phrases.

The user-data path of the override precedence (§2.1) is **assistant-defined**;
this module takes it as a parameter and imports no configuration.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Protocol

from ovos_spec_tools.expansion import MalformedTemplate, expand

__all__ = [
    "LocaleResources",
    "LanguageMatcher",
    "MalformedResource",
    "read_resource_file",
    "SLOT_BEARING_ROLES",
    "SLOT_FREE_ROLES",
]

# Resource roles, by file extension (OVOS-INTENT-2 §1).
SLOT_BEARING_ROLES = (".intent", ".dialog")
SLOT_FREE_ROLES = (".entity", ".voc", ".blacklist")

# Default cap for the smart language fallback (OVOS-INTENT-2 §2.2): the
# `langcodes` library treats a tag distance below 10 as a usable regional
# match.
DEFAULT_MAX_LANGUAGE_DISTANCE = 10


class LanguageMatcher(Protocol):
    """Computes the distance between two BCP-47 language tags.

    A lower distance is a closer match; ``0`` is exact. The ``langcodes``
    module satisfies this protocol structurally — its ``tag_distance``
    function has exactly this signature — so `langcodes` itself can be passed
    wherever a ``LanguageMatcher`` is expected.
    """

    def tag_distance(self, desired: str, supported: str) -> int:
        ...


def _default_language_matcher() -> Optional["LanguageMatcher"]:
    """Return the ``langcodes`` module if it is installed, else ``None``.

    `langcodes` is an optional dependency; without it the smart language
    fallback is disabled and only exact (case-insensitive) tags resolve.
    """
    try:
        import langcodes
    except ImportError:
        return None
    return langcodes


class MalformedResource(ValueError):
    """A resource file or skill layout that violates OVOS-INTENT-2.

    Raised for an empty resource file (§5), a duplicate ``(role, base name)``
    within one language tree (§2), and a named slot in a slot-free role (§4.3).
    """


def read_resource_file(path: Path) -> List[str]:
    """Apply the OVOS-INTENT-2 §3 common reader to one file.

    The file is read as UTF-8, a leading byte-order mark is discarded, and both
    ``LF`` and ``CRLF`` line endings are accepted. Each line is stripped; blank
    lines and ``#``-comment lines are dropped. The surviving lines — each one
    template — are returned in order.
    """
    text = path.read_text(encoding="utf-8-sig")  # utf-8-sig discards a BOM
    templates: List[str] = []
    for raw_line in text.splitlines():  # splitlines() accepts LF and CRLF
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        templates.append(line)
    return templates


class LocaleResources:
    """Loads OVOS-INTENT-2 resource files for one skill in one language.

    A resource is resolved through the override precedence of §2.1 — user
    overrides, then skill resources, then core resources — searching each
    source's ``<lang>/`` directory and all its subdirectories recursively.

    When the requested language has no directory, a **smart language
    fallback** (OVOS-INTENT-2 §2.2, non-normative) selects the nearest
    available language whose tag distance is within
    ``max_language_distance``. The fallback needs a :class:`LanguageMatcher`;
    by default the optional ``langcodes`` dependency supplies one, and the
    fallback is silently disabled if ``langcodes`` is not installed.
    """

    def __init__(self, lang: str, skill_locale: str,
                 core_locale: Optional[str] = None,
                 user_locale: Optional[str] = None,
                 language_matcher: Optional[LanguageMatcher] = None,
                 max_language_distance: int = DEFAULT_MAX_LANGUAGE_DISTANCE):
        """
        Args:
            lang: a BCP-47 language tag; compared case-insensitively (§2).
            skill_locale: path to the skill's ``locale/`` directory.
            core_locale: path to the assistant's core ``locale/`` directory.
            user_locale: path to the user-override ``locale/`` directory
                (its root is assistant-defined, §2.1).
            language_matcher: a :class:`LanguageMatcher` for the smart language
                fallback. Defaults to the ``langcodes`` module if installed.
            max_language_distance: the largest tag distance accepted by the
                fallback. ``0`` disables the fallback — only exact tags match.
        """
        self.lang = lang
        # Highest precedence first (§2.1): user, skill, core.
        self._sources: List[Path] = [
            Path(p) for p in (user_locale, skill_locale, core_locale)
            if p is not None
        ]
        if language_matcher is None:
            language_matcher = _default_language_matcher()
        self._language_matcher = language_matcher
        self.max_language_distance = max_language_distance

    def _lang_dir(self, source: Path) -> Optional[Path]:
        """The ``<lang>/`` directory under one source.

        An exact tag (case-insensitive, §2) wins. Failing that, the smart
        language fallback (§2.2) picks the nearest available language within
        ``max_language_distance``, if a :class:`LanguageMatcher` is available.
        """
        if not source.is_dir():
            return None
        subdirectories = [c for c in source.iterdir() if c.is_dir()]

        target = self.lang.lower()
        for child in subdirectories:
            if child.name.lower() == target:
                return child

        if self._language_matcher is None or self.max_language_distance <= 0:
            return None
        nearest: Optional[Path] = None
        nearest_distance = self.max_language_distance + 1
        for child in subdirectories:
            try:
                distance = self._language_matcher.tag_distance(
                    self.lang, child.name)
            except Exception:
                continue  # an unparseable directory name is simply not a match
            if distance < nearest_distance:
                nearest, nearest_distance = child, distance
        if nearest is not None and nearest_distance <= self.max_language_distance:
            return nearest
        return None

    def _locate(self, base_name: str, extension: str) -> Optional[Path]:
        """Find a resource file by ``(base name, extension)`` through the
        precedence chain. Returns the first match, or ``None``."""
        filename = base_name + extension
        for source in self._sources:
            lang_dir = self._lang_dir(source)
            if lang_dir is None:
                continue
            matches = sorted(p for p in lang_dir.rglob(filename) if p.is_file())
            if len(matches) > 1:
                raise MalformedResource(
                    f"duplicate resource {filename!r} within {lang_dir} — "
                    f"a (role, base name) must be unique per language tree")
            if matches:
                return matches[0]
        return None

    def vocabularies(self) -> Dict[str, List[str]]:
        """Every ``.voc`` reachable for this language, as a name→templates map
        suitable for resolving ``<name>`` references during expansion."""
        vocs: Dict[str, List[str]] = {}
        # Lowest precedence first, so a higher-precedence file overrides.
        for source in reversed(self._sources):
            lang_dir = self._lang_dir(source)
            if lang_dir is None:
                continue
            for path in lang_dir.rglob("*.voc"):
                if path.is_file():
                    vocs[path.stem] = read_resource_file(path)
        return vocs

    def entities(self) -> Dict[str, List[str]]:
        """Every ``.entity`` reachable for this language, as a name→value-set
        map — each value set expanded, with override precedence applied."""
        names = set()
        for source in self._sources:
            lang_dir = self._lang_dir(source)
            if lang_dir is None:
                continue
            for path in lang_dir.rglob("*.entity"):
                if path.is_file():
                    names.add(path.stem)
        return {name: self.load_entity(name) for name in sorted(names)}

    def _load_expanded(self, base_name: str, extension: str) -> List[str]:
        """Load a resource and expand it to its sample set."""
        path = self._locate(base_name, extension)
        if path is None:
            raise FileNotFoundError(
                f"no {extension} resource named {base_name!r} for "
                f"language {self.lang!r}")
        templates = read_resource_file(path)
        if not templates:
            raise MalformedResource(
                f"empty resource file {path} — every file must contribute at "
                f"least one template (§5)")
        vocabularies = self.vocabularies()
        slot_free = extension in SLOT_FREE_ROLES
        samples: List[str] = []
        for template in templates:
            for sample in expand(template, vocabularies):
                if slot_free and "{" in sample:
                    raise MalformedResource(
                        f"{extension} resource {path} is slot-free but "
                        f"template {template!r} contains a named slot")
                if sample not in samples:
                    samples.append(sample)
        return samples

    def load_intent(self, base_name: str) -> List[str]:
        """Load an ``.intent`` as its sample set, named slots intact (§4.1)."""
        return self._load_expanded(base_name, ".intent")

    def load_entity(self, base_name: str) -> List[str]:
        """Load an ``.entity`` value set (§4.3)."""
        return self._load_expanded(base_name, ".entity")

    def load_vocabulary(self, base_name: str) -> List[str]:
        """Load a ``.voc`` phrase set (§4.3)."""
        return self._load_expanded(base_name, ".voc")

    def load_blacklist(self, base_name: str) -> List[str]:
        """Load a ``.blacklist`` phrase set (§4.3)."""
        return self._load_expanded(base_name, ".blacklist")

    def load_dialog(self, base_name: str) -> List[str]:
        """Load a ``.dialog`` as its list of phrase strings.

        Unlike the other roles a ``.dialog`` is **not** expanded at load time —
        expansion happens per render, on the one phrase chosen (§4.2). The
        phrase strings are returned verbatim, for a dialog renderer to consume.
        """
        path = self._locate(base_name, ".dialog")
        if path is None:
            raise FileNotFoundError(
                f"no .dialog resource named {base_name!r} for "
                f"language {self.lang!r}")
        phrases = read_resource_file(path)
        if not phrases:
            raise MalformedResource(
                f"empty resource file {path} — every file must contribute at "
                f"least one template (§5)")
        return phrases
