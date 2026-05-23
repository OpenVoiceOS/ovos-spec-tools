"""Reference loader for OVOS-INTENT-2 — Locale Resource Formats.

This module is the reference implementation of the loader of OVOS-INTENT-2: it
discovers a skill's locale resource files, reads them with the common reader
(§3), and loads each of the six resource roles per its format (§4).

The six roles, by extension:

- ``.intent`` — slot-bearing intent training samples;
- ``.dialog`` — slot-bearing spoken-response phrases;
- ``.entity`` — slot-free example values for a slot;
- ``.voc`` — slot-free vocabulary;
- ``.blacklist`` — slot-free intent-suppression phrases;
- ``.prompt`` — a whole-file plain-text language-model prompt (§4.4).

The user-data path of the override precedence (§2.1) is **assistant-defined**;
this module takes it as a parameter and imports no configuration.

The **language is given per query**, not fixed at construction: a locale
folder is the multilingual unit of a skill, so one :class:`LocaleResources`
serves every language the skill ships.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from ovos_spec_tools.expansion import MalformedTemplate, expand
from ovos_spec_tools.language import (
    DEFAULT_MAX_LANGUAGE_DISTANCE,
    closest_lang,
    standardize_lang,
)

__all__ = [
    "LocaleResources",
    "MalformedResource",
    "iter_locale_dirs",
    "read_resource_file",
    "read_prompt_file",
    "SLOT_BEARING_ROLES",
    "SLOT_FREE_ROLES",
    "PROMPT_ROLE",
]

# Resource roles, by file extension (OVOS-INTENT-2 §1). The five template
# roles are line-oriented; `.prompt` is a single whole-file document (§4.4).
SLOT_BEARING_ROLES = (".intent", ".dialog")
SLOT_FREE_ROLES = (".entity", ".voc", ".blacklist")
PROMPT_ROLE = ".prompt"

# A resolver maps a requested language and the available language tags to the
# best one, or None — the signature of `ovos_spec_tools.language.closest_lang`.
LanguageResolver = Callable[[str, Sequence[str], int], Optional[str]]


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


def iter_locale_dirs(root: Path,
                     native_langs: Optional[Sequence[str]] = None,
                     max_distance: int = DEFAULT_MAX_LANGUAGE_DISTANCE
                     ):
    """Iterate ``<root>/locale/<lang>/`` subdirs as ``(lang, path)`` pairs.

    Each immediate subdirectory of ``<root>/locale/`` is treated as a locale
    tree; its name is normalized with :func:`standardize_lang` and yielded as
    the first item of the pair. The second item is the directory ``Path``.

    When ``native_langs`` is given, each subdir is matched against the natives
    via :func:`closest_lang` and yielded only when its closest native is within
    ``max_distance`` — useful for "a skill declares ``en``, the locale tree has
    ``en-US``, accept it" without forcing the caller to repeat that walk.

    Resource loaders (``.rx``, ``.dialog``, ``.voc``, ``.intent``, ``.json``)
    reinvent this walk by hand and disagree on the macro/full-tag policy. Use
    this and the disagreement goes away — locales are always discovered as
    full-tag directories, ``closest_lang`` reconciles at query time.

    ``root`` without a ``locale/`` child yields nothing.
    """
    root = Path(root)
    locales_root = root / "locale"
    if not locales_root.is_dir():
        return
    natives_norm = ([standardize_lang(l) for l in native_langs]
                    if native_langs is not None else None)
    for entry in sorted(locales_root.iterdir()):
        if not entry.is_dir():
            continue
        try:
            lang_norm = standardize_lang(entry.name)
        except Exception:
            continue
        if natives_norm is not None:
            if closest_lang(lang_norm, natives_norm,
                            max_distance=max_distance) is None:
                continue
        yield lang_norm, entry


def read_prompt_file(path: Path) -> str:
    """Read a ``.prompt`` whole and verbatim (OVOS-INTENT-2 §3, §4.4).

    A ``.prompt`` is **not** line-oriented: it is read whole, with no line
    stripping and no blank- or ``#``-comment-line filtering, because every
    character is part of the prompt. The file is UTF-8 and a leading
    byte-order mark is discarded.
    """
    return path.read_text(encoding="utf-8-sig")  # utf-8-sig discards a BOM


class LocaleResources:
    """Loads OVOS-INTENT-2 resource files for one skill, across languages.

    One instance serves **every language** a skill ships: the language is a
    parameter of each load call, not of the constructor, because a locale
    folder is the multilingual unit of a skill.

    A resource is resolved through the override precedence of §2.1 — user
    overrides, then skill resources, then core resources — searching each
    source's ``<lang>/`` directory and all its subdirectories recursively.

    When the requested language has no directory, a **smart language fallback**
    (OVOS-INTENT-2 §2.2, non-normative) selects the nearest available language.
    Resolution is done by :func:`ovos_spec_tools.language.closest_lang` and is
    re-run on every load, so one instance serves different languages — and
    different fallbacks. The fallback needs the optional ``langcodes``
    dependency; without it, only exact tags resolve.
    """

    def __init__(self, skill_locale: str,
                 core_locale: Optional[str] = None,
                 user_locale: Optional[str] = None,
                 lang_resolver: Optional[LanguageResolver] = None,
                 max_language_distance: int = DEFAULT_MAX_LANGUAGE_DISTANCE):
        """
        Args:
            skill_locale: path to the skill's ``locale/`` directory.
            core_locale: path to the assistant's core ``locale/`` directory.
            user_locale: path to the user-override ``locale/`` directory
                (its root is assistant-defined, §2.1).
            lang_resolver: ``(target, available, max_distance) -> best | None``;
                resolves a requested language against the available ones.
                Defaults to :func:`ovos_spec_tools.language.closest_lang`.
            max_language_distance: passed to the resolver — the fallback
                accepts a language whose tag distance is **below** this
                (default 10, §2.2). ``0`` disables the fallback.
        """
        # Highest precedence first (§2.1): user, skill, core.
        self._sources: List[Path] = [
            Path(p) for p in (user_locale, skill_locale, core_locale)
            if p is not None
        ]
        self._lang_resolver: LanguageResolver = (
            lang_resolver if lang_resolver is not None else closest_lang)
        self.max_language_distance = max_language_distance

    def _lang_dir(self, source: Path, lang: str) -> Optional[Path]:
        """The ``<lang>/`` directory for ``lang`` under one source.

        The language is resolved against the available subdirectories by the
        ``lang_resolver`` — an exact tag, or the smart fallback of §2.2.
        """
        if not source.is_dir():
            return None
        names = [c.name for c in source.iterdir() if c.is_dir()]
        match = self._lang_resolver(lang, names, self.max_language_distance)
        return (source / match) if match is not None else None

    def _locate(self, base_name: str, extension: str,
                lang: str) -> Optional[Path]:
        """Find a resource file by ``(base name, extension)`` in ``lang``
        through the precedence chain. Returns the first match, or ``None``."""
        filename = base_name + extension
        for source in self._sources:
            lang_dir = self._lang_dir(source, lang)
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

    def vocabularies(self, lang: str) -> Dict[str, List[str]]:
        """Every ``.voc`` reachable for ``lang``, as a name→templates map
        suitable for resolving ``<name>`` references during expansion."""
        vocs: Dict[str, List[str]] = {}
        # Lowest precedence first, so a higher-precedence file overrides.
        for source in reversed(self._sources):
            lang_dir = self._lang_dir(source, lang)
            if lang_dir is None:
                continue
            for path in lang_dir.rglob("*.voc"):
                if path.is_file():
                    vocs[path.stem] = read_resource_file(path)
        return vocs

    def entities(self, lang: str) -> Dict[str, List[str]]:
        """Every ``.entity`` reachable for ``lang``, as a name→value-set map —
        each value set expanded, with override precedence applied."""
        names = set()
        for source in self._sources:
            lang_dir = self._lang_dir(source, lang)
            if lang_dir is None:
                continue
            for path in lang_dir.rglob("*.entity"):
                if path.is_file():
                    names.add(path.stem)
        return {name: self.load_entity(name, lang) for name in sorted(names)}

    def _load_expanded(self, base_name: str, extension: str,
                       lang: str) -> List[str]:
        """Load a resource and expand it to its sample set."""
        path = self._locate(base_name, extension, lang)
        if path is None:
            raise FileNotFoundError(
                f"no {extension} resource named {base_name!r} for "
                f"language {lang!r}")
        templates = read_resource_file(path)
        if not templates:
            raise MalformedResource(
                f"empty resource file {path} — every file must contribute at "
                f"least one template (§5)")
        vocabularies = self.vocabularies(lang)
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

    def load_intent(self, base_name: str, lang: str) -> List[str]:
        """Load an ``.intent`` as its sample set, named slots intact (§4.1)."""
        return self._load_expanded(base_name, ".intent", lang)

    def load_entity(self, base_name: str, lang: str) -> List[str]:
        """Load an ``.entity`` value set (§4.3)."""
        return self._load_expanded(base_name, ".entity", lang)

    def load_vocabulary(self, base_name: str, lang: str) -> List[str]:
        """Load a ``.voc`` phrase set (§4.3)."""
        return self._load_expanded(base_name, ".voc", lang)

    def load_blacklist(self, base_name: str, lang: str) -> List[str]:
        """Load a ``.blacklist`` phrase set (§4.3)."""
        return self._load_expanded(base_name, ".blacklist", lang)

    def load_dialog(self, base_name: str, lang: str) -> List[str]:
        """Load a ``.dialog`` as its list of phrase strings.

        Unlike the other roles a ``.dialog`` is **not** expanded at load time —
        expansion happens per render, on the one phrase chosen (§4.2). The
        phrase strings are returned verbatim, for a dialog renderer to consume.
        """
        path = self._locate(base_name, ".dialog", lang)
        if path is None:
            raise FileNotFoundError(
                f"no .dialog resource named {base_name!r} for "
                f"language {lang!r}")
        phrases = read_resource_file(path)
        if not phrases:
            raise MalformedResource(
                f"empty resource file {path} — every file must contribute at "
                f"least one template (§5)")
        return phrases

    def load_prompt(self, base_name: str, lang: str) -> str:
        """Load a ``.prompt`` as its whole-file string (§4.4).

        A ``.prompt`` is read whole and verbatim — not split into templates,
        not line-filtered — and is returned for a prompt renderer to fill. See
        :class:`ovos_spec_tools.prompt.PromptRenderer`.

        Raises:
            FileNotFoundError: no such ``.prompt`` for ``lang``.
            MalformedResource: the file is empty or only whitespace (§5).
        """
        path = self._locate(base_name, PROMPT_ROLE, lang)
        if path is None:
            raise FileNotFoundError(
                f"no .prompt resource named {base_name!r} for "
                f"language {lang!r}")
        text = read_prompt_file(path)
        if not text.strip():
            raise MalformedResource(
                f"empty resource file {path} — every file must contribute "
                f"content (§5)")
        return text
