"""SessionManager (singleton registry) + forward/reply session stamping.

SessionManager is an implementation detail enforcing the OVOS-SESSION-1 §4
value-passing contract; these tests pin its core invariants.
"""
import unittest

from ovos_spec_tools.session import Session, SessionManager
from ovos_spec_tools.message import Message


class TestSessionManagerRegistry(unittest.TestCase):
    def setUp(self):
        SessionManager.sessions = {}
        SessionManager.default_session = None

    def test_one_live_object_per_id(self):
        a = SessionManager.update(Session("s1"))
        b = SessionManager.get(Message("x", context={"session": {"session_id": "s1"}}))
        self.assertIs(a, b)  # same live object, folded not replaced

    def test_held_reference_observes_later_fold(self):
        held = SessionManager.update(Session("s2"))
        # a later snapshot for the same id is folded onto the held object
        snap = {"session_id": "s2", "active_handlers": [{"skill_id": "k", "activated_at": 1.0}]}
        SessionManager.get(Message("x", context={"session": snap}))
        self.assertEqual([h["skill_id"] for h in held.active_handlers], ["k"])

    def test_default_folds_like_any_session(self):
        # the default session is a normal session per §4 — no owner-only
        # reservation; a message carrying it folds onto the live default.
        d = SessionManager.get_default_session()
        SessionManager.get(Message("x", context={"session": {"session_id": "default",
                                                             "lang": "pt-PT"}}))
        self.assertEqual(d.lang, "pt-PT")
        self.assertIs(d, SessionManager.get_default_session())


class TestForwardReplyStamping(unittest.TestCase):
    def setUp(self):
        SessionManager.sessions = {}
        SessionManager.default_session = None

    def test_forward_refreshes_to_live_session(self):
        # get -> mutate -> forward: the derived message carries the live state,
        # not the originating message's pre-mutation snapshot.
        live = SessionManager.update(Session("123"))
        live.add_active_handler("my.skill")
        orig = Message("utt", context={"session": {"session_id": "123"}})
        fwd = orig.forward("my.skill.activate")
        ah = fwd.context["session"]["active_handlers"]
        self.assertEqual([h["skill_id"] for h in ah], ["my.skill"])

    def test_reply_refreshes_to_live_session(self):
        live = SessionManager.update(Session("123"))
        live.add_active_handler("my.skill")
        orig = Message("ask", context={"session": {"session_id": "123"},
                                       "source": "A", "destination": "B"})
        rep = orig.reply("ask.response")
        ah = rep.context["session"]["active_handlers"]
        self.assertEqual([h["skill_id"] for h in ah], ["my.skill"])
        # §5.2 routing still reversed
        self.assertEqual(rep.context["source"], "B")
        self.assertEqual(rep.context["destination"], "A")

    def test_reply_with_explicit_session_not_stamped(self):
        # an author-supplied session via context= is honoured, not refreshed
        live = SessionManager.update(Session("123"))
        live.add_active_handler("live.skill")
        orig = Message("ask", context={"session": {"session_id": "123"}})
        rep = orig.reply("ask.response",
                         context={"session": {"session_id": "123",
                                              "lang": "explicit"}})
        self.assertEqual(rep.context["session"], {"session_id": "123",
                                                  "lang": "explicit"})

    def test_reply_without_explicit_session_is_stamped(self):
        live = SessionManager.update(Session("123"))
        live.add_active_handler("live.skill")
        orig = Message("ask", context={"session": {"session_id": "123"},
                                       "source": "A"})
        # context= overrides routing only -> session still refreshed
        rep = orig.reply("ask.response", context={"destination": "X"})
        ah = rep.context["session"]["active_handlers"]
        self.assertEqual([h["skill_id"] for h in ah], ["live.skill"])

    def test_unowned_id_left_untouched(self):
        # a session id this process never folded is carried verbatim (§5)
        snap = {"session_id": "remote", "active_handlers": []}
        fwd = Message("u", context={"session": dict(snap)}).forward("x")
        self.assertEqual(fwd.context["session"], snap)

    def test_session_less_message_stays_session_less(self):
        fwd = Message("u", context={}).forward("x")
        self.assertNotIn("session", fwd.context)

    def test_idless_session_normalizes_to_default(self):
        # §4.1/§4.3: a session that names no id IS the default session.
        SessionManager.get_default_session().add_active_handler("d.skill")
        fwd = Message("u", context={"session": {"lang": "en-US"}}).forward("x")
        self.assertEqual(fwd.context["session"]["session_id"], "default")

    def test_stamp_is_noop_when_nothing_changed(self):
        # no intervening update -> stamp re-serializes the same state
        live = SessionManager.update(Session("123"))
        live.add_active_handler("a")
        orig = Message("u", context={"session": live.to_dict()})
        fwd = orig.forward("x")
        self.assertEqual([h["skill_id"] for h in fwd.context["session"]["active_handlers"]],
                         ["a"])


if __name__ == "__main__":
    unittest.main()
