# Bus namespaces — the legacy ↔ `ovos.*` migration

OVOS bus topics span two namespaces: the Mycroft-era names
(`speak`, `recognizer_loop:utterance`, `mycroft.skill.handler.start`, …)
and the `ovos.*` namespace the specifications define
(`ovos.utterance.speak`, `ovos.utterance.handle`,
`ovos.intent.handler.start`, …). `ovos-spec-tools` owns the **vocabulary**
of the mapping between them and the **transparent bridge** that lets a
deployment cross from one to the other without a flag day. Two things implement it, both in `ovos_spec_tools/messages.py`:

- `SpecMessage` — the enum of spec-defined `ovos.*` topics;
- `MIGRATION_MAP` + `NamespaceTranslator` — the rename map and the
  dual-emit/dedup bridge the bus runs on top of it.

Everything here references the spec that *owns* each topic, so a reader can
always answer "which document made this a topic?" — see the
[spec traceability map](spec-traceability.md) for the full index.

## `SpecMessage` — the spec topic vocabulary

`SpecMessage` is a `str` enum (OVOS-MSG-1 §2.1 topics are strings, so a
member *is* a usable topic):

```python
from ovos_spec_tools import SpecMessage, Message

bus.on(SpecMessage.SPEAK, handler)                 # 'ovos.utterance.speak'
bus.emit(Message(SpecMessage.UTTERANCE, {...}))    # 'ovos.utterance.handle'
str(SpecMessage.STOP)            # 'ovos.stop'  (StrEnum-like)
```

Referencing `SpecMessage.SPEAK` instead of the bare string makes code
self-documenting: a `SpecMessage` member is *provably* spec-defined; a bare
string is visibly legacy or implementation-specific. Each member's owning
spec section is cited in the source and in the table below.

| Group | Owning spec | Topics |
|---|---|---|
| Utterance lifecycle | OVOS-PIPELINE-1 §9 | `UTTERANCE` (§9.1), `SPEAK` (§9.6), `UTTERANCE_HANDLED` (§9.5), `UTTERANCE_CANCELLED` (§6.4), `INTENT_MATCHED` (§9.2), `INTENT_UNMATCHED` (§9.3) |
| Handler-lifecycle trio | OVOS-PIPELINE-1 §8 | `INTENT_HANDLER_START`, `INTENT_HANDLER_COMPLETE`, `INTENT_HANDLER_ERROR` |
| Registration / management | OVOS-INTENT-4 §§5–8 | `INTENT_REGISTER_KEYWORD` (§5), `INTENT_REGISTER_TEMPLATE` (§6), `ENTITY_REGISTER` (§7), `INTENT_DEREGISTER` (§8.2), `ENTITY_DEREGISTER` (§8.3), `SKILL_DEREGISTER` (§8.4), `INTENT_ENABLE`/`INTENT_DISABLE` (§8.5) |
| Introspection | OVOS-INTENT-4 §10 | `INTENT_LIST`, `INTENT_LIST_RESPONSE`, `INTENT_DESCRIBE`, `INTENT_DESCRIBE_RESPONSE` |
| Stop cascade | OVOS-STOP-1 §4–§5 | `STOP_PING` (§4.2), `STOP_PONG` (§4.2), `STOP` (§5.3) |
| Listener / mic / output | OVOS-AUDIO-IN-1 (provisional) | `MIC_LISTEN`, `LISTENER_RECORD_STARTED`, `LISTENER_RECORD_ENDED`, `LISTENER_SLEEP`, `LISTENER_AWOKEN`, `AUDIO_OUTPUT_STARTED`, `AUDIO_OUTPUT_ENDED` |

The AUDIO-IN-1 group is **provisional**: the topic *names* are settled
(listening signals belong on `ovos.listener.*`), but the spec prose that
formally defines them is not yet finalized.

## `MIGRATION_MAP` — the rename map

`MIGRATION_MAP` maps each **legacy** topic to the `SpecMessage` that
supersedes it. `SPEC_TO_LEGACY` is its reverse, and `migration_counterpart`
resolves either direction:

```python
from ovos_spec_tools import migration_counterpart

migration_counterpart("speak")                 # 'ovos.utterance.speak'
migration_counterpart("ovos.utterance.speak")  # 'speak'
migration_counterpart("some.app.topic")        # None  (does not migrate)
```

Each entry encodes one spec rename. A sample:

| Legacy topic | `SpecMessage` | Spec § |
|---|---|---|
| `recognizer_loop:utterance` | `UTTERANCE` | PIPELINE-1 §9.1 |
| `speak` | `SPEAK` | PIPELINE-1 §9.6 |
| `complete_intent_failure` | `INTENT_UNMATCHED` | PIPELINE-1 §9.3 |
| `mycroft.skill.handler.start` | `INTENT_HANDLER_START` | PIPELINE-1 §8.1 |
| `skill.stop.pong` | `STOP_PONG` | STOP-1 §4.2 |
| `mycroft.stop` | `STOP` | STOP-1 §5.3 |
| `detach_intent` | `INTENT_DEREGISTER` | INTENT-4 §8.2 |
| `mycroft.skill.enable_intent` | `INTENT_ENABLE` | INTENT-4 §8.5 |

### Two deliberate exclusions

The bridge mirrors the **payload verbatim** (see below), so only renames that
need no payload transformation can live in the map. Two spec renames are
intentionally *not* mapped:

1. **INTENT-4 §5–§7 registration.** The rename is not 1:1. Legacy Adapt emits
   *N* `register_vocab` messages plus one `register_intent` (the intent
   references its vocab by name); INTENT-4 §5.2 consolidates all of that into
   **one** `ovos.intent.register.keyword` Message with the vocab descriptors
   **inlined** (§5.1). A transparent bus bridge cannot synthesize that N→1
   join — it would have to buffer and merge messages it has no schema for — so
   registration is adopted in the **producer** (`ovos_workshop/intents.py`)
   and **consumers** (the pipeline plugins), not bridged here.

2. **STOP-1 per-skill ping placeholders.** The legacy stoppability handshake
   used per-skill topics shaped `{skill_id}.stop.ping` / `{skill_id}.stop`
   (OVOS-MSG-1 §2.1.1 *runtime-assembled* topics). STOP-1 §4.2/§5.3 replace
   them with the single broadcast `ovos.stop.ping` / `ovos.stop`. A
   `{skill_id}.*` placeholder is not a static string, so it cannot be a dict
   key; that migration is handled by producers/consumers subscribing on both
   forms.

> A subtlety: some mapped entries are commented "payload restructured to
> `{skill_id, intent_name}`" (the handler trio, the INTENT-4 management
> topics). The bridge *itself* still transforms nothing — once the **producer**
> adopts the modern payload shape, the mirror carries that already-modern
> payload on the legacy topic too. The restructure is producer-side adoption;
> the map owns only the topic rename. The two are composed, never conflated.

## The transparent bridge — `NamespaceTranslator`

`NamespaceTranslator` is the reference implementation of the **dual-emit
bus bridge**. `ovos-bus-client`'s `MessageBusClient` and `ovos_utils`'
`FakeBus` both delegate to it, so the real websocket bus and the
test/satellite double behave identically. It is pure logic — no I/O, no
config — so `ovos-spec-tools` stays dependency-free; the caller reads
env/config and passes the two direction flags in.

```python
from ovos_spec_tools import NamespaceTranslator
xlat = NamespaceTranslator(modernize=True, emit_legacy=True, window=1.0)
```

| Flag | Effect |
|---|---|
| `modernize` | emitting a **legacy** topic also emits its `ovos.*` counterpart — carries the migration forward |
| `emit_legacy` | emitting an `ovos.*` topic also emits the legacy counterpart — keeps un-migrated consumers working |
| `window` | the **mirror window** (seconds) for receive-side dedup (below) |

### Send side — `counterpart_topics`

When a producer emits one topic, the bus asks the translator which extra
topic to mirror onto, then re-emits the **same payload** there:

```python
xlat.counterpart_topics("speak")                 # ['ovos.utterance.speak']
xlat.counterpart_topics("ovos.utterance.speak")  # ['speak']
xlat.counterpart_topics("some.app.topic")        # []  (never mirrored)
```

At most one counterpart per topic. The flags gate each direction
independently (a `modernize`-only bus mirrors legacy→spec but not the
reverse).

### Receive side — `new_mirror_guard` and the mirror window

A handler subscribed to **both** namespaces would otherwise fire twice on a
dual-emit. `new_mirror_guard()` returns a stateful predicate
`is_mirror(message) -> bool` — **one per handler**, each with private
`seen` state — that the bus uses to run the handler exactly once:

```python
guard = xlat.new_mirror_guard()
guard(Message("speak", {"utterance": "hi"}))                 # False — first arrival, run it
guard(Message("ovos.utterance.speak", {"utterance": "hi"}))  # True  — mirror, drop it
```

Mirror-window semantics, precisely:

- A Message is a **mirror** iff a recently-seen Message had the same
  payload+context fingerprint, a **different** `msg_type`, **and** that
  earlier type's `migration_counterpart` equals this one — i.e. the same
  event re-delivered on the counterpart topic. The payload fingerprint is
  order-independent (OVOS-MSG-1 §6: key order is not significant).
- Two genuine events on the **same** topic are never suppressed — identical
  repeats on one topic are real repeats, not a mirror.
- Entries older than `window` are evicted before each check, so a
  counterpart that arrives *after* the window counts as a new event. The
  bridge only ever collapses a near-simultaneous dual-emit **pair**, never
  two deliberate emissions spaced apart.
- The guard is defensive: anything not Message-shaped (no `msg_type` /
  `data` / `context`, or an unfingerprintable payload) returns `False` —
  it never drops what it cannot prove is a mirror.

## Worked example — a skill says "hello" during the migration

A skill emits the modern spec topic only:

```python
bus.emit(Message(SpecMessage.SPEAK, {"utterance": "hello"}))   # 'ovos.utterance.speak'
```

On a bus configured `emit_legacy=True`:

1. **Send.** The bus emits `ovos.utterance.speak`, then calls
   `counterpart_topics("ovos.utterance.speak")` → `['speak']` and re-emits
   the **same** `{"utterance": "hello"}` payload on the legacy `speak`
   topic. Old TTS components still listening on `speak` receive it.
2. **Receive.** A modernized audio component subscribed to *both*
   `ovos.utterance.speak` and `speak` runs its `is_mirror` guard:
   - `ovos.utterance.speak` arrives first → `False` → handler runs once;
   - `speak` arrives within the window, same payload, counterpart topic →
     `True` → dropped.

The skill wrote one modern emission; legacy and modern consumers both got
exactly one delivery. When the migration completes and `emit_legacy` is
turned off, the legacy mirror simply stops — no skill code changes.

## What this is *not*

The bridge is a **topic rename**, not a payload translator and not a
correlation mechanism. It never invents fields, never joins messages (hence
exclusion 1), and never touches `context` routing or `session` — those follow
the OVOS-MSG-1 §5 derivation rules implemented by [`Message`](message.md).

## See also

- [Bus messages](message.md) — the OVOS-MSG-1 envelope and the `forward` /
  `reply` / `response` derivations these topics ride on.
- [Spec traceability](spec-traceability.md) — every public symbol mapped to
  its authoritative spec section.
