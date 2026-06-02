# AGENTS.md — ovos-spec-tools

Reference implementation of the OVOS formal specifications: a dependency-light Python library and `ovos-spec-lint` CLI providing the conformant primitives those specs describe (sentence template expansion, locale resource loading, dialog/prompt rendering, language-tag matching, bus message envelope, and a locale linter).

## Setup

```bash
pip install -e .            # core, zero runtime dependencies
pip install -e .[langcodes] # adds smart language fallback for LocaleResources / language.py
pip install -e .[test]      # pytest + langcodes
```

Requires Python 3.10+.

## Test

```bash
pytest test
```

The `test/` suite covers every module. `langcodes` must be installed (it is in the `test` extra) or language-fallback paths degrade to exact-match.

## Lint/Typecheck

`ruff` runs in CI via the shared `lint.yml` workflow. No local ruff config is committed; no typechecker is configured. There is no `.pre-commit-config.yaml`.

## Layout

`ovos_spec_tools/` is a flat package, one module per spec primitive:

- `expansion.py` — OVOS-INTENT-1 sentence template expander (`expand`, `MalformedTemplate`).
- `resources.py` — OVOS-INTENT-2 locale loader (`LocaleResources`), `iter_locale_dirs`, `find_lang_dir`, `keyword_form`, `utterance_contains`, `strip_samples`, resource-file readers, role constants.
- `dialog.py` — OVOS-INTENT-2 §4.2 dialog renderer (`render`, `DialogRenderer`, `UnfilledSlot`).
- `prompt.py` — OVOS-INTENT-2 §4.4 `.prompt` renderer (`render_prompt`, `PromptRenderer`).
- `language.py` — OVOS-INTENT-2 §2.2 language-tag matching (`standardize_lang`, `lang_distance`, `lang_matches`, `closest_lang`); uses `langcodes` when present.
- `message.py` — OVOS-MSG-1 bus message envelope (`Message`, `forward`/`reply`/`response`, `serialize`, `DEFAULT_SESSION_ID`).
- `lint.py` — locale linter (`lint_locale`, `Finding`, `main`); console entry point `ovos-spec-lint`.
- `version.py` — version string (do not edit).

`test/` mirrors the modules. `examples/` holds runnable scripts plus sample/dirty locale fixtures and a HuggingFace-dataset exporter. `docs/` is a zero-to-hero guide.

Entry point: console script `ovos-spec-lint` only (`[project.scripts]`). This is **not** an OPM/OVOS plugin or skill — there are no `ovos.plugin.*` or skill entry-point groups.

## Conventions

- Branches: `dev` (work) and `master` (stable). NEVER use `main`.
- Never edit `version.py`; gh-automations bumps semver from conventional-commit prefixes (`feat:`, `fix:`, `feat!:`).
- New repos private by default.
- Commit identity: `JarbasAi <jarbasai@mailfence.com>`.
- Reference `OpenVoiceOS/gh-automations` reusable workflows at `@dev`.
- No Neon / `neon-*` references.
- No meta-commentary (no history, dates, or "design mistake" framing) in docs, commits, code comments, or PRs — describe current state only.
- CI is provided by `OpenVoiceOS/gh-automations`.

## Gotchas

- Core has zero runtime dependencies by design; keep it that way. `langcodes` is optional — guard its use so language resolution degrades to exact-match without it, never imports unconditionally.
- `license_check.yml` runs `warn_only: true`: the published PyPI release predates the SPDX classifier so the package self-audits as unknown; do not treat that warning as a regression.
- `lint.py` understands a `--spec-version` (0–3) gate to flag features newer than a target spec; keep role/feature additions wired into that gate.
- Generated artifacts (`build/`, `*.egg-info/`, `.coverage`) appear on disk but are gitignored and untracked — do not commit them.
