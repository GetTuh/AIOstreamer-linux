import unittest

from jellyfin_tv.tests.helpers import app
from jellyfin_tv.inhibit import SleepInhibitor


class FakeBackend:
    def __init__(self, fail=False):
        self.log = []
        self.fail = fail
        self.next = 0

    def inhibit(self, reason):
        if self.fail:
            raise RuntimeError("no bus")
        self.next += 1
        self.log.append(("inhibit", self.next))
        return self.next

    def uninhibit(self, cookie):
        self.log.append(("uninhibit", cookie))


class SleepInhibitorTest(unittest.TestCase):
    def setUp(self):
        app()
        self.backend = FakeBackend()
        self.inhibitor = SleepInhibitor(self.backend)

    def test_inhibits_once_while_any_player_plays(self):
        for _ in range(3):
            self.inhibitor.hold("a", True)
            self.inhibitor.hold("b", True)
            self.inhibitor.hold("a", False)
            self.assertTrue(self.inhibitor.active)
            self.inhibitor.hold("b", False)
            self.assertFalse(self.inhibitor.active)
        self.assertEqual(self.backend.log, [("inhibit", 1), ("uninhibit", 1), ("inhibit", 2), ("uninhibit", 2),
                                            ("inhibit", 3), ("uninhibit", 3)])

    def test_repeated_release_is_harmless(self):
        self.inhibitor.hold("a", False)
        self.inhibitor.hold("a", True)
        self.inhibitor.hold("a", False)
        self.inhibitor.hold("a", False)
        self.assertEqual(self.backend.log, [("inhibit", 1), ("uninhibit", 1)])

    def test_release_all_on_shutdown(self):
        self.inhibitor.hold("a", True)
        self.inhibitor.hold("b", True)
        self.inhibitor.release_all()
        self.assertFalse(self.inhibitor.active)
        self.assertEqual(self.backend.log[-1], ("uninhibit", 1))

    def test_missing_bus_does_not_raise(self):
        inhibitor = SleepInhibitor(FakeBackend(fail=True))
        inhibitor.hold("a", True)
        self.assertFalse(inhibitor.active)
        inhibitor.hold("a", False)


if __name__ == "__main__":
    unittest.main()
