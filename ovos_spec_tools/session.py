"""Reference implementation of OVOS-SESSION-1 — the session **wire carrier**.

SESSION-1 §1 scopes this module to one thing: the **wire shape** of the
JSON object that travels inside ``Message.context.session``, plus the
consumer rules for reading and propagating it. It is a pure
**WIRE-CARRIER**. The *semantics* of every field — recency ordering,
the converse cap, TTL decay, response-window timing — belong to the
owner specifications and to the orchestrator that drives them, **not**
to this carrier. This module fixes the field name + wire type (§3) and
the consume / produce rules (§2 / §5 / §6); it does not own, schedule,
or apply any orchestrator mechanic.

Scope per OVOS-SESSION-1 §1:

- the JSON shape (§2), including the *omissible-but-never-nullable*
  rule (§2 / §2.1);
- the closed set of fields claimed in this version (§3), each carried
  as a first-class attribute;
- the reserved ``"default"`` ``session_id`` value (§3.1);
- propagation across the OVOS-MSG-1 §5 derivations (§4) — modelled
  here as round-trip equality;
- serialization per OVOS-MSG-1 §6 (§5).

The **consume / produce split** is the load-bearing design rule:

- **Consume** (:meth:`Session.from_dict` / :meth:`Session.deserialize`)
  is **tolerant**. SESSION-1 §6 forbids a consumer from rejecting a
  Message because of the *value* of any single session field — an
  invalid value triggers that field's fallback (the deployment
  default), never Message rejection. ``from_dict`` therefore
  sanitizes each field, dropping bad values back to omission, and
  raises :class:`MalformedSession` **only** for the genuinely
  structural failures §5 mandates (a non-object root, unparsable JSON).
- **Produce** (:meth:`Session.serialize` / the constructor's producer
  guards) **enforces** the producer MUSTs: ``session_id`` non-empty
  when set (§6), omission-not-``null`` and finite numbers (§5, §2).

This carrier never fabricates orchestrator-stamped data. A missing
``activated_at`` (PIPELINE-1 §7.1 / CONVERSE-1 §2.1 — the orchestrator
stamps it at dispatch) is treated as a malformed handler entry and
dropped; the carrier never invents a timestamp. The recency / cap /
prune **helpers** on this class are inert conveniences an
**orchestrator** may call at the boundaries its owner spec defines
(PIPELINE-1 §7.1, CONVERSE-1 §3.1 / §3.2); nothing in this module
auto-invokes them.

Design constraints — this is **pure data + stdlib only**. It does not
import ``ovos-bus-client``, ``ovos-config``, the bus, or any heavy
``ovos-utils`` machinery. Deployment defaults (the pipeline ordering,
the converse-handler cap, the configured language) are **injected** by
the caller, never read from a config singleton here. The lifecycle
surface that bus-client layers on top — ``SessionManager``,
``dig_for_message``, the ``active_skills`` / ``utterance_states``
back-compat projections — lives in bus-client's subclass, not here.

Out of scope (§1 non-goals): session lifecycle, a session store,
authentication / authorization, encryption, and the *semantics* of any
field — owned by the citing specification or by the orchestrator. This
module fixes only the wire contract and the §3.1 / §3.2 / §3.3 fields
whose meaning OVOS-SESSION-1 itself owns.
"""
from __future__ import annotations

import json
import logging
import time
from copy import deepcopy
from typing import Any, Dict, List, Optional, Union

from ovos_spec_tools.message import DEFAULT_SESSION_ID

__all__ = [
    "Session",
    "MalformedSession",
    "DEFAULT_SESSION_ID",
    "DEFAULT_CONVERSE_HANDLERS_CAP",
    "SESSION1_OWNED_FIELDS",
    "SESSION1_REGISTERED_FIELDS",
]


_log = logging.getLogger(__name__)


#: OVOS-CONVERSE-1 §2.1 default cap for the converse-handler recency
#: stack. A deployment MAY raise, lower, or set it to "unbounded"
#: (a value ``<= 0``). The cap is **not** session state: it is a
#: deployment value the orchestrator applies at insertion time, passed
#: as the ``cap`` argument to :meth:`Session.add_converse_handler`. This
#: constant is the spec's documented §2.1 default for that argument.
DEFAULT_CONVERSE_HANDLERS_CAP = 64


#: The field names whose semantics OVOS-SESSION-1 itself owns
#: (§3.1 ``session_id`` + §3.2 language signals + §3.3 ``site_id``).
SESSION1_OWNED_FIELDS = frozenset({
    "session_id", "site_id", "lang",
    "secondary_langs", "output_lang",
    "stt_lang", "request_lang", "detected_lang",
})


#: The six OVOS-TRANSFORM-1 §5 transformer-chain fields, each an ordered
#: array of plugin ids.
_TRANSFORMER_FIELDS = (
    "audio_transformers", "utterance_transformers",
    "metadata_transformers", "intent_transformers",
    "dialog_transformers", "tts_transformers",
)

#: The list-valued denylist / override fields claimed by other specs
#: (OVOS-PIPELINE-1 §5, OVOS-TRANSFORM-1 §5.2). All are arrays of string
#: for which an empty array is wire-equivalent to omission (§3.4).
_LIST_OVERRIDE_FIELDS = (
    "pipeline",
    "blacklisted_skills", "blacklisted_intents", "blacklisted_pipelines",
    "blacklisted_audio_transformers", "blacklisted_utterance_transformers",
    "blacklisted_metadata_transformers", "blacklisted_intent_transformers",
    "blacklisted_dialog_transformers", "blacklisted_tts_transformers",
) + _TRANSFORMER_FIELDS

#: The object-valued override field (OVOS-CONTEXT-1 §2 ``intent_context``).
_OBJECT_OVERRIDE_FIELDS = ("intent_context",)

#: The handler-list / response-mode fields whose recency / cap / prune
#: behaviour this module reproduces (OVOS-PIPELINE-1 §7.1,
#: OVOS-CONVERSE-1 §2.1 / §2.2).
_HANDLER_FIELDS = ("active_handlers", "converse_handlers", "response_mode")


#: The full closed set of fields OVOS-SESSION-1 §3 recognizes in this
#: version. A consumer that recognizes any of these interprets it per
#: its owner specification; everything else is unknown-field passthrough
#: (§2.4) carried opaquely in :attr:`Session.extras`.
SESSION1_REGISTERED_FIELDS = frozenset(SESSION1_OWNED_FIELDS).union(
    _LIST_OVERRIDE_FIELDS, _OBJECT_OVERRIDE_FIELDS, _HANDLER_FIELDS)


class MalformedSession(ValueError):
    """A serialized session payload violates OVOS-SESSION-1 §2 / §5.

    Raised only for structural failures that the spec calls a hard
    error: the carrier is not a JSON object, or the JSON is unparsable.
    Per §2 an explicit ``null`` on a field is **not** a Message-level
    rejection — it is logged and treated as omitted; see
    :meth:`Session.from_dict`.
    """


def _is_bcp47(value: Any) -> bool:
    """Cheap shape check: a BCP-47 tag is a non-empty string with no
    whitespace. The full grammar is owned by language tools; this
    module rejects only obvious type errors."""
    return isinstance(value, str) and bool(value) and not any(
        c.isspace() for c in value)


class Session:
    """OVOS-SESSION-1 **wire carrier** — the canonical reference
    implementation of the §3 field set.

    This class is a pure carrier of the SESSION-1 wire contract. It does
    not own the *semantics* of any field: recency ordering, the converse
    cap, TTL pruning, and response-window timing are owned by the citing
    specs (PIPELINE-1 §7.1, CONVERSE-1 §2 / §3) and applied by an
    orchestrator. The mutation helpers below (``add_active_handler``,
    ``add_converse_handler``, ``prune_converse_handlers`` …) are inert
    conveniences an orchestrator may call at the boundaries those specs
    define; nothing on this class invokes them automatically.

    Consume vs. produce: construction from the wire
    (:meth:`from_dict` / :meth:`deserialize`) is **tolerant** — a bad
    single field value falls back to omission rather than rejecting the
    Message (§6). Producing the wire (:meth:`serialize` and the
    constructor's producer guards) **enforces** the producer MUSTs
    (``session_id`` non-empty when set §6; omission-not-``null`` §2;
    finite numbers §5).

    Every field is **optional** on the wire (§2). The constructor and
    :meth:`to_dict` honour the omissible-but-never-nullable rule: a
    field whose value is ``None`` / empty is **absent** from the
    serialized object, never emitted as ``null`` (§2.1, §3.4). Unknown
    fields supplied via ``extras`` round-trip unchanged (§2.4).

    The Python-level default for ``session_id`` is ``None`` (omitted on
    the wire). :meth:`resolved_session_id` returns the value a consumer
    would fill in — ``"default"`` when omitted (§3.1, §2.1).

    :param session_id: §3.1 — opaque identity string. ``None`` ⇒ omitted
        ⇒ resolves to ``"default"`` at consumption.
    :param lang: §3.2.1 — user's preferred language (BCP-47).
    :param secondary_langs: §3.2.2 — additional BCP-47 tags, ordered.
        Empty list and ``None`` are equivalent on the wire (both omitted).
    :param output_lang: §3.2.3 — preferred response language (BCP-47).
    :param stt_lang: §3.2.4 — language STT actually transcribed in.
    :param request_lang: §3.2.5 — language the emitter reported (hint).
    :param detected_lang: §3.2.6 — language a detector classified.
    :param site_id: §3.3 — opaque group / location identifier.
    :param pipeline: OVOS-PIPELINE-1 §5 — ordered pipeline-plugin ids.
    :param intent_context: OVOS-CONTEXT-1 §2 — the declarative intent
        context object (opaque to this module).
    :param blacklisted_skills: OVOS-PIPELINE-1 §5 — skill ids to ignore.
    :param blacklisted_intents: OVOS-PIPELINE-1 §5 — intent ids to ignore.
    :param blacklisted_pipelines: OVOS-PIPELINE-1 §5 — pipeline ids to skip.
    :param audio_transformers ... tts_transformers: OVOS-TRANSFORM-1 §5 —
        the six ordered transformer chains.
    :param blacklisted_*_transformers: OVOS-TRANSFORM-1 §5.2 — per-chain
        denylists.
    :param active_handlers: OVOS-PIPELINE-1 §7.1 dispatch-recency record —
        a head-first, deduplicated list of ``{skill_id, activated_at}``.
    :param converse_handlers: OVOS-CONVERSE-1 §2.1 converse-eligibility
        list — head-first, deduplicated, tail-dropped at the
        orchestrator-supplied cap. The cap itself is **not** a session
        field (not serialized, not in :data:`SESSION1_REGISTERED_FIELDS`);
        it is a deployment value the orchestrator applies at insertion
        time via the ``cap`` argument to :meth:`add_converse_handler`.
    :param response_mode: OVOS-CONVERSE-1 §2.2 pending-response window —
        a single ``{skill_id, expires_at}`` object, or ``None``.
    :param extras: passthrough mapping for fields claimed by future
        specifications (anything outside :data:`SESSION1_REGISTERED_FIELDS`).
        Treated opaquely per §2.4.
    """

    def __init__(self,
                 session_id: Optional[str] = None,
                 lang: Optional[str] = None,
                 secondary_langs: Optional[List[str]] = None,
                 output_lang: Optional[str] = None,
                 stt_lang: Optional[str] = None,
                 request_lang: Optional[str] = None,
                 detected_lang: Optional[str] = None,
                 site_id: Optional[str] = None,
                 pipeline: Optional[List[str]] = None,
                 intent_context: Optional[Dict[str, Any]] = None,
                 blacklisted_skills: Optional[List[str]] = None,
                 blacklisted_intents: Optional[List[str]] = None,
                 blacklisted_pipelines: Optional[List[str]] = None,
                 audio_transformers: Optional[List[str]] = None,
                 utterance_transformers: Optional[List[str]] = None,
                 metadata_transformers: Optional[List[str]] = None,
                 intent_transformers: Optional[List[str]] = None,
                 dialog_transformers: Optional[List[str]] = None,
                 tts_transformers: Optional[List[str]] = None,
                 blacklisted_audio_transformers: Optional[List[str]] = None,
                 blacklisted_utterance_transformers: Optional[List[str]] = None,
                 blacklisted_metadata_transformers: Optional[List[str]] = None,
                 blacklisted_intent_transformers: Optional[List[str]] = None,
                 blacklisted_dialog_transformers: Optional[List[str]] = None,
                 blacklisted_tts_transformers: Optional[List[str]] = None,
                 active_handlers: Optional[List[Dict[str, Any]]] = None,
                 converse_handlers: Optional[List[Dict[str, Any]]] = None,
                 response_mode: Optional[Dict[str, Any]] = None,
                 extras: Optional[Dict[str, Any]] = None):
        if session_id is not None and (not isinstance(session_id, str)
                                       or not session_id):
            # §6 producer: non-empty string when set.
            raise MalformedSession(
                "session_id must be a non-empty string when set (§6)")
        if site_id is not None and (not isinstance(site_id, str)
                                    or not site_id):
            raise MalformedSession(
                "site_id must be a non-empty string when set (§3.3)")
        for name, value in (("lang", lang), ("output_lang", output_lang),
                            ("stt_lang", stt_lang),
                            ("request_lang", request_lang),
                            ("detected_lang", detected_lang)):
            if value is not None and not _is_bcp47(value):
                raise MalformedSession(
                    f"{name} must be a non-empty BCP-47 string (§3.2)")
        if secondary_langs is not None:
            if not isinstance(secondary_langs, list):
                raise MalformedSession(
                    "secondary_langs must be an array (§3.2.2)")
            seen = set()
            for tag in secondary_langs:
                if not _is_bcp47(tag):
                    raise MalformedSession(
                        "secondary_langs entries must be BCP-47 strings "
                        "(§3.2.2)")
                if tag in seen:
                    raise MalformedSession(
                        "secondary_langs MUST NOT contain duplicates "
                        "(§3.2.2)")
                seen.add(tag)
            # §3.2.2: MUST NOT contain `lang`.
            if lang is not None and lang in seen:
                raise MalformedSession(
                    "secondary_langs MUST NOT contain `lang` (§3.2.2)")
        if extras is not None and not isinstance(extras, dict):
            raise MalformedSession("extras must be a dict")

        # --- §3.1 / §3.2 / §3.3 owned scalars and lists ---------------------
        self.session_id = session_id
        self.lang = lang
        self.secondary_langs = list(secondary_langs) if secondary_langs else None
        self.output_lang = output_lang
        self.stt_lang = stt_lang
        self.request_lang = request_lang
        self.detected_lang = detected_lang
        self.site_id = site_id

        # --- other-spec list/object override fields (carried opaquely) ------
        self.pipeline = list(pipeline) if pipeline else None
        self.intent_context = dict(intent_context) if intent_context else None
        self.blacklisted_skills = self._as_str_list(blacklisted_skills)
        self.blacklisted_intents = self._as_str_list(blacklisted_intents)
        self.blacklisted_pipelines = self._as_str_list(blacklisted_pipelines)
        self.audio_transformers = self._as_str_list(audio_transformers)
        self.utterance_transformers = self._as_str_list(utterance_transformers)
        self.metadata_transformers = self._as_str_list(metadata_transformers)
        self.intent_transformers = self._as_str_list(intent_transformers)
        self.dialog_transformers = self._as_str_list(dialog_transformers)
        self.tts_transformers = self._as_str_list(tts_transformers)
        self.blacklisted_audio_transformers = self._as_str_list(
            blacklisted_audio_transformers)
        self.blacklisted_utterance_transformers = self._as_str_list(
            blacklisted_utterance_transformers)
        self.blacklisted_metadata_transformers = self._as_str_list(
            blacklisted_metadata_transformers)
        self.blacklisted_intent_transformers = self._as_str_list(
            blacklisted_intent_transformers)
        self.blacklisted_dialog_transformers = self._as_str_list(
            blacklisted_dialog_transformers)
        self.blacklisted_tts_transformers = self._as_str_list(
            blacklisted_tts_transformers)

        # --- PIPELINE-1 §7.1 / CONVERSE-1 §2.1 / §2.2 handler state ---------
        # The §2.1 converse-handler cap is NOT session state: a constructed
        # or deserialized session is never capped on load. The cap is a
        # deployment value the orchestrator supplies at insertion time
        # (see :meth:`add_converse_handler`).
        self.active_handlers: List[Dict[str, Any]] = self._coerce_handlers(
            active_handlers)
        self.converse_handlers: List[Dict[str, Any]] = self._coerce_handlers(
            converse_handlers)
        self.response_mode: Optional[Dict[str, Any]] = self._coerce_response_mode(
            response_mode)

        # --- §2.4 unknown-field passthrough --------------------------------
        self.extras: Dict[str, Any] = dict(extras) if extras else {}

    # --- helpers ------------------------------------------------------------

    @staticmethod
    def _as_str_list(value: Optional[List[str]]) -> Optional[List[str]]:
        """Normalize a list-valued override into a copied list, or
        ``None`` when empty / unset. An empty array is wire-equivalent
        to omission (§3.4), so both collapse to ``None``."""
        if not value:
            return None
        if not isinstance(value, list):
            raise MalformedSession("expected an array of string (§3)")
        return list(value)

    # --- §3.1 reserved-default resolution -----------------------------------

    @property
    def is_default(self) -> bool:
        """``True`` when this session resolves to the reserved
        ``"default"`` identity (§3.1): an omitted, empty, or explicit
        ``"default"`` ``session_id`` all map here."""
        return self.session_id in (None, DEFAULT_SESSION_ID)

    def resolved_session_id(self) -> str:
        """The ``session_id`` a consumer would key per-session state on
        — ``"default"`` when omitted (§3.1 + §2.1)."""
        return self.session_id or DEFAULT_SESSION_ID

    # ------------------------------------------------------------------
    # OVOS-PIPELINE-1 §7.1 / OVOS-CONVERSE-1 §2.1 / §2.2 handler helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce_handlers(
            handlers: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Normalize a handler list into the spec ``{skill_id,
        activated_at}`` object shape (PIPELINE-1 §7.1 / CONVERSE-1 §2.1).

        Both PIPELINE-1 §7.1 and CONVERSE-1 §2.1 fix the wire type as an
        array of ``{skill_id, activated_at}`` **objects**. Only the
        object shape is accepted — no spec defines a pair shape, and
        the spec-adoption program forbids back-compat shims.

        ``activated_at`` is **orchestrator-stamped at dispatch**
        (PIPELINE-1 §7.1); a carrier MUST NOT fabricate it. An entry
        that lacks a usable ``skill_id`` or a finite numeric
        ``activated_at`` is malformed and is **dropped** (the whole
        session is not rejected — SESSION-1 §6). Surviving entries are
        deduplicated by ``skill_id`` (head wins) and kept head-first by
        recency."""
        out: List[Dict[str, Any]] = []
        seen = set()
        for entry in handlers or []:
            if not isinstance(entry, dict):
                # only the spec object shape is accepted; drop the rest.
                continue
            skill_id = entry.get("skill_id")
            activated_at = entry.get("activated_at")
            if not skill_id or skill_id in seen:
                continue
            # activated_at is orchestrator-stamped (PIPELINE-1 §7.1); the
            # carrier never mints it. A missing/invalid stamp makes the
            # entry malformed — drop it, never invent time.time().
            if not isinstance(activated_at, (int, float)) \
                    or isinstance(activated_at, bool):
                _log.warning(
                    "OVOS-PIPELINE-1 §7.1: handler entry for `%s` lacks a "
                    "valid orchestrator-stamped activated_at; dropping the "
                    "malformed entry (not fabricating a timestamp)", skill_id)
                continue
            seen.add(skill_id)
            out.append({"skill_id": skill_id, "activated_at": activated_at})
        return out

    @staticmethod
    def _coerce_response_mode(
            response_mode: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Normalize a ``response_mode`` value into the spec
        ``{skill_id, expires_at}`` shape, or ``None`` when there is no
        holder. Malformed values resolve to ``None`` (SESSION-1 §2.1,
        CONVERSE-1 §2.2).

        CONVERSE-1 §2.2 marks **both** ``skill_id`` and ``expires_at``
        Required and defines **no** default for either. A holder missing
        a usable ``skill_id`` or a finite numeric ``expires_at`` is not
        a valid window — it resolves to ``None``. The carrier never
        fabricates an ``expires_at`` (no ``-1`` sentinel)."""
        if not isinstance(response_mode, dict):
            return None
        skill_id = response_mode.get("skill_id")
        if not skill_id:
            return None
        expires_at = response_mode.get("expires_at")
        if not isinstance(expires_at, (int, float)) \
                or isinstance(expires_at, bool):
            return None
        return {"skill_id": skill_id, "expires_at": expires_at}

    @staticmethod
    def _promote_handler(handlers: List[Dict[str, Any]], skill_id: str,
                         activated_at: Optional[float] = None
                         ) -> List[Dict[str, Any]]:
        """Dedup-and-promote ``skill_id`` to the head of ``handlers``
        (in place).

        Removes any existing entry with the same ``skill_id`` then
        inserts a fresh ``{skill_id, activated_at}`` at index 0 — the
        recency-stack rule shared by OVOS-PIPELINE-1 §7.1 and
        OVOS-CONVERSE-1 §3.1."""
        if activated_at is None:
            activated_at = time.time()
        handlers[:] = [h for h in handlers if h.get("skill_id") != skill_id]
        handlers.insert(0, {"skill_id": skill_id, "activated_at": activated_at})
        return handlers

    @staticmethod
    def _cap_handlers(handlers: List[Dict[str, Any]],
                      cap: Optional[int]) -> List[Dict[str, Any]]:
        """Tail-drop ``handlers`` down to ``cap`` entries (in place).

        ``cap`` is the orchestrator-supplied per-insertion limit
        (OVOS-CONVERSE-1 §2.1), not session state. A ``cap`` of ``None``
        or ``<= 0`` means "unbounded". The least-recent surviving owners
        (the tail) are dropped."""
        if cap and cap > 0 and len(handlers) > cap:
            del handlers[cap:]
        return handlers

    @property
    def active(self) -> bool:
        """``True`` when any handler is active in ``active_handlers``
        (OVOS-PIPELINE-1 §7.1)."""
        return len(self.active_handlers) > 0

    # active_handlers (OVOS-PIPELINE-1 §7.1)
    def add_active_handler(self, skill_id: str,
                           activated_at: Optional[float] = None):
        """Push a handler onto ``active_handlers``, dedup-and-promoting
        it to the head (OVOS-PIPELINE-1 §7.1). The list is head-first by
        recency; any prior entry with the same ``skill_id`` is evicted."""
        self._promote_handler(self.active_handlers, skill_id, activated_at)

    def remove_active_handler(self, skill_id: str):
        """Remove ``skill_id`` from ``active_handlers`` (e.g. a STOP-1
        drain)."""
        self.active_handlers[:] = [h for h in self.active_handlers
                                   if h.get("skill_id") != skill_id]

    # converse_handlers (OVOS-CONVERSE-1 §2.1 / §3.1)
    def add_converse_handler(self, skill_id: str,
                             activated_at: Optional[float] = None,
                             cap: Optional[int] = DEFAULT_CONVERSE_HANDLERS_CAP):
        """Stamp a handler onto ``converse_handlers``: dedup-promote to
        head, then tail-drop at ``cap`` (OVOS-CONVERSE-1 §2.1 / §3.1).

        ``cap`` is the orchestrator-supplied per-insertion limit — a
        deployment value applied here, never stored on the session. It
        defaults to the spec's documented §2.1 default
        (:data:`DEFAULT_CONVERSE_HANDLERS_CAP`); ``None`` or ``<= 0``
        means "unbounded"."""
        self._promote_handler(self.converse_handlers, skill_id, activated_at)
        self._cap_handlers(self.converse_handlers, cap)

    def remove_converse_handler(self, skill_id: str):
        """Remove ``skill_id`` from ``converse_handlers``."""
        self.converse_handlers[:] = [h for h in self.converse_handlers
                                     if h.get("skill_id") != skill_id]

    def prune_converse_handlers(self, ttl: float,
                                now: Optional[float] = None):
        """Drop ``converse_handlers`` entries older than ``ttl`` seconds
        (OVOS-CONVERSE-1 §3.2).

        This is an **orchestrator-invoked** operation, not carrier
        behaviour. CONVERSE-1 §3.2 / §9.1 assign TTL pruning to the
        orchestrator, which runs it at two boundaries (pre-converse and
        pre-list-emission); this carrier never invokes it automatically.
        It is exposed only as an inert helper the orchestrator may call.

        ``now - activated_at > ttl`` is dropped. A non-positive ``ttl``
        disables time-based pruning."""
        if not ttl or ttl <= 0:
            return
        now = now if now is not None else time.time()
        self.converse_handlers[:] = [
            h for h in self.converse_handlers
            if now - h.get("activated_at", now) <= ttl
        ]

    # response_mode (OVOS-CONVERSE-1 §2.2) — single-holder
    def set_response_mode(self, skill_id: str, expires_at: float):
        """Set the single-holder response window (OVOS-CONVERSE-1 §2.2).

        Overwrites any existing holder silently (single-holder
        invariant)."""
        self.response_mode = {"skill_id": skill_id, "expires_at": expires_at}

    def clear_response_mode(self, skill_id: Optional[str] = None):
        """Clear the response window.

        When ``skill_id`` is given, clears it only if that skill
        currently holds the window (a skill MUST NOT clear another's
        hold); otherwise clears unconditionally."""
        if self.response_mode is None:
            return
        if skill_id is None or self.response_mode.get("skill_id") == skill_id:
            self.response_mode = None

    # --- §2 / §5 wire shape -------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Render the session as a JSON-friendly dict per §2 + §5.

        Fields whose Python value is ``None`` / empty are **omitted**,
        never emitted as ``null`` (§2.1). An empty list-valued override
        is wire-equivalent to omission and is dropped (§3.4). ``extras``
        are merged in last and round-trip unchanged (§2.4)."""
        out: Dict[str, Any] = {}

        # §3.1 / §3.2 / §3.3 owned scalars
        if self.session_id is not None:
            out["session_id"] = self.session_id
        if self.lang is not None:
            out["lang"] = self.lang
        if self.secondary_langs:
            out["secondary_langs"] = list(self.secondary_langs)
        if self.output_lang is not None:
            out["output_lang"] = self.output_lang
        if self.stt_lang is not None:
            out["stt_lang"] = self.stt_lang
        if self.request_lang is not None:
            out["request_lang"] = self.request_lang
        if self.detected_lang is not None:
            out["detected_lang"] = self.detected_lang
        if self.site_id is not None:
            out["site_id"] = self.site_id

        # other-spec list/object override fields (omit-when-empty, §3.4)
        for name in _LIST_OVERRIDE_FIELDS:
            value = getattr(self, name)
            if value:
                out[name] = list(value)
        for name in _OBJECT_OVERRIDE_FIELDS:
            value = getattr(self, name)
            if value:
                out[name] = deepcopy(value)

        # PIPELINE-1 §7.1 / CONVERSE-1 §2.1 / §2.2 — omit-when-empty
        if self.active_handlers:
            out["active_handlers"] = deepcopy(self.active_handlers)
        if self.converse_handlers:
            out["converse_handlers"] = deepcopy(self.converse_handlers)
        if self.response_mode:
            out["response_mode"] = dict(self.response_mode)

        # §2.4 unknown-field tolerance — passthrough.
        for k, v in self.extras.items():
            if k in out:
                # An owned field set both ways is a programming error;
                # owned wins (single source of truth).
                continue
            out[k] = deepcopy(v)
        return out

    def serialize(self) -> str:
        """Emit a JSON string per §5 (no NaN, UTF-8, single object)."""
        return json.dumps(self.to_dict(), ensure_ascii=False,
                          allow_nan=False)

    # --- construction from the wire -----------------------------------------

    @staticmethod
    def _sanitize_inbound(kwargs: Dict[str, Any]) -> None:
        """Apply the SESSION-1 §6 consumer rule to inbound field values
        (in place): a consumer **MUST NOT** reject a Message because of
        the value of any single session field — an invalid value falls
        back to the field's deployment default (omission), never a
        Message rejection.

        This sanitizes the consume path so the constructor's producer
        guards never fire on inbound wire data. Each bad value is logged
        and dropped from ``kwargs`` (→ omitted ⇒ deployment default):

        - non-BCP-47 ``lang`` / ``output_lang`` / ``stt_lang`` /
          ``request_lang`` / ``detected_lang`` (§3.2);
        - empty / non-string ``site_id`` (§3.3 imposes no non-empty
          rule, unlike §6's ``session_id``-only MUST);
        - ``secondary_langs`` that is not a list, or whose entries are
          bad / duplicated / include ``lang`` — §3.2.2 is a **producer**
          emission rule, not a consumer rejection trigger;
        - non-list list-valued overrides (``pipeline`` etc.) and non-dict
          object overrides (``intent_context``).

        ``session_id`` is *not* sanitized away here: an empty/non-string
        ``session_id`` on the wire is dropped to omission (resolving to
        ``"default"`` §3.1 / §2.1) rather than rejected, but a valid
        non-empty string passes through to the producer guard unchanged.
        """
        def _drop(field: str, reason: str) -> None:
            _log.warning(
                "OVOS-SESSION-1 §6: invalid `%s` (%s); falling back to the "
                "deployment default (treating field as omitted)",
                field, reason)
            kwargs.pop(field, None)

        # §6 / §3.1 — session_id: non-empty string or omit-and-default.
        if "session_id" in kwargs:
            sid = kwargs["session_id"]
            if not isinstance(sid, str) or not sid:
                _drop("session_id", "not a non-empty string")

        # §3.2 — BCP-47 language scalars.
        for field in ("lang", "output_lang", "stt_lang",
                      "request_lang", "detected_lang"):
            if field in kwargs and not _is_bcp47(kwargs[field]):
                _drop(field, "not a BCP-47 string")

        # §3.3 — site_id is opaque; the spec imposes no non-empty MUST,
        # but an empty / non-string value carries no meaning → omit.
        if "site_id" in kwargs:
            site = kwargs["site_id"]
            if not isinstance(site, str) or not site:
                _drop("site_id", "not a non-empty string")

        # §3.2.2 — secondary_langs producer rules (no dup, no `lang`,
        # BCP-47 entries) MUST NOT reject on consume. Drop bad entries /
        # the whole field rather than raise.
        if "secondary_langs" in kwargs:
            raw = kwargs["secondary_langs"]
            if not isinstance(raw, list):
                _drop("secondary_langs", "not an array")
            else:
                primary = kwargs.get("lang")
                cleaned: List[str] = []
                seen = set()
                for tag in raw:
                    if not _is_bcp47(tag) or tag in seen or tag == primary:
                        # bad / duplicate / equals primary → drop the entry
                        continue
                    seen.add(tag)
                    cleaned.append(tag)
                if cleaned != raw:
                    _log.warning(
                        "OVOS-SESSION-1 §6 / §3.2.2: sanitized inbound "
                        "`secondary_langs` (dropped invalid / duplicate / "
                        "primary-language entries) instead of rejecting")
                kwargs["secondary_langs"] = cleaned or None

        # §3 list/object overrides — wrong wire type falls back, no raise.
        for field in _LIST_OVERRIDE_FIELDS:
            if field in kwargs and not isinstance(kwargs[field], list):
                _drop(field, "not an array")
        for field in _OBJECT_OVERRIDE_FIELDS:
            if field in kwargs and not isinstance(kwargs[field], dict):
                _drop(field, "not an object")

    @classmethod
    def from_dict(cls, payload: Optional[Dict[str, Any]]) -> "Session":
        """Construct a Session from a JSON-decoded dict per §2 — the
        **tolerant consume path**.

        SESSION-1 §6: a consumer MUST NOT reject a Message because of the
        presence / absence / value of any single session field. An
        explicit ``null`` (§2.1) or any otherwise-invalid single field
        value is logged and falls back to omission (→ the deployment
        default), **never** a Message rejection. Only the structural
        failures §5 mandates raise :class:`MalformedSession`: a non-object
        root here, and unparsable JSON in :meth:`deserialize`.

        Unknown fields are preserved verbatim in :attr:`extras` (§2.4).
        Passing ``None`` (no ``session`` key in ``context``) yields the
        same well-formed empty session as ``{}`` (§2.1)."""
        if payload is None:
            return cls()
        if not isinstance(payload, dict):
            # §5 — a non-object root is the one structural failure that is
            # a hard error; everything below it falls back per §6.
            raise MalformedSession(
                "session must be a JSON object (§2 / §5)")

        kwargs: Dict[str, Any] = {}
        extras: Dict[str, Any] = {}
        for key, value in payload.items():
            if key not in SESSION1_REGISTERED_FIELDS:
                extras[key] = value
                continue
            if value is None:
                # §2.1: explicit null is malformed — log, treat as omitted.
                _log.warning(
                    "OVOS-SESSION-1 §2.1: explicit null on `%s` is "
                    "malformed; treating as omitted", key)
                continue
            kwargs[key] = value
        # §6 — fall back per-field on bad values before construction so the
        # constructor's producer guards never reject inbound wire data.
        cls._sanitize_inbound(kwargs)
        if extras:
            kwargs["extras"] = extras
        return cls(**kwargs)

    @classmethod
    def deserialize(cls,
                    payload: Union[str, bytes, bytearray,
                                   Dict[str, Any], None]) -> "Session":
        """Parse a serialized session per §5 and §2.

        Accepts bytes/str JSON, an already-parsed dict, or ``None``.
        Raises :class:`MalformedSession` only for the structural
        failures §5 calls hard errors (unparsable JSON, non-object
        root). Field-level malformedness (an explicit ``null``) is
        absorbed by :meth:`from_dict`."""
        if payload is None:
            return cls()
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode("utf-8")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise MalformedSession(
                    f"session payload is not valid JSON: {exc}") from exc
        return cls.from_dict(payload)

    # --- §4 propagation -----------------------------------------------------

    def propagate(self) -> "Session":
        """Return a deep copy suitable for attaching to a derived
        Message (§4). Every field — known and unknown — rides along
        unchanged."""
        return Session.from_dict(self.to_dict())

    @classmethod
    def materialize_default(cls) -> "Session":
        """Materialize the default session per §4.1.

        Sets ``session_id`` to ``"default"`` and leaves every other
        field omitted; the §4.1 rule forbids populating per-component
        overrides on a materialized default."""
        return cls(session_id=DEFAULT_SESSION_ID)

    # --- value semantics ----------------------------------------------------

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, Session)
                and self.to_dict() == other.to_dict())

    def __repr__(self) -> str:
        return f"Session({self.to_dict()!r})"
