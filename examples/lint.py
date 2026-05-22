"""Linting a locale folder programmatically.

`lint_locale()` is what the `ovos-spec-lint` command wraps; it returns every
`Finding` so a tool can process them. Run: `python examples/lint.py`

See dirty-locale/ and README.md for the locale being linted here.
"""
from pathlib import Path

from ovos_spec_tools import lint_locale

dirty_locale = Path(__file__).parent / "dirty-locale" / "locale"
findings = lint_locale(dirty_locale)

for finding in findings:
    print(finding)

errors = sum(1 for f in findings if f.severity == "error")
warnings = len(findings) - errors
print(f"\n{errors} error(s), {warnings} warning(s)")
