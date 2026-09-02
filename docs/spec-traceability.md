# Spec traceability

`ovos-spec-tools` exists for one reason: to be the **reference
implementation of the OVOS formal specifications**. Every public symbol in
the package implements a specific clause of a specific spec. There is no
"general-purpose" code here. This page is the proof: every name exported
from `ovos_spec_tools`, mapped to its authoritative spec section.

The specs live in the
[OpenVoiceOS/architecture](https://github.com/OpenVoiceOS/architecture)
repository. Section numbers (`§N`) refer to the spec named in the same row.
Where a symbol is a *shared primitive* used across several spec clauses, the
"primary" owning clause is cited and the dependents are noted.

## Bus / message domain

The bus domain (`message.py`, `messages.py`) is the most heavily
spec-annotated; its module and per-symbol docstrings cite OVOS-MSG-1 inline.
See [Bus messages](message.md) and [Bus namespaces](bus-namespaces.md) for
the prose.

### `message.py`: OVOS-MSG-1 (Bus Message)

| Symbol | Spec | § |
|---|---|---|
| `Message` | OVOS-MSG-1 | §2 (envelope) |
| `Message.msg_type` / `.data` / `.context` | OVOS-MSG-1 | §2.1 / §2.2 / §2.3 |
| `Message.__init__` (type checks) | OVOS-MSG-1 | §2.1-§2.3, §7 |
| `Message.forward` | OVOS-MSG-1 | §5.1 |
| `Message.reply` | OVOS-MSG-1 | §5.2 |
| `Message.response` | OVOS-MSG-1 | §5.3 |
| `Message.serialize` | OVOS-MSG-1 | §6 |
| `Message.deserialize` | OVOS-MSG-1 | §6, §7 |
| `Message.as_dict` | OVOS-MSG-1 | §2, §6 |
| `MalformedMessage` | OVOS-MSG-1 | §2, §6, §7 (consumer "MUST reject") |
| `DEFAULT_SESSION_ID` | OVOS-MSG-1 | §4.1 (reserved `"default"`) |
| `RoutingValue` (type alias) | OVOS-MSG-1 | §3 / §3.3 (routing key shape) |

The routing keys (`context.source` / `context.destination`, §3) and the
session carrier (`context.session`, §4) are carried by `Message` but their
*inner* semantics are owned elsewhere: §3 by MSG-1 itself (opaque), §4's
inner shape by **OVOS-SESSION-1**.

### `messages.py`: the spec topic vocabulary and the migration bridge

`SpecMessage` members each name a topic owned by another spec; the bridge
(`MIGRATION_MAP` / `NamespaceTranslator`) is the cross-cutting machinery that
moves the bus onto those topics.

| Symbol | Spec | § |
|---|---|---|
| `SpecMessage.UTTERANCE` | OVOS-PIPELINE-1 | §9.1 |
| `SpecMessage.SPEAK` | OVOS-PIPELINE-1 | §9.6 |
| `SpecMessage.UTTERANCE_HANDLED` | OVOS-PIPELINE-1 | §9.5 |
| `SpecMessage.UTTERANCE_CANCELLED` | OVOS-TRANSFORM-1 | §8.2 (defined here; PIPELINE-1 §6.4 references it) |
| `SpecMessage.INTENT_MATCHED` | OVOS-PIPELINE-1 | §9.2 |
| `SpecMessage.INTENT_UNMATCHED` | OVOS-PIPELINE-1 | §9.3 |
| `SpecMessage.INTENT_HANDLER_START` / `_COMPLETE` / `_ERROR` | OVOS-PIPELINE-1 | §8.1 |
| `SpecMessage.INTENT_REGISTER_KEYWORD` | OVOS-INTENT-4 | §5 |
| `SpecMessage.INTENT_REGISTER_TEMPLATE` | OVOS-INTENT-4 | §6 |
| `SpecMessage.ENTITY_REGISTER` | OVOS-INTENT-4 | §7 |
| `SpecMessage.INTENT_DEREGISTER` | OVOS-INTENT-4 | §8.2 |
| `SpecMessage.ENTITY_DEREGISTER` | OVOS-INTENT-4 | §8.3 |
| `SpecMessage.SKILL_DEREGISTER` | OVOS-INTENT-4 | §8.4 |
| `SpecMessage.INTENT_ENABLE` / `INTENT_DISABLE` | OVOS-INTENT-4 | §8.5 |
| `SpecMessage.INTENT_LIST` / `_LIST_RESPONSE` | OVOS-INTENT-4 | §10.1 |
| `SpecMessage.INTENT_DESCRIBE` / `_DESCRIBE_RESPONSE` | OVOS-INTENT-4 | §10.2 |
| `SpecMessage.STOP_PING` / `STOP_PONG` | OVOS-STOP-1 | §4.2 |
| `SpecMessage.STOP` | OVOS-STOP-1 | §5.3 |
| `SpecMessage.LISTENER_RECORD_STARTED` / `_RECORD_ENDED` / `LISTENER_SLEEP` / `LISTENER_AWOKEN` | OVOS-AUDIO-IN-1 | §6.1 / §6.2 / §6.3 / §6.4 |
| `SpecMessage.SPEAK_B64` | OVOS-AUDIO-1 | §3.4 |
| `SpecMessage.AUDIO_SPEECH` | OVOS-AUDIO-1 | §4.3 |
| `SpecMessage.AUDIO_QUEUE` / `AUDIO_PLAY_SOUND` | OVOS-AUDIO-1 | §4.1 / §4.2 |
| `SpecMessage.AUDIO_STOP` | OVOS-AUDIO-1 | §6 |
| `SpecMessage.AUDIO_IS_SPEAKING` | OVOS-AUDIO-1 | §5.3 |
| `SpecMessage.AUDIO_OUTPUT_STARTED` / `_OUTPUT_ENDED` | OVOS-AUDIO-1 | §5.1 / §5.2 |
| `SpecMessage.MIC_LISTEN` | OVOS-AUDIO-1 | §4.4 |
| `SpecMessage.SESSION_SYNC` | OVOS-SESSION-2 | §2.7 (bus table §7) |
| `SpecMessage.CONVERSE_ACTIVE_LIST` / `_ACTIVE_LIST_RESPONSE` | OVOS-CONVERSE-1 | §6.1 |
| `SpecMessage.PERSONA_QUERY` / `_ANSWER` | OVOS-PERSONA-1 | §8.5 (§11 bus surface) |
| `SpecMessage.PERSONA_LIST` / `_LIST_RESPONSE` | OVOS-PERSONA-1 | §8.7 (§11) |
| `SpecMessage.PERSONA_REGISTER` / `_DEREGISTER` | OVOS-PERSONA-1 | §9 (§11) |
| `SpecMessage.PERSONA_ACTIVATED` / `_DISMISSED` | OVOS-PERSONA-1 | §11 |
| `SpecMessage.FALLBACK_REGISTER` / `_DEREGISTER` | OVOS-FALLBACK-1 | §3.1 / §3.2 (§9 bus surface) |
| `SpecMessage.COMMON_QUERY_PING` / `_PONG` | OVOS-COMMON-QUERY-1 | §6.1 / §6.2 (§13 bus surface) |
| `SpecMessage.TRANSFORMER_{AUDIO,UTTERANCE,METADATA,INTENT,DIALOG,TTS}_LIST` / `_LIST_RESPONSE` | OVOS-TRANSFORM-1 | §6 (six static query/response pairs) |
| `SpecMessage.COMMON_PLAY_{PLAY,SEARCH}` | OVOS-OCP-1 | §4.2 |
| `SpecMessage.COMMON_PLAY_{PAUSE,RESUME,STOP,NEXT,PREVIOUS,SEEK}` | OVOS-OCP-1 | §4.3 |
| `SpecMessage.COMMON_PLAY_{PLAYER,MEDIA,TRACK}_STATE` | OVOS-OCP-1 | §4.4 |
| `MIGRATION_MAP` | (bridge) | encodes the renames defined by PIPELINE-1 §8/§9, INTENT-4 §8, STOP-1 §4/§5, AUDIO-IN-1 |
| `SPEC_TO_LEGACY` | (bridge) | reverse of `MIGRATION_MAP` |
| `migration_counterpart` | (bridge) | symmetric counterpart lookup |
| `NamespaceTranslator` | (bridge) | dual-emit + receive-dedup; mirrors `ovos-bus-client` / `FakeBus` |
| `NamespaceTranslator.counterpart_topics` | (bridge) | send-side dual-emit |
| `NamespaceTranslator.is_migrated` | (bridge) | namespace-bridge participation check (static map only) |
| `NamespaceTranslator.has_mirror` | (bridge) | general dual-emit participation pre-check (both bridges) |
| `NamespaceTranslator.new_mirror_guard` | (bridge) | receive-side mirror-window dedup |

The bridge symbols are not owned by one numbered spec clause. They are the
*mechanism* that carries the bus from the legacy topic names to the `ovos.*`
topics the specs above define, while honouring OVOS-MSG-1 §6 (payload key
order is not significant, used in the dedup fingerprint). The two topics the
bridge deliberately does **not** map trace to OVOS-INTENT-4 §5 (N→1
registration consolidation) and OVOS-MSG-1 §2.1.1 (runtime-assembled
placeholder topics); see [Bus namespaces](bus-namespaces.md).

### `intent_topics.py` — OVOS-MSG-1 §2.1.1 (runtime-assembled dispatch topic)

The per-intent dispatch topic `<skill_id>:<intent_name>` is assembled at
runtime, so `SpecMessage` cannot name it. These helpers own its shape and the
transitional translation of the legacy `.intent`-suffixed spelling old
`ovos-workshop` releases put on the wire.

| Symbol | Spec | § |
|---|---|---|
| `is_intent_topic` | OVOS-MSG-1 | §2.1.1 (`:` is the structural separator) |
| `canonical_intent_topic` | OVOS-MSG-1 | §2.1.1 (`<intent_name>`, not a filename) |
| `legacy_intent_topic` | (migration) | inverse of the above; historical spelling |
| `INTENT_FILE_SUFFIX` | OVOS-INTENT-2 | §3 (`.intent` is an authoring resource extension) |

Like the namespace bridge, the translation is a migration *policy* of this
tooling, not a spec-mandated mechanism: no spec defines the suffixed topic.

## Session domain: OVOS-SESSION-1

`session.py` is the reference implementation of the §4 session carrier's
*inner* shape (which OVOS-MSG-1 §4 defers to OVOS-SESSION-1), plus the
handler-list helpers that PIPELINE-1 and CONVERSE-1 keep in the session.

| Symbol | Spec | § |
|---|---|---|
| `Session` | OVOS-SESSION-1 | §3 (registered field set) |
| `SESSION1_REGISTERED_FIELDS` | OVOS-SESSION-1 | §3 |
| `SESSION1_OWNED_FIELDS` | OVOS-SESSION-1 | §3 (fields SESSION-1 itself owns) |
| `DEFAULT_CONVERSE_HANDLERS_CAP` | OVOS-CONVERSE-1 | §2.1 (handler-list cap) |
| `MalformedSession` | OVOS-SESSION-1 | §3 (malformed wire shape) |
| `Session.merge_from` | OVOS-SESSION-2 | §5.1 (default-session store write) |
| `parse_session_payload` | OVOS-SESSION-1 | §5 (carrier parsing) |

(`session.py` is owned by an in-flight PR; the citations above describe the
symbols it exports as imported by the package `__init__`.)

## Intent template / locale domain

### `expansion.py`: OVOS-INTENT-1 (Sentence Template Grammar)

| Symbol | Spec | § |
|---|---|---|
| `expand` | OVOS-INTENT-1 | §3 (grammar), §3.7 (inline vocab), §4 (sample set) |
| `inline_keywords` | OVOS-INTENT-1 | §3.7 (`<name>` inline vocabulary references) |
| `MalformedTemplate` | OVOS-INTENT-1 | §3.6 (malformed templates) |

### `resources.py`: OVOS-INTENT-2 (Locale Resource Formats)

| Symbol | Spec | § |
|---|---|---|
| `LocaleResources` | OVOS-INTENT-2 | §2 (layout / override precedence), §4 (six roles) |
| `read_resource_file` | OVOS-INTENT-2 | §3 (common reader) |
| `read_prompt_file` | OVOS-INTENT-2 | §3, §4.4 (`.prompt` whole-file read) |
| `iter_locale_dirs` | OVOS-INTENT-2 | §2 (locale layout) + §2.2 distance fallback |
| `find_lang_dir` | OVOS-INTENT-2 | §2.2 (closest-language directory resolution) |
| `keyword_form` | OVOS-INTENT-2 | §4.3 (slot-free template grouping) |
| `normalize_for_match` | OVOS-INTENT-2 | §4.3 (match-comparison normalization) |
| `utterance_contains` | OVOS-INTENT-2 | §4.3 (vocabulary / keyword match) |
| `strip_samples` | OVOS-INTENT-2 | §4.3 (keyword removal) |
| `MalformedResource` | OVOS-INTENT-2 | §3, §4 (malformed file / layout) |

### `dialog.py`: OVOS-INTENT-2 §4.2 (Dialog)

| Symbol | Spec | § |
|---|---|---|
| `render` | OVOS-INTENT-2 | §4.2 (select + fill a `.dialog` phrase) |
| `DialogRenderer` | OVOS-INTENT-2 | §4.2 (stateful, multilingual renderer) |
| `UnfilledSlot` | OVOS-INTENT-2 | §4.2 (a chosen phrase has an unfilled slot) |
| `verify_slot_consistency` | OVOS-INTENT-1 | §7 + §5.5 (Dialog renderer MUST verify all phrases declare the same slot set) |

### `prompt.py`: OVOS-INTENT-2 §4.4 (`.prompt`)

| Symbol | Spec | § |
|---|---|---|
| `render_prompt` | OVOS-INTENT-2 | §4.4 (conservative `{name}` substitution) |
| `PromptRenderer` | OVOS-INTENT-2 | §4.4 (stateful, multilingual prompt renderer) |

## Language matching: shared OVOS-INTENT-2 §2.2 primitive

`language.py` is the single implementation of "closest available language",
the smart-fallback logic OVOS-INTENT-2 §2.2 relies on for resource
resolution (and which TTS/STT plugins reuse).

| Symbol | Spec | § |
|---|---|---|
| `standardize_lang` | OVOS-INTENT-2 | §2.2 (BCP-47 tag normalization) |
| `lang_distance` | OVOS-INTENT-2 | §2.2 (regional-match distance, `<10` usable) |
| `lang_matches` | OVOS-INTENT-2 | §2.2 (match predicate) |
| `closest_lang` | OVOS-INTENT-2 | §2.2 (closest-match resolution) |

## Linting: OVOS-INTENT-1 / OVOS-INTENT-2

`lint.py` validates resource *syntax* (INTENT-1) and *naming/layout*
(INTENT-2); the `--spec-version` switch flags features newer than a target
spec version.

| Symbol | Spec | § |
|---|---|---|
| `lint_locale` | OVOS-INTENT-1 + OVOS-INTENT-2 | INTENT-1 §3 (syntax) + INTENT-2 §2/§4 (layout/roles) |
| `Finding` | (tooling) | a single lint result (`severity`/`path`/`message`) |
| `ovos-spec-lint` (CLI) | (tooling) | command wrapper over `lint_locale` |

## Package

| Symbol | Spec | § |
|---|---|---|
| `__version__` | (packaging) | installed package version string |

## Coverage

Every name in `ovos_spec_tools.__all__` appears in a table above. The only
rows whose "spec" column is not a numbered OVOS spec clause are:

- the **bridge** machinery (`MIGRATION_MAP`, `SPEC_TO_LEGACY`,
  `migration_counterpart`, `NamespaceTranslator` and its methods). These
  *carry* the bus onto spec topics rather than implementing one clause, and
  each entry/mapping is itself traced to the spec rename it encodes;
- the **intent-topic translation** (`legacy_intent_topic`) — the same kind of
  migration carrier, tracing to the OVOS-MSG-1 §2.1.1 topic shape it restores;
- **tooling/packaging** surface (`Finding`, the `ovos-spec-lint` command,
  `__version__`).

Everything else is a direct reference implementation of a cited OVOS-MSG-1,
OVOS-SESSION-1, OVOS-SESSION-2, OVOS-INTENT-1, OVOS-INTENT-2, OVOS-INTENT-4,
OVOS-PIPELINE-1, OVOS-STOP-1, OVOS-AUDIO-IN-1, OVOS-AUDIO-1, OVOS-CONVERSE-1,
OVOS-PERSONA-1, OVOS-FALLBACK-1, OVOS-COMMON-QUERY-1, OVOS-TRANSFORM-1, or
OVOS-OCP-1 clause.

`SpecMessage` is the static `ovos.*` topic vocabulary: it carries one member
per spec-defined fixed-string topic and deliberately omits runtime-templated
topics (MSG-1 §2.1.1: the `<skill_id>:…`, `<pipeline_id>…`, per-skill ping
placeholders) and topics used by `ovos-bus-client` that no spec defines
(`ovos.session.update_default`, `ovos.session.start`, `ovos.context.set`).

---
[Home](README.md)
