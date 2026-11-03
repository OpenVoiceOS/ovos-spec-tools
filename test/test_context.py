import time
import unittest

from ovos_spec_tools.context import (
    gate_satisfied, context_supplied_slots, context_slot_candidates,
    normalize_declaration, resolve_key, is_live, prune, decrement, enforce_cap,
)


class TestGating(unittest.TestCase):
    def _ctx(self, **kw):
        return {k: (v if isinstance(v, dict) else {"value": v}) for k, v in kw.items()}

    def test_requires_private_scope(self):
        ctx = {"lights.skill:kitchen": {"value": "kitchen", "turns_remaining": 2}}
        self.assertTrue(gate_satisfied(ctx, ["kitchen"], None, "lights.skill"))
        # a different owner's private key does not satisfy
        self.assertFalse(gate_satisfied(ctx, ["kitchen"], None, "other.skill"))

    def test_requires_shared_scope(self):
        ctx = {"kitchen": {"value": "kitchen"}}
        self.assertTrue(gate_satisfied(ctx, [{"key": "kitchen", "scope": "shared"}], None, "x"))
        # private lookup of the same name misses the shared entry
        self.assertFalse(gate_satisfied(ctx, ["kitchen"], None, "x"))

    def test_excludes_blocks(self):
        ctx = {"x:modal": {"value": None}}
        self.assertFalse(gate_satisfied(ctx, None, ["modal"], "x"))
        self.assertTrue(gate_satisfied({}, None, ["modal"], "x"))

    def test_missing_required_fails(self):
        self.assertFalse(gate_satisfied({}, ["kitchen"], None, "x"))

    def test_malformed_requires_never_satisfied(self):
        self.assertFalse(gate_satisfied({}, [{"bad": 1}], None, "x"))

    def test_dead_entry_not_satisfying(self):
        ctx = {"x:k": {"value": "v", "turns_remaining": 0}}
        self.assertFalse(gate_satisfied(ctx, ["k"], None, "x"))


class TestLiveness(unittest.TestCase):
    def test_turns(self):
        self.assertTrue(is_live({"value": "v"}))
        self.assertTrue(is_live({"value": "v", "turns_remaining": 1}))
        self.assertFalse(is_live({"value": "v", "turns_remaining": 0}))

    def test_expiry(self):
        self.assertFalse(is_live({"value": "v", "expires_at": time.time() - 1}))
        self.assertTrue(is_live({"value": "v", "expires_at": time.time() + 100}))


class TestScope(unittest.TestCase):
    def test_resolve(self):
        self.assertEqual(resolve_key("k", "private", "s"), "s:k")
        self.assertEqual(resolve_key("k", "shared", None), "k")
        self.assertIsNone(resolve_key("k", "private", None))

    def test_normalize(self):
        self.assertEqual(normalize_declaration("k"), {"key": "k", "scope": "private"})
        self.assertEqual(normalize_declaration({"key": "k", "scope": "shared"}),
                         {"key": "k", "scope": "shared"})
        self.assertIsNone(normalize_declaration({"nope": 1}))


class TestSlotFill(unittest.TestCase):
    def test_context_fills_unfilled_slot(self):
        ctx = {"x:room": {"value": "kitchen"}}
        got = context_supplied_slots(ctx, ["room"], ["room"], "x", filled_slots={})
        self.assertEqual(got, {"room": "kitchen"})

    def test_utterance_wins(self):
        ctx = {"x:room": {"value": "kitchen"}}
        got = context_supplied_slots(ctx, ["room"], ["room"], "x", filled_slots={"room": "hall"})
        self.assertEqual(got, {})

    def test_gated_only_key_not_a_slot(self):
        ctx = {"x:flag": {"value": "v"}}
        got = context_supplied_slots(ctx, ["flag"], ["room"], "x", filled_slots={})
        self.assertEqual(got, {})


class TestDecay(unittest.TestCase):
    def test_prune_removes_dead(self):
        ctx = {"a": {"value": "v", "turns_remaining": 0}, "b": {"value": "w"}}
        prune(ctx)
        self.assertNotIn("a", ctx)
        self.assertIn("b", ctx)

    def test_prune_is_in_place_and_returns_map(self):
        ctx = {"dead": {"value": "b", "turns_remaining": 0}}
        out = prune(ctx)
        self.assertIs(out, ctx)
        self.assertEqual(ctx, {})

    def test_decrement(self):
        ctx = {"a": {"value": "v", "turns_remaining": 2}}
        decrement(ctx)
        self.assertEqual(ctx["a"]["turns_remaining"], 1)

    def test_turns_one_lives_exactly_next_round(self):
        # §4: turns_remaining 1 is live for the next match round, gone after
        ctx = {"k": {"value": None, "turns_remaining": 1}}
        prune(ctx)
        self.assertIn("k", ctx)
        decrement(ctx)
        prune(ctx)
        self.assertNotIn("k", ctx)

    def test_decrement_only_keys_skips_midispatch(self):
        # §4.1: an entry synced mid-dispatch is not decremented this turn
        ctx = {"old": {"value": None, "turns_remaining": 1}}
        pre = set(ctx.keys())
        ctx["new"] = {"value": None, "turns_remaining": 1}
        decrement(ctx, only_keys=pre)
        self.assertEqual(ctx["old"]["turns_remaining"], 0)
        self.assertEqual(ctx["new"]["turns_remaining"], 1)

    def test_decrement_leaves_untimed_entries(self):
        ctx = {"perm": {"value": "x"}}
        decrement(ctx)
        self.assertNotIn("turns_remaining", ctx["perm"])

    def test_enforce_cap(self):
        ctx = {f"k{i}": {"value": i} for i in range(10)}
        enforce_cap(ctx, max_entries=5)
        self.assertLessEqual(len(ctx), 5)

    def test_cap_evicts_entry_closest_to_expiry(self):
        ctx = {"near": {"value": "x", "turns_remaining": 1},
               "far": {"value": "y", "turns_remaining": 99},
               "perm": {"value": "z"}}
        enforce_cap(ctx, max_entries=2)
        self.assertEqual(len(ctx), 2)
        self.assertNotIn("near", ctx)

    def test_cap_noop_under_limit(self):
        ctx = {"a": {"value": "1"}, "b": {"value": "2"}}
        enforce_cap(ctx, max_entries=10)
        self.assertEqual(set(ctx.keys()), {"a", "b"})


if __name__ == "__main__":
    unittest.main()


class TestSlotCandidates(unittest.TestCase):
    def test_candidate_for_declared_slot(self):
        ctx = {"x:room": {"value": "kitchen"}}
        got = context_slot_candidates(ctx, ["room"], "x")
        self.assertEqual(got, {"room": "kitchen"})

    def test_no_candidate_for_slot_without_entry(self):
        ctx = {"x:flag": {"value": "v"}}
        self.assertEqual(context_slot_candidates(ctx, ["room"], "x"), {})

    def test_no_candidate_for_flag_value(self):
        ctx = {"x:room": {"value": None}}
        self.assertEqual(context_slot_candidates(ctx, ["room"], "x"), {})

    def test_dead_entry_not_a_candidate(self):
        ctx = {"x:room": {"value": "kitchen", "turns_remaining": 0}}
        self.assertEqual(context_slot_candidates(ctx, ["room"], "x"), {})

    def test_shared_entry_resolved_without_declaration(self):
        ctx = {"person": {"value": "Bob"}}
        self.assertEqual(context_slot_candidates(ctx, ["person"], "bio.skill"),
                         {"person": "Bob"})

    def test_private_takes_precedence_over_shared(self):
        ctx = {"bio.skill:person": {"value": "Alice"}, "person": {"value": "Bob"}}
        self.assertEqual(context_slot_candidates(ctx, ["person"], "bio.skill"),
                         {"person": "Alice"})
