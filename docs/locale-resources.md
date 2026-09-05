# 3. Locale resources

> **Spec coverage.** This chapter is the reference for **OVOS-INTENT-2: Locale
> Resource Formats** (`resources.py`). `LocaleResources` is the *conformant
> loader* of OVOS-INTENT-2 §5: it discovers languages (§5.1 / §2), locates a
> file under the override precedence (§5.2 / §2.1), applies the common reader
> (§5.3 / §3), applies the per-format rule (§5.4 / §4), and rejects an empty
> file (§5.5 / §5).
>
> Template expansion is delegated to the OVOS-INTENT-1
> Expander ([chapter 2](templates.md)).

A skill ships its localized text as plain-text files under a `locale/` folder.
This chapter covers what those files are and how `LocaleResources` loads them.
It is the implementation of OVOS-INTENT-2.

## The folder layout

```
my-skill/
└── locale/
    ├── en-US/
    │   ├── play.intent
    │   ├── confirm.dialog
    │   ├── media.entity
    │   ├── yes.voc
    │   └── trailers.blacklist
    ├── pt-PT/
    │   └── …
    └── de-DE/
        └── …
```

One subdirectory per language, named with a **BCP-47 tag** (`en-US`, `pt-PT`,
`zh-Hans`). A language directory may itself contain subdirectories. They are
an authoring convenience and carry no meaning. A recursive search finds a
resource.

A resource is identified by its **`(role, base name)`** pair,
so `confirm.intent` and `confirm.dialog` are two distinct resources.

## The six roles

The file extension is a resource's **role**:

| Role | Extension | Slots? | What it is |
|------|-----------|--------|------------|
| Intent | `.intent` | yes | training samples for one skill action |
| Dialog | `.dialog` | yes | phrases the assistant speaks back |
| Entity | `.entity` | no | example values for a slot |
| Vocabulary | `.voc` | no | a named keyword / phrase set |
| Blacklist | `.blacklist` | no | phrases that suppress an intent |

| Role | Extension | Slots? | What it is |
|------|-----------|--------|------------|
| Prompt | `.prompt` | yes | a whole-file prompt for a language model |

The first five are **lists of templates** ([chapter 2](templates.md)), one
per line, with `#` comment lines and blank lines ignored. `.intent` and
`.dialog` are **slot-bearing** (they may use `{name}`). `.entity`, `.voc` and
`.blacklist` are **slot-free**.

`.prompt` is the exception: not a template list but **one whole-file document**
read verbatim. Every line, including `#` and blank lines, is kept. It carries
`{name}` substitution points but is otherwise plain text ([chapter 4](dialog.md)).

Legacy OVOS file types (`.rx`, `.value`, `.list`, …) are deliberately *not*
roles here. The linter flags them ([chapter 7](linting.md)).

## Loading with `LocaleResources`

```python
from ovos_spec_tools import LocaleResources

res = LocaleResources("my-skill/locale")
```

The **language is given per call**, not at construction. A locale folder is a
skill's multilingual unit, so one `LocaleResources` serves every language:

```python
res.load_intent("play", "en-US")
res.load_intent("play", "pt-PT")     # same instance
```

Installed **skill** and **core** resources are immutable for the lifetime of
the owning process. `LocaleResources` reads and indexes those trees at
construction and retains their raw lines, dialogs, and prompts in memory. When
no user resource tree is configured, it also pre-expands valid intent, entity,
vocabulary, and blacklist resources. This avoids filesystem discovery and
parsing in the runtime intent path. Recreate the instance after installing or
editing skill/core resources; there is intentionally no refresh operation for
package-owned data.

The optional **user** resource tree is deliberately different. It remains
live and is checked on every call, so a user override can be created, edited,
or removed without rebuilding the installed-resource snapshot. A live user
`.voc` override also re-expands a static intent that references it. When a user
tree is configured, expanded results are therefore computed per call against
the in-memory static snapshot and the current user files instead of being
retained.

The load methods:

| Method | Returns |
|--------|---------|
| `load_intent(name, lang)` | the union of every template's sample set, slots intact |
| `load_entity(name, lang)` | the expanded value set |
| `load_vocabulary(name, lang)` | the expanded phrase set |
| `load_blacklist(name, lang)` | the expanded phrase set |

| Method | Returns |
|--------|---------|
| `load_dialog(name, lang)` | the raw phrase strings, **not** expanded (see below) |
| `load_prompt(name, lang)` | the whole `.prompt` file as one string |
| `vocabularies(lang)` | every `.voc`, as a `name → templates` dict |
| `entities(lang)` | every `.entity`, as a `name → values` dict |

`.intent`, `.entity`, `.voc`, and `.blacklist` are expanded at load time. A
`.dialog` is **not**. Its phrases are returned verbatim, because expansion
happens once per spoken response, on the single phrase chosen
([chapter 4](dialog.md)).

A `.prompt` is returned as the whole file, for a
prompt renderer to fill ([chapter 4](dialog.md)).

`<name>` references inside an `.intent` resolve automatically against the
`.voc` files of the same language, you do not pass vocabularies yourself.

A missing resource raises `FileNotFoundError`. A malformed one raises
`MalformedResource`, each case tied to a spec MUST:

- an **empty file**, OVOS-INTENT-2 §5 ("every file MUST contribute at least
  one template").
- a **duplicate `(role, base name)`** in one language tree, §2 ("MUST NOT share
  a base name anywhere within one language directory tree").
- a **named slot in a slot-free role**, §4.3 (`.entity`/`.voc`/`.blacklist`
  are the slot-free format).

## Override precedence

A resource may come from three places (OVOS-INTENT-2 §2.1), highest priority
first. **First match wins**, and an override replaces the whole lower file:

1. **user**: per-user overrides, under a path the assistant decides.
2. **skill**: the files bundled with the skill.
3. **core**: fallback files shipped by the assistant framework.

```python
res = LocaleResources(
    skill_locale="my-skill/locale",
    core_locale="/opt/ovos/locale",
    user_locale="/home/me/.local/share/ovos/my-skill/locale",
)
```

A file at a higher level replaces the whole lower-level file with the same
`(role, base name)`. The user-data path is **assistant-defined**. This package
takes it as a parameter and imports no configuration of its own. Skill and
core changes require a new `LocaleResources` instance; user changes do not.

## Smart language fallback

OVOS-INTENT-2 §2.2 is explicit that fallback is **non-normative**: a loader
*SHOULD* prefer an exact match and *MAY* fall back to the nearest available
language. `LocaleResources` implements that suggested fallback.

When a skill has no directory for the requested language, it resolves to the
**nearest available** language instead. A request for `en-AU` loads `en-US`.
Static resolution is retained per requested language, so the same instance can
serve an exact language and a fallback one side by side without repeating
installed-directory discovery. The live user tree is still resolved on every
call.

```python
res.load_intent("play", "en-AU")   # finds en-US/ if there is no en-AU/
```

The nearness logic is [language matching](language-matching.md). Two knobs on
the constructor:

- `max_language_distance`: how far a fallback may reach (default 10). `0`
  disables the fallback, leaving exact matches only.
- `lang_resolver`: a `(target, available, max_distance) -> str | None`
  callable, defaulting to `closest_lang`. Replace it to change the policy.

## Next

[Dialog](dialog.md), turning a loaded `.dialog` into a spoken sentence.

---
[← Sentence templates](templates.md) · [Home](README.md) · [Dialog →](dialog.md)
