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
| Locale resource loader | OVOS-INTENT-2 | planned |
| Dialog renderer | OVOS-INTENT-2 §4.2 | planned |

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

## Install

```bash
pip install ovos-intent-primitives
```

## License

Apache 2.0
