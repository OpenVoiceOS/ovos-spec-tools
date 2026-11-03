"""Language-tag utilities: standardization, distance, and closest match.

OVOS-INTENT-2 §2 names locale directories with BCP-47 tags and compares them
case-insensitively. OVOS-INTENT-2 §2.2 suggests, without requiring it, that a
loader may fall back to the nearest available language. The functions here
are the policy OVOS uses for both, for locale resources, TTS voices and STT
models alike.

The implementation is `linguatag <https://github.com/TigreGotico/linguatag>`_;
this module re-exports it. A tag with no region is measured from its default
region, the region where the language first appeared and is still spoken:
``en`` is ``en-GB`` and ``pt`` is ``pt-PT``. A tag that ``langcodes`` cannot
parse, such as a voice id, is measured as its longest parseable prefix. The
linguatag README documents the full rule set.
"""
from linguatag import (
    DEFAULT_MAX_LANGUAGE_DISTANCE,
    closest_lang,
    default_region,
    lang_distance,
    lang_matches,
    standardize_lang,
    with_default_region,
)

__all__ = [
    "DEFAULT_MAX_LANGUAGE_DISTANCE",
    "closest_lang",
    "default_region",
    "lang_distance",
    "lang_matches",
    "standardize_lang",
    "with_default_region",
]
