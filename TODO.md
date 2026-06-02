# TODO — ovos-spec-tools

## Open issues

- [ ] #2 Dependency Dashboard (Renovate bot)

## Gaps

- [ ] `license_check.yml` runs in `warn_only` mode because the PyPI release predates the SPDX license classifier; re-publish so the package self-audits cleanly, then drop `warn_only`.
- [ ] No `coverage_source` enforcement: `coverage.yml` sets `min_coverage: 0`; raise once the suite is judged complete.
- [ ] Build/egg-info/.coverage artifacts present in the working tree (gitignored, untracked) — keep the tree clean before packaging.

## Code TODOs

None found.
