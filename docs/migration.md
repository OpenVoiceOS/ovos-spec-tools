# Move to ovos-spec-tools
<!-- agent-hint
covers: what changes for code that moves from older OVOS helpers or older alphas to ovos-spec-tools
source: ovos_spec_tools/language.py, ovos_spec_tools/session.py, ovos_spec_tools/messages.py, ovos_spec_tools/dialog.py, ovos_spec_tools/expansion.py
generated: no
verify: python3 docs/check_page.py docs/migration.md standardize_lang_tag handle_sync ovos.session.sync
see: index.md
-->

This page tells you what changes when your code moves from the older OVOS helpers to `ovos-spec-tools`. `CHANGELOG.md` lists each change by version.

## Language tags

`standardize_lang(tag)` is not a rename of the older `standardize_lang_tag`. It returns a full BCP-47 tag (`en-us` gives `en-US`), with the policy of [linguatag](https://github.com/TigreGotico/linguatag):

- A bare tag is measured from its default region, where the language first appeared: `pt` is `pt-PT` and `en` is `en-GB`.
- Do not expect the most-populous region that `langcodes` gives for a bare tag.

See [language-matching.md](language-matching.md).

## Sessions

- `Session` has no `extras` attribute. `Session.from_dict()` drops unknown keys and does not raise. `Message.forward()` and `Message.reply()` copy the raw wire `context`, so an unknown key still travels on the wire.
- `SessionManager` has no `handle_sync`, and `SpecMessage` has no `SESSION_SYNC`. No spec topic pushes a session. `ovos-bus-client` folds a legacy `ovos.session.sync`.

## Topic bridge

`MIGRATION_MAP` and `NamespaceTranslator` hold the pairs of legacy and `ovos.*` topics, and the payload change for each pair. Use them, not a local table of legacy topics. The handler topics `ovos.intent.handler.start`, `ovos.intent.handler.complete` and `ovos.intent.handler.error` are not in the bridge: the orchestrator sends them, and `mycroft.skill.handler.*` is a separate signal of the skill framework. See [bus-namespaces.md](bus-namespaces.md).

## Dialogs

`DialogRenderer` renders one named dialog. Make one renderer for each dialog name, and give the language on each `render()` call. There is no renderer for a full locale directory. For a one-time render with no memory of the last phrase, call `render()`. See [dialog.md](dialog.md).

## Templates

`iter_expand()` gives the same samples as `expand()`, in the same order, one at a time. An engine that keeps only some samples (`itertools.islice`) does not build the full product. See [templates.md](templates.md).

---
[← Spec traceability](spec-traceability.md) · [Home](index.md)
