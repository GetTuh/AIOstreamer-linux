import ctypes
import struct
import time
import unittest

from aiostreamer.tests.helpers import FakeSettings, app
from PySide6.QtCore import Qt

from aiostreamer import gamepad as gp
from aiostreamer.app import AppController
from aiostreamer.gamepad import AXIS_MOTION, BUTTON_DOWN, BUTTON_UP, Gamepad, decode, load_sdl

A, B, Y, DPAD_DOWN, DPAD_RIGHT = 0, 1, 3, 12, 14


def stick(pad, x=0, y=0):
    pad.handle(AXIS_MOTION, 0, gp.STICK_X, x)
    pad.handle(AXIS_MOTION, 0, gp.STICK_Y, y)


class DecodeTest(unittest.TestCase):
    def test_button_and_axis_layout(self):
        raw = bytearray(64)
        struct.pack_into("<IIiBB", raw, 0, BUTTON_DOWN, 1, 7, A, 1)
        self.assertEqual(decode(bytes(raw)), (BUTTON_DOWN, 7, A, 0))
        raw = bytearray(64)
        struct.pack_into("<IIiB", raw, 0, AXIS_MOTION, 1, 7, gp.STICK_Y)
        struct.pack_into("<h", raw, 16, -20000)
        self.assertEqual(decode(bytes(raw)), (AXIS_MOTION, 7, gp.STICK_Y, -20000))


class GamepadTest(unittest.TestCase):
    def setUp(self):
        app()
        self.pad = Gamepad()
        self.actions = []
        self.pad.action.connect(self.actions.append)

    def test_buttons(self):
        for button in (A, B, Y, DPAD_DOWN):
            self.pad.handle(BUTTON_DOWN, 0, button, 0)
            self.pad.handle(BUTTON_UP, 0, button, 0)
        self.assertEqual(self.actions, ["select", "back", "trailer", "down"])

    def test_held_direction_repeats_until_release(self):
        self.pad.handle(BUTTON_DOWN, 0, DPAD_RIGHT, 0)
        self.assertTrue(self.pad._repeat.isActive())
        for _ in range(3):
            self.pad._repeat_fire()
        self.assertEqual(self.actions, ["right"] * 4)
        self.assertEqual(self.pad._repeat.interval(), gp.REPEAT_MS)
        self.pad.handle(BUTTON_UP, 0, DPAD_RIGHT, 0)
        self.assertFalse(self.pad._repeat.isActive())

    def test_non_directions_do_not_repeat(self):
        self.pad.handle(BUTTON_DOWN, 0, A, 0)
        self.assertFalse(self.pad._repeat.isActive())

    def test_stick_fires_once_per_push_with_hysteresis(self):
        for value in (int(gp.PRESS) + 1, 30000, int(gp.RELEASE) + 1000, 32000):
            stick(self.pad, x=value)
        self.assertEqual(self.actions, ["right"])
        stick(self.pad, x=int(gp.RELEASE) - 1000)
        self.assertFalse(self.pad._repeat.isActive())
        for _ in range(3):
            stick(self.pad, x=-30000)
            stick(self.pad, x=0)
        self.assertEqual(self.actions, ["right", "left", "left", "left"])

    def test_stick_follows_dominant_axis_and_up_is_negative(self):
        stick(self.pad, x=20000, y=-30000)
        self.assertEqual(self.actions[-1], "up")
        for _ in range(3):
            stick(self.pad, x=22000, y=-30000)
        self.assertEqual(self.actions[-1], "up")
        self.assertEqual(self.actions.count("up"), 1)

    def test_slight_diagonal_keeps_direction(self):
        for y in (0, 15000, 20000, 25000):
            stick(self.pad, x=30000, y=y)
        self.assertEqual(self.actions, ["right"])

    def test_stick_flip_switches_direction(self):
        stick(self.pad, y=30000)
        stick(self.pad, y=-30000)
        self.assertEqual(self.actions, ["down", "up"])

    def test_missing_sdl_is_harmless(self):
        pad = Gamepad()
        pad._sdl = None
        gp_load = gp.load_sdl
        gp.load_sdl = lambda: None
        try:
            self.assertFalse(pad.start())
        finally:
            gp.load_sdl = gp_load
        pad.poll()
        pad.stop()


@unittest.skipIf(load_sdl() is None, "SDL2 not installed")
class VirtualControllerTest(unittest.TestCase):
    def test_real_sdl_events_from_virtual_pad(self):
        app()
        sdl = load_sdl()
        pad = Gamepad(sdl=sdl)
        actions = []
        pad.action.connect(actions.append)
        self.assertTrue(pad.start())
        self.addCleanup(pad.stop)
        sdl.SDL_JoystickAttachVirtual.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        sdl.SDL_JoystickSetVirtualButton.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint8]
        sdl.SDL_JoystickSetVirtualAxis.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int16]
        index = sdl.SDL_JoystickAttachVirtual(1, 6, 15, 0)
        self.assertGreaterEqual(index, 0)
        self.addCleanup(lambda: sdl.SDL_JoystickDetachVirtual(index))
        before = len(pad.names)
        pad.poll()
        self.assertGreater(len(pad.names), before)
        handle = [h for h, (_, name) in pad._controllers.items()][-1]
        joystick = sdl.SDL_GameControllerGetJoystick(handle)

        def settle():
            deadline = time.monotonic() + 0.3
            while time.monotonic() < deadline:
                pad.poll()
                time.sleep(0.01)

        for button in (A, B):
            sdl.SDL_JoystickSetVirtualButton(joystick, button, 1)
            settle()
            sdl.SDL_JoystickSetVirtualButton(joystick, button, 0)
            settle()
        sdl.SDL_JoystickSetVirtualAxis(joystick, gp.STICK_X, 32000)
        settle()
        sdl.SDL_JoystickSetVirtualAxis(joystick, gp.STICK_X, 0)
        settle()
        self.assertEqual(actions[:3], ["select", "back", "right"])


class FakeWindow:
    def __init__(self, active):
        self.active = active
        self.activations = 0

    def isActive(self):
        return self.active

    def isVisible(self):
        return True

    def raise_(self):
        pass

    def requestActivate(self):
        self.activations += 1


class RoutingTest(unittest.TestCase):
    def setUp(self):
        app()
        self.settings = FakeSettings()
        self.controller = AppController(self.settings)
        self.pressed = []
        self.mpv_keys = []
        self.controller.press = lambda key, text="": self.pressed.append((key, text))
        self.controller.player.press_key = self.mpv_keys.append

    def tearDown(self):
        self.controller.shutdown()

    def test_focused_app_gets_qt_keys(self):
        self.controller._window = FakeWindow(active=True)
        for action in ("down", "select", "back", "trailer"):
            self.controller.gamepad_action(action)
        self.assertEqual(self.pressed, [(Qt.Key_Down, ""), (Qt.Key_Return, "\r"), (Qt.Key_Escape, ""), (Qt.Key_T, "t")])

    def test_playback_gets_mpv_keys(self):
        self.controller._window = FakeWindow(active=False)
        self.controller.player._active = {"player": None}
        try:
            for action in ("left", "select", "back", "trailer"):
                self.controller.gamepad_action(action)
        finally:
            self.controller.player._active = None
        self.assertEqual(self.mpv_keys, ["LEFT", "ENTER", "ESC"])
        self.assertEqual(self.pressed, [])

    def test_unfocused_app_ignores_pad(self):
        self.controller._window = FakeWindow(active=False)
        for _ in range(3):
            self.controller.gamepad_action("select")
        self.assertEqual(self.pressed, [])

    def test_right_after_playback_the_pad_reaches_the_app(self):
        window = FakeWindow(active=False)
        self.controller._window = window
        self.controller._playback_ended_at = time.monotonic()
        self.controller.gamepad_action("down")
        self.assertEqual(self.pressed, [(Qt.Key_Down, "")])
        self.assertEqual(window.activations, 1)
        self.controller._playback_ended_at = time.monotonic() - gp_after()
        self.controller.gamepad_action("down")
        self.assertEqual(len(self.pressed), 1)

    def test_setting_off(self):
        self.controller._window = FakeWindow(active=True)
        self.settings.set("gamepad", False)
        self.controller.gamepad_action("select")
        self.assertEqual(self.pressed, [])


def gp_after():
    from aiostreamer.app import GAMEPAD_AFTER_PLAYBACK_S
    return GAMEPAD_AFTER_PLAYBACK_S + 1


if __name__ == "__main__":
    unittest.main()
