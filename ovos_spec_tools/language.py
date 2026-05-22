"""Language-tag utilities — standardization and closest-match resolution.

OVOS resolves "the closest available language for a request" in many places —
locale resources, TTS voices, STT models — and the logic has been
reimplemented repeatedly (``ovos_utils.lang.get_language_dir``,
``phoonnx.match_lang``, …) with subtle drift between the copies. This module is
intended to be the **single implementation**: it powers the smart language
fallback of :class:`~ovos_spec_tools.resources.LocaleResources`
(OVOS-INTENT-2 §2.2) and is importable on its own to replace those copies.

``langcodes`` is an optional dependency. Without it, :func:`standardize_lang`
does a best-effort normalization and :func:`closest_lang` resolves exact
matches only.
"""
from __future__ import annotations

from typing import Optional, Sequence

__all__ = ["standardize_lang", "closest_lang", "DEFAULT_MAX_LANGUAGE_DISTANCE"]

# A `langcodes` tag distance below 10 is a usable regional match
# (OVOS-INTENT-2 §2.2; see the langcodes distance-values documentation).
DEFAULT_MAX_LANGUAGE_DISTANCE = 10

# The norm region for a bare language tag. `langcodes` resolves a bare tag to
# its *most-populous* region — for "pt" that is "pt-BR" — but the unmarked
# form of a language should resolve to its reference variety. Portuguese is
# "from Portugal" by name, and every Lusophone country except Brazil follows
# the pt-PT norm, so bare "pt" favors "pt-PT". Add a language here only when
# its bare tag has a clear reference region distinct from the populous one.
_NORM_REGION = {
    "pt": "PT",
}


def standardize_lang(tag: str) -> str:
    """Normalize a BCP-47 language tag for comparison.

    Uses ``langcodes.standardize_tag`` when available — handling underscores,
    case, and script/region forms — and falls back to a simple normalization
    otherwise.
    """
    if tag.lower() in ("tl", "tgl"):
        # langcodes folds Tagalog into the `fil` macrolanguage; OVOS keeps
        # `tl` distinct, so this one tag is normalized by hand.
        return "tl"
    try:
        from langcodes import standardize_tag
        return str(standardize_tag(tag))
    except Exception:
        normalized = tag.replace("_", "-")
        if "-" in normalized:
            primary, rest = normalized.split("-", 1)
            return f"{primary.lower()}-{rest.upper()}"
        return normalized.lower()


def _tag_distance(desired: str, supported: str) -> Optional[int]:
    """``langcodes.tag_distance``, retried on the primary subtag if the full
    tag is unparseable. Returns ``None`` if no distance can be computed —
    including when ``langcodes`` is not installed."""
    try:
        from langcodes import tag_distance
    except ImportError:
        return None
    for candidate in (supported, supported.split("-")[0]):
        try:
            return tag_distance(desired, candidate)
        except Exception:
            continue
    return None


def closest_lang(target: str, available: Sequence[str],
                 max_distance: int = DEFAULT_MAX_LANGUAGE_DISTANCE
                 ) -> Optional[str]:
    """Return the entry of ``available`` closest to ``target``.

    An exact match (after standardization, so ``en_US`` matches ``en-US``)
    always wins. When ``target`` is a bare language tag with a norm region
    (see ``_NORM_REGION``), a candidate in that region is preferred next — so
    bare ``pt`` favors ``pt-PT`` over ``pt-BR``. Otherwise the nearest tag
    whose distance is **below** ``max_distance`` is returned; if none
    qualifies, or ``max_distance`` is not positive, ``None`` is returned.
    Without ``langcodes`` installed only exact matches resolve.

    The value returned is the original string from ``available``, so a caller
    can map it back to a directory, a voice, a model, and so on.
    """
    wanted = standardize_lang(target)
    for candidate in available:
        if standardize_lang(candidate).lower() == wanted.lower():
            return candidate

    if max_distance <= 0:
        return None

    # A bare language tag favors its norm region over langcodes' populous
    # default (which would, for "pt", pick "pt-BR").
    if "-" not in wanted and wanted.lower() in _NORM_REGION:
        norm = f"{wanted.lower()}-{_NORM_REGION[wanted.lower()]}"
        for candidate in available:
            if standardize_lang(candidate).lower() == norm.lower():
                return candidate

    nearest: Optional[str] = None
    nearest_distance = max_distance  # accept only a distance strictly below this
    for candidate in available:
        distance = _tag_distance(wanted, standardize_lang(candidate))
        if distance is not None and distance < nearest_distance:
            nearest, nearest_distance = candidate, distance
    return nearest
