# 7. API reference

Every public name, in brief. All are importable from the top-level package:

```python
from ovos_spec_tools import expand, LocaleResources, render, closest_lang  # etc.
```

For the why and the worked examples, see the chapter each section links to.

## Expansion — [chapter 2](templates.md)

### `expand(template, vocabularies=None) -> list[str]`

Expand a sentence template to its sample set. `vocabularies` is a
`name -> list[str]` dict, needed only if the template uses `<name>` references.
Raises `MalformedTemplate`.

### `MalformedTemplate`

`ValueError` subclass — a template violates OVOS-INTENT-1 §3.6.

## Locale resources — [chapter 3](locale-resources.md)

### `LocaleResources(skill_locale, core_locale=None, user_locale=None, lang_resolver=None, max_language_distance=10)`

Loads a skill's locale resource files. The three `*_locale` arguments are paths
to `locale/` directories, in ascending override precedence. `lang_resolver` is
a `(target, available, max_distance) -> str | None` callable (default
`closest_lang`); `max_language_distance` caps the smart fallback (`0` disables
it).

Methods — each takes a resource base name and a BCP-47 `lang`:

| Method | Returns |
|--------|---------|
| `load_intent(name, lang)` | expanded sample set, slots intact |
| `load_entity(name, lang)` | expanded value set |
| `load_vocabulary(name, lang)` | expanded phrase set |
| `load_blacklist(name, lang)` | expanded phrase set |
| `load_dialog(name, lang)` | raw phrase strings (not expanded) |
| `vocabularies(lang)` | `name -> templates` for every `.voc` |
| `entities(lang)` | `name -> values` for every `.entity` |

A missing resource raises `FileNotFoundError`; a malformed one raises
`MalformedResource`.

### `read_resource_file(path) -> list[str]`

Apply the OVOS-INTENT-2 §3 common reader to one file: UTF-8, BOM discarded,
`LF`/`CRLF` accepted, lines stripped, blank and `#`-comment lines dropped.

### `MalformedResource`

`ValueError` subclass — a resource file or layout violates OVOS-INTENT-2
(empty file, duplicate `(role, base name)`, a slot in a slot-free role).

## Dialog — [chapter 4](dialog.md)

### `render(phrases, slots=None, vocabularies=None, rng=None) -> str`

Render one phrase from an explicit list. `slots` fills `{name}` slots;
`vocabularies` resolves `<name>` references; `rng` is any object with a
`choice` method (for reproducible output). Raises `UnfilledSlot`, or
`ValueError` if `phrases` is empty.

### `DialogRenderer(resources, name, rng=None, slots=None)`

A stateful, multilingual renderer for the dialog `name`, backed by a
`LocaleResources`. `slots` are default slot values reused on every call.

- **`render(lang, slots=None) -> str`** — render one phrase in `lang`. Avoids
  repeating the previous phrase (per language). Slot precedence: per-call,
  then default, then a random `.entity` value, then `UnfilledSlot`.

### `UnfilledSlot`

`ValueError` subclass — a chosen phrase has a slot with no value.

## Language matching — [chapter 5](language-matching.md)

### `standardize_lang(tag) -> str`

Normalize a BCP-47 tag (underscores, case, canonical forms).

### `lang_distance(desired, supported) -> int`

Distance between two tags: `0` is identical, `>= 10` is not a usable match. A
bare tag is measured from its norm region.

### `closest_lang(target, available, max_distance=10) -> str | None`

The entry of `available` with the smallest `lang_distance`, if it is below
`max_distance` (or exact). Returns the original string, or `None`.

## Linting — [chapter 6](linting.md)

### `lint_locale(path) -> list[Finding]`

Validate every resource file under a locale (or single-language) directory.

### `Finding`

A dataclass with `severity` (`"error"` / `"warning"`), `path`, and `message`.
`str(finding)` formats it as one line.

### `ovos-spec-lint` (command)

CLI wrapper over `lint_locale`. `ovos-spec-lint <path> [--strict]`; exit code
is non-zero on errors (with `--strict`, on warnings too).

## Package

### `__version__`

The installed package version string.
