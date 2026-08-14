# Prerelease quirks

`ovos-spec-tools` has never had a stable release. Every version on PyPI so
far is an alpha (`0.0.1a2` through the current `1.7.0a2`). This page covers
every user-visible change since the first release, newest first, and will
reset to empty the first time a stable version ships.

## Breaking changes

- **`Session.extras` removed (#97).** It was added early as a catch-all
  passthrough for unknown session-wire keys, but OVOS-SESSION-1 never names
  it and nothing in ovos-bus-client, ovos-core, ovos-workshop, or ovos-utils
  read or wrote it. `Session.from_dict()` still silently drops unknown keys
  instead of raising (§2.4 compliance kept), and §4 propagation of unknown
  keys happens at the `Message` level: `Message.forward`/`reply` deep-copy
  the raw wire `context` dict rather than reconstructing it through
  `Session`, so an unknown key still rides through on the wire even though
  `Session` no longer models it. Code that read or set `.extras` on a
  `Session` object needs to stop.
- **Handler-lifecycle trio dropped from the namespace-migration bridge
  (#63).** `ovos.intent.handler.{start,complete,error}` is orchestrator-owned
  per PIPELINE-1 §8; the legacy `mycroft.skill.handler.*` topics are a
  separate, private, skill-framework-owned done-signal. Bridging the two
  double-emitted the spec trio and applied a lossy transform. The three
  entries were removed from `MIGRATION_MAP` along with their payload
  transforms. The `INTENT_HANDLER_*` `SpecMessage` members still exist;
  only the legacy<->spec auto-bridge for them is gone.

## `standardize_lang` vs. the old `standardize_lang_tag`

`ovos_spec_tools.language.standardize_lang(tag)` is not a drop-in rename of
the older `ovos_utils`/`ovos-utils`-side `standardize_lang_tag` shim.
`standardize_lang` folds underscores to hyphens, lowercases the primary
subtag, and uppercases the region, then resolves canonical script/region
forms through `langcodes` when it is installed (`en-us` -> `en-US`, not just
a case-folded string). Two deliberate, non-normative policy overrides on top
of `langcodes`' own resolution:

- a bare `pt` resolves to `pt-PT` (the reference variety OVOS prefers), not
  `langcodes`' default most-populous-region pick of `pt-BR`.
- `tl` is kept distinct from `langcodes`' `fil` macrolanguage fold.

Code migrating off the old `standardize_lang_tag` should expect full BCP-47
tags back, not just normalized casing, and should not assume `langcodes`'
raw region-resolution defaults for `pt`.

## `MIGRATION_MAP` / `NamespaceTranslator` — the legacy<->`ovos.*` bridge

`ovos_spec_tools.messages.MIGRATION_MAP` is the rename half of the legacy
`mycroft.*`/bare-topic <-> canonical `ovos.*` bridge; `NamespaceTranslator`
is the runtime object other packages (`ovos-utils`' `FakeBus`,
`ovos-bus-client`'s `MessageBusClient`) call into to dispatch both spellings
of a migrated topic with the payload reshaped per-topic where the migration
changed its shape. This module is the shared source of truth — packages that
used to carry their own ad hoc legacy-topic tables should migrate onto it
instead of keeping a local copy, since the map now also drives payload
translation, not just topic renaming.

## Session / context helpers (OVOS-CONTEXT-1, OVOS-SESSION-1)

`ovos_spec_tools.context` implements the OVOS-CONTEXT-1 gating and decay
helpers as stateless functions operating on a session's flat
`intent_context` map:

- `resolve_key(key, scope, owner_id)` — §3.1: `scope="private"` resolves to
  `<owner_id>:<key>` (a shared entry with the same bare key does not satisfy
  a private gate); `scope="shared"` resolves to the bare key. A private
  lookup with no `owner_id` returns `None`.
- `prune(intent_context, now=None)` — §4 pre-match: strips every non-live
  entry (expired by `expires_at` or `turns_remaining <= 0`) in place.
- `decrement(intent_context, only_keys=None)` — §4 post-match: decrements
  `turns_remaining` on remaining entries. Per §4.1 an entry written by an
  `ovos.session.sync` emitted mid-dispatch must not be decremented by the
  same dispatch that wrote it, so the orchestrator must capture the key set
  present at dispatch start and pass it as `only_keys`.

`SessionManager` is now a process-wide singleton registry (added alongside
`forward`/`reply` session stamping); its registry lock is reentrant (#84,
fixing a deadlock a nested `forward()`/`reply()` call could hit). The default
session folds like any other session — an earlier "owner-only" reservation
that exempted it from folding was dropped (#71) — and is the sessions dict's
single source of truth rather than a separately-tracked mirror (#69).

## `DialogRenderer` shape

`ovos_spec_tools.dialog.DialogRenderer` is a **stateful, per-dialog**
renderer: construct one with a `LocaleResources` and a single dialog `name`;
language is passed per `render()` call, so one instance serves every
language the dialog ships in, loading that language's phrases and
`.entity` value sets fresh on each call. It tracks the last phrase chosen
**per language** and avoids repeating it on the next call for that language.
This replaces the older pattern of a single renderer that walked an entire
locale directory of Mustache templates by path — there is no
directory-wide renderer here. Callers that want one dialog file get one
`DialogRenderer`; callers that render many dialogs construct one renderer
per name (or call the bare `render()` function directly for a stateless,
no-repetition-tracking one-off render).

## Other notable additions

- `IntentBuilder`/`Intent` + `voc_match` — a plugin-agnostic keyword intent
  model (INTENT-4) usable without `adapt`.
- `inline_keywords` — resolves `<keyword>` references as `(a|b|c)` for
  matcher engines without native `.voc` support.
- `union slot sets` for `.intent` files (OVOS-INTENT-1 §5.5).
- `context_slot_candidates` — CONTEXT-1 §7 pre-match slot injection from live
  context.
- `.blacklist` pairing with an `.entity` or `{slot}` for slot-value
  exclusion, enforced by the linter.
- Malformed keyword/`.intent` files now reject (later downgraded to warn) at
  build/emit time per INTENT-3 §4.2, instead of failing silently later.
- `persona_id` and `fallback_handlers` added as registered `Session` fields
  (OVOS-PERSONA-1, OVOS-FALLBACK-1).
- Dual-brace template refs: both `{x}` and `{{x}}` are accepted in general
  templates; `.prompt` files are double-brace-only.
- `Message.serialize()` enforces OVOS-MSG-1 §2.1 topic-type syntax.
- `Session` and `Message` are now hashable.

See [docs/message.md](message.md), [docs/language-matching.md](language-matching.md),
and [docs/dialog.md](dialog.md) for the current reference on these surfaces.
