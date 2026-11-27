# AGENTS.md

`ovos-spec-tools` is the reference implementation of the OVOS specifications in `OpenVoiceOS/architecture`. Each public name implements one spec section. `docs/spec-traceability.md` maps them. Code that no spec names does not go here.

## Map

| Path | Holds |
| :--- | :--- |
| `ovos_spec_tools/expansion.py` | `expand`, `iter_expand`: OVOS-INTENT-1 templates |
| `ovos_spec_tools/resources.py` | `LocaleResources`: OVOS-INTENT-2 locale folders |
| `ovos_spec_tools/dialog.py`, `prompt.py` | Dialog and prompt rendering |
| `ovos_spec_tools/language.py` | Language tags, a re-export of linguatag |
| `ovos_spec_tools/message.py`, `messages.py`, `session.py`, `context.py` | The message envelope, `SpecMessage`, `MIGRATION_MAP`, sessions and intent context |
| `ovos_spec_tools/intent.py`, `intent_topics.py` | The keyword intent model and the intent topics |
| `ovos_spec_tools/lint.py` | The `ovos-spec-lint` command |
| `test/` | The tests |
| `docs/` | The documentation. Start at `docs/index.md`. |

## Setup and test

```bash
uv venv
uv pip install --prerelease=allow -e ".[test]"
.venv/bin/pytest test
```

CI (`build-tests.yml`) runs `test` on Python 3.11 to 3.14 with the `test` extra.

## Rules

- Open pull requests against `dev`, as drafts until CI passes. Never push to `dev` or `master`.
- Use conventional commits. Use `feat:` only for a change that a user or a consumer can see.
- Do not edit `ovos_spec_tools/version.py`. CI sets the version from the commit history.
- Pull requests are squash-merged. Do not squash by hand.
- Put an AI disclosure at the top of each PR and issue that an agent writes. Name the exact model and say that no human reviewed the text.
- Use `uv`, not `pip`. Use floor pins with prereleases (`>=X.Y.Za1`). Use no lockfile and no git URL dependency. All metadata is in `pyproject.toml`.
- The only runtime dependency is `linguatag`. Do not add another one.
- Before you change a public name, search the org for its consumers (`gh search code`) and fix them first. ovos-core, ovos-workshop, ovos-bus-client and ovos-utils import this package.
- A regression test fails on the code before the fix and passes after it.
- A change in behaviour updates the page in `docs/` that describes it, and `docs/spec-traceability.md` when it adds or removes a public name, in the same PR.
