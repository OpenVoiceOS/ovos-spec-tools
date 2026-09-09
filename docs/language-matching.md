# 5. Language matching

> **Spec coverage.** This chapter is the reference for the cross-spec BCP-47
> language-matching rules (`language.py`). The case-insensitive tag comparison
> comes from **OVOS-INTENT-2 §2**. The nearest-language fallback and its
> "distance below 10 is a usable regional match" threshold come from
> **OVOS-INTENT-2 §2.2** (non-normative). The same rules decide whether an
> available resource, voice, or model serves a **SESSION-1** session language.
>
> Everything here is a *reference policy*, not a conformance obligation:
> §2.2 is explicitly an implementation choice.

OVOS constantly needs to answer this question: "the assistant was asked for
language X, which of the languages I actually have is the best fit?" It needs
the answer for locale folders, TTS voices, and STT models.

The logic was reimplemented in several places (`ovos_utils.lang`, `phoonnx`,
…) and drifted. This module is the one implementation.

Three functions:

```python
from ovos_spec_tools import standardize_lang, lang_distance, closest_lang
```

## `standardize_lang(tag)`

Normalizes a BCP-47 tag for comparison, underscores to hyphens, consistent
case, canonical script/region forms:

```python
standardize_lang("en_us")    # 'en-US'
standardize_lang("PT")       # 'pt'
```

It uses `langcodes` when installed and a simple normalization otherwise. One
deliberate exception: `tl` and `tgl` (Tagalog) are kept as `tl`, `langcodes`
would fold them into the `fil` macrolanguage, which OVOS keeps distinct.

## `lang_distance(a, b)`

The heart of the module. It returns an integer: **`0` is identical**, larger is
further apart, and `10` or more is not a usable match.

```python
lang_distance("en-US", "en_us")   # 0, the same tag
lang_distance("en-US", "en-GB")   # small, a regional difference
lang_distance("en-US", "fr-FR")   # large, a different language
```

All the policy lives here, so callers never need special cases.

### A bare tag is measured from its norm region

`langcodes` resolves a bare tag to its *most-populous* region. It considers
`pt` closest to `pt-BR`.

But the unmarked form of a language should mean its **reference variety**:
Portuguese is "from Portugal" by name, and every Lusophone country except
Brazil follows the pt-PT norm. So `lang_distance` measures a bare tag from its
norm region:

```python
lang_distance("pt", "pt-PT")   # 0, the norm region
lang_distance("pt", "pt-BR")   # > 0, a regional variant
```

The norm regions are a small explicit table (currently just `pt → PT`). A
language is added only when its bare tag has a clear reference region distinct
from the populous one.

### Without `langcodes`

`langcodes` is optional. Without it, `lang_distance` falls back to a coarse
measure: a shared primary subtag is near, a different language is far, and the
generic region-less form counts as nearer than a sibling region.

It is enough to keep a request for `en-AU` resolving against `en`, `en-GB`,
`en-US`, just without `langcodes`' finer regional ranking. Install the
`langcodes` extra for that:

```bash
pip install ovos-spec-tools[langcodes]
```

## `closest_lang(target, available, max_distance=10)`

Given a wanted tag and the tags you have, returns the closest one, or `None`.
It is simply *the candidate with the smallest `lang_distance`*:

```python
closest_lang("en-AU", ["pt-BR", "en-US", "de-DE"])   # 'en-US'
closest_lang("pt",    ["pt-BR", "pt-PT"])            # 'pt-PT'  (norm region)
closest_lang("zz-ZZ", ["en-US", "pt-BR"])            # None
```

An exact match always resolves. Any other match resolves only if its distance
is **below** `max_distance` (default 10, the OVOS-INTENT-2 §2.2 threshold).
`max_distance=0` accepts exact matches only.

The return value is the original string from `available`, so you can map it
straight back to a directory, a voice file, a model name.

This is exactly what `LocaleResources` uses for its smart language fallback
([chapter 3](locale-resources.md)), and you can use it directly anywhere else
the same question comes up.

### Dialect-fallback semantics: precisely

A request resolves to a candidate **iff** their distance is below the threshold
(an exact match, distance `0`, always resolves). The distance ladder, nearest
to farthest:

| Relationship | Distance | Resolves (default threshold 10)? |
|--------------|----------|----------------------------------|
| identical tag (case aside) | `0` | yes |
| bare tag vs its norm region (`pt` / `pt-PT`) | `0` | yes |
| two regions of one language (`en-US` / `en-GB`) | small (`<10`) | yes |
| a different primary language (`en` / `fr`) | large (`≥100` coarse) | no |

So `en-AU` falls back to `en-US` over `de-DE`, `pt` prefers `pt-PT` over
`pt-BR`, and `zz-ZZ` resolves to nothing. The fallback is **dialect-only** by
design: it never crosses primary languages, because serving French wording to a
request for English is worse than failing (OVOS-INTENT-2 §2.2's caution that
"cross-region substitution can produce wording a user would not expect").

## Next

[Linting](linting.md), checking a whole locale folder at once.

---
[← Dialog](dialog.md) · [Home](README.md) · [Bus messages →](message.md)
