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

# Default slots are set once and reused; a per-call value overrides them. A slot
# with neither raises UnfilledSlot: an `.entity` never fills a dialog slot.
print("\nDialogRenderer — default slots:")
agenda = DialogRenderer(resources, "agenda", rng=random.Random(2),
                        slots={"weekday": "Monday"})
print("   default:", agenda.render("en-US"))
print("   per call:", agenda.render("en-US", {"weekday": "Friday"}))
