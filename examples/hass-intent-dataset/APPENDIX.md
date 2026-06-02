# APPENDIX — hassil → OVOS-INTENT-2 conversion

This appendix formalises the mapping between the [hassil] intent grammar
(used by Home Assistant's [OHF-Voice/intents] corpus) and the
OVOS-INTENT-1 / OVOS-INTENT-2 resource model. It documents the rules
implemented by `examples/hass-intent-dataset/convert_hassil_intents.py` and the trade-offs
the script makes when the two formats disagree.

This is **not** a normative OVOS specification. It is a reference for
anyone writing a bidirectional translator between the two ecosystems.

[hassil]: https://github.com/home-assistant/hassil
[OHF-Voice/intents]: https://github.com/OHF-Voice/intents

---

## 1. Grammar correspondence

| hassil | OVOS-INTENT-1 | Notes |
|--------|---------------|-------|
| `[opt]` | `[opt]` | identical — optional block |
| `(a\|b)` | `(a\|b)` | identical — alternation |
| `A\|B\|C` (top-level) | `(A\|B\|C)` | hassil allows top-level alternation without an enclosing paren; OVOS treats those as literal `\|` chars, so we wrap in a virtual outer group during path-counting and enumeration |
| `{slot}` | `{slot}` | identical — slot reference |
| `<rule>` | `<rule>` | identical token shape, but semantics differ — see §4 |
| `(a; b; c)` | enumerated `(a b c\|a c b\|…)` | hassil's permutation operator has no OVOS counterpart |
| `{list:slot}` | `{slot}` | list-name suppressed; entity stored under the slot name |
| `{@list}` | `{list}` | compact capture, no OVOS analogue |
| `{list:@cap}` | `{cap}` | capture name becomes the slot name |
| `\X` | `\X` | identical backslash escape |

The four core tokens — optional, alternation, slot, reference — are
syntactically shared. Permutations and the four list-naming variants
are hassil-only and are normalised away during conversion.

## 2. Resource correspondence

| hassil source | OVOS resource | Role |
|---------------|---------------|------|
| `sentences/<lang>/<file>.yaml` — `intents:` block | `<intent_name>.intent` | matched templates |
| `sentences/<lang>/_common.yaml` — `lists:` with `values:` | `<slot>.entity` | slot value sets |
| `sentences/<lang>/_common.yaml` — `lists:` with `range:` | `<slot>.entity` | enumerated integer slot values |
| `sentences/<lang>/_common.yaml` — `lists:` with `wildcard:` | _(none)_ | free-form capture slot, no value file |
| `sentences/<lang>/_common.yaml` — `expansion_rules:` | inlined, or `<rule>.voc` (see §4) | slot-free vocabularies |
| `responses/<lang>/<file>.yaml` | `<intent_name>.dialog` | response phrase sets |

### 2.1 Rule scoping

Hassil's `expansion_rules:` can appear at three scopes:

  1. `_common.yaml` — global to the language.
  2. Per-file `expansion_rules:` block — scoped to that intent file.
  3. Per-data-block `expansion_rules:` inside an `intents:` data block
     — scoped to a single set of samples.

The converter **hoists all three scopes into a single global pool**
before running the promotion pipeline (§4). Without this hoist,
narrow-scoped helper rules like `<quant_queda>` (Catalan timer status)
or `<my_list>` (per-intent shopping list wrapper) stayed inlined and
contributed to cartesian explosions. `_common.yaml` definitions take
precedence on name collision.

A per-block or per-file rule that *shadows* a globally promoted rule
is skipped — reinstating the inlined body would undo the `.voc`
promotion and reintroduce the very cartesian explosion the promotion
was meant to fix.

## 3. Naming

OVOS-INTENT-2 requires lowercase ASCII base names. Hassil intent names
are CamelCase; rule and slot names in non-English locales contain
language-script characters (Spanish `habitación`, German `öffnen`,
Cyrillic `включити`).

  * Intent names → snake-cased: `HassTurnOn` → `hass_turn_on.intent`.
  * Rule / slot / list names → run through a slug filter that
    (1) NFKD-folds accented Latin to ASCII (`habitación` → `habitacion`,
    `öffnen` → `offnen`), (2) replaces remaining non-ASCII with `_`,
    (3) for names that fold to empty (CJK, Arabic, Devanagari, …) falls
    back to a stable `x_<8hex>` hash slug.

For non-Latin scripts the `x_<hash>` slugs are unreadable; the
canonical-name table (§5) can override them with English topic names.

## 4. Expansion rules — `.voc` versus inline

A hassil `<rule>` is a parameterless macro that substitutes a template
fragment at the call site. OVOS-INTENT-2's `<name>` reference is a
**lookup** into a `.voc` resource — a slot-free vocabulary file. The
semantics line up only when the rule body is slot-free.

The converter classifies each rule into one of four buckets:

### 4.1 Inlined

Rules whose enumeration has fewer than `PROMOTE_RULE_THRESHOLD = 2`
paths (i.e. literal, no alternation or optional) are inlined at every
call site. Trivial.

### 4.2 Auto-promoted to `.voc`

When a rule's body is slot-free *and* its Cartesian enumeration fits
within `MAX_PROMOTED_VALUES = 2048`, the rule is **promoted to a
vocabulary file**:

    rule:     <close> = "(close|shut|lower) [up|down]"
    sample:   <close> [the] {name}
    output:   close.voc        ← enumerated values, one per line
              hass_close.intent: <close> [the] {name}

The `<rule>` reference is preserved verbatim in the `.intent` sample;
the `.voc` file holds the alternation flattened to one literal phrase
per line. This is the OVOS-INTENT-2 canonical form and lint-friendly
(no nested alternation to enumerate).

### 4.3 Force-promoted to free-form capture slot

A small hardcoded set of rules (`timer_duration`, `timer_start`,
`area`, `name`, `floor`) have bodies dense with nested optionals,
alternations, and `{slot}` references. Inlining them produces samples
with 10⁹-path expansions; they can't be enumerated to a `.voc` because
they carry inner slots; and their matched text is a structured artefact
that downstream code wants to parse.

These are **force-promoted to free-form capture slots**:

    rule:     <area> = "[<preposition>|<artikel_bestimmt> ]{area}|…"
    sample:   turn on [the] {name} in <area>
    output:   hass_turn_on.intent: turn on [the] {name} in {area}
              _(no value-set file — runtime captures arbitrary text)_

`<timer_duration>` similarly collapses to `{timer_duration}` and a
duration-resolver in the skill parses the captured text.

### 4.4 Multi-source canonical aggregation

When multiple local-language rules canonicalise to the same English
concept (see §5), each keeps its own `.voc` with local synonyms and
a **parent `.voc`** named after the canonical English concept lists
them as references:

    es/cancel.voc:                     fr/turn_off.voc:
      <cancela>                          <eteins>
      <cancelar_temporizador>            <eteins_dirty>

    es/cancela.voc:                    fr/eteins.voc:
      cancela                            arrête
      cancelación                        arrêter
      cancelar                           coupe
                                         couper
                                         …

This is the OVOS "vocabulary of vocabularies" pattern. The `.intent`
samples reference the canonical parent (`<cancel>`, `<turn_off>`) and
the parent transitively pulls in all sibling local-language children.

Two safety guards apply:

  * **Intra-group reference preservation** — when a child rule's body
    references a sibling (e.g. French `eteins` body contains
    `<eteins_dirty>`, both mapping to `turn_off`), the sibling
    reference is kept local to avoid a cycle through the canonical
    parent.
  * **Collision avoidance** — if the canonical English name already
    exists as another rule in the same language (e.g. `ro/brightness`
    is a slot-wrapper while `ro/luminozitatea` is the noun), the
    mapping is dropped rather than silently overwriting the existing
    rule. The local name is kept.

## 5. Canonical rule-name table

`CANONICAL_RULE_NAMES[<lang>] = {local_name: english_name}` maps each
language's hassil rule names to canonical English topic names so that
the resulting locale tree is portable. Coverage (per-language, in the
checked-in table) currently includes:

  * **Romance**: es, ca, fr, gl, it, pt, pt-BR, pt-PT, ro
  * **Germanic**: de, de-CH, nl, da, sv, nb, lb, is
  * **Slavic**: cs, sk, sl, hr, sr-Latn, pl
  * **Hellenic / Celtic / Hungarian**: el, cy, hu
  * **Uralic**: fi
  * **Sino-Tibetan**: zh-CN, zh-HK, zh-TW
  * **Other**: ar, vi, th

Concepts mapped per language vary, but commonly include:

  * actions — `turn_on`, `turn_off`, `open`, `close`, `start`, `stop`,
    `cancel`, `pause`, `resume`, `play`, `skip`, `raise`, `lower`,
    `increase`, `decrease`, `add`, `remove`, `set`, `broadcast`,
    `clean`, `lock`, `unlock`, `mow`, `vacuum`
  * objects — `light`, `lights`, `fan`, `fans`, `door`, `doors`,
    `window`, `gate`, `cover`, `shutter`, `curtain`, `garage`,
    `device`, `sensor`, `script`, `scene`
  * concepts — `battery`, `battery_level`, `brightness`, `volume`,
    `temperature`, `color`, `here`, `now`, `all`, `everywhere`,
    `home`, `previous`, `next`, `any`, `which`, `what_is`, `where_is`,
    `how_many`, `how_much`, `percent`, `degrees`
  * units — `hour_unit`, `minute_unit`, `second_unit`, `meter_unit`

### 5.1 Kept local-language (intentional)

Per the "keep local only when the concept is language-specific" rule,
these stay under their hassil-original names:

  * **Articles** — `le/la/les` (fr), `der/die/das` (de),
    `el/la/els/les` (ca), `il/lo/gli` (it), `el/la` (es).
  * **Declension / case markers** — German `artikel_bestimmt`,
    `artikel_unbestimmt`, `possessivpronom_mein`,
    `possessivpronom_unser`; Finnish `*_taivutus`; Hungarian
    `*_ragok`, `*_szavak`; Catalan `preposicio_singular_masc`,
    `pronom_plural`; Romanian prepositions `de/din/in/la`.
  * **Politeness particles** — Thai `polite_prefix*`,
    `polite_suffix*`.

These have no useful English mapping because they encode grammar
specific to the source language.

### 5.2 Children of multi-source canonical groups

A side-effect of §4.4: when multiple local rules collapse to one
canonical English name, the *children* are kept under their hassil
names so the canonical parent can reference them. The user-visible
behaviour is that browsing the `.voc` directory shows e.g.

    es/cancel.voc           ← canonical parent
    es/cancela.voc          ← child (kept local, referenced by parent)
    es/cancelar_temporizador.voc

These local-named files are intentional and exist solely to support
the canonical parent.

## 6. Sample validation — OVOS-INTENT-1 §3.6 / §5.5

OVOS-INTENT-1 imposes two constraints hassil does not:

  * **No adjacent slots** — `{a} {b}` is forbidden; a literal word must
    separate any two slots. Hassil allows it.
  * **No repeated slot names per sample** — `{a} and {a}` is forbidden.
    Hassil allows it.

The third historical constraint — **uniform slot signature** (§5.5) —
was relaxed in OVOS-INTENT-1 v3. `.intent` files now allow templates
with differing slot sets under union semantics. Every valid path is
kept regardless of its signature.

When a template has some enumerated paths that violate §3.6, the
converter falls back to **path-level salvage**:

  1. Enumerate the full template (literal text included).
  2. Drop paths that violate §3.6 (adjacency or repeated slots).
  3. Keep every surviving path regardless of slot signature (v3
     union semantics).

If every path is invalid the sample is logged as `all_paths_invalid`
and dropped.

Dialog phrase sets recovered from `{% if … %}` branches are exempt from
the union-sig rule — see §8.2 — because dropping a branch means losing
one conditional response, which is worse than emitting an extra file.

## 7. Safety caps

Hassil grammars use rule inlining and permutations that combine into
exponential string explosion. The converter guards every stage:

| Cap | Value | Purpose |
|-----|-------|---------|
| `MAX_PERM_ELEMS` | 5 | permutations of >5 elements collapse to literal concatenation |
| `MAX_SAMPLE_BYTES` | 4 KiB | drop any rewritten template larger than this |
| `MAX_SAMPLE_PATHS` | 20000 | drop samples whose Cartesian expansion exceeds this |
| `MAX_ENTITY_VALUES` | 2000 | cap on `range:` list materialisation |
| `MAX_RULE_BYTES` | 16 KiB | short-circuit fixed-point rule inlining if a body blows up |
| `PROMOTE_RULE_THRESHOLD` | 2 | any rule with ≥1 alt/opt becomes a `.voc` file |
| `MAX_PROMOTED_VALUES` | 2048 | rules whose enumeration exceeds this stay inlined |

Every output file is written line-by-line; the dedupe set for the
currently-open file is the only state held in memory.

## 8. Response normalisation

Hassil responses are Jinja2 templates. The converter handles a small
subset and drops the rest.

### 8.1 Variable substitution

| Jinja | OVOS dialog | Notes |
|-------|-------------|-------|
| `{{ var }}` | `{var}` | bare variable |
| `{{ slots.X }}` | `{X}` | slot access — most common pattern |
| `{{ state.X }}` | `{X}` | state-object access |
| `{{ query.X }}` | `{X}` | query-object access (matched lists, …) |
| `{{ X \| filter }}` | `{X}` | filters dropped — OVOS has no Jinja filter pipeline |

### 8.2 Control flow

`{% set ... %}` blocks are stripped (their bindings can't be carried
into a stateless dialog phrase).

`{% if ... %} A {% elif ... %} B {% else %} C {% endif %}` is
**decomposed into one phrase per branch**. Each (response key, Jinja
branch) pair becomes its own `.dialog` file:

    <intent>.dialog                        default key, no Jinja
    <intent>_branch_<N>.dialog             default key, branch N
    <intent>_<key>.dialog                  non-default response key, no Jinja
    <intent>_<key>_branch_<N>.dialog       non-default key, branch N

The skill calls the file whose name corresponds to its runtime
condition — mirroring the original Jinja branch selection.

### 8.3 Unresolvable

Anything else falls under `jinja_template_unresolvable` and is logged
to the audit TSV. Typical examples:

  * dict lookups — `{{ months[slots.date.month] }}`
  * deep object navigation — `{{ slots.date.day }}`, `{{ slots.time.hour }}`
  * `format()` calls — `{{ '{0:02d}'.format(slots.time.minute) }}`
  * array operations — `{{ query.matched | length }}` (length filter
    is dropped but the bare `query.matched` substitution survives),
    `{% for name in matched %} … {% endfor %}` (loop body discarded)

These idioms have no static template equivalent — they would need a
Python helper resolver at render time, which is out of scope for a
template-to-template converter.

## 9. Audit log

Every hard failure is recorded in
`examples/hass-intent-dataset/convert_hassil_intents.skipped.tsv` with columns:

    lang     language code (ISO 639-1 / BCP-47)
    kind     "sample" | "response" | "entity"
    intent   hassil intent name
    reason   stable identifier (cartesian_explosion, adjacent_slots,
             repeated_slot, jinja_template_unresolvable,
             all_paths_invalid, sample_too_large_after_*, …)
    original the raw hassil source string

Only **hard failures** are logged — slots that degrade gracefully to
free-form capture (wildcard lists, undefined lists referenced by a
slot) are not, because the corresponding `.intent` line is still
emitted and the slot remains functional at runtime.

## 10. Round-trip considerations

The conversion is **lossy** and **one-way**:

  * Permutations are enumerated and lose their compact form.
  * Hassil filters and Jinja control flow other than `{% if %}` are
    dropped.
  * Path-salvage emits literal enumerations in place of the original
    compact template — the `{slot}` placeholders survive but the
    optional grouping does not.
  * §5.5 v3 union semantics means samples with differing slot signatures
    are kept as separate template lines — they are not grouped or
    salvaged into `_branch_<n>` files. For *dialogs*, sub-signature
    branches from `{% if %}` decomposition still land in
    `_branch_<n>` files (see §8.2).
  * The canonical-name table folds language-local rule names to
    English topic names — the reverse direction would need the same
    table read backwards (one canonical name → multiple local names).

A reverse converter (OVOS → hassil) would need to re-discover common
alternations across sample lines to rebuild compact templates, run the
canonical map in reverse to recover local rule names, and reconstruct
the per-block scoping. None of that is trivial.

The audit TSV is intended to make every loss visible: anyone using
the converter as part of a build pipeline can grep the TSV for
specific (lang, intent) pairs and either accept the loss, rewrite the
source by hand, or extend the converter with another targeted
heuristic (a new entry in `CANONICAL_RULE_NAMES`, a new
`FORCE_PROMOTE` entry, or a new Jinja substitution rule).
