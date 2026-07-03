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

    def test_decrement(self):
        ctx = {"a": {"value": "v", "turns_remaining": 2}}
        decrement(ctx)
        self.assertEqual(ctx["a"]["turns_remaining"], 1)

    def test_enforce_cap(self):
        ctx = {f"k{i}": {"value": i} for i in range(10)}
        enforce_cap(ctx, max_entries=5)
        self.assertLessEqual(len(ctx), 5)


if __name__ == "__main__":
    unittest.main()


class TestSlotCandidates(unittest.TestCase):
    def test_candidate_for_declared_slot(self):
        ctx = {"x:room": {"value": "kitchen"}}
        got = context_slot_candidates(ctx, ["room"], ["room"], "x")
        self.assertEqual(got, {"room": "kitchen"})

    def test_no_candidate_for_gated_only_key(self):
        ctx = {"x:flag": {"value": "v"}}
        self.assertEqual(context_slot_candidates(ctx, ["flag"], ["room"], "x"), {})

    def test_no_candidate_for_flag_value(self):
        ctx = {"x:room": {"value": None}}
        self.assertEqual(context_slot_candidates(ctx, ["room"], ["room"], "x"), {})

    def test_dead_entry_not_a_candidate(self):
        ctx = {"x:room": {"value": "kitchen", "turns_remaining": 0}}
        self.assertEqual(context_slot_candidates(ctx, ["room"], ["room"], "x"), {})

    def test_shared_scope_candidate(self):
        ctx = {"person": {"value": "Bob"}}
        got = context_slot_candidates(ctx, [{"key": "person", "scope": "shared"}],
                                      ["person"], "bio.skill")
        self.assertEqual(got, {"person": "Bob"})
