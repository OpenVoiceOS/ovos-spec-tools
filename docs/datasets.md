# 7. HuggingFace datasets

The `datasets` module loads OVOS-INTENT-2 templates from three HuggingFace
datasets, expands them into concrete utterances, and exports them to a standard
locale directory tree.

```python
from ovos_spec_tools.datasets import (
    load_dataset_templates,
    expand_hf_template,
    export_to_locale,
    SUPPORTED_DATASETS,
)
```

This module requires the optional `datasets` extra:

```bash
pip install ovos-spec-tools[datasets]
```

It is optional because the core library has zero runtime dependencies by design.

---

## 7.1 Supported datasets

| Short name | HF repo | Configs | Rows per config | Template style |
|------------|---------|---------|-----------------|----------------|
| `hassil-intents` | `OpenVoiceOS/hass-intent-templates` | per-language (`en`, `pt_BR`, …) | ~2–21k | full OVOS syntax with `<keyword>` refs + `expansions` column |
| `intents-for-eval` | `OpenVoiceOS/intents-for-eval` | `{tag}-templates` (`en-US-templates`, …) | ~1–30k | `<keyword>` inlined to `(a\|b\|c)` groups |
| `massive-templates` | `OpenVoiceOS/massive-templates` | `{tag}-templates` (`en-US-templates`, …) | ~1–100k | same style as intents-for-eval |

`SUPPORTED_DATASETS` gives you the mapping:

```python
SUPPORTED_DATASETS
# {'hassil-intents': 'OpenVoiceOS/hass-intent-templates',
#  'intents-for-eval': 'OpenVoiceOS/intents-for-eval',
#  'massive-templates': 'OpenVoiceOS/massive-templates'}
```

---

## 7.2 Loading templates

`load_dataset_templates(dataset_id, lang)` returns a list of normalized row
dicts. Every row has at least `intent_id`, `template`, and `slots`; when the
dataset carries an `expansions` column (hassil-intents only) it is preserved.

```python
# Load English hassil-intent templates
templates = load_dataset_templates("hassil-intents", lang="en")
len(templates)  # 3804

templates[0]
# {'intent_id': 'homeassistant:hass_broadcast',
#  'template': '(broadcast|announce) [everywhere] [that] {message}',
#  'slots': [{'name': 'message', 'examples': ['hello', 'dinner is ready']}],
#  'expansions': []}
```

Language tags follow the dataset's convention:

| Dataset | Example `lang` |
|---------|----------------|
| hassil-intents | `en`, `pt_BR`, `zh_CN` |
| intents-for-eval | `en-US`, `pt-PT`, or full config `en-US-templates` |
| massive-templates | same as intents-for-eval |

---

## 7.3 Expanding templates

`expand_hf_template(template, expansions=None, max_samples=2048)` resolves
`<keyword>` refs, `(a|b)` alternations, and `[x]` optionals into concrete
utterances using the same engine as `ovos_spec_tools.expansion.expand()`.

### With expansions (hassil-intents style)

When the row carries an `expansions` column, pass it in:

```python
row = templates[1]
# {'template': '<timer_cancel> all [[of ](the|my)] timers',
#  'expansions': [{'keyword': 'timer_cancel', 'values': ['cancel', 'stop']}]}

results = expand_hf_template(row["template"], row["expansions"])
# ['cancel all of the timers', 'stop all of the timers',
#  'cancel all timers', 'stop all timers',
#  'cancel all the timers']
```

### Without expansions (intents-for-eval style)

When the template already has `<keyword>` refs inlined to `(a|b|c)` groups,
omit the expansions argument:

```python
expand_hf_template("(turn on|switch on) [the] {name}")
# ['turn on the {name}', 'switch on the {name}',
#  'turn on {name}', 'switch on {name}']
```

### Safety cap

The `max_samples` parameter (default 2048) caps the output list so that a
combinatorial explosion in a template cannot fill memory.

```python
results = expand_hf_template("(a|b|c|d|e) (1|2|3|4|5) (x|y|z)",
                              max_samples=5)
len(results)  # 5
```

---

## 7.4 Exporting to a locale directory

`export_to_locale(dataset_id, lang, output_dir)` writes `.intent`, `.voc`,
and `.entity` files to `<output_dir>/locale/<lang>/`.

```python
export_to_locale("hassil-intents", lang="en", output_dir="/tmp/my-locale")
```

Produces:

```
/tmp/my-locale/locale/en/
├── hass_broadcast.intent      # template lines for this intent
├── hass_turn_on.intent
├── ...
├── timer_cancel.voc           # keyword expansions
├── area.entity                # slot example values
├── color.entity
└── ...                        # 86 files total for English
```

### Round-trip workflow

A typical pipeline loads from HF, inspects, and exports to a locale that a
skill's `LocaleResources` can consume:

```python
from ovos_spec_tools.datasets import expand_hf_template, export_to_locale
from ovos_spec_tools.resources import LocaleResources

# 1. Export HF dataset to locale directory
export_to_locale("hassil-intents", lang="en", output_dir="/tmp/locale")

# 2. Load it with the standard resource loader
resources = LocaleResources(skill_locale="/tmp/locale")

# 3. Use normally
samples = resources.load_intent("hass_turn_on", "en")
phrases = resources.vocabularies("en")
```

---

## 7.5 CLI usage

The module also runs as a command-line tool:

```bash
# Export English templates
python -m ovos_spec_tools.datasets hassil-intents en /tmp/locale

# Show expansions for the first 3 templates
python examples/hf_dataset.py hassil-intents en /tmp/locale --expand
```

```text
Loading hassil-intents (OpenVoiceOS/hass-intent-templates) / en ...
Loaded 3804 templates

--- Template expansion samples ---

  [0] intent_id=homeassistant:hass_broadcast
      template: (broadcast|announce) [everywhere] [that] {message}
      sample utterances (5 total):
        - broadcast everywhere that {message}
        - announce everywhere that {message}
        - broadcast that {message}
        - announce that {message}
        - broadcast everywhere {message}
```
