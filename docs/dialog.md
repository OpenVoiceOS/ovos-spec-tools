# 4. Dialog

> **Spec coverage.** This chapter is the reference for the **Dialog renderer**
> conformance role of OVOS-INTENT-1 §7 over the `.dialog` format of
> OVOS-INTENT-2 §4.2 (`dialog.py`), and for the `.prompt` format of
> OVOS-INTENT-2 §4.4 (`prompt.py`, at the end of the chapter). A dialog renderer
> MUST embed a conformant expander, verify slot-set consistency (§5.5), fill
> every `{name}` from caller-supplied values, and MUST NOT emit an unfilled slot
> (§5.1) — `UnfilledSlot` is that last MUST.

A `.dialog` file holds the phrases an assistant may speak for one response.
**Rendering** a dialog means: pick one phrase, expand its `(a|b)` / `[x]`
variety down to a single variant, and fill its `{name}` slots with values. This
chapter covers the two ways to do it. It implements OVOS-INTENT-2 §4.2.

A `.dialog` phrase is spoken *output*, not ASR input, so — unlike the
input-direction roles — it may contain mixed case and punctuation:

```
# weather.dialog
It is {temperature} degrees.
Right now it's {temperature} degrees out.
(Currently|At the moment) {temperature} degrees.
```

## `render()` — the stateless function

`render()` takes an explicit list of phrases and returns one rendered sentence:

```python
from ovos_spec_tools import render

phrases = res.load_dialog("weather", "en-US")
render(phrases, slots={"temperature": 21})
# 'It is 21 degrees.'
```

Slots are filled from the `slots` dict. The phrase and the `(a|b)` variant are
chosen at random; pass `rng=` (anything with a `choice` method, e.g. a seeded
`random.Random`) for reproducible output. `vocabularies=` supplies any
`<name>` references.

Expansion runs **before** filling, with slots kept opaque — so a slot value can
never be mis-parsed as grammar. A value of `"(a|b)"` is filled in literally,
not expanded.

If the chosen phrase has a slot with no value, `render()` raises
`UnfilledSlot` — a half-filled phrase must never reach text-to-speech.

## `DialogRenderer` — the stateful, multilingual renderer

`render()` is fine for one-off use. For a skill that speaks a response
repeatedly, `DialogRenderer` does better. It is built from a `LocaleResources`
and a dialog name:

```python
from ovos_spec_tools import DialogRenderer

renderer = DialogRenderer(res, "weather")
renderer.render("en-US", {"temperature": 21})
renderer.render("pt-PT", {"temperature": 22})   # same renderer, another language
```

It adds three things over the bare function.

### It is multilingual

The language is a parameter of `render()`, not of the constructor — one
renderer serves every language the dialog ships in.

### It avoids repeating itself

`DialogRenderer` remembers the phrase it chose last time and avoids picking it
again — tracked **per language** — so a frequently-spoken response does not
sound mechanical. With two phrases, consecutive renders strictly alternate.

### It carries default slots and an `.entity` fallback

A slot is resolved in a clear order of precedence:

1. a value passed to this `render()` call;
2. a **default** value, set once on the constructor and reused every call;
3. a random value from the slot's **`.entity`** value set;
4. otherwise — `UnfilledSlot`.

```python
renderer = DialogRenderer(res, "greeting", slots={"assistant": "OVOS"})
renderer.render("en-US")
```

Here `{assistant}` is filled from the default every time. A `{weekday}` slot
that the caller does not supply is filled from `weekday.entity` if the skill
ships one — useful for a slot whose value is a free pick from a known set
rather than a computed value.

## Choosing between them

| | `render()` | `DialogRenderer` |
|--|------------|------------------|
| Input | an explicit phrase list | a `LocaleResources` + dialog name |
| Language | decided by the caller | per `render()` call |
| Repetition avoidance | no | yes, per language |
| Default slots / `.entity` fallback | no | yes |

Use `render()` when you already hold the phrases and want one sentence. Use
`DialogRenderer` for a skill response spoken more than once.

## Rendering `.prompt` files

A `.prompt` is the localized prompt a skill feeds to a language model. Unlike a
`.dialog` it is **not** a template — it is plain text — and the whole file,
verbatim, is one prompt. The only special construct is `{name}` substitution,
and it is **conservative**: a prompt is free-form text full of code and JSON,
so rendering must never corrupt a brace the author did not write as a slot.

`render_prompt()` is the stateless function:

```python
from ovos_spec_tools import render_prompt

render_prompt("You are {role}. Answer: {query}", {"role": "concise"})
# 'You are concise. Answer: {query}'
```

A `{name}` is replaced **only** when all three OVOS-INTENT-2 §4.4 conditions
hold: it is a well-formed name (§4.4 condition 1), the caller supplied a value
(condition 2), and it is not inside a ``` ``` ``` fenced code block
(condition 3). Everything else stays literal:

- an **unfilled** slot is left as `{name}` — §4.4 "slots are optional", the
  deliberate opposite of `.dialog`, where every slot must be filled;
- any other `{`/`}` — `{}`, `{ }`, JSON like `{"k": 1}` — is untouched;
- a `{name}` inside a fenced code block is never substituted.

> **Known gap.** OVOS-INTENT-2 §4.4 also requires author-only HTML comments
> `<!-- … -->` to be **stripped** before a prompt reaches a model (a MUST).
> `render_prompt()` does **not** yet do this — a comment passes through
> verbatim. Do not rely on comment removal until it is implemented.

`PromptRenderer` is the resource-backed, multilingual form — built from a
`LocaleResources`, with the language given per call and optional default slots:

```python
from ovos_spec_tools import PromptRenderer

renderer = PromptRenderer(res, "system", slots={"assistant": "OVOS"})
renderer.render("en-US", {"query": "what time is it"})
renderer.render("pt-PT", {"query": "que horas são"})   # same prompt, another language
```

It has no phrase selection, no repetition avoidance, and no `.entity` fallback
— a prompt is one whole-file body and its slots are optional.

## Next

[Language matching](language-matching.md) — the tag logic behind the loader's
smart fallback.
