"""Rendering dialog — OVOS-INTENT-2 §4.2.

Shows the stateless `render()` function and the stateful `DialogRenderer`.
A seeded `random.Random` is used so the output is reproducible.
Run: `python examples/render_dialog.py`
"""
import random
from pathlib import Path

from ovos_spec_tools import DialogRenderer, LocaleResources, render

locale = Path(__file__).parent / "skill-locale" / "locale"
resources = LocaleResources("en-US", str(locale))
phrases = resources.load_dialog("weather")

# The stateless function: pick a phrase, expand its variety, fill the slots.
print("render() — stateless:")
print("  ", render(phrases, slots={"temperature": 21}, rng=random.Random(1)))

# The stateful renderer avoids repeating the phrase it chose last time.
print("\nDialogRenderer — repetition avoidance:")
renderer = DialogRenderer(phrases, rng=random.Random(1))
for _ in range(3):
    print("  ", renderer.render({"temperature": 21}))

# Default slots are set once and reused; `.entity` fills anything left over.
# `agenda.dialog` has a {weekday} slot and weekday.entity supplies the values.
print("\nDialogRenderer — default slots + .entity fallback:")
agenda = DialogRenderer.from_resources(resources, "agenda", rng=random.Random(2))
print("   no slots passed:", agenda.render())  # {weekday} filled from .entity
