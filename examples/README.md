# Examples

## `dirty-locale` — the linter against a broken locale

`dirty-locale/` is a deliberately broken skill locale. Every file in it trips
at least one `ovos-spec-lint` check, so it doubles as a tour of what the linter
catches. Two files (`en-US/good.intent`, `en-US/good.voc`) are valid and
produce no findings.

### The locale

```
dirty-locale/locale/
├── stray.intent                 misplaced — not inside a language directory
├── english/                     directory name is not a BCP-47 tag
│   └── hello.intent             (valid content)
└── en-US/
    ├── good.intent              valid — no findings
    ├── good.voc                 valid — no findings
    ├── unbalanced.intent        unbalanced metacharacters
    ├── single_branch.intent     a group with only one branch
    ├── adjacent.intent          two slots with no word between them
    ├── repeat.intent            the same slot name twice in a sample
    ├── empty.voc                no templates after comments are dropped
    ├── colors.voc               a named slot in a slot-free role
    ├── Bad-Name.intent          base name outside the allowed charset
    ├── 2nd.entity               .entity base name begins with a digit
    ├── refs.intent              <name> reference to a vocabulary that does not exist
    ├── old.rx                   a legacy file type, not an OVOS-INTENT-2 role
    ├── sub1/menu.intent  ┐      same (role, base name) twice in one
    └── sub2/menu.intent  ┘      language tree
```

### Running the linter

```console
$ ovos-spec-lint examples/dirty-locale/locale
examples/dirty-locale/locale/stray.intent: warning: resource file is not inside a language directory
examples/dirty-locale/locale/en-US/old.rx: warning: .rx is a legacy file type, not an OVOS-INTENT-2 resource role
examples/dirty-locale/locale/en-US/sub2/menu.intent: error: duplicate .intent resource 'menu' — also at examples/dirty-locale/locale/en-US/sub1/menu.intent
examples/dirty-locale/locale/en-US/2nd.entity: error: .entity base name '2nd' names a slot and must not begin with a digit
examples/dirty-locale/locale/en-US/Bad-Name.intent: error: base name 'Bad-Name' must be lowercase ASCII letters, digits and underscores only
examples/dirty-locale/locale/en-US/Bad-Name.intent: warning: file name should be lowercase
examples/dirty-locale/locale/en-US/adjacent.intent: error: adjacent slots in sample 'set {hours}{minutes}' of template 'set {hours}{minutes}': a literal word must separate any two slots  [in: 'set {hours}{minutes}']
examples/dirty-locale/locale/en-US/colors.voc: error: .voc is slot-free but a template contains a named slot  [in: 'the color {shade}']
examples/dirty-locale/locale/en-US/empty.voc: error: empty file — every resource file must contribute at least one template (OVOS-INTENT-2 §5)
examples/dirty-locale/locale/en-US/refs.intent: error: undefined vocabulary reference <undefined_voc>  [in: '<undefined_voc> {name}']
examples/dirty-locale/locale/en-US/repeat.intent: error: repeated slot name in sample '{x} and {x}' of template '{x} and {x}': each slot is defined once per sample  [in: '{x} and {x}']
examples/dirty-locale/locale/en-US/single_branch.intent: error: single-branch group (button): a group must offer a choice between at least two branches  [in: 'press (button)']
examples/dirty-locale/locale/en-US/unbalanced.intent: error: unbalanced metacharacters in template 'turn (on|off the lights'  [in: 'turn (on|off the lights']
examples/dirty-locale/locale/english: warning: directory name 'english' is not a BCP-47 language tag

10 error(s), 4 warning(s)
$ echo $?
1
```

The command exits non-zero because there are errors. With `--strict` it would
also exit non-zero on the warnings alone.

### Findings, by rule

| File | Severity | Rule |
|------|----------|------|
| `stray.intent` | warning | a resource file must live inside a `<lang>/` directory (OVOS-INTENT-2 §2) |
| `english/` | warning | a language directory is named with a BCP-47 tag (§2) |
| `old.rx` | warning | `.rx` is a legacy type, not one of the five OVOS-INTENT-2 roles |
| `Bad-Name.intent` | warning | file names are lowercase |
| `unbalanced.intent` | error | unbalanced metacharacters (OVOS-INTENT-1 §3.6) |
| `single_branch.intent` | error | a group must have at least two branches (§3.6) |
| `adjacent.intent` | error | a literal word must separate two slots (§3.6) |
| `repeat.intent` | error | a slot name appears once per sample (§3.6) |
| `empty.voc` | error | every file contributes at least one template (OVOS-INTENT-2 §5) |
| `colors.voc` | error | `.voc` is slot-free — no named slots (§4.3) |
| `Bad-Name.intent` | error | base name charset: lowercase letters, digits, underscores (§2) |
| `2nd.entity` | error | an `.entity` base name names a slot — no leading digit (§3.4) |
| `refs.intent` | error | `<name>` must resolve to a known vocabulary (§3.7) |
| `sub1`+`sub2/menu.intent` | error | `(role, base name)` is unique per language tree (§2) |
