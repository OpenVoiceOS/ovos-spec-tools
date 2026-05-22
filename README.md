# ovos-spec-tools

Reference implementation of the OVOS [formal
specifications](https://github.com/OpenVoiceOS/formal-specifications) — the
low-level, dependency-light primitives those specifications describe.

OVOS components reimplement template expansion, resource loading, and language
matching in several places, and the copies drift. This package is the single
conformant implementation those components — and any third-party tool — can
depend on.

## Status

| Tool | Spec | State |
|------|------|-------|
| Sentence template expander | OVOS-INTENT-1 v2 | available |
| Locale resource loader | OVOS-INTENT-2 | available |
| Dialog renderer | OVOS-INTENT-2 §4.2 | available |
| Language-tag matching | OVOS-INTENT-2 §2.2 | available |
| `ovos-spec-lint` locale linter | OVOS-INTENT-1 / -2 | available |

## The expander

`expand()` turns a sentence template into its **sample set** — the finite set
of sentences it denotes (OVOS-INTENT-1 §4). It resolves `(a|b)` alternatives,
`[x]` optionals, and `<name>` inline vocabulary references; named `{name}`
slots are opaque and carried through unchanged.

```python
from ovos_spec_tools import expand

expand("(turn|switch) [the] (light|fan)")
# ['turn the light', 'turn the fan', 'turn light', 'turn fan',
#  'switch the light', 'switch the fan', 'switch light', 'switch fan']

expand("<greeting> {name}", {"greeting": ["hello", "hi"]})
# ['hello {name}', 'hi {name}']
```

A template that violates OVOS-INTENT-1 §3.6 — unbalanced metacharacters, a
single-branch group, an empty sample, a slot-only template, adjacent slots, a
repeated slot name, or an undefined or cyclic vocabulary reference — raises
`MalformedTemplate`.

Input is assumed already ASR-normalized (OVOS-INTENT-1 §2): lowercase,
single-spaced, alphanumeric. This package expands; it does not normalize.

## The resource loader

`LocaleResources` discovers and loads a skill's locale resource files
(OVOS-INTENT-2) — the five roles `.intent`, `.dialog`, `.entity`, `.voc`,
`.blacklist` — through the user → skill → core override precedence, searching
each `locale/<lang>/` tree recursively.

The **language is given per call**, not at construction: a locale folder is
the multilingual unit of a skill, so one instance serves every language.

```python
from ovos_spec_tools import LocaleResources

res = LocaleResources(skill_locale="my-skill/locale")
res.load_intent("play", "en-US")     # sample set, named slots intact
res.load_intent("play", "pt-BR")     # same instance, another language
res.load_dialog("weather", "en-US")  # phrase strings, not expanded (§4.2)
```

The user-data path of the override precedence is assistant-defined and passed
in (`user_locale=`); this package imports no configuration.

**Smart language fallback.** When the requested language has no directory,
`LocaleResources` resolves to the nearest available language instead
(OVOS-INTENT-2 §2.2) — so a request for `en-AU` finds `en-US`. Resolution uses
`closest_lang` (below) and is re-run per call. Without `langcodes` installed,
resolution is exact-match only; pass `max_language_distance=0` to disable the
fallback, or a custom `lang_resolver` to change it.

## Language matching

`standardize_lang`, `lang_distance`, and `closest_lang` are the language-tag
primitives — the logic OVOS reimplements across locale loading, TTS voices,
and STT models, gathered in one place.

```python
from ovos_spec_tools import lang_distance, closest_lang

lang_distance("pt", "pt-PT")               # 0   — a bare tag's norm region
lang_distance("pt", "pt-BR")               # > 0 — merely a regional variant
closest_lang("en-AU", ["pt-BR", "en-US"])  # 'en-US'
closest_lang("zz-ZZ", ["pt-BR", "en-US"])  # None
```

`closest_lang` is just "the candidate with the smallest `lang_distance`",
accepted when it is below `max_distance` (default 10). `lang_distance` carries
all the policy: it standardizes tags, measures a bare tag from its **norm
region** (correcting langcodes' population-based default — so `pt` favors
`pt-PT` over `pt-BR`), and uses `langcodes` when available, falling back to a
coarse same-language measure that still resolves `en-AU` against `en`,
`en-GB`, … when `langcodes` is absent.

## The dialog renderer

Rendering a dialog selects one phrase from a loaded `.dialog`, expands its
variety to a single variant, and fills every `{name}` slot with a value
(OVOS-INTENT-2 §4.2). A slot with no value raises `UnfilledSlot`.

`render()` is a stateless one-shot function over explicit phrases:

```python
from ovos_spec_tools import render

render(res.load_dialog("weather", "en-US"), slots={"temperature": 21})
# 'It is 21 degrees.'
```

`DialogRenderer` is a stateful, **multilingual** alternative, backed by a
`LocaleResources`. The language is given per `render()` call, and the renderer
**avoids repeating the phrase it chose last time** — per language — so a
repeatedly-spoken response does not sound mechanical:

```python
from ovos_spec_tools import DialogRenderer

renderer = DialogRenderer(res, "weather")
renderer.render("en-US", {"temperature": 21})   # a phrase
renderer.render("en-US", {"temperature": 22})   # a different phrase
renderer.render("pt-BR", {"temperature": 23})   # the same dialog, another language
```

It also holds **default slot values** set once and reused, and falls back to a
slot's **`.entity` value set** for anything still unfilled. A slot is resolved
in order: the per-call value, then a default, then a random `.entity` value,
then `UnfilledSlot`.

## The locale linter

`ovos-spec-lint` validates every resource file under a locale directory — the
syntax of every template (OVOS-INTENT-1) and the naming and layout of every
file (OVOS-INTENT-2) — and reports every problem rather than stopping at the
first.

```bash
ovos-spec-lint path/to/locale
# path/to/locale/en-US/bad.intent: error: unbalanced metacharacters ...
# 1 error(s), 0 warning(s)
```

It checks template syntax, malformed forms, empty files, slot-free roles
carrying a slot, base-name and language-tag naming, duplicate resources, and
unresolved `<name>` references. The argument may be a `locale/` directory or a
single `<lang>/` directory. Exit code is non-zero on errors (or, with
`--strict`, on warnings) — suitable for CI.

## Install

```bash
pip install ovos-spec-tools            # core — no dependencies
pip install ovos-spec-tools[langcodes] # adds the smart language fallback
```

## License

Apache 2.0
