# ovos-intent-primitives

Reference implementation of the OVOS intent specifications — the low-level,
dependency-light primitives that the [formal
specifications](https://github.com/OpenVoiceOS/formal-specifications) describe.

OVOS components reimplement template expansion and resource loading in several
places, and the copies drift. This package is the single conformant
implementation those components — and any third-party tool — can depend on.

## Status

| Primitive | Spec | State |
|-----------|------|-------|
| Sentence template expander | OVOS-INTENT-1 v2 | available |
| Locale resource loader | OVOS-INTENT-2 | available |
| Dialog renderer | OVOS-INTENT-2 §4.2 | available |

## The expander

`expand()` turns a sentence template into its **sample set** — the finite set
of sentences it denotes (OVOS-INTENT-1 §4). It resolves `(a|b)` alternatives,
`[x]` optionals, and `<name>` inline vocabulary references; named `{name}`
slots are opaque and carried through unchanged.

```python
from ovos_intent_primitives import expand

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
from ovos_intent_primitives import LocaleResources

res = LocaleResources("en-US", skill_locale="my-skill/locale")
res.load_intent("play")        # sample set, named slots intact
res.load_dialog("weather")     # phrase strings, not expanded (§4.2)
res.load_vocabulary("yes")     # expanded phrase set
```

The user-data path of the override precedence is assistant-defined and passed
in (`user_locale=`); this package imports no configuration.

## The dialog renderer

`render()` selects one phrase from a loaded `.dialog`, expands its variety to a
single variant, and fills every `{name}` slot with a caller-supplied value
(OVOS-INTENT-2 §4.2). A phrase with an unfilled slot raises `UnfilledSlot`.

```python
from ovos_intent_primitives import render

render(res.load_dialog("weather"), slots={"temperature": 21})
# 'It is 21 degrees.'
```

## Install

```bash
pip install ovos-intent-primitives
```

## License

Apache 2.0
