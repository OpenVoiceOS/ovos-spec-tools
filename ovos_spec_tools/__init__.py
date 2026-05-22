"""Reference implementation of the OVOS formal specifications.

`ovos-spec-tools` provides the low-level, dependency-light primitives the OVOS
formal specifications describe:

- :func:`~ovos_spec_tools.expansion.expand` — the OVOS-INTENT-1 sentence
  template expander;
- :class:`~ovos_spec_tools.resources.LocaleResources` — the OVOS-INTENT-2
  locale resource-file loader;
- :func:`~ovos_spec_tools.dialog.render` / :class:`~ovos_spec_tools.dialog.DialogRenderer`
  — the OVOS-INTENT-2 §4.2 dialog renderer;
- :func:`~ovos_spec_tools.language.standardize_lang`,
  :func:`~ovos_spec_tools.language.lang_distance`, and
  :func:`~ovos_spec_tools.language.closest_lang` — language-tag normalization,
  distance, and closest-match resolution;
- :func:`~ovos_spec_tools.lint.lint_locale` — a locale resource linter, also
  exposed as the ``ovos-spec-lint`` command.
"""
from ovos_spec_tools.dialog import DialogRenderer, UnfilledSlot, render
from ovos_spec_tools.expansion import MalformedTemplate, expand
from ovos_spec_tools.language import (
    closest_lang,
    lang_distance,
    standardize_lang,
)
from ovos_spec_tools.lint import Finding, lint_locale
from ovos_spec_tools.resources import (
    LocaleResources,
    MalformedResource,
    read_resource_file,
)
from ovos_spec_tools.version import __version__

__all__ = [
    "expand",
    "MalformedTemplate",
    "LocaleResources",
    "MalformedResource",
    "read_resource_file",
    "render",
    "DialogRenderer",
    "UnfilledSlot",
    "standardize_lang",
    "lang_distance",
    "closest_lang",
    "lint_locale",
    "Finding",
    "__version__",
]
