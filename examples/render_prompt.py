"""Rendering prompts — OVOS-INTENT-2 §4.4.

Shows the stateless `render_prompt()` and the resource-backed `PromptRenderer`.
A `.prompt` is whole-file plain text: only the double-brace `{{name}}` form is
a substitution point. Single-brace `{name}`, literal JSON braces, unfilled
slots, and fenced code blocks are all left untouched.
Run: `python examples/render_prompt.py`
"""
from pathlib import Path

from ovos_spec_tools import LocaleResources, PromptRenderer, render_prompt

locale = Path(__file__).parent / "skill-locale" / "locale"
resources = LocaleResources(str(locale))

# The stateless function over an explicit prompt string. Only `{{assistant}}`
# and `{{query}}` are supplied — the literal JSON single braces and the
# `{{example}}` inside the fenced code block are left exactly as written.
text = resources.load_prompt("system", "en-US")
print("render_prompt() — only the supplied slots are filled:\n")
print(render_prompt(text, {"assistant": "OVOS", "query": "what time is it"}))

# The resource-backed renderer: the language is given per call, and default
# slots set once are reused on every call.
print("\nPromptRenderer — default {{assistant}}, {{query}} per call:\n")
renderer = PromptRenderer(resources, "system", slots={"assistant": "OVOS"})
print(renderer.render("en-US", {"query": "set a five minute timer"}))
