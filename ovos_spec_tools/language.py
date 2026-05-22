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
    always wins. Otherwise the nearest tag whose distance is **below**
    ``max_distance`` is returned; if none qualifies, or ``max_distance`` is not
    positive, ``None`` is returned. Without ``langcodes`` installed only exact
    matches resolve.

    The value returned is the original string from ``available``, so a caller
    can map it back to a directory, a voice, a model, and so on.
    """
    wanted = standardize_lang(target)
    for candidate in available:
        if standardize_lang(candidate).lower() == wanted.lower():
            return candidate

    if max_distance <= 0:
        return None
    nearest: Optional[str] = None
    nearest_distance = max_distance  # accept only a distance strictly below this
    for candidate in available:
        distance = _tag_distance(wanted, standardize_lang(candidate))
        if distance is not None and distance < nearest_distance:
            nearest, nearest_distance = candidate, distance
    return nearest
