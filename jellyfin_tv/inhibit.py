import logging

from PySide6.QtCore import QObject, Slot

log = logging.getLogger("jellyfin_tv.inhibit")

SERVICE = "org.freedesktop.ScreenSaver"
PATH = "/org/freedesktop/ScreenSaver"


class DBusScreenSaver:
    def __init__(self):
        self._iface = None

    def _interface(self):
        if self._iface is None:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface
            self._iface = QDBusInterface(SERVICE, PATH, SERVICE, QDBusConnection.sessionBus())
        return self._iface

    def inhibit(self, reason):
        reply = self._interface().call("Inhibit", "Jellyfin TV", reason)
        args = reply.arguments()
        if reply.errorMessage() or not args:
            log.info("inhibit failed: %s", reply.errorMessage())
            return None
        return args[0]

    def uninhibit(self, cookie):
        self._interface().call("UnInhibit", cookie)


class SleepInhibitor(QObject):
    def __init__(self, backend=None, parent=None):
        super().__init__(parent)
        self._backend = backend or DBusScreenSaver()
        self._holders = set()
        self._cookie = None

    @property
    def active(self):
        return self._cookie is not None

    @Slot(str, bool)
    def hold(self, key, on):
        if on:
            self._holders.add(key)
        else:
            self._holders.discard(key)
        self._sync()

    def release_all(self):
        self._holders.clear()
        self._sync()

    def _sync(self):
        try:
            if self._holders and self._cookie is None:
                self._cookie = self._backend.inhibit("Playing a trailer")
            elif not self._holders and self._cookie is not None:
                cookie, self._cookie = self._cookie, None
                self._backend.uninhibit(cookie)
        except Exception as exc:
            log.info("inhibit: %s", exc)
