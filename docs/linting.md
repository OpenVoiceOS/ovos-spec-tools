# 6. Linting

`ovos-spec-lint` checks a skill's locale folder against both specs at once —
the **syntax** of every template (OVOS-INTENT-1) and the **naming and layout**
of every file (OVOS-INTENT-2) — and reports *every* problem rather than
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

The exit code is **non-zero when there are errors** — so the command drops
straight into a CI pipeline. With `--strict`, warnings fail the run too.

## What it checks

**Errors** — the file is wrong:

- a template that does not parse — any malformed form of
  [chapter 2](templates.md);
- an empty file (no templates after comments and blank lines);
- a named slot inside a slot-free role (`.entity` / `.voc` / `.blacklist`);
- a base name outside the allowed charset (lowercase letters, digits,
  underscores);
- an `.entity` whose base name — which names a slot — begins with a digit;
- the same `(role, base name)` appearing twice in one language tree;
- a `<name>` reference to a vocabulary that does not exist.

**Warnings** — suspicious but not fatal:

- a resource file sitting outside any language directory;
- a language directory not named like a BCP-47 tag;
- a legacy file type (`.rx`, `.value`, `.list`, …) — not one of the five
  OVOS-INTENT-2 roles;
- a file name that is not lowercase.

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

[API reference](api-reference.md) — every public name at a glance.
