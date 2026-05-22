"""Rendering dialog — OVOS-INTENT-2 §4.2.

Shows the stateless `render()` function and the stateful, multilingual
`DialogRenderer`. A seeded `random.Random` makes the output reproducible.
Run: `python examples/render_dialog.py`
"""
import random
from pathlib import Path

from ovos_spec_tools import DialogRenderer, LocaleResources, render

locale = Path(__file__).parent / "skill-locale" / "locale"
resources = LocaleResources(str(locale))

# The stateless function: pick a phrase, expand its variety, fill the slots.
phrases = resources.load_dialog("weather", "en-US")
print("render() — stateless:")
print("  ", render(phrases, slots={"temperature": 21}, rng=random.Random(1)))

# The stateful renderer is multilingual — the language is given per render()
# call — and avoids repeating the phrase it chose last (per language).
print("\nDialogRenderer — repetition avoidance:")
renderer = DialogRenderer(resources, "weather", rng=random.Random(1))
for _ in range(3):
    print("  ", renderer.render("en-US", {"temperature": 21}))

# Default slots are set once and reused; `.entity` fills anything left over.
# `agenda.dialog` has a {weekday} slot and weekday.entity supplies the values.
print("\nDialogRenderer — .entity fallback:")
agenda = DialogRenderer(resources, "agenda", rng=random.Random(2))
print("   no slots passed:", agenda.render("en-US"))  # {weekday} from .entity
