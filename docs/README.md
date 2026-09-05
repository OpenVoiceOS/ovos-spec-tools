# ovos-spec-tools documentation

`ovos-spec-tools` is the reference implementation of the
[OVOS formal specifications](https://github.com/OpenVoiceOS/architecture):
the small, dependency-light primitives those specs describe, in one place, so
OVOS components and third-party tools stop reimplementing them and drifting
apart.

It gives you five things:

- an **expander**: turns a sentence template into the set of sentences it
  stands for (OVOS-INTENT-1).
- a **resource loader**: reads a skill's `locale/` folder (OVOS-INTENT-2).
- a **dialog renderer**: picks and fills a spoken response (OVOS-INTENT-2 §4.2).

- **language matching**: normalizes tags and finds the closest one.
- a **bus message envelope**: the `type` / `data` / `context` JSON contract
  and its `forward` / `reply` / `response` derivations (OVOS-MSG-1).

plus **`ovos-spec-lint`**, a command-line linter for locale folders.

## The guide

Read it in order. Each chapter builds on the one before, and **templates**
are the foundation everything else rests on.

1. [Getting started](getting-started.md), install it, and a first taste of
   every tool.
2. [Sentence templates](templates.md), the grammar: alternatives, optionals,
   slots, vocabulary references, and what counts as malformed.
3. [Locale resources](locale-resources.md), the `locale/` folder, the five
   file roles, and loading them across languages.
4. [Dialog](dialog.md), choosing and filling a spoken response, with the
   stateless function and the stateful renderer.

5. [Language matching](language-matching.md), tag standardization, distance,
   and closest-match resolution.
6. [Bus messages](message.md), the on-the-wire envelope, the three
   derivations (`forward` / `reply` / `response`), and the session carrier.
7. [Bus namespaces](bus-namespaces.md), the spec topic vocabulary
   (`SpecMessage`), the legacy↔`ovos.*` `MIGRATION_MAP`, and the transparent
   dual-emit bridge with its migration window.
8. [Linting](linting.md), validating a locale folder, from the command line
   or in CI.
9. [API reference](api-reference.md), every public name, in brief.
10. [Prerelease quirks](prerelease-quirks.md), user-visible changes since the
    last stable release (none has shipped yet, so this covers everything
    since the first alpha).

### Proving the scope

- **[Spec traceability](spec-traceability.md)**, every public symbol in
  `ovos-spec-tools` mapped to its authoritative OVOS spec section. This is
  the index that backs the scope note below: the package is *exclusively* a
  reference implementation of the specs, with no general-purpose code.

## A note on scope

This package **expands, loads, renders, matches language, lints, and
provides the bus message envelope**. It does not *recognize* intents.
Matching an utterance to an intent is the job of an intent engine, and is
deliberately out of scope (see OVOS-INTENT-1 §4).

It does not *transport* messages either. Wire framing, encryption, websocket
clients, multi-tenant routing, and session lifecycle all belong to the layers
that consume the envelope (`ovos-bus-client` for the websocket transport,
HiveMind for layer-2 routing).

What you get here is the data those engines consume, the message shape they
exchange, and the tooling around them.
