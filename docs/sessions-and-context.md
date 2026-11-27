# Sessions and intent context
<!-- agent-hint
covers: the Session fields, the SessionManager store, and the OVOS-CONTEXT-1 helpers for intent context
source: ovos_spec_tools/session.py, ovos_spec_tools/context.py
generated: no
verify: python3 docs/check_page.py docs/sessions-and-context.md weather.skill:location
see: bus-namespaces.md
-->

This page tells you how a session carries its state, and how to gate, prune and age the intent context of a session with the OVOS-CONTEXT-1 helpers.

## Example

```python
from ovos_spec_tools.context import resolve_key, prune, decrement

print(resolve_key("location", "private", "weather.skill"))
print(resolve_key("location", "shared", "weather.skill"))

ctx = {"location": {"value": "Lisbon", "turns_remaining": 1},
       "old": {"value": "x", "turns_remaining": 0}}
prune(ctx)
print(sorted(ctx))
decrement(ctx)
print(ctx["location"]["turns_remaining"])
```

```text
weather.skill:location
location
['location']
0
```

## Steps

1. Resolve the key of a context entry with `resolve_key(key, scope, owner_id)`. A `private` key is `<owner_id>:<key>`. A `shared` key is the bare key. A shared entry with the same bare key does not satisfy a private gate. A private key with no owner gives `None`.
2. Before a match, call `prune(intent_context)`. It removes each entry that is not live: past its `expires_at`, or with `turns_remaining` at 0 or less.
3. After the match, call `decrement(intent_context, only_keys=...)`. Give it the set of keys that existed at the prune. An entry that a session wrote during the dispatch is then not decremented, and it stays live for the next match.
4. To fill slots from live context before a match, call `context_slot_candidates()`.

## Reference

### Session

`Session` is hashable: two sessions with the same content have the same hash. `Message` is hashable too. Besides the SESSION-1 fields, a session has these fields from other specs:

| Field | Spec | Holds |
| :--- | :--- | :--- |
| `persona_id` | OVOS-PERSONA-1 | The ID of the active persona, or `None` |
| `fallback_handlers` | OVOS-FALLBACK-1 | The ordered list of fallback handlers, or `None` |

### SessionManager

`SessionManager` is the store of the orchestrator. It is not part of a spec. It holds one session, the reserved `default` session. Each other session belongs to its client: its state arrives whole on each inbound message. The default session folds like any other session.

### Context helpers

| Function | Spec | Does |
| :--- | :--- | :--- |
| `is_live(entry)` | CONTEXT-1 §2 | Tells if an entry is live |
| `resolve_key(key, scope, owner_id)` | CONTEXT-1 §3.1 | Gives the stored key |
| `gate_satisfied(intent_context, ...)` | CONTEXT-1 §6 | Tells if the context gate of an intent is met |
| `context_slot_candidates(intent_context, ...)` | CONTEXT-1 §7 | Gives slot values from live context |
| `prune(intent_context)` | CONTEXT-1 §4 | Removes the entries that are not live |
| `decrement(intent_context, only_keys=None)` | CONTEXT-1 §4.1 | Decrements `turns_remaining` |
| `enforce_cap(intent_context, ...)` | CONTEXT-1 §2 | Limits the number of live entries, and removes the entry closest to its expiry first |

---
[← Bus messages](message.md) · [Home](index.md) · [Next →](bus-namespaces.md)
