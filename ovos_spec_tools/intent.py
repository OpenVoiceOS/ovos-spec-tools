"""Plugin-agnostic intent-definition primitives for the OVOS-INTENT-4 keyword model.

This module is a clean, dependency-light ``IntentBuilder`` / ``Intent`` pair —
the plugin-agnostic form of the intent-definition classes ``ovos-workshop``
exposes to skills. It carries **no** ``adapt`` dependency: it is pure data
describing the **structure** of a keyword intent —
which vocabularies are *required*, *optional*, *one_of*, or *excluded* — exactly
as OVOS-INTENT-4 §5 defines the ``ovos.intent.register.keyword`` payload.

The split of responsibility, per OVOS-INTENT-4 §5.1, is:

- the **builder** captures the intent *structure* (vocabulary **names** under
  each role) — that is all a skill expresses when it writes
  ``IntentBuilder("Foo").require("Set").one_of("Up", "Down").build()``;
- a **producer** (the skill loader) later inlines each vocabulary's expanded
  ``samples`` to form the wire :meth:`Intent.to_keyword_payload` descriptors —
  file paths never cross the bus (§5.1).

Because samples are inlined downstream, the descriptors this module emits carry
``name`` only by default. A producer that already has the expanded samples may
supply them through the ``samples`` argument of :meth:`Intent.to_keyword_payload`.

The public API is **source-compatible** with the ``ovos-workshop`` classes it
replaces, so skills and intent engines can re-point their imports here without
code changes:

- ``IntentBuilder(name).require(t, attribute_name=None, optional=False)``,
  ``.optionally(t, attribute_name=None)``, ``.one_of(*args)``,
  ``.exclude(t)``, ``.build()``, ``.name``;
- ``Intent(name, requires, at_least_one, optional, excludes)`` exposing
  ``.name``, ``.requires``, ``.at_least_one``, ``.optional``, ``.excludes``;
- :func:`open_intent_envelope` reconstructing an :class:`Intent` from a Message.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "Intent",
    "IntentBuilder",
    "MalformedIntent",
    "open_intent_envelope",
    "voc_match",
]

# A keyword role entry as the legacy adapt/workshop classes stored it:
# ``(entity_type, attribute_name)`` for required/optional, a bare entity type
# for excludes, and a tuple of entity types for each one_of group.
RoleEntry = Tuple[str, str]


class MalformedIntent(ValueError):
    """A keyword intent that violates an OVOS-INTENT-3 §4.2 structural MUST.

    Raised when a built / emitted intent breaks one of the two §4.2
    well-formedness MUSTs:

    - it declares **no** ``required`` and **no** ``one-of`` constraint, so
      nothing must be present for it to match ("an intent with only optional
      and excluded constraints has nothing that must be present and is
      malformed");
    - it lists the **same vocabulary under two different roles** ("a vocabulary
      MUST appear under at most one role within a single intent. Listing the
      same vocabulary under two roles … is contradictory and malformed").

    These are the data-model counterparts of the checks the locale linter
    already performs; raising at build/emit time means an invalid keyword
    intent is rejected before it can be registered on the bus.
    """


class Intent:
    """A built keyword-intent **definition** — name plus the four role lists.

    This mirrors the attribute surface of the legacy ``ovos-workshop`` /
    ``adapt`` ``Intent`` so existing readers keep working:

    - ``name`` (str) — the intent name (skills munge it to
      ``<skill_id>:<name>`` before registration);
    - ``requires`` — ``list[(entity_type, attribute_name)]``; every entry MUST
      occur (OVOS-INTENT-4 §5.2 ``required``);
    - ``at_least_one`` — ``list[tuple[entity_type, ...]]``; each inner tuple is
      a group, one member of which MUST occur (§5.2 ``one_of``);
    - ``optional`` — ``list[(entity_type, attribute_name)]``; captured if
      present (§5.2 ``optional``);
    - ``excludes`` — ``list[entity_type]``; any occurrence suppresses the
      match (§5.2 ``excluded``).

    Unlike the legacy class this carries **no matching logic** — matching is a
    pipeline-plugin concern (OVOS-PIPELINE-1). It is pure data: the structural
    half of a ``ovos.intent.register.keyword`` registration, ready for a
    producer to inline vocabulary samples into (§5.1).
    """

    def __init__(self, name: str = "",
                 requires: Optional[Sequence] = None,
                 at_least_one: Optional[Sequence] = None,
                 optional: Optional[Sequence] = None,
                 excludes: Optional[Sequence] = None):
        """
        Args:
            name: the intent name.
            requires: required entries, each ``(entity_type, attribute_name)``
                or a bare ``entity_type`` (normalized to a pair).
            at_least_one: ``one_of`` groups, each a sequence of entity types.
            optional: optional entries, same shape as ``requires``.
            excludes: excluded entity types, each a bare ``entity_type`` (a
                ``(type, attr)`` pair is accepted and reduced to its type).
        """
        self.name = name
        self.requires: List[RoleEntry] = [self._as_pair(r)
                                          for r in (requires or [])]
        self.at_least_one: List[Tuple[str, ...]] = [tuple(self._as_name(e)
                                                          for e in group)
                                                    for group in
                                                    (at_least_one or [])]
        self.optional: List[RoleEntry] = [self._as_pair(o)
                                         for o in (optional or [])]
        self.excludes: List[str] = [self._as_name(e) for e in (excludes or [])]

    @staticmethod
    def _as_pair(entry) -> RoleEntry:
        """Normalize an entry to ``(entity_type, attribute_name)``.

        Accepts a bare string (attribute defaults to the type) or any 2-tuple.
        """
        if isinstance(entry, str):
            return (entry, entry)
        entity_type, attribute_name = entry[0], entry[1]
        return (entity_type, attribute_name or entity_type)

    @staticmethod
    def _as_name(entry) -> str:
        """Reduce an entry to its bare entity-type name."""
        if isinstance(entry, str):
            return entry
        return entry[0]

    # -- OVOS-INTENT-3 §4.2 well-formedness ----------------------------------

    def validate(self) -> "Intent":
        """Reject an intent that violates an OVOS-INTENT-3 §4.2 structural MUST.

        Enforces the two §4.2 well-formedness rules the spec calls ``MUST``:

        - **(a)** a keyword intent **MUST** declare at least one ``required``
          or ``one-of`` constraint — "an intent with only optional and
          excluded constraints has nothing that must be present and is
          malformed";
        - **(b)** a vocabulary **MUST** appear under at most one role — listing
          the same vocabulary under two roles (e.g. both required and excluded)
          "is contradictory and malformed".

        Returns ``self`` so it can be used inline (``Intent(...).validate()``).

        Raises:
            MalformedIntent: if either §4.2 rule is violated.
        """
        # (a) at least one required or one-of must be present.
        if not self.requires and not self.at_least_one:
            raise MalformedIntent(
                f"keyword intent {self.name!r} declares no required and no "
                "one-of constraint — it has nothing that must be present "
                "(OVOS-INTENT-3 §4.2)")

        # (b) a vocabulary appears under at most one role. Collect every
        # (vocabulary -> roles it appears in) and reject any vocabulary that
        # spans more than one role. one-of vocabularies count once per name
        # regardless of how many groups list them.
        roles: Dict[str, set] = {}
        for name, _ in self.requires:
            roles.setdefault(name, set()).add("required")
        for name, _ in self.optional:
            roles.setdefault(name, set()).add("optional")
        for group in self.at_least_one:
            for name in group:
                roles.setdefault(name, set()).add("one_of")
        for name in self.excludes:
            roles.setdefault(name, set()).add("excluded")
        clashes = {name: sorted(r) for name, r in roles.items() if len(r) > 1}
        if clashes:
            detail = "; ".join(f"{name!r} under {roles}"
                               for name, roles in sorted(clashes.items()))
            raise MalformedIntent(
                f"keyword intent {self.name!r} lists a vocabulary under more "
                f"than one role — {detail} (OVOS-INTENT-3 §4.2)")
        return self

    # -- OVOS-INTENT-4 §5 emission -------------------------------------------

    @staticmethod
    def _descriptor(name: str,
                    samples: Optional[Dict[str, List[str]]]) -> Dict[str, Any]:
        """Build one §5.1 vocabulary descriptor for ``name``.

        ``samples`` is an optional ``vocab_name -> samples`` map a producer may
        supply when it has already expanded the vocabularies. When absent — the
        usual builder-side case — only ``name`` is emitted and the producer is
        expected to inline ``samples`` before the payload crosses the bus
        (§5.1).
        """
        descriptor: Dict[str, Any] = {"name": name}
        if samples and name in samples:
            descriptor["samples"] = list(samples[name])
        return descriptor

    def to_keyword_payload(self, skill_id: Optional[str] = None,
                           lang: Optional[str] = None,
                           samples: Optional[Dict[str, List[str]]] = None
                           ) -> Dict[str, Any]:
        """Emit the OVOS-INTENT-4 §5.2 keyword-registration structure.

        Returns a dict with the four shape-stable role keys ``required``,
        ``optional``, ``one_of``, ``excluded`` (§5.2 mandates all four are
        present, even when empty), each a list of vocabulary descriptors (§5.1).
        ``one_of`` is a list of groups, each a list of descriptors.

        Identity fields (``skill_id``, ``intent_name``, ``lang``; §3.2) are
        included when provided — ``intent_name`` is always set from ``name``.
        Vocabulary ``samples`` are inlined per descriptor only when the
        ``samples`` map carries them; otherwise the producer inlines them
        before emission (§5.1).

        Args:
            skill_id: optional ``skill_id`` identity field (§3.2).
            lang: optional ``lang`` identity field (§3.2).
            samples: optional ``vocab_name -> expanded samples`` map; when a
                name is present its descriptor gains a ``samples`` entry.

        Returns:
            the §5.2 keyword payload structure.

        Raises:
            MalformedIntent: if the intent violates an OVOS-INTENT-3 §4.2
                well-formedness MUST — a register payload MUST NOT be emitted
                for an intent with no required/one-of constraint or with a
                vocabulary listed under two roles.
        """
        self.validate()
        payload: Dict[str, Any] = {}
        if skill_id is not None:
            payload["skill_id"] = skill_id
        payload["intent_name"] = self.name
        if lang is not None:
            payload["lang"] = lang
        payload["required"] = [self._descriptor(t, samples)
                               for t, _ in self.requires]
        payload["optional"] = [self._descriptor(t, samples)
                               for t, _ in self.optional]
        payload["one_of"] = [[self._descriptor(t, samples) for t in group]
                             for group in self.at_least_one]
        payload["excluded"] = [self._descriptor(t, samples)
                               for t in self.excludes]
        return payload

    def __repr__(self) -> str:
        return (f"Intent(name={self.name!r}, requires={self.requires!r}, "
                f"at_least_one={self.at_least_one!r}, "
                f"optional={self.optional!r}, excludes={self.excludes!r})")

    def __eq__(self, other) -> bool:
        if not isinstance(other, Intent):
            return NotImplemented
        return (self.name == other.name and
                self.requires == other.requires and
                self.at_least_one == other.at_least_one and
                self.optional == other.optional and
                self.excludes == other.excludes)


class IntentBuilder:
    """Fluent builder for a keyword :class:`Intent` — adapt-free.

    Source-compatible with the ``ovos-workshop`` / ``adapt`` ``IntentBuilder``:
    it accumulates vocabulary **names** under the four OVOS-INTENT-4 §5 roles
    and :meth:`build` freezes them into an :class:`Intent`. It captures only the
    intent *structure* (§5.1) — no samples, no matching.

    Example:
        >>> intent = (IntentBuilder("SetBrightness")
        ...           .require("Set")
        ...           .require("Brightness")
        ...           .one_of("Up", "Down")
        ...           .optionally("Politely")
        ...           .exclude("Question")
        ...           .build())
        >>> intent.to_keyword_payload()["required"]
        [{'name': 'Set'}, {'name': 'Brightness'}]
    """

    def __init__(self, intent_name: str):
        """
        Args:
            intent_name: the name of the intent being built.
        """
        self.name = intent_name
        self.requires: List[RoleEntry] = []
        self.at_least_one: List[Tuple[str, ...]] = []
        self.optional: List[RoleEntry] = []
        self.excludes: List[str] = []

    def require(self, entity_type: str, attribute_name: Optional[str] = None,
                optional: bool = False) -> "IntentBuilder":
        """Require (or, with ``optional=True``, optionally capture) a vocabulary.

        Args:
            entity_type: the vocabulary name.
            attribute_name: name of the captured attribute on the match result;
                defaults to ``entity_type``.
            optional: when True, behaves like :meth:`optionally` — kept for
                source-compatibility with the legacy signature.

        Returns:
            self, for chaining.
        """
        if not attribute_name:
            attribute_name = entity_type
        if optional:
            self.optional.append((entity_type, attribute_name))
        else:
            self.requires.append((entity_type, attribute_name))
        return self

    def optionally(self, entity_type: str,
                   attribute_name: Optional[str] = None) -> "IntentBuilder":
        """Optionally capture a vocabulary (OVOS-INTENT-4 §5.2 ``optional``).

        Args:
            entity_type: the vocabulary name.
            attribute_name: captured-attribute name; defaults to ``entity_type``.

        Returns:
            self, for chaining.
        """
        if not attribute_name:
            attribute_name = entity_type
        self.optional.append((entity_type, attribute_name))
        return self

    def one_of(self, *args: str) -> "IntentBuilder":
        """Require at least one of the given vocabularies (§5.2 ``one_of``).

        Each call adds one **group**; at least one member of each group must
        occur. Separate calls express ``one_of(A, B)`` *and* ``one_of(C, D)``.

        Args:
            *args: vocabulary names forming one group.

        Returns:
            self, for chaining.
        """
        self.at_least_one.append(tuple(args))
        return self

    def exclude(self, entity_type: str) -> "IntentBuilder":
        """Forbid a vocabulary (§5.2 ``excluded``): its presence suppresses the
        match.

        Args:
            entity_type: the vocabulary name to exclude.

        Returns:
            self, for chaining.
        """
        self.excludes.append(entity_type)
        return self

    def build(self) -> Intent:
        """Freeze the accumulated roles into a validated :class:`Intent`.

        The result is checked against the OVOS-INTENT-3 §4.2 well-formedness
        MUSTs (:meth:`Intent.validate`): a built intent must declare at least
        one required or one-of constraint, and must not list a vocabulary under
        two roles. A malformed builder state raises :class:`MalformedIntent`.
        """
        return Intent(self.name, self.requires, self.at_least_one,
                      self.optional, self.excludes).validate()


def open_intent_envelope(message) -> Intent:
    """Reconstruct an :class:`Intent` from a Message payload.

    Mirrors the legacy ``ovos-workshop`` helper: it reads an intent definition
    out of ``message.data``. Both the legacy serialization keys
    (``name`` / ``requires`` / ``at_least_one`` / ``optional`` / ``excludes``,
    as produced by ``Intent.__dict__``) and the OVOS-INTENT-4 §5.2 wire keys
    (``intent_name`` / ``required`` / ``one_of`` / ``optional`` / ``excluded``,
    whose role entries are vocabulary descriptors) are accepted, so the helper
    round-trips a definition serialized by either generation.

    For §5.2 descriptors only the ``name`` is read into the role list — the
    inlined ``samples`` are not part of the structural :class:`Intent`.

    Args:
        message: a Message-like object exposing a ``data`` mapping.

    Returns:
        the reconstructed :class:`Intent`.
    """
    data = getattr(message, "data", None)
    if data is None:
        data = message  # tolerate being handed a raw dict

    name = data.get("name") or data.get("intent_name") or ""

    def _names(role) -> List[str]:
        # Accept §5.2 descriptors ({"name": ...}), bare strings, or legacy
        # (type, attr) pairs — reduce each to its vocabulary name.
        out = []
        for entry in role or []:
            if isinstance(entry, dict):
                out.append(entry.get("name"))
            elif isinstance(entry, str):
                out.append(entry)
            else:  # (entity_type, attribute_name)
                out.append(entry[0])
        return out

    requires = data.get("requires")
    if requires is None:
        requires = _names(data.get("required"))

    optional = data.get("optional")
    # legacy `optional` is already pairs; §5.2 `optional` is descriptors
    if optional and isinstance(optional[0], dict):
        optional = _names(optional)

    excludes = data.get("excludes")
    if excludes is None:
        excludes = _names(data.get("excluded"))

    at_least_one = data.get("at_least_one")
    if at_least_one is None:
        # §5.2 `one_of`: list of groups, each a list of descriptors.
        at_least_one = [_names(group) for group in data.get("one_of") or []]

    return Intent(name, requires, at_least_one, optional, excludes)


def voc_match(utterance: str, voc_name: str, lang: str,
              locale, *,
              exact: bool = False,
              strip_diacritics: bool = True,
              strip_punct: bool = True) -> bool:
    """Load a named ``.voc`` and test whether ``utterance`` matches it.

    This is the plugin-agnostic equivalent of
    ``OVOSAbstractApplication.voc_match`` / the skill ``voc_match`` — the
    helper common-query, OCP, and other pipelines use without depending on
    ``ovos-workshop``. It loads the ``<voc_name>.voc`` for ``lang`` and
    matches with whole-word OVOS-INTENT-2 §4.3 semantics — identical to the
    skill helper (so pipelines behave the same): a sample ``yes`` matches
    ``"yes, please"`` but not ``"yesterday"``.

    Args:
        utterance: the (ASR-normalized) text to test.
        voc_name: the ``.voc`` base name (no extension).
        lang: BCP-47 language tag of the resource to load.
        locale: either a :class:`~ovos_spec_tools.resources.LocaleResources`
            instance, or a ``locale/`` directory path (``str`` / ``Path``), or
            a sequence of such paths searched in override-precedence order
            (user, skill, core — see
            :class:`~ovos_spec_tools.resources.LocaleResources`).
        exact: require equality after normalization rather than whole-word
            substring containment.
        strip_diacritics: forwarded to the matcher.
        strip_punct: forwarded to the matcher.

    Returns:
        ``True`` iff any ``.voc`` sample matches; ``False`` when the resource
        does not exist for the language.
    """
    from ovos_spec_tools.resources import LocaleResources

    if isinstance(locale, LocaleResources):
        resources = locale
    elif isinstance(locale, (str, bytes)) or hasattr(locale, "__fspath__"):
        resources = LocaleResources(str(locale))
    else:  # a sequence of locale dirs, highest precedence first
        dirs = [str(p) for p in locale]
        if not dirs:
            return False
        # Map the precedence-ordered dirs onto the user/skill/core slots, which
        # LocaleResources searches in that same order. A single dir is the
        # skill locale; the spare slots stay empty.
        if len(dirs) == 1:
            resources = LocaleResources(skill_locale=dirs[0])
        else:
            resources = LocaleResources(
                user_locale=dirs[0],
                skill_locale=dirs[1],
                core_locale=dirs[2] if len(dirs) > 2 else None)
    return resources.voc_match(
        utterance, voc_name, lang, exact=exact,
        strip_diacritics=strip_diacritics, strip_punct=strip_punct)
