"""Reference implementation of OVOS-MSG-1 — the bus :class:`Message` envelope.

This module owns only what the spec owns: the JSON envelope of §2, the
routing keys of §3 (which it touches but does not interpret), the
session carrier of §4 (which it treats as an opaque dict), and the
three derivations of §5 — :meth:`Message.forward`, :meth:`Message.reply`,
and :meth:`Message.response`.

It explicitly does **not** own (§7 non-goals): transport, encryption,
authentication, delivery guarantees, session lifecycle, identifier
assignment, multi-tenant routing. Those concerns live in the layers
that consume this primitive — ``ovos-bus-client`` for the websocket
transport, HiveMind for multi-tenant routing, ``ovos-audio`` /
``ovos-core`` for the per-topic policy decisions keyed on ``session_id``
and ``lang``.

The implementation has **no dependencies** outside the standard library;
it is the foundation other bus-layer code builds on.
"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict, Optional, Union

__all__ = ["Message", "MalformedMessage", "DEFAULT_SESSION_ID"]


#: The reserved ``session_id`` meaning "the Message originates from the
#: device itself" (OVOS-MSG-1 §4.1). Used by ``ovos-audio`` to decide
#: that synthesized TTS plays out of the device's own speakers, and as
#: the implicit value for any Message that arrives without a ``session``
#: in its context (§4.3).
DEFAULT_SESSION_ID = "default"


class MalformedMessage(ValueError):
    """A serialized payload that does not conform to OVOS-MSG-1 §2 / §6.

    Raised by :meth:`Message.deserialize` when the payload fails any
    structural rule the spec calls out as ``MUST``: unknown top-level
    keys (§2), missing ``type`` (§2), wrong value types, or unparsable
    JSON (§6).
    """


class Message:
    """OVOS-MSG-1 envelope.

    Three top-level fields per §2:

    - :attr:`msg_type` (the wire field ``type``) — non-empty topic string
      matching the §2.1 syntax (ASCII letters/digits/``.``/``:``/``_``/``-``,
      no whitespace);
    - :attr:`data` — JSON-object payload; shape fixed by whichever
      specification defines :attr:`msg_type`;
    - :attr:`context` — JSON-object metadata, carrying the §3 routing
      keys (``source`` / ``destination``), the §4 session carrier, and
      any layer-2 metadata higher systems attach.

    The :attr:`data` and :attr:`context` dicts are stored by reference;
    callers that mutate them after constructing a Message see those
    mutations reflected in the Message. :meth:`forward` / :meth:`reply`
    / :meth:`response` deep-copy the context before deriving so the
    derived Message is independent of the source.
    """

    def __init__(self, msg_type: str,
                 data: Optional[Dict[str, Any]] = None,
                 context: Optional[Dict[str, Any]] = None):
        if not isinstance(msg_type, str) or not msg_type:
            raise MalformedMessage(
                "msg_type must be a non-empty string (§2.1)")
        if data is not None and not isinstance(data, dict):
            raise MalformedMessage("data must be a dict (§2.2)")
        if context is not None and not isinstance(context, dict):
            raise MalformedMessage("context must be a dict (§2.3)")
        self.msg_type = msg_type
        self.data = data if data is not None else {}
        self.context = context if context is not None else {}

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, Message)
                and other.msg_type == self.msg_type
                and other.data == self.data
                and other.context == self.context)

    def __repr__(self) -> str:
        return (f"{self.__class__.__name__}("
                f"msg_type={self.msg_type!r}, "
                f"data={self.data!r}, context={self.context!r})")

    # --- §6 serialization ---------------------------------------------------

    def serialize(self) -> str:
        """Render the Message as a single UTF-8 JSON object per §6.

        Object key order is not significant; ``NaN`` / ``Infinity`` are
        forbidden (``allow_nan=False``). Subclasses may override to add
        transport-layer concerns — encryption, framing, GUI-specific
        serialization — which the spec explicitly leaves out (§7).
        """
        return json.dumps(
            {"type": self.msg_type,
             "data": self.data,
             "context": self.context},
            ensure_ascii=False, allow_nan=False)

    @classmethod
    def deserialize(cls,
                    payload: Union[str, bytes, bytearray, Dict[str, Any]]
                    ) -> "Message":
        """Construct a Message from a serialized JSON object per §6.

        ``payload`` may be a UTF-8 byte string, a ``str`` (parsed as JSON),
        or an already-parsed ``dict``. Returns an instance of ``cls`` so
        subclasses (e.g. ``ovos-bus-client``'s transport-layer Message)
        deserialize to their own type.

        Raises :class:`MalformedMessage` per the §7 ``MUST reject``
        conformance rules: unparsable JSON, non-object root, unknown
        top-level keys, missing ``type``, or wrong value types.
        """
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode("utf-8")
        if isinstance(payload, str):
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise MalformedMessage(
                    f"payload is not valid JSON: {exc}") from exc
        else:
            obj = payload
        if not isinstance(obj, dict):
            raise MalformedMessage(
                "Message payload must be a JSON object (§2)")
        # §2: "Other top-level keys MUST NOT appear; consumers MUST
        # reject any Message with unknown top-level keys."
        unknown = set(obj.keys()) - {"type", "data", "context"}
        if unknown:
            raise MalformedMessage(
                f"unknown top-level keys {sorted(unknown)!r} — §2 "
                "forbids any key other than 'type', 'data', 'context'")
        if "type" not in obj:
            raise MalformedMessage("missing required key 'type' (§2)")
        # data and context default to {} per §2.2/§2.3 ("MAY be empty").
        return cls(obj["type"], obj.get("data") or {},
                   obj.get("context") or {})

    # --- §5 derivations -----------------------------------------------------

    def forward(self, msg_type: str,
                data: Optional[Dict[str, Any]] = None) -> "Message":
        """OVOS-MSG-1 §5.1 — relay under a new topic, preserve context.

        The forwarder does **not** become the new ``source``; the original
        producer remains named. Returns an instance of this Message's
        runtime class so subclasses propagate naturally.
        """
        return self.__class__(
            msg_type, data or {}, deepcopy(self.context))

    def reply(self, msg_type: str,
              data: Optional[Dict[str, Any]] = None,
              context: Optional[Dict[str, Any]] = None) -> "Message":
        """OVOS-MSG-1 §5.2 — send back to the asker.

        Copies :attr:`context` and swaps the §3 routing keys so the new
        Message is addressed back to the source Message's producer:

        - the new ``destination`` is the old ``source`` (if set);
        - the new ``source`` is the old ``destination`` — if the old
          ``destination`` was an array, the first entry is chosen
          (§5.2 leaves the exact choice implementation-defined);
        - every other context key, including ``session`` (§4), is
          preserved unchanged.

        Any keys provided via ``context`` are merged in on top of the
        copied context **before** the source/destination swap, matching
        the historical ``ovos_bus_client.Message.reply`` behaviour:
        passing ``context={"source": "C", "destination": "D"}`` ends up
        producing ``source=D, destination=C`` because the swap is the
        final step. Non-routing keys overlaid this way (a custom
        ``session`` shape, a tracing identifier, …) pass through
        untouched.
        """
        new_context = deepcopy(self.context)
        if context:
            new_context.update(context)
        # §5.2 swap. Read both sides BEFORE writing to avoid clobbering.
        src = new_context.get("source")
        dst = new_context.get("destination")
        if dst is not None:
            # array-of-strings form: producer chooses one; consumers
            # MUST NOT rely on a particular member being chosen (§5.2)
            new_context["source"] = (
                dst[0] if isinstance(dst, list) and dst else dst)
        if src is not None:
            new_context["destination"] = src
        return self.__class__(msg_type, data or {}, new_context)

    def response(self, data: Optional[Dict[str, Any]] = None,
                 context: Optional[Dict[str, Any]] = None) -> "Message":
        """OVOS-MSG-1 §5.3 — sugar for ``reply(self.msg_type + '.response', ...)``.

        Topics defined elsewhere MAY rely on the ``.response`` suffix
        convention to mark a Message as the answer to a prior one.
        """
        return self.reply(self.msg_type + ".response", data, context)
