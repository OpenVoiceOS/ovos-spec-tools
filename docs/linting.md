# 6. Linting

> **Spec coverage.** This chapter is the reference for the locale linter
> (`lint.py`). Every finding enforces a specific clause: template syntax from
> **OVOS-INTENT-1 §3.6**, naming/layout/empty-file/uniqueness from
> **OVOS-INTENT-2 §2/§4.3/§5**, slot-set consistency from **OVOS-INTENT-1 §5.5**
> (restated for `.intent` by **OVOS-INTENT-2 §4.1** / **OVOS-INTENT-3 §5.1**,
> and for `.dialog` by **OVOS-INTENT-2 §4.2**).
>
> Each message names the clause it failed, so a red lint points straight at
> the violated MUST.

`ovos-spec-lint` checks a skill's locale folder against both specs at once:
the **syntax** of every template (OVOS-INTENT-1) and the **naming and layout**
of every file (OVOS-INTENT-2). It reports *every* problem rather than
stopping at the first.

## The command

```bash
ovos-spec-lint path/to/locale
```

The argument may be a whole `locale/` directory (every language subdirectory is
checked) or a single `<lang>/` directory. Output is one line per finding:

```
locale/en-US/play.intent: error: single-branch group (button): ...
locale/en-US/old.rx: warning: .rx is a legacy file type, not an OVOS-INTENT-2 role
locale/english: warning: directory name 'english' is not a BCP-47 language tag

2 error(s), 1 warning(s)
```

The exit code is **non-zero when there are errors**, so the command drops
straight into a CI pipeline. With `--strict`, warnings fail the run too.

## What it checks

**Errors**: the file is wrong.

- a template that does not parse, any malformed form of
  [chapter 2](templates.md).
- an empty file (no templates after comments and blank lines).
- a file that is not valid UTF-8.
- a named slot inside a slot-free role (`.entity` / `.voc` / `.blacklist`).

- templates within one **`.intent`** or **`.dialog`** declaring **different
  slot sets**. Every line of one definition MUST declare the same `{slots}` so
  the engine captures, or the caller fills, the same slots whichever line
  matched or was chosen (OVOS-INTENT-1 §5.5, OVOS-INTENT-2 §4.1/§4.2,
  OVOS-INTENT-3 §5.1).
- a base name outside the allowed charset (lowercase letters, digits,
  underscores).
- an `.entity` whose base name, which names a slot, begins with a digit.
- the same `(role, base name)` appearing twice in one language tree.
- a `<name>` reference to a vocabulary that does not exist.

**Warnings**: suspicious but not fatal.

- a resource file sitting outside any language directory.
- a language directory not named like a BCP-47 tag.

- a language directory with no resource files.
- a legacy file type (`.rx`, `.value`, `.list`, …), not one of the six
  OVOS-INTENT-2 roles.
- a `.blacklist` with no matching `.intent` to suppress.
- a file name that is not lowercase.

A `.prompt` is checked too, but not as a template, it is plain text, so only
its naming and non-emptiness are checked, never template syntax.

### Slot-set consistency

OVOS-INTENT-1 §5.5 says every template of one definition MUST declare the
identical slot set, and a tool "MUST reject" one that does not. This is restated
normatively for each slot-bearing role: `.intent` by OVOS-INTENT-2 §4.1 and
OVOS-INTENT-3 §5.1 ("Every template in one intent MUST declare the same set of
named slots"), `.dialog` by OVOS-INTENT-2 §4.2.

So the linter treats a divergent slot set as an **error** for both. A
phrasing that genuinely needs a different slot, such as:

```
(play|put on) {query}
(play|put on) {query} (on|using) {engine}
```

is **two** intents, not one: §5.5 says "place them in separate files and handle
them individually". (The two-line block above appears as a *worked example* in
OVOS-INTENT-3 §5.3, but that example is illustrative and itself violates the
§5.5 MUST it does not restate. The normative rule governs.)

## Targeting an older spec version

A skill may need to run on a device that has not been updated. `--spec-version`
flags any feature **newer than a target version**, so you learn before
shipping that a skill will not work there:

| Version | Adds |
|---------|------|
| `0` | the legacy, undocumented Mycroft/OVOS de-facto behaviour |
| `1` | the formalized specs, and the `.blacklist` role |
| `2` | `<name>` inline vocabulary references |
| `3` | the `.prompt` role *(the default)* |

```bash
ovos-spec-lint my-skill/locale --spec-version 1
```

With `--spec-version 1`, a template using `<name>` is an **error**. A
version-1 runtime cannot expand it.

With `--spec-version 2`, a `.prompt` file is a **warning**, and with
`--spec-version 0` a `.blacklist` file likewise. An older runtime silently
ignores a role it does not know, so that resource just will not take effect.
The default, `3`, flags nothing extra.

## Using it as a library

The CLI is a thin wrapper over `lint_locale`, which returns the findings so a
tool can process them:

```python
from ovos_spec_tools import lint_locale

findings = lint_locale("my-skill/locale")
for finding in findings:
    print(finding.severity, finding.path, finding.message)

errors = [f for f in findings if f.severity == "error"]
```

Each `Finding` has `.severity` (`"error"` or `"warning"`), `.path`, and
`.message`.

## In CI

Add a step that lints the locale folder of any skill you maintain:

```yaml
- run: pip install ovos-spec-tools
- run: ovos-spec-lint locale
```

A malformed template now fails the build instead of failing a user's device.

## Next

[API reference](api-reference.md), every public name at a glance.

---
[← Bus namespaces](bus-namespaces.md) · [Home](README.md) · [API reference →](api-reference.md)
