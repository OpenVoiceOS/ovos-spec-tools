"""Regression: SessionManager._store must tolerate same-thread re-entry.

_store folds an incoming snapshot via Session.update_from while holding the
registry lock, and update_from runs full deserialization (Session.__init__).
Any code reached during that construction can re-enter the registry on the same
thread — in the field a garbage-collected skill whose __del__ emits a deregister
message folds back through SessionManager.update while the outer fold is still in
progress. With a non-reentrant lock the thread self-deadlocks and the process
hangs until it is killed (observed as multi-minute CI job-timeout hangs that a
pytest-timeout thread cannot break, because the thread is blocked in a C-level
lock acquire).

The re-entry here stands in for that finalizer/emit path deterministically.
"""
import threading
import unittest

from ovos_spec_tools.session import Session, SessionManager


class TestStoreReentrancy(unittest.TestCase):
    def setUp(self):
        SessionManager.sessions = {}
        SessionManager.default_session = None

    def test_store_survives_same_thread_reentry(self):
        armed = {"on": False}

        class ReentrantSession(Session):
            # Reached from _store -> update_from -> deserialize -> __init__,
            # i.e. while _store already holds the registry lock. Re-enter the
            # registry exactly as a skill __del__ -> bus.emit -> on_message ->
            # SessionManager.update would.
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if armed["on"]:
                    armed["on"] = False  # fire exactly once
                    SessionManager.update(Session("default"))

        # seed the registry so the fold takes the update_from branch; keep the
        # re-entry disarmed until the seed object exists
        seed = ReentrantSession("default")
        SessionManager.sessions["default"] = seed

        done = threading.Event()

        def fold():
            armed["on"] = True
            SessionManager.update(Session("default"))
            done.set()

        worker = threading.Thread(target=fold, daemon=True)
        worker.start()
        # a non-reentrant lock deadlocks the worker here; RLock lets it complete
        self.assertTrue(
            done.wait(timeout=10),
            "SessionManager._store self-deadlocked on same-thread re-entry "
            "(registry lock is not reentrant)",
        )


if __name__ == "__main__":
    unittest.main()
