# ovos-spec-tools
<!-- agent-hint
covers: what ovos-spec-tools is, how to install it, and where each topic is documented
source: pyproject.toml, ovos_spec_tools/__init__.py
generated: no
verify: python3 docs/check_page.py README.md
see: docs/index.md
-->

`ovos-spec-tools` is the reference implementation of the [OVOS specifications](https://github.com/OpenVoiceOS/architecture). It expands sentence templates, loads `locale/` folders, renders dialogs and prompts, matches language tags, gives the bus message envelope, and lints locale folders. OVOS components and other tools use it, so that each one does not have its own copy.

## Install

```bash
uv pip install --prerelease=allow ovos-spec-tools
```

## Quickstart

```python
from ovos_spec_tools import expand, closest_lang, Message

print(expand("(turn|switch) [the] light"))
print(closest_lang("en-AU", ["pt-BR", "en-US"]))
reply = Message("ovos.intent.list", {}, {"source": "skill.id"}).response({"intents": ["..."]})
print(reply.serialize())
```

```text
['turn the light', 'switch the light', 'turn light', 'switch light']
en-US
{"type": "ovos.intent.list.response", "data": {"intents": ["..."]}, "context": {"source": "skill.id", "destination": "skill.id"}}
```

To check a locale folder: `ovos-spec-lint my-skill/locale`.

## Documentation

| Page | What you get there |
| :--- | :--- |
| [docs/index.md](docs/index.md) | The reading order of all pages |
| [docs/templates.md](docs/templates.md) | The sentence template grammar |
| [docs/locale-resources.md](docs/locale-resources.md) | How to load a `locale/` folder |
| [docs/language-matching.md](docs/language-matching.md) | How language tags are standardized and matched |
| [docs/message.md](docs/message.md) | The bus message envelope |
| [docs/api-reference.md](docs/api-reference.md) | Each public name |

Example scripts are in [examples/](examples/README.md).

## Credits

Developed by [TigreGótico](https://tigregotico.pt) for [OpenVoiceOS](https://openvoiceos.org). Funded through the [NGI0 Commons Fund](https://nlnet.nl/commonsfund), a fund of [NLnet](https://nlnet.nl) with financial support from the European Commission's [Next Generation Internet](https://ngi.eu) programme, under grant agreement No [101135429](https://cordis.europa.eu/project/id/101135429).

[![NGI0 Commons Fund](./ngi.png)](https://nlnet.nl/project/OpenVoiceOS)

## License

Apache 2.0. See [LICENSE.md](LICENSE.md).
