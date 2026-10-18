import unittest

from aiostreamer.tests.helpers import FakeSettings, app
from aiostreamer.app import AppController


class FakeWindow:
    def __init__(self, active=False, visible=True):
        self.active = active
        self.visible = visible
        self.requests = 0

    def isVisible(self):
        return self.visible

    def isActive(self):
        return self.active

    def raise_(self):
        pass

    def requestActivate(self):
        self.requests += 1


class ActivationTest(unittest.TestCase):
    def setUp(self):
        app()
        self.controller = AppController(FakeSettings())

    def tearDown(self):
        self.controller.shutdown()

    def test_retries_only_while_inactive(self):
        window = FakeWindow()
        self.controller._window = window
        for _ in range(3):
            self.controller._activate()
        self.assertEqual(window.requests, 3)
        window.active = True
        self.controller._activate()
        self.assertEqual(window.requests, 3)

    def test_no_activation_when_hidden(self):
        window = FakeWindow(visible=False)
        self.controller._window = window
        self.controller._activate()
        self.assertEqual(window.requests, 0)


if __name__ == "__main__":
    unittest.main()
