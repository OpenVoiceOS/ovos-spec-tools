"""Reference implementation of the OVOS formal specifications.

`ovos-spec-tools` provides the low-level, dependency-light primitives the OVOS
formal specifications describe:

- :func:`~ovos_spec_tools.expansion.expand` — the OVOS-INTENT-1 sentence
  template expander;
- :class:`~ovos_spec_tools.resources.LocaleResources` — the OVOS-INTENT-2
  locale resource-file loader;
- :func:`~ovos_spec_tools.dialog.render` — the OVOS-INTENT-2 §4.2 dialog
  renderer;
- :func:`~ovos_spec_tools.lint.lint_locale` — a locale resource linter, also
  exposed as the ``ovos-spec-lint`` command.
"""
from ovos_spec_tools.dialog import DialogRenderer, UnfilledSlot, render
from ovos_spec_tools.expansion import MalformedTemplate, expand
from ovos_spec_tools.lint import Finding, lint_locale
from ovos_spec_tools.resources import (
    LanguageMatcher,
    LocaleResources,
    MalformedResource,
    read_resource_file,
)
from ovos_spec_tools.version import __version__

__all__ = [
    "expand",
    "MalformedTemplate",
    "LocaleResources",
    "LanguageMatcher",
    "MalformedResource",
    "read_resource_file",
    "render",
    "DialogRenderer",
    "UnfilledSlot",
    "lint_locale",
    "Finding",
    "__version__",
]
