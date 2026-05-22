"""Language-tag utilities — standardization, distance, and closest match.

OVOS resolves "the closest available language for a request" in many places —
locale resources, TTS voices, STT models — and the logic has been
reimplemented repeatedly (``ovos_utils.lang.get_language_dir``,
``phoonnx.match_lang``, …) with subtle drift between the copies. This module is
intended to be the **single implementation**.

It is built on one distance function, :func:`lang_distance`; :func:`closest_lang`
is simply "the candidate with the smallest distance". All the policy — tag
standardization, the norm-region preference, the behaviour when ``langcodes``
is absent — lives inside :func:`lang_distance`, not in branchy callers.

``langcodes`` is an optional dependency. Without it, :func:`lang_distance`
falls back to a coarse same-language / different-language measure.
"""
from __future__ import annotations

from typing import Optional, Sequence

__all__ = [
    "standardize_lang",
    "lang_distance",
    "closest_lang",
    "DEFAULT_MAX_LANGUAGE_DISTANCE",
]

# A language distance below 10 is a usable regional match (OVOS-INTENT-2 §2.2;
# see the langcodes distance-values documentation).
DEFAULT_MAX_LANGUAGE_DISTANCE = 10

# The norm region for a bare language tag. `langcodes` resolves a bare tag to
# its *most-populous* region — for "pt" that is "pt-BR" — but the unmarked
# form of a language should resolve to its reference variety. Portuguese is
# "from Portugal" by name, and every Lusophone country except Brazil follows
# the pt-PT norm, so a bare "pt" is measured from "pt-PT". Add a language here
# only when its bare tag has a clear reference region distinct from the
# populous one.
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


def _with_norm_region(tag: str) -> str:
    """Give a bare language tag its norm region (``pt`` -> ``pt-PT``).

    A regioned tag, or a language with no norm region, is returned unchanged.
    """
    if "-" in tag:
        return tag
    region = _NORM_REGION.get(tag.lower())
    return f"{tag.lower()}-{region.upper()}" if region else tag


def _langcodes_distance(desired: str, supported: str) -> Optional[int]:
    """``langcodes.tag_distance``, retried on the primary subtag if the full
    tag is unparseable. ``None`` if no distance can be computed — including
    when ``langcodes`` is not installed."""
    try:
        from langcodes import tag_distance
    except ImportError:
        return None
    for candidate in (supported, supported.split("-")[0]):
        try:
            return int(tag_distance(desired, candidate))
        except Exception:
            continue
    return None


def _coarse_distance(desired: str, supported: str) -> int:
    """A ``langcodes``-free distance.

    The two tags are already standardized and norm-expanded. A shared primary
    subtag is near, a differing one is far; the generic (region-less) form of
    a language counts as nearer than a sibling region of it.
    """
    if desired.split("-")[0].lower() != supported.split("-")[0].lower():
        return 100  # a different language — beyond any usable threshold
    if "-" not in desired or "-" not in supported:
        return 3  # one side is the generic language tag
    return 5  # two different regions of the same language


def lang_distance(desired: str, supported: str) -> int:
    """The distance between two BCP-47 language tags.

    ``0`` is identical; a larger number is further apart; a value of 10 or
    more is not a usable match. Both tags are standardized, and a bare tag is
    measured **from its norm region** — so ``lang_distance("pt", "pt-PT")`` is
    ``0`` while ``lang_distance("pt", "pt-BR")`` is a regional difference,
    correcting ``langcodes``' population-based default.

    Uses ``langcodes.tag_distance`` when available, and a coarse same-language
    measure otherwise.
    """
    a = standardize_lang(desired)
    b = standardize_lang(supported)
    if a.lower() == b.lower():
        return 0
    a, b = _with_norm_region(a), _with_norm_region(b)
    if a.lower() == b.lower():
        return 0
    distance = _langcodes_distance(a, b)
    return distance if distance is not None else _coarse_distance(a, b)


def closest_lang(target: str, available: Sequence[str],
                 max_distance: int = DEFAULT_MAX_LANGUAGE_DISTANCE
                 ) -> Optional[str]:
    """Return the entry of ``available`` closest to ``target``.

    The candidate with the smallest :func:`lang_distance` wins. An exact match
    always resolves; any other match resolves only if its distance is **below**
    ``max_distance`` (so ``max_distance=0`` accepts exact matches only).
    ``None`` is returned when nothing qualifies.

    The value returned is the original string from ``available``, so a caller
    can map it back to a directory, a voice, a model, and so on.
    """
    best: Optional[str] = None
    best_distance: Optional[int] = None
    for candidate in available:
        distance = lang_distance(target, candidate)
        if best_distance is None or distance < best_distance:
            best, best_distance = candidate, distance

    if best is None:
        return None
    if best_distance == 0:
        return best
    if max_distance > 0 and best_distance < max_distance:
        return best
    return None
