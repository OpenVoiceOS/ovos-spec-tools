"""Loading a skill's locale resources — OVOS-INTENT-2.

`LocaleResources` discovers and loads the five resource roles from a
`locale/<lang>/` tree. One instance serves every language: the language is a
parameter of each load call. Run: `python examples/load_resources.py`
"""
from pathlib import Path

from ovos_spec_tools import LocaleResources

locale = Path(__file__).parent / "skill-locale" / "locale"
resources = LocaleResources(str(locale))

# `.intent` — loaded as its sample set, named slots intact.
print("play.intent samples (en-US):")
for sample in resources.load_intent("play", "en-US"):
    print("  ", sample)

# `.intent` using a `<greeting>` reference — the .voc is resolved automatically.
print("\ngreet.intent samples (uses <greeting>):")
for sample in resources.load_intent("greet", "en-US"):
    print("  ", sample)

# `.voc` — a slot-free vocabulary, loaded as its expanded phrase set.
print("\ngreeting.voc:", resources.load_vocabulary("greeting", "en-US"))

# `.entity` — a value set.
print("weekday.entity:", resources.load_entity("weekday", "en-US"))

# `.dialog` — loaded as raw phrase strings, NOT expanded (expansion is
# per-render; see render_dialog.py).
print("\nweather.dialog phrases:")
for phrase in resources.load_dialog("weather", "en-US"):
    print("  ", phrase)
