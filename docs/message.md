# Bus Messages

The `Message` class is the on-the-wire envelope that OVOS components
exchange: utterances coming in, intent matches going out, skills
announcing handler outcomes, hosts dispatching to skills. The shape is
defined by [OVOS-MSG-1][spec] and this module is the reference
implementation.

[spec]: https://github.com/OpenVoiceOS/architecture/blob/dev/message-object.md

## What is in a Message

Every Message is a JSON object with exactly three top-level fields:

| Field | Type | Meaning |
|---|---|---|
| `type` | string | The topic: `ovos.intent.matched`, `speak`, `<skill_id>:<intent_name>`, … |
| `data` | object | Topic-specific payload; shape fixed by whichever spec defines `type` |
| `context` | object | Routing keys, the session carrier, and any layer-2 metadata |

```python
from ovos_spec_tools import Message

m = Message("speak", {"utterance": "hello"}, {"source": "skill.id"})
```

The constructor rejects malformed input: an empty `type`, a non-string
`type`, or a non-`dict` `data` / `context` raise
`MalformedMessage`. Pass the dicts by reference. They are stored
as-is; if you need a detached copy use the derivations below.

## Routing keys

Two `context` keys mark the OVOS/handler-code boundary:

- `source`: opaque identifier of the producer.
- `destination`: opaque identifier (or list of identifiers) of the
  intended consumer(s). Absent or empty means **broadcast**.

The envelope treats both as opaque strings, with no parsing and no validation
beyond "is it there". How identifiers are minted is a deployment
concern. Hivemind, for example, uses `source` / `destination` to thread
remote peers through the bus without OVOS itself learning about them.

## The session carrier

`context.session` is the carrier for one conversational session: the
unit of "this wake-word interaction" or "this HiveMind client
connection". OVOS-MSG-1 makes two of its keys normative:

- `session.session_id`: string identifier. The value `"default"` is
  **reserved** and means *originates from the device itself* (used by
  `ovos-audio` to keep TTS local).
- `session.lang`: BCP-47 tag for the user's preferred output language
  (distinct from `data.lang` which describes the payload).

The rest of `session`'s shape is opaque to this Message. Full Session
structure is the job of the consumer (typically `ovos-bus-client`'s
`Session` class or a future session spec).

**Absent session = `session_id: "default"`.** A Message with no
`session` in its context is treated the same as one carrying the
reserved value. Producers don't have to emit a session for
device-local messages.

## The three derivations

Each derivation returns a new Message with the right routing/session
fields for its role. The runtime class is preserved: subclasses of
`Message` get back instances of their own subclass.

### `forward(type, data)`: relay under a new topic

Keeps `context` (including `source`, `destination`, and `session`)
exactly as it was. The forwarder does **not** become the new `source`;
the original producer remains named.

```python
ack = m.forward("ovos.utterance.handled", {"id": "u-7"})
# ack.context == m.context  (deep-copied)
```

### `reply(type, data, context=None)`: send back to the asker

Copies `context`, then swaps the routing keys so the new Message is
addressed back to the original producer:

- the new `destination` is the old `source`;
- the new `source` is the old `destination` (the first entry if it was
  an array; exact choice is implementation-defined).

Other `context` keys, including `session`, pass through unchanged. The
optional `context` argument is overlaid before the swap, matching
`ovos-bus-client.Message.reply` behaviour:

```python
ack = m.reply("speak", {"utterance": "got it"})
# ack.context["source"] == m.context["destination"]
# ack.context["destination"] == m.context["source"]
```

### `response(data, context=None)`: sugar for `.response`-suffixed reply

A response is a `reply` whose topic is the source topic with
`.response` appended. Used by request/response chains so an observer
can recognize the answer:

```python
res = Message("ovos.intent.list").response({"intents": ["..."]})
res.msg_type   # 'ovos.intent.list.response'
```

## Serialization

`serialize()` produces a single UTF-8 JSON object per [OVOS-MSG-1
§6][spec]:

```python
wire = m.serialize()
recovered = Message.deserialize(wire)
assert recovered == m
```

Nested objects in `data` / `context` that expose a `.serialize()`
method (the duck-typed protocol used by `ovos-bus-client.Session` and
similar carriers) are converted before JSON encoding. `Message`
itself doesn't know about Session or any specific carrier type, but
its `.serialize()` walks containers and calls the method when present.

For a JSON-decoded view without the string intermediate, `m.as_dict`
returns the same envelope as a dictionary:

```python
m.as_dict   # {'type': 'ovos.test', 'data': {...}, 'context': {...}}
```

`deserialize` rejects malformed payloads as `MalformedMessage`:
unparsable JSON, non-object root, unknown top-level keys, missing
`type`, wrong value types. Both `str` and `bytes` are accepted, and an
already-parsed `dict` short-circuits the JSON step.

## A note on correlation

There is **no** per-message identifier, no in-reply-to chain, no
host-managed request/response bookkeeping. Messages on the bus are
fully asynchronous. The `.response` suffix and the preserved `session`
give you enough raw material to do your own correlation if you need
it: match an incoming `<topic>.response` against an outstanding
request in the same `session_id`.

Components that need per-conversation state track it themselves keyed
on `session.session_id`. A Message on the bus is **self-contained**;
any state a later consumer needs is either inside the Message or kept
by some component out of band. It is never recovered by a hidden host-side
correlation index.

## What this module does not do

By design, no transport (websocket, queue, …), no encryption, no
authentication, no delivery guarantees, no ordering guarantees, no
session lifecycle, no identifier-assignment policy. Each of those is
out of scope for the envelope and belongs in the layer that consumes
it: `ovos-bus-client` for the websocket transport, layer-2 systems
(HiveMind) for multi-tenant routing, and individual subsystems for their
own per-session state.

## Subclassing

`Message` is designed to be subclassed. Both `deserialize` (a
classmethod) and `forward` / `reply` / `response` return instances of
the runtime class, so a transport-layer subclass propagates through
derivation chains without losing identity:

```python
class TransportMessage(Message):
    def serialize(self):
        body = super().serialize()
        # add framing, encryption, … here
        return body

m = TransportMessage("ovos.test")
forwarded = m.forward("ovos.next")
assert isinstance(forwarded, TransportMessage)
```

This is exactly how `ovos-bus-client.Message` is expected to extend
the spec primitive once it adopts this class.

## Spec section map

Every part of the `Message` API traces to a specific OVOS-MSG-1
clause. The module's docstrings cite these inline; this table is the
quick index.

| API surface | OVOS-MSG-1 § | What it implements |
|---|---|---|
| `Message(type, data, context)` | §2, §2.1-§2.3 | the three-field envelope; constructor type checks |
| `MalformedMessage` (constructor) | §2.1-§2.3 | reject non-string `type`, non-dict `data`/`context` |
| `msg_type` / `data` / `context` | §2 | the wire fields `type` / `data` / `context` |
| `context["source"]` / `["destination"]` | §3, §3.2-§3.4 | opaque routing keys, carried not parsed |
| `context["session"]` | §4 | session carrier (inner shape owned by OVOS-SESSION-1) |
| `DEFAULT_SESSION_ID` | §4.1 | the reserved `"default"` session id |
| `forward(type, data)` | §5.1 | relay, context preserved unchanged (deep-copied) |
| `reply(type, data, context)` | §5.2 | swap routing keys, address back to the asker |
| `response(data, context)` | §5.3 | `.response`-suffixed reply |
| (no correlation API) | §5.4 | messages are fully async; no host-side correlation |
| `serialize()` | §6 | single UTF-8 JSON object, finite numbers only |
| `as_dict` | §2, §6 | JSON-decoded envelope view |
| `deserialize(payload)` | §6, §7 | parse + reject malformed payloads |
| `MalformedMessage` (deserialize) | §7 | the consumer "MUST reject" rules |

## See also

- [Bus namespaces](bus-namespaces.md), `SpecMessage`, `MIGRATION_MAP`,
  and the transparent legacy↔`ovos.*` bridge that rides on top of these
  derivations (`forward` for the handler-lifecycle trio, `reply` for the
  stop pong, and so on).
- [Spec traceability](spec-traceability.md), every public symbol in
  `ovos-spec-tools` mapped to its authoritative spec section.

---
[← Language matching](language-matching.md) · [Home](README.md) · [Bus namespaces →](bus-namespaces.md)
