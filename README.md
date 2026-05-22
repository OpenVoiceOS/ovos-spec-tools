# ovos-spec-tools

Reference implementation of the OVOS [formal
specifications](https://github.com/OpenVoiceOS/formal-specifications) — the
low-level, dependency-light primitives those specifications describe.

OVOS components reimplement template expansion and resource loading in several
places, and the copies drift. This package is the single conformant
implementation those components — and any third-party tool — can depend on.

## Status

| Tool | Spec | State |
|------|------|-------|
| Sentence template expander | OVOS-INTENT-1 v2 | available |
| Locale resource loader | OVOS-INTENT-2 | available |
| Dialog renderer | OVOS-INTENT-2 §4.2 | available |
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

```python
from ovos_spec_tools import LocaleResources

res = LocaleResources("en-US", skill_locale="my-skill/locale")
res.load_intent("play")        # sample set, named slots intact
res.load_dialog("weather")     # phrase strings, not expanded (§4.2)
res.load_vocabulary("yes")     # expanded phrase set
```

The user-data path of the override precedence is assistant-defined and passed
in (`user_locale=`); this package imports no configuration.

## The dialog renderer

Rendering a dialog selects one phrase from a loaded `.dialog`, expands its
variety to a single variant, and fills every `{name}` slot with a
caller-supplied value (OVOS-INTENT-2 §4.2). A phrase with an unfilled slot
raises `UnfilledSlot`.

`render()` is a stateless one-shot function:

```python
from ovos_spec_tools import render

render(res.load_dialog("weather"), slots={"temperature": 21})
# 'It is 21 degrees.'
```

`DialogRenderer` is a stateful, object-oriented alternative. It holds the
dialog and, unlike the function, **avoids repeating the phrase it chose last
time** — so a repeatedly-spoken response does not sound mechanical:

```python
from ovos_spec_tools import DialogRenderer

renderer = DialogRenderer.from_resources(res, "weather")
renderer.render({"temperature": 21})   # a phrase
renderer.render({"temperature": 22})   # a different phrase
```

It also holds **default slot values** set once and reused, and falls back to a
slot's **`.entity` value set** for anything still unfilled. A slot is resolved
in order: the per-call value, then a default, then a random `.entity` value,
then `UnfilledSlot`.

```python
renderer = DialogRenderer.from_resources(res, "greeting",
                                         slots={"assistant": "OVOS"})
renderer.render()              # {assistant} reused; an {day} slot from day.entity
```

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
pip install ovos-spec-tools
```

## License

Apache 2.0
