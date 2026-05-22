"""Reference implementation of the OVOS intent specifications.

`ovos-intent-primitives` provides the low-level, dependency-light primitives
the OVOS intent specifications describe:

- :func:`~ovos_intent_primitives.expansion.expand` — the OVOS-INTENT-1
  sentence template expander;
- :class:`~ovos_intent_primitives.resources.LocaleResources` — the
  OVOS-INTENT-2 locale resource-file loader;
- :func:`~ovos_intent_primitives.dialog.render` — the OVOS-INTENT-2 §4.2
  dialog renderer.
"""
from ovos_intent_primitives.dialog import UnfilledSlot, render
from ovos_intent_primitives.expansion import MalformedTemplate, expand
from ovos_intent_primitives.resources import (
    LocaleResources,
    MalformedResource,
    read_resource_file,
)
from ovos_intent_primitives.version import __version__

__all__ = [
    "expand",
    "MalformedTemplate",
    "LocaleResources",
    "MalformedResource",
    "read_resource_file",
    "render",
    "UnfilledSlot",
    "__version__",
]
