# 1. Getting started

## What this package is

OVOS skills ship plain-text resource files: sentence templates,
vocabularies, and spoken-response phrases, grouped by language under a
`locale/` folder. Several
OVOS components each grew their own code to parse and expand those files, and
the copies drifted: the same template could expand differently depending on
which copy ran.

`ovos-spec-tools` is the **one conformant implementation** of that machinery,
matching the formal specifications. Depend on it instead of rolling your own.

## Install

```bash
pip install ovos-spec-tools            # core — no dependencies
pip install ovos-spec-tools[langcodes] # adds the smart language fallback
```

The core package has **no dependencies**. The optional `langcodes` extra
improves only one thing: how a missing language falls back to a near one
(see [Language matching](language-matching.md)); everything else works without
it.

Requires Python 3.8 or newer.

## A first taste

Every tool is one import away. The four snippets below are the whole package
in miniature; the later chapters go deep on each.

### Expand a template

A *template* describes many sentences at once. `expand()` enumerates them:

```python
from ovos_spec_tools import expand

expand("(turn|switch) [the] (light|fan)")
# ['turn the light', 'switch the light', 'turn light', 'switch light',
#  'turn the fan', 'switch the fan', 'turn fan', 'switch fan']
```

→ [Sentence templates](templates.md)

### Load a skill's locale folder

`LocaleResources` reads the resource files under `locale/<lang>/`:

```python
from ovos_spec_tools import LocaleResources

res = LocaleResources("my-skill/locale")
res.load_intent("play", "en-US")     # the expanded training samples
res.load_dialog("weather", "en-US")  # the spoken-response phrases
```

→ [Locale resources](locale-resources.md)

### Render a spoken response

`render()` picks one phrase from a `.dialog` and fills its slots:

```python
from ovos_spec_tools import render

render(res.load_dialog("weather", "en-US"), slots={"temperature": 21})
# 'It is 21 degrees.'
```

→ [Dialog](dialog.md)

### Match a language tag

`closest_lang()` finds the nearest available language:

```python
from ovos_spec_tools import closest_lang

closest_lang("en-AU", ["pt-BR", "en-US", "de-DE"])   # 'en-US'
```

→ [Language matching](language-matching.md)

### Construct a bus message

`Message` is the JSON envelope OVOS components exchange:

```python
from ovos_spec_tools import Message

m = Message("ovos.intent.list", {}, {"source": "skill.id"})
res = m.response({"intents": ["..."]})   # 'ovos.intent.list.response'
```

→ [Bus messages](message.md)

### Lint a locale folder

From the command line:

```bash
ovos-spec-lint my-skill/locale
```

→ [Linting](linting.md)

## Where to next

Continue with [Sentence templates](templates.md): the grammar is the
foundation the resource loader and the dialog renderer both build on.

---
[Home](README.md) · [Sentence templates →](templates.md)
