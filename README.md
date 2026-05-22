# ovos-spec-tools

Reference implementation of the OVOS [formal
specifications](https://github.com/OpenVoiceOS/architecture) — the
low-level, dependency-light primitives those specifications describe.

OVOS components reimplement template expansion, resource loading, and language
matching in several places, and the copies drift. This package is the single
conformant implementation those components — and any third-party tool — can
depend on.

## Status

| Tool | Spec | Code |
|------|------|-------|
| Sentence template expander | OVOS-INTENT-1 v2 | `expansion.py` |
| Locale resource loader | OVOS-INTENT-2 |  `resources.py`  |
| Dialog renderer | OVOS-INTENT-2 §4.2 |  `dialog.py`  |
| Language-tag matching | OVOS-INTENT-2 §2.2 |  `language.py` |
| `ovos-spec-lint` locale linter | OVOS-INTENT-1 / -2 |  `lint.py`  |

## Install

```bash
pip install ovos-spec-tools            # core — no dependencies
pip install ovos-spec-tools[langcodes] # adds the smart language fallback
```

Requires Python 3.8+.

## Quick taste

```python
from ovos_spec_tools import expand, LocaleResources, render, closest_lang

expand("(turn|switch) [the] light")          # all 4 sentences it denotes
res = LocaleResources("my-skill/locale")
res.load_intent("play", "en-US")             # a skill's intent samples
render(res.load_dialog("weather", "en-US"),  # a spoken response
       slots={"temperature": 21})
closest_lang("en-AU", ["pt-BR", "en-US"])    # 'en-US'
```

```bash
ovos-spec-lint my-skill/locale               # validate a locale folder
```

## Documentation

A zero-to-hero guide lives in [`docs/`](docs/README.md):

1. [Getting started](docs/getting-started.md) — install, and a first taste of
   every tool.
2. [Sentence templates](docs/templates.md) — the grammar: alternatives,
   optionals, slots, vocabulary references, malformed forms.
3. [Locale resources](docs/locale-resources.md) — the `locale/` folder, the
   five file roles, loading across languages, override precedence.
4. [Dialog](docs/dialog.md) — choosing and filling a spoken response.
5. [Language matching](docs/language-matching.md) — tag standardization,
   distance, and closest-match resolution.
6. [Linting](docs/linting.md) — validating a locale folder, on the CLI or in CI.
7. [API reference](docs/api-reference.md) — every public name, in brief.

Runnable example scripts are in [`examples/`](examples/README.md).

## Credits

This package was produced as part of a documentation and interoperability
effort for OpenVoiceOS, funded by NLnet's
[NGI0 Commons Fund](https://nlnet.nl/project/OpenVoiceOS) under grant
agreement No [101135429](https://cordis.europa.eu/project/id/101135429).

![NGI0 / NLnet](./ngi.png)

## License

Apache 2.0
