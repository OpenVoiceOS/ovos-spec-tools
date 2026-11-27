# Keyword intents
<!-- agent-hint
covers: how to build an OVOS-INTENT-4 keyword intent with IntentBuilder, and how to test an utterance against a .voc file with voc_match
source: ovos_spec_tools/intent.py
generated: no
verify: python3 docs/check_page.py docs/intents.md weather.skill
see: linting.md
-->

This page tells you how to describe a keyword intent with no intent engine installed, and how to test an utterance against a vocabulary file.

## Example

```python
from ovos_spec_tools import IntentBuilder

intent = IntentBuilder("WeatherIntent").require("weather").optionally("location").build()
print(intent.to_keyword_payload("weather.skill"))
```

```text
{'skill_id': 'weather.skill', 'intent_name': 'WeatherIntent', 'required': [{'name': 'weather'}], 'optional': [{'name': 'location'}], 'one_of': [], 'excluded': []}
```

## Steps

1. Start an `IntentBuilder` with the intent name.
2. Add the vocabularies: `require()`, `optionally()`, `one_of()` and `exclude()`.
3. Call `build()`. It gives an `Intent`. A malformed intent raises `MalformedIntent`.
4. Call `intent.to_keyword_payload(skill_id)` to get the OVOS-INTENT-4 registration payload. An engine reads this payload. `open_intent_envelope(message)` reads it back from a bus message.
5. To test an utterance against one `.voc` file, call `voc_match(utterance, voc_name, lang, locale)`. It matches whole words: the sample `yes` matches "yes, please" and does not match "yesterday". Pass `exact=True` to match the full utterance.
6. For an engine that cannot read `.voc` files, `inline_keywords(template, vocabularies)` writes each `<name>` reference as an alternative group, such as `(a|b|c)`.

## Reference

| Name | Does |
| :--- | :--- |
| `IntentBuilder` | Builds an `Intent` from the names of vocabularies |
| `Intent.validate()` | Raises `MalformedIntent` when the intent is not valid |
| `Intent.to_keyword_payload(skill_id)` | Gives the registration payload |
| `open_intent_envelope(message)` | Reads an `Intent` from a registration message |
| `voc_match(utterance, voc_name, lang, locale)` | Tells if the utterance holds a sample of the `.voc` file |
| `validate_typed_slots(typed_slots)` | Raises `MalformedTypedSlots` when a typed slot value is not valid |
| `drop_unregistered_typed_slots(...)` | Removes each key that OVOS-INTENT-1 §5.6 does not register, and each type with no entries, from `typed_slots` |

`Intent.validate()` applies the structural rules of OVOS-INTENT-3 §4.2.

---
[← Bus namespaces](bus-namespaces.md) · [Home](index.md) · [Next →](linting.md)
