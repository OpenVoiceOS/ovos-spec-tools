# 7. API reference

Every public name, in brief. All are importable from the top-level package:

```python
from ovos_spec_tools import expand, LocaleResources, render, closest_lang  # etc.
```

For the why and the worked examples, see the chapter each section links to.

## Expansion: [chapter 2](templates.md)

### `expand(template, vocabularies=None) -> list[str]`

Expand a sentence template to its sample set. `vocabularies` is a
`name -> list[str]` dict, needed only if the template uses `<name>` references.
Raises `MalformedTemplate`.

### `MalformedTemplate`

`ValueError` subclass: a template violates OVOS-INTENT-1 §3.6.

## Locale resources: [chapter 3](locale-resources.md)

### `LocaleResources(skill_locale, core_locale=None, user_locale=None, lang_resolver=None, max_language_distance=10)`

Loads a skill's locale resource files. The three `*_locale` arguments are paths
to `locale/` directories, in ascending override precedence. `lang_resolver` is
a `(target, available, max_distance) -> str | None` callable (default
`closest_lang`). `max_language_distance` caps the smart fallback (`0` disables
it).

Methods, each takes a resource base name and a BCP-47 `lang`:

| Method | Returns |
|--------|---------|
| `load_intent(name, lang)` | expanded sample set, slots intact |
| `load_entity(name, lang)` | expanded value set |
| `load_vocabulary(name, lang)` | expanded phrase set |
| `load_blacklist(name, lang)` | expanded phrase set |
| `load_dialog(name, lang)` | raw phrase strings (not expanded) |
| `load_prompt(name, lang)` | the whole `.prompt` file, as one string |
| `vocabularies(lang)` | `name -> templates` for every `.voc` |
| `entities(lang)` | `name -> values` for every `.entity` |

A missing resource raises `FileNotFoundError`. A malformed one raises
`MalformedResource`.

### `read_resource_file(path) -> list[str]`

Apply the OVOS-INTENT-2 §3 common reader to one file: UTF-8, BOM discarded,
`LF`/`CRLF` accepted, lines stripped, blank and `#`-comment lines dropped.

### `read_prompt_file(path) -> str`

Read a `.prompt` whole and verbatim, UTF-8, BOM discarded, no line filtering.

### `MalformedResource`

`ValueError` subclass: a resource file or layout violates OVOS-INTENT-2
(empty file, duplicate `(role, base name)`, a slot in a slot-free role).

## Dialog: [chapter 4](dialog.md)

### `render(phrases, slots=None, vocabularies=None, rng=None) -> str`

Render one phrase from an explicit list. `slots` fills `{name}` slots.
`vocabularies` resolves `<name>` references. `rng` is any object with a
`choice` method (for reproducible output). Raises `UnfilledSlot`, or
`ValueError` if `phrases` is empty.

### `DialogRenderer(resources, name, rng=None, slots=None)`

A stateful, multilingual renderer for the dialog `name`, backed by a
`LocaleResources`. `slots` are default slot values reused on every call.

- **`render(lang, slots=None) -> str`**, render one phrase in `lang`. Avoids
  repeating the previous phrase (per language). Slot precedence: per-call,
  then default, then a random `.entity` value, then `UnfilledSlot`.

### `UnfilledSlot`

`ValueError` subclass: a chosen phrase has a slot with no value.

## Prompts: [chapter 4](dialog.md)

### `render_prompt(text, slots=None) -> str`

Render a `.prompt` string. The whole `text` is the prompt. A `{name}` is
substituted only when it is a well-formed name, `slots` supplies a value, and
it is not inside a fenced code block (marked with triple backticks). An
unfilled slot, and any other `{`/`}`, is left literal. Never raises for an
unfilled slot.

### `PromptRenderer(resources, name, slots=None)`

A stateful, multilingual renderer for the prompt `name`, backed by a
`LocaleResources`. `slots` are default values reused on every call.

- **`render(lang, slots=None) -> str`**: render the prompt in `lang`. A
  per-call value overrides a default. Raises `FileNotFoundError` if the prompt
  is missing for `lang`, `MalformedResource` if the file is empty.

## Language matching: [chapter 5](language-matching.md)

### `standardize_lang(tag) -> str`

Normalize a BCP-47 tag (underscores, case, canonical forms).

### `lang_distance(desired, supported) -> int`

Distance between two tags: `0` is identical, `>= 10` is not a usable match. A
bare tag is measured from its norm region.

### `closest_lang(target, available, max_distance=10) -> str | None`

The entry of `available` with the smallest `lang_distance`, if it is below
`max_distance` (or exact). Returns the original string, or `None`.

## Bus messages: [chapter 6](message.md)

### `Message(msg_type, data=None, context=None)`

The OVOS-MSG-1 envelope: exactly three top-level fields, `msg_type`
(the wire field `type`), `data`, `context`. The constructor rejects
malformed input as `MalformedMessage`. `data` and `context` default to
empty dicts and are stored by reference.

#### Derivations

- `m.forward(msg_type, data=None) -> Message`: same context, new
  type/data. The forwarder does not become the new `source`.
- `m.reply(msg_type, data=None, context=None) -> Message`: copies
  context, overlays the optional `context`, and swaps `source` and
  `destination`. Other context keys (including `session`) pass through
  unchanged.
- `m.response(data=None, context=None) -> Message`: sugar for
  `reply(msg_type + ".response", ...)`.

All three preserve the runtime class. Subclasses get back instances
of their own subclass.

#### Serialization

- `m.serialize() -> str`: single UTF-8 JSON object per OVOS-MSG-1 §6. It
  recursively converts nested objects exposing a `.serialize()` method
  (e.g. `Session`).
- `m.as_dict -> dict` (property): JSON-decoded envelope, equivalent
  to `json.loads(m.serialize())`. Nested `.serialize()`-walking carriers
  are converted the same way they would be on the wire.
- `Message.deserialize(payload) -> Message`: parse a JSON string,
  bytes, or already-parsed dict. Rejects unknown top-level keys, missing
  `type`, wrong value types, NaN/Infinity as `MalformedMessage`.

### `MalformedMessage`

`ValueError` subclass raised by the constructor and `deserialize` when a
payload violates OVOS-MSG-1 §2 / §6 / §7.

### `DEFAULT_SESSION_ID`

The reserved `"default"` value (OVOS-MSG-1 §4.1): *the Message
originates from the device itself*. An absent `session` on a Message is
equivalent for every policy decision.

## Intent dispatch topics — [bus namespaces](bus-namespaces.md)

### `is_intent_topic(msg_type) -> bool`

Whether `msg_type` is a `<skill_id>:<intent_name>` dispatch topic (OVOS-MSG-1
§2.1.1) — a topic with a `:` and non-empty halves.

### `canonical_intent_topic(msg_type) -> str`

Strip a trailing legacy `.intent` suffix from the intent-name half (after the
last colon). Idempotent; non-intent topics are returned unchanged.

### `legacy_intent_topic(msg_type) -> str`

The inverse: append the `.intent` suffix. Idempotent; non-intent topics are
returned unchanged.

## Linting — [chapter 7](linting.md)

### `lint_locale(path, spec_version=2) -> list[Finding]`

Validate every resource file under a locale (or single-language) directory.
`spec_version` (0, 1, or 2) flags features newer than that target, see
[chapter 7](linting.md).

### `Finding`

A dataclass with `severity` (`"error"` / `"warning"`), `path`, and `message`.
`str(finding)` formats it as one line.

### `ovos-spec-lint` (command)

CLI wrapper over `lint_locale`. `ovos-spec-lint <path> [--strict]
[--spec-version {0,1,2}]`. Exit code is non-zero on errors (with `--strict`,
on warnings too).

## Package

### `__version__`

The installed package version string.

---
[← Linting](linting.md) · [Home](README.md)
