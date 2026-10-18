import ctypes
import ctypes.util
import logging
import struct

from PySide6.QtCore import QObject, QTimer, Signal

log = logging.getLogger("aiostreamer.gamepad")

INIT_FLAGS = 0x200 | 0x2000
AXIS_MOTION, BUTTON_DOWN, BUTTON_UP, DEVICE_ADDED, DEVICE_REMOVED = 0x650, 0x651, 0x652, 0x653, 0x654
EVENT_SIZE = 64

BUTTONS = {
    0: "select",
    1: "back",
    2: "play",
    3: "trailer",
    4: "back",
    6: "menu",
    9: "page_up",
    10: "page_down",
    11: "up",
    12: "down",
    13: "left",
    14: "right",
}
DIRECTIONS = ("up", "down", "left", "right")
STICK_X, STICK_Y = 0, 1
PRESS = 0.55 * 32767
RELEASE = 0.35 * 32767
SWITCH_RATIO = 1.3
REPEAT_DELAY_MS = 400
REPEAT_MS = 90
POLL_MS = 16
IDLE_POLL_MS = 500

HINTS = {
    b"SDL_NO_SIGNAL_HANDLERS": b"1",
    b"SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS": b"1",
}


def load_sdl():
    for name in ("SDL2-2.0", "SDL2"):
        path = ctypes.util.find_library(name)
        for candidate in filter(None, (path, "lib%s.so.0" % name)):
            try:
                lib = ctypes.CDLL(candidate)
            except OSError:
                continue
            lib.SDL_SetHint.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
            lib.SDL_Init.argtypes = [ctypes.c_uint32]
            lib.SDL_QuitSubSystem.argtypes = [ctypes.c_uint32]
            lib.SDL_PollEvent.argtypes = [ctypes.c_void_p]
            lib.SDL_GameControllerOpen.argtypes = [ctypes.c_int]
            lib.SDL_GameControllerOpen.restype = ctypes.c_void_p
            lib.SDL_GameControllerClose.argtypes = [ctypes.c_void_p]
            lib.SDL_GameControllerName.argtypes = [ctypes.c_void_p]
            lib.SDL_GameControllerName.restype = ctypes.c_char_p
            lib.SDL_GameControllerGetJoystick.argtypes = [ctypes.c_void_p]
            lib.SDL_GameControllerGetJoystick.restype = ctypes.c_void_p
            lib.SDL_JoystickInstanceID.argtypes = [ctypes.c_void_p]
            lib.SDL_GetError.restype = ctypes.c_char_p
            return lib
    return None


def decode(raw):
    kind, _ts, which = struct.unpack_from("<IIi", raw, 0)
    if kind in (BUTTON_DOWN, BUTTON_UP):
        return kind, which, raw[12], 0
    if kind == AXIS_MOTION:
        return kind, which, raw[12], struct.unpack_from("<h", raw, 16)[0]
    return kind, which, 0, 0


class Gamepad(QObject):
    action = Signal(str)
    connectedChanged = Signal()

    def __init__(self, sdl=None, parent=None):
        super().__init__(parent)
        self._sdl = sdl
        self._controllers = {}
        self._stick = {STICK_X: 0, STICK_Y: 0}
        self._stick_dir = None
        self._held = []
        self._event = ctypes.create_string_buffer(EVENT_SIZE)
        self._poll = QTimer(self)
        self._poll.timeout.connect(self.poll)
        self._repeat = QTimer(self)
        self._repeat.timeout.connect(self._repeat_fire)

    @property
    def names(self):
        return [name for _, name in self._controllers.values()]

    def start(self):
        if self._sdl is None:
            self._sdl = load_sdl()
        if self._sdl is None:
            log.info("SDL2 not found, gamepad support off")
            return False
        for key, value in HINTS.items():
            self._sdl.SDL_SetHint(key, value)
        if self._sdl.SDL_Init(INIT_FLAGS) != 0:
            log.warning("SDL_Init failed: %s", self._sdl.SDL_GetError())
            self._sdl = None
            return False
        self._poll.start(IDLE_POLL_MS)
        self.poll()
        return True

    def stop(self):
        self._poll.stop()
        self._repeat.stop()
        if self._sdl is not None:
            for handle in list(self._controllers):
                self._sdl.SDL_GameControllerClose(handle)
            self._controllers.clear()
            self._sdl.SDL_QuitSubSystem(INIT_FLAGS)

    def poll(self):
        if self._sdl is None:
            return
        while self._sdl.SDL_PollEvent(self._event):
            self.handle(*decode(self._event.raw))

    def handle(self, kind, which, code, value):
        if kind == DEVICE_ADDED:
            self._open(which)
        elif kind == DEVICE_REMOVED:
            self._close(which)
        elif kind == BUTTON_DOWN and code in BUTTONS:
            self._press(BUTTONS[code])
        elif kind == BUTTON_UP and code in BUTTONS:
            self._release(BUTTONS[code])
        elif kind == AXIS_MOTION and code in self._stick:
            self._stick[code] = value
            self._update_stick()

    def _open(self, index):
        handle = self._sdl.SDL_GameControllerOpen(index)
        if not handle:
            return
        instance = self._sdl.SDL_JoystickInstanceID(self._sdl.SDL_GameControllerGetJoystick(handle))
        if any(i == instance for i, _ in self._controllers.values()):
            self._sdl.SDL_GameControllerClose(handle)
            return
        name = (self._sdl.SDL_GameControllerName(handle) or b"").decode(errors="replace")
        self._controllers[handle] = (instance, name)
        log.info("gamepad connected: %s", name)
        self._poll.setInterval(POLL_MS)
        self.connectedChanged.emit()

    def _close(self, instance):
        for handle, (inst, name) in list(self._controllers.items()):
            if inst == instance:
                self._sdl.SDL_GameControllerClose(handle)
                del self._controllers[handle]
                log.info("gamepad disconnected: %s", name)
        if not self._controllers:
            self._poll.setInterval(IDLE_POLL_MS)
            self._held.clear()
            self._repeat.stop()
        self.connectedChanged.emit()

    def _update_stick(self):
        x, y = self._stick[STICK_X], self._stick[STICK_Y]
        candidate = None
        if max(abs(x), abs(y)) >= PRESS:
            if abs(x) >= abs(y):
                candidate = "left" if x < 0 else "right"
            else:
                candidate = "up" if y < 0 else "down"
        current = self._stick_dir
        if current is not None:
            axis, other = (x, y) if current in ("left", "right") else (y, x)
            held = abs(axis) >= RELEASE and (axis < 0) == (current in ("left", "up"))
            if held and (candidate in (None, current) or abs(other) < abs(axis) * SWITCH_RATIO):
                return
            self._stick_dir = None
            self._release(current)
        if candidate is not None:
            self._stick_dir = candidate
            self._press(candidate)

    def _press(self, name):
        self.action.emit(name)
        if name in DIRECTIONS:
            if name in self._held:
                self._held.remove(name)
            self._held.append(name)
            self._repeat.start(REPEAT_DELAY_MS)

    def _release(self, name):
        if name in self._held:
            self._held.remove(name)
        if not self._held:
            self._repeat.stop()

    def _repeat_fire(self):
        if not self._held:
            self._repeat.stop()
            return
        self._repeat.setInterval(REPEAT_MS)
        self.action.emit(self._held[-1])
