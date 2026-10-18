import logging
import time

from PySide6.QtCore import Property, QEvent, QObject, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtQml import qmlRegisterType

from aiostreamer.api.library import Library
from aiostreamer.api.session import LoginError, Session
from aiostreamer.api.tasks import TaskRunner
from aiostreamer.gamepad import Gamepad
from aiostreamer.inhibit import SleepInhibitor
from aiostreamer.models.details import DetailsModel
from aiostreamer.models.home import HomeModel
from aiostreamer.models.items import LibraryModel, SearchModel
from aiostreamer.models.series import SeriesModel
from aiostreamer.models.services import services
from aiostreamer.models.trailers import TrailerPreview
from aiostreamer.player.playback import PlaybackController

log = logging.getLogger("aiostreamer.app")

QML_MODULE = "AIOstreamer"
REACTIVATE_MS = (400, 1200)
GAMEPAD_AFTER_PLAYBACK_S = 15
GAMEPAD_QT_KEYS = {
    "up": (Qt.Key_Up, ""),
    "down": (Qt.Key_Down, ""),
    "left": (Qt.Key_Left, ""),
    "right": (Qt.Key_Right, ""),
    "select": (Qt.Key_Return, "\r"),
    "back": (Qt.Key_Escape, ""),
    "menu": (Qt.Key_Menu, ""),
    "play": (Qt.Key_MediaTogglePlayPause, ""),
    "trailer": (Qt.Key_T, "t"),
    "page_up": (Qt.Key_PageUp, ""),
    "page_down": (Qt.Key_PageDown, ""),
}
GAMEPAD_MPV_KEYS = {
    "up": "UP",
    "down": "DOWN",
    "left": "LEFT",
    "right": "RIGHT",
    "select": "ENTER",
    "back": "ESC",
    "menu": "MENU",
    "play": "PLAYPAUSE",
    "page_up": "PGUP",
    "page_down": "PGDWN",
}


class AppController(QObject):
    sessionChanged = Signal()
    accountsChanged = Signal()
    loginFailed = Signal(str)
    busyChanged = Signal()
    message = Signal(str)
    itemChanged = Signal(str)

    def __init__(self, settings, kirigami=False, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._kirigami = kirigami
        self.runner = TaskRunner()
        self.session = Session(settings)
        self.library = Library(self.session)
        services.runner = self.runner
        services.library = self.library
        services.settings = settings
        self._home = None
        self._busy = False
        self._ready = False
        self._window = None
        self._visibility = None
        self._accounts = []
        self.player = PlaybackController(self.runner, self.session, self.library, settings, self)
        self.player.playbackStarted.connect(self._on_playback_started)
        self.player.playbackEnded.connect(self._on_playback_ended)
        self.player.playbackAdvanced.connect(self.notifyChanged)
        self.player.errorOccurred.connect(self.message)
        self._trailers = TrailerPreview(self.runner, self.library, settings, parent=self)
        self._inhibitor = SleepInhibitor(parent=self)
        self.player.playbackStarted.connect(lambda _id: self._trailers.stop())
        self._playback_ended_at = None
        self.gamepad = Gamepad(parent=self)
        self.gamepad.action.connect(self.gamepad_action)

    @staticmethod
    def register_types():
        qmlRegisterType(DetailsModel, QML_MODULE, 1, 0, "DetailsModel")
        qmlRegisterType(LibraryModel, QML_MODULE, 1, 0, "LibraryModel")
        qmlRegisterType(SeriesModel, QML_MODULE, 1, 0, "SeriesModel")
        qmlRegisterType(SearchModel, QML_MODULE, 1, 0, "SearchModel")

    def attach_window(self, window):
        self._window = window

    @Property(QObject, constant=True)
    def settings(self):
        return self._settings

    @Property(QObject, constant=True)
    def playback(self):
        return self.player

    @Property(bool, constant=True)
    def kirigami(self):
        return self._kirigami

    @Property(bool, notify=sessionChanged)
    def ready(self):
        return self._ready

    @Property(bool, notify=sessionChanged)
    def loggedIn(self):
        return self.session.logged_in

    @Property(str, notify=sessionChanged)
    def userName(self):
        return self.session.username

    @Property("QVariantList", notify=accountsChanged)
    def accounts(self):
        return self._accounts

    def _refresh_accounts(self):
        self.runner.run(self.session.accounts, self._accounts_loaded, lambda _e: None)

    def _accounts_loaded(self, accounts):
        self._accounts = accounts
        self.accountsChanged.emit()

    @Slot(str)
    def switchAccount(self, key):
        if self._busy:
            return
        self.player.stop()
        self._set_busy(True)
        self.runner.run(lambda: self.session.switch(key), self._logged_in, self._switch_failed)

    def _switch_failed(self, exc):
        self._login_failed(exc)
        self._refresh_accounts()

    @Property(str, notify=sessionChanged)
    def serverUrl(self):
        return self.session.server or self._settings.get("server")

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    def _set_busy(self, value):
        if self._busy != value:
            self._busy = value
            self.busyChanged.emit()

    @Property(QObject, notify=sessionChanged)
    def home(self):
        return self._home

    @Slot()
    def restore(self):
        self._set_busy(True)
        self.runner.run(self.session.restore, self._restored, self._restore_failed)

    def _restore_failed(self, exc):
        self._restored(False)
        if isinstance(exc, LoginError):
            self.message.emit(str(exc))

    def _restored(self, ok):
        self._set_busy(False)
        self._ready = True
        if ok is True:
            self._start_home()
        self._refresh_accounts()
        self.sessionChanged.emit()

    @Slot(str, str, str)
    def login(self, server, username, password):
        if self._busy:
            return
        self._set_busy(True)
        self.runner.run(lambda: self.session.login(server, username, password) or True, self._logged_in, self._login_failed)

    def _logged_in(self, _):
        self._set_busy(False)
        self._start_home()
        self._refresh_accounts()
        self.sessionChanged.emit()

    def _login_failed(self, exc):
        self._set_busy(False)
        text = str(exc) if isinstance(exc, LoginError) else "Could not connect: %s" % exc
        self.loginFailed.emit(text)

    @Slot()
    def logout(self):
        self.player.stop()
        self.session.logout()
        self._home = None
        self._refresh_accounts()
        self.sessionChanged.emit()

    def _start_home(self):
        self._home = HomeModel(self.runner, self.library, self)
        self._home.load()

    @Slot()
    def clearCache(self):
        self.session.clear_cache()
        if self._home is not None:
            self._home.refreshCatalogs()
        self.message.emit("Cache cleared")

    @Property(QObject, constant=True)
    def trailers(self):
        return self._trailers

    @Property(QObject, constant=True)
    def inhibitor(self):
        return self._inhibitor

    def press(self, key, text=""):
        if self._window is None:
            return
        for kind in (QEvent.KeyPress, QEvent.KeyRelease):
            QGuiApplication.sendEvent(self._window, QKeyEvent(kind, key, Qt.NoModifier, text))

    def start_gamepad(self):
        return self.gamepad.start()

    def _window_active(self):
        return self._window is not None and self._window.isActive()

    def gamepad_action(self, action):
        if not self._settings.get("gamepad"):
            return
        if self.player.active:
            key = GAMEPAD_MPV_KEYS.get(action)
            if key:
                self.player.press_key(key)
            return
        if not self._window_active():
            ended = self._playback_ended_at
            if ended is None or time.monotonic() - ended > GAMEPAD_AFTER_PLAYBACK_S:
                return
            self._activate()
        key, text = GAMEPAD_QT_KEYS[action]
        self.press(key, text)

    @Slot(str, float)
    def play(self, item_id, seconds):
        self.player.play(item_id, seconds, "")

    @Slot(str, float, str)
    def playSource(self, item_id, seconds, source_id):
        self.player.play(item_id, seconds, source_id)

    @Slot(str)
    def notifyChanged(self, item_id):
        if self._home is not None:
            self._home.refreshPlayback()
        self.itemChanged.emit(item_id)

    def _on_playback_started(self, _item_id):
        if self._window is not None and self._visibility is None:
            self._visibility = self._window.visibility()
            self._window.hide()

    def _on_playback_ended(self, item_id, finished):
        self._playback_ended_at = time.monotonic()
        if self._window is not None and self._visibility is not None:
            self._window.setVisibility(self._visibility)
            self._visibility = None
            self._activate()
            for delay in REACTIVATE_MS:
                QTimer.singleShot(delay, self._activate)
        if self._home is not None:
            self._home.refreshPlayback()
        self.itemChanged.emit(item_id)

    def _activate(self):
        window = self._window
        if window is not None and window.isVisible() and not window.isActive() and not self.player.active:
            window.raise_()
            window.requestActivate()

    @Slot(str)
    def setAccent(self, color):
        if color:
            self.player.theme["accent"] = color

    @Slot()
    def quit(self):
        QGuiApplication.quit()

    def shutdown(self):
        self.gamepad.stop()
        self._trailers.shutdown()
        self._inhibitor.release_all()
        self.player.shutdown()
        self.runner.shutdown()
