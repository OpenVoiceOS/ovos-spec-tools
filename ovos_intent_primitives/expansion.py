"""Reference expander for OVOS-INTENT-1 — the Sentence Template Grammar.

This module is the reference implementation of the **Expander** conformance
role of OVOS-INTENT-1 version 2. It turns a *sentence template* into its
**sample set**: the finite set of sample sentences the template denotes.

The grammar has four tokens:

- literal words;
- ``(a|b|c)`` alternatives;
- ``[x]`` optional segments, equivalent to ``(x|)``;
- ``{name}`` named slots — opaque, carried through unchanged, never expanded;
- ``<name>`` inline vocabulary references — replaced, before expansion, by a
  named slot-free vocabulary (OVOS-INTENT-1 §3.7).

Input is assumed to be already ASR-normalized (OVOS-INTENT-1 §2): lowercase,
alphanumeric word tokens separated by single spaces. This module does **not**
normalize; it expands.

Malformed templates (OVOS-INTENT-1 §3.6) raise :class:`MalformedTemplate`.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = ["expand", "MalformedTemplate"]

# A slot or vocabulary name: lowercase ASCII letters, digits, underscores;
# never beginning with a digit (OVOS-INTENT-1 §3.4).
_NAME_RE = re.compile(r"[a-z][a-z0-9_]*")
# A named-slot token and an inline-vocabulary-reference token. The interiors
# forbid the matching bracket so a malformed/nested token cannot be matched.
_SLOT_TOKEN_RE = re.compile(r"\{([^{}]*)\}")
_VOC_TOKEN_RE = re.compile(r"<([^<>]*)>")
# Two named slots in a sample with only whitespace between them.
_ADJACENT_SLOTS_RE = re.compile(r"\}\s*\{")


class MalformedTemplate(ValueError):
    """A template that violates OVOS-INTENT-1 §3.6.

    Raised for unbalanced metacharacters, single-branch groups, empty samples,
    slot-only templates, adjacent slots, repeated slot names, and undefined or
    cyclic vocabulary references.
    """


def expand(template: str,
           vocabularies: Optional[Dict[str, Sequence[str]]] = None) -> List[str]:
    """Expand a template to its sample set (OVOS-INTENT-1 §4).

    Args:
        template: a sentence template in the OVOS-INTENT-1 grammar.
        vocabularies: maps a vocabulary name to its members — a sequence of
            slot-free templates (the lines of a ``.voc``). Required only if
            ``template`` contains ``<name>`` references.

    Returns:
        The sample set: distinct sample sentences, in first-seen order. Each
        is a single-spaced string of literal words and opaque ``{name}`` slots.

    Raises:
        MalformedTemplate: if the template (or a referenced vocabulary) is
            malformed per OVOS-INTENT-1 §3.6.
    """
    return _expand(template, dict(vocabularies or {}), ())


def _expand(template: str,
            vocabularies: Dict[str, Sequence[str]],
            stack: Tuple[str, ...]) -> List[str]:
    """Expand ``template``; ``stack`` is the chain of vocabularies being
    resolved, for cycle detection."""
    if not isinstance(template, str):
        raise MalformedTemplate(f"template must be a string, got {type(template)!r}")

    _check_balanced(template)
    _check_names(template)

    # Slot-only template (§3.6): the whole template is a single named slot.
    if _SLOT_TOKEN_RE.fullmatch(template.strip()):
        raise MalformedTemplate(
            f"slot-only template {template!r}: a template must carry at least "
            f"one literal word")

    resolved = _resolve_references(template, vocabularies, stack)
    converted = _convert_optionals(resolved)
    raw = _expand_groups(converted)

    samples: List[str] = []
    for sentence in raw:
        sentence = " ".join(sentence.split())  # normalize whitespace (§4.1)
        if sentence not in samples:  # remove duplicates (§4.1)
            samples.append(sentence)

    for sentence in samples:
        _check_sample(sentence, template)
    return samples


def _check_balanced(template: str) -> None:
    """Reject unbalanced or malformed metacharacters (§3.6)."""
    # `{name}` and `<name>` are flat tokens — they do not nest. Strip every
    # well-formed token; any bracket left behind is unbalanced or nested.
    residue = _SLOT_TOKEN_RE.sub(" ", template)
    if "{" in residue or "}" in residue:
        raise MalformedTemplate(
            f"unbalanced or nested braces in template {template!r}")
    residue = _VOC_TOKEN_RE.sub(" ", residue)
    if "<" in residue or ">" in residue:
        raise MalformedTemplate(
            f"unbalanced or nested angle brackets in template {template!r}")

    # `(...)` and `[...]` nest; check with a stack.
    opener = {")": "(", "]": "["}
    stack: List[str] = []
    for char in template:
        if char in "([":
            stack.append(char)
        elif char in ")]":
            if not stack or stack[-1] != opener[char]:
                raise MalformedTemplate(
                    f"unbalanced metacharacters in template {template!r}")
            stack.pop()
    if stack:
        raise MalformedTemplate(
            f"unbalanced metacharacters in template {template!r}")


def _check_names(template: str) -> None:
    """Reject slot or vocabulary names outside the §3.4 charset."""
    for match in _SLOT_TOKEN_RE.finditer(template):
        if not _NAME_RE.fullmatch(match.group(1)):
            raise MalformedTemplate(
                f"invalid slot name {{{match.group(1)}}}: a name is lowercase "
                f"letters, digits and underscores, not beginning with a digit")
    for match in _VOC_TOKEN_RE.finditer(template):
        if not _NAME_RE.fullmatch(match.group(1)):
            raise MalformedTemplate(
                f"invalid vocabulary name <{match.group(1)}>: a name is "
                f"lowercase letters, digits and underscores, not beginning "
                f"with a digit")


def _resolve_references(template: str,
                        vocabularies: Dict[str, Sequence[str]],
                        stack: Tuple[str, ...]) -> str:
    """Resolve every ``<name>`` (§4.1 step 1), recursively, leftmost first."""
    while True:
        match = _VOC_TOKEN_RE.search(template)
        if match is None:
            return template
        name = match.group(1)

        if name in stack:
            raise MalformedTemplate(
                f"cyclic vocabulary reference <{name}> "
                f"(chain: {' -> '.join(stack + (name,))})")
        if name not in vocabularies:
            raise MalformedTemplate(f"undefined vocabulary reference <{name}>")

        members: List[str] = []
        for member_template in vocabularies[name]:
            for member in _expand(member_template, vocabularies, stack + (name,)):
                if "{" in member or "}" in member:
                    raise MalformedTemplate(
                        f"vocabulary <{name}> is not slot-free: member "
                        f"{member!r} contains a named slot")
                if member not in members:
                    members.append(member)
        if not members:
            raise MalformedTemplate(f"empty vocabulary <{name}>")

        # A single-member vocabulary substitutes its bare member; two or more
        # substitute as an alternatives group.
        if len(members) == 1:
            substitution = members[0]
        else:
            substitution = "(" + "|".join(members) + ")"
        template = template[:match.start()] + substitution + template[match.end():]


def _convert_optionals(template: str) -> str:
    """Replace every ``[x]`` with ``(x|)`` (§4.1 step 2)."""
    while "[" in template:
        open_idx = template.rfind("[")
        close_idx = template.find("]", open_idx)
        inner = template[open_idx + 1:close_idx]
        template = (template[:open_idx] + "(" + inner + "|)"
                    + template[close_idx + 1:])
    return template


def _expand_groups(template: str) -> List[str]:
    """Expand every ``(...)`` group by Cartesian product (§4.1 step 3)."""
    open_idx = template.rfind("(")
    if open_idx == -1:
        return [template]
    close_idx = template.find(")", open_idx)
    inner = template[open_idx + 1:close_idx]
    branches = inner.split("|")
    if len(branches) == 1:
        raise MalformedTemplate(
            f"single-branch group ({inner}): a group must offer a choice "
            f"between at least two branches")
    prefix = template[:open_idx]
    suffix = template[close_idx + 1:]
    result: List[str] = []
    for branch in branches:
        result.extend(_expand_groups(prefix + branch + suffix))
    return result


def _check_sample(sentence: str, template: str) -> None:
    """Reject a sample that is malformed per §3.6."""
    if sentence == "":
        raise MalformedTemplate(
            f"template {template!r} yields an empty sample")
    if _ADJACENT_SLOTS_RE.search(sentence):
        raise MalformedTemplate(
            f"adjacent slots in sample {sentence!r} of template {template!r}: "
            f"a literal word must separate any two slots")
    names = _SLOT_TOKEN_RE.findall(sentence)
    if len(names) != len(set(names)):
        raise MalformedTemplate(
            f"repeated slot name in sample {sentence!r} of template "
            f"{template!r}: each slot is defined once per sample")
