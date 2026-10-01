"""Expanding sentence templates — OVOS-INTENT-1.

`expand()` turns a template into its sample set. Run: `python examples/expand.py`
"""
from ovos_spec_tools import MalformedTemplate, expand

# Alternatives and optionals expand to every combination.
print("worked example:")
for sample in sorted(expand("(turn|switch) [the] (light|fan)")):
    print("  ", sample)

# Named slots are opaque — carried through, never expanded.
print("\nnamed slots are opaque:")
print("  ", expand("(play|put on) {query}"))

# `<name>` references expand a named vocabulary in place.
print("\ninline vocabulary reference:")
vocabularies = {"greeting": ["hello", "hi", "hey"]}
print("  ", expand("<greeting> [there] {name}", vocabularies))

# Malformed templates (OVOS-INTENT-1 §3.6) are rejected.
print("\nmalformed templates are rejected:")
for bad in ["turn (on|off the lights", "press (button)", "{a}{b}"]:
    try:
        expand(bad)
    except MalformedTemplate as error:
        print(f"   {bad!r} -> {error}")
