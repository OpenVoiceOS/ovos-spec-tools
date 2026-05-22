"""Reference implementation of the OVOS intent specifications.

`ovos-intent-primitives` provides the low-level, dependency-light primitives
the OVOS intent specifications describe:

- :func:`~ovos_intent_primitives.expansion.expand` — the OVOS-INTENT-1
  sentence template expander.

The resource-file loader (OVOS-INTENT-2) and the dialog renderer
(OVOS-INTENT-2 §4.2) are added in a later release.
"""
from ovos_intent_primitives.expansion import MalformedTemplate, expand
from ovos_intent_primitives.version import __version__

__all__ = ["expand", "MalformedTemplate", "__version__"]
