# 2. Sentence templates

> **Spec coverage.** This chapter is the reference for **OVOS-INTENT-1 — the
> Sentence Template Grammar** (`expansion.py`). `expand()` is the *Expander*
> conformance role of OVOS-INTENT-1 §7: it implements the token set of §3, the
> enumeration algorithm of §4.1, and the malformed-form rejection of §3.6.

A **sentence template** is a compact string that stands for a set of
sentences. It is the grammar of OVOS-INTENT-1, and it is the foundation of this
package: resource files are lists of templates, and the dialog renderer
renders them.

`expand()` is the whole interface:

```python
from ovos_spec_tools import expand, MalformedTemplate
```

`expand(template)` returns the **sample set** — the finite list of sentences
the template denotes.

## The four tokens

A template is literal words interspersed with four kinds of token.

### Literal words

Anything that is not a token is literal text, matched verbatim:

```python
expand("turn on the lights")
# ['turn on the lights']
```

### Alternatives — `(a|b|c)`

Parentheses hold branches separated by `|`; each combination takes one branch:

```python
expand("(turn on|switch on|enable) it")
# ['turn on it', 'switch on it', 'enable it']
```

A branch may be empty — `(please|)` means "please, or nothing":

```python
expand("(please|) help me")
# ['please help me', 'help me']
```

### Optionals — `[x]`

`[x]` is exactly `(x|)` — the segment is included or omitted:

```python
expand("turn on [the] lights")
# ['turn on the lights', 'turn on lights']
```

Groups nest freely:

```python
expand("turn on [(all|every) ]light[s]")
# ['turn on all lights', 'turn on lights', 'turn on every lights',
#  'turn on all light', 'turn on light', 'turn on every light']
```

### Named slots — `{name}`

A `{name}` slot is a placeholder for a value that varies — a song title, a
city. It is **opaque**: expansion carries it through untouched and never
enumerates it.

```python
expand("(play|put on) {query}")
# ['play {query}', 'put on {query}']
```

Who fills a slot, and when, depends on the file role: an intent engine fills it
from speech; a skill fills a dialog slot before the phrase is spoken. Expansion
itself never does.

### Vocabulary references — `<name>`

`<name>` (OVOS-INTENT-1 §3.7) pulls in a named **vocabulary** — a reusable set
of phrasings — and expands it in place. Pass the vocabularies as a dict:

```python
expand("<greeting> [there]", {"greeting": ["hello", "hi", "hey"]})
# ['hello there', 'hi there', 'hey there', 'hello', 'hi', 'hey']
```

This is how you avoid repeating the same `(hello|hi|hey)` group across many
templates: define it once as a vocabulary, reference it as `<greeting>`. A
vocabulary may itself contain `<name>` references; they resolve recursively
(§4.1 step 1). A reference must resolve to a **slot-free** set — a vocabulary
may not introduce a `{slot}` — and a single-member vocabulary substitutes its
bare member rather than a one-branch group.

## How expansion works — the §4.1 algorithm

`expand()` follows OVOS-INTENT-1 §4.1 exactly, in order:

1. **Resolve `<name>` references** to alternative groups (recursively).
2. **Rewrite `[x]` as `(x|)`** — an optional is sugar for an empty branch.
3. **Cartesian product** of the innermost `(...)` groups, repeated until no
   parenthesis remains.
4. **Normalize whitespace** — collapse runs of spaces, strip the ends (this is
   what removes the double space an empty branch leaves behind).
5. **De-duplicate**, preserving first-seen order.

Worked through on `(turn|switch) [the] (light|fan)` — three 2-branch groups
once `[the]` becomes `(the|)`, so `2×2×2 = 8` combinations collapse (after
whitespace normalization) to the 8-sentence sample set of §4.2:

```python
expand("(turn|switch) [the] (light|fan)")
# ['turn the light', 'switch the light', 'turn light', 'switch light',
#  'turn the fan', 'switch the fan', 'turn fan', 'switch fan']
```

The **sample set is a set** — §4 defines its membership, not an ordering — so
the eight sentences are exactly those of §4.2; the sequence above is just the
order `expand()` happens to emit them in. Throughout, `{name}` slots are
**opaque** — carried through and never enumerated (§4.1 final note).

## The input model

The grammar is built for **voice**. Templates and the utterances matched
against them are assumed already *ASR-normalized*: lowercase, alphanumeric
words, single spaces, no punctuation. This package **expands; it does not
normalize** — normalization happens upstream.

One consequence: the metacharacters `( ) [ ] { } < > |` never occur as literal
spoken text, so there is no escaping mechanism and none is needed.

(`.dialog` phrases are the exception — they are spoken *output*, so they may
carry mixed case and punctuation. See [Dialog](dialog.md).)

## Malformed templates

A template that cannot mean anything sensible raises `MalformedTemplate`:

```python
try:
    expand("turn (on|off the lights")
except MalformedTemplate as error:
    print(error)   # unbalanced metacharacters ...
```

The malformed forms (OVOS-INTENT-1 §3.6):

| Form | Example | Why |
|------|---------|-----|
| Unbalanced metacharacters | `(a|b` | a bracket is never closed |
| Single-branch group | `(word)`, `()` | a group must offer a *choice* |
| Empty sample | `[hello]`, `(|)` | a sample with no words trains nothing |
| Slot-only template | `{name}` | a template needs anchoring literal text |
| Adjacent slots | `{a} {b}` | no word between two slots to delimit them |
| Repeated slot name | `{x} and {x}` | a slot is defined once per sample |
| Undefined vocabulary | `<missing>` | no such vocabulary was supplied |
| Cyclic vocabulary | `<a>`→`<b>`→`<a>` | resolution would not terminate |

Two are checked against the **expanded samples**, not the raw template:
`{a} [x] {b}` is malformed because the empty-`x` branch yields the adjacent
pair `{a} {b}`; and a template is malformed if *any* branch combination
produces an empty sentence.

## Templates as training data

Expansion produces the *shape of the training data* a template contributes —
nothing more. A capable intent engine **generalizes beyond** the sample set: it
recognizes phrasings that were never enumerated. So keep templates focused and
readable; you are not obliged to spell out every wording. Matching and
generalization are the engine's job and are out of scope here.

## Next

[Locale resources](locale-resources.md) — where templates live on disk, and
how to load them.
