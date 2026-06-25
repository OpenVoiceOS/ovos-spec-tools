"""Reference implementation of the OVOS formal specifications.

`ovos-spec-tools` provides the low-level, dependency-light primitives the OVOS
formal specifications describe:

- :func:`~ovos_spec_tools.expansion.expand` — the OVOS-INTENT-1 sentence
  template expander;
- :class:`~ovos_spec_tools.resources.LocaleResources` — the OVOS-INTENT-2
  locale resource-file loader;
- :func:`~ovos_spec_tools.dialog.render` / :class:`~ovos_spec_tools.dialog.DialogRenderer`
  — the OVOS-INTENT-2 §4.2 dialog renderer;
- :func:`~ovos_spec_tools.prompt.render_prompt` / :class:`~ovos_spec_tools.prompt.PromptRenderer`
  — the OVOS-INTENT-2 §4.4 ``.prompt`` renderer;
- :func:`~ovos_spec_tools.language.standardize_lang`,
  :func:`~ovos_spec_tools.language.lang_distance`,
  :func:`~ovos_spec_tools.language.lang_matches`, and
  :func:`~ovos_spec_tools.language.closest_lang` — language-tag normalization,
  distance, match checking, and closest-match resolution;
- :func:`~ovos_spec_tools.resources.iter_locale_dirs` — locale subdirectory
  discovery with optional native-language filtering;
- :func:`~ovos_spec_tools.resources.keyword_form`,
  :func:`~ovos_spec_tools.resources.utterance_contains`,
  :func:`~ovos_spec_tools.resources.strip_samples` — slot-free template
  grouping (§4.3) and utterance match / strip primitives;
- :class:`~ovos_spec_tools.message.Message` — the OVOS-MSG-1 bus message
  envelope with the ``forward`` / ``reply`` / ``response`` derivations;
- :func:`~ovos_spec_tools.lint.lint_locale` — a locale resource linter, also
  exposed as the ``ovos-spec-lint`` command.
"""
from ovos_spec_tools.dialog import DialogRenderer, UnfilledSlot, render
from ovos_spec_tools.expansion import MalformedTemplate, expand, inline_keywords
from ovos_spec_tools.message import (
    DEFAULT_SESSION_ID,
    MalformedMessage,
    Message,
)
from ovos_spec_tools.language import (
    closest_lang,
    lang_distance,
    lang_matches,
    standardize_lang,
)
from ovos_spec_tools.lint import Finding, lint_locale
from ovos_spec_tools.messages import (
    MIGRATION_MAP,
    SPEC_TO_LEGACY,
    SpecMessage,
    migration_counterpart,
)
from ovos_spec_tools.prompt import PromptRenderer, render_prompt
from ovos_spec_tools.resources import (
    LocaleResources,
    MalformedResource,
    find_lang_dir,
    iter_locale_dirs,
    keyword_form,
    normalize_for_match,
    read_prompt_file,
    read_resource_file,
    strip_samples,
    utterance_contains,
)
from ovos_spec_tools.version import __version__

__all__ = [
    "Message",
    "MalformedMessage",
    "DEFAULT_SESSION_ID",
    "expand",
    "inline_keywords",
    "MalformedTemplate",
    "LocaleResources",
    "MalformedResource",
    "find_lang_dir",
    "iter_locale_dirs",
    "keyword_form",
    "normalize_for_match",
    "read_resource_file",
    "read_prompt_file",
    "strip_samples",
    "utterance_contains",
    "render",
    "DialogRenderer",
    "UnfilledSlot",
    "render_prompt",
    "PromptRenderer",
    "standardize_lang",
    "lang_distance",
    "lang_matches",
    "closest_lang",
    "lint_locale",
    "Finding",
    "SpecMessage",
    "MIGRATION_MAP",
    "SPEC_TO_LEGACY",
    "migration_counterpart",
    "__version__",
]
