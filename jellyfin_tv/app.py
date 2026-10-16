import logging
import time

from PySide6.QtCore import Property, QEvent, QMetaObject, QObject, Q_ARG, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtQml import qmlRegisterType

from jellyfin_tv.api.library import Library
from jellyfin_tv.api.remote_socket import RemoteSocket
from jellyfin_tv.api.session import LoginError, Session
from jellyfin_tv.api.tasks import TaskRunner
from jellyfin_tv.gamepad import Gamepad
from jellyfin_tv.inhibit import SleepInhibitor
from jellyfin_tv.models.details import DetailsModel
from jellyfin_tv.models.home import HomeModel
from jellyfin_tv.models.items import LibraryModel, SearchModel, SimilarModel
from jellyfin_tv.models.series import SeriesModel
from jellyfin_tv.models.services import services
from jellyfin_tv.models.trailers import TrailerPreview
from jellyfin_tv.player.playback import PlaybackController
from jellyfin_tv.player.remote_control import RemoteControl
from jellyfin_tv.player.syncplay import SyncPlay

log = logging.getLogger("jellyfin_tv.app")

QML_MODULE = "JellyfinTV"
REACTIVATE_MS = (400, 1200)
QUICK_CONNECT_POLL_MS = 3000
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
    quickConnectChanged = Signal()
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
        self._quick_code = ""
        self._quick_timer = QTimer(self)
        self._quick_timer.setInterval(QUICK_CONNECT_POLL_MS)
        self._quick_timer.timeout.connect(self._poll_quick_connect)
        self.player = PlaybackController(self.runner, self.session, self.library, settings, self)
        self.player.playbackStarted.connect(self._on_playback_started)
        self.player.playbackEnded.connect(self._on_playback_ended)
        self.player.playbackAdvanced.connect(self.notifyChanged)
        self.player.errorOccurred.connect(self.message)
        self._trailers = TrailerPreview(self.runner, self.library, settings, parent=self)
        self._inhibitor = SleepInhibitor(parent=self)
        self.player.playbackStarted.connect(lambda _id: self._trailers.stop())
        self.remote_socket = RemoteSocket(self)
        self.remote = RemoteControl(self.player, self, self)
        self.remote_socket.message.connect(self.remote.handle)
        self._syncplay = SyncPlay(self.session, self.player, self.runner, self)
        self._syncplay.notice.connect(self.message)
        self._remote_on = None
        settings.changed.connect(self._sync_remote)
        self._playback_ended_at = None
        self.gamepad = Gamepad(parent=self)
        self.gamepad.action.connect(self.gamepad_action)

    @staticmethod
    def register_types():
        qmlRegisterType(DetailsModel, QML_MODULE, 1, 0, "DetailsModel")
        qmlRegisterType(LibraryModel, QML_MODULE, 1, 0, "LibraryModel")
        qmlRegisterType(SeriesModel, QML_MODULE, 1, 0, "SeriesModel")
        qmlRegisterType(SimilarModel, QML_MODULE, 1, 0, "SimilarModel")
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

    @Property(str, notify=quickConnectChanged)
    def quickConnectCode(self):
        return self._quick_code

    def _refresh_accounts(self):
        self.runner.run(self.session.accounts, self._accounts_loaded, lambda _e: None)

    def _accounts_loaded(self, accounts):
        self._accounts = accounts
        self.accountsChanged.emit()

    @Slot(str)
    def startQuickConnect(self, server):
        if self._busy:
            return
        self._set_busy(True)
        self.runner.run(lambda: self.session.quick_connect_start(server), self._quick_started, self._login_failed)

    def _quick_started(self, code):
        self._set_busy(False)
        self._quick_code = code
        self.quickConnectChanged.emit()
        self._quick_timer.start()

    def _poll_quick_connect(self):
        self.runner.run(self.session.quick_connect_poll, self._quick_polled, self._quick_failed)

    def _quick_polled(self, done):
        if done and self._quick_code:
            self.cancelQuickConnect()
            self._logged_in(True)

    def _quick_failed(self, exc):
        self.cancelQuickConnect()
        self._login_failed(exc)

    @Slot()
    def cancelQuickConnect(self):
        self._quick_timer.stop()
        self.session.quick_connect_cancel()
        if self._quick_code:
            self._quick_code = ""
            self.quickConnectChanged.emit()

    @Slot(str)
    def switchAccount(self, key):
        if self._busy:
            return
        self.player.stop()
        if self._syncplay.active:
            self._syncplay.leave()
        self.remote_socket.stop()
        self._remote_on = None
        self._set_busy(True)
        self.runner.run(lambda: self.session.switch(key), self._logged_in, self._switch_failed)

    def _switch_failed(self, exc):
        self._home = None
        self._login_failed(exc)
        self._refresh_accounts()
        self.sessionChanged.emit()

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
        self.runner.run(self.session.restore, self._restored, self._restored)

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
        if self._syncplay.active:
            self._syncplay.leave()
        self.player.stop()
        self._set_busy(True)
        self.runner.run(self.session.logout, self._logged_out, self._logged_out)

    def _logged_out(self, _):
        self._set_busy(False)
        self._home = None
        self._sync_remote()
        self._refresh_accounts()
        self.sessionChanged.emit()

    def _start_home(self):
        self._home = HomeModel(self.runner, self.library, self)
        self._home.load()
        self._sync_remote()

    @Property(QObject, constant=True)
    def trailers(self):
        return self._trailers

    @Property(QObject, constant=True)
    def inhibitor(self):
        return self._inhibitor

    @Property(QObject, constant=True)
    def syncplay(self):
        return self._syncplay

    def syncplay_message(self, message):
        self._syncplay.handle(message)

    def _sync_remote(self):
        enabled = bool(self._settings.get("remote_control"))
        self.remote.enabled = enabled
        wanted = (self.session.token, enabled) if self.session.logged_in else None
        if wanted == self._remote_on:
            return
        self.remote_socket.stop()
        if wanted:
            s = self.session
            self.remote_socket.start(s.server, s.token, self._settings.device_id, s.auth_header(), enabled)
        self._remote_on = wanted

    def press(self, key, text=""):
        if self._window is None:
            return
        for kind in (QEvent.KeyPress, QEvent.KeyRelease):
            QGuiApplication.sendEvent(self._window, QKeyEvent(kind, key, Qt.NoModifier, text))

    def type_text(self, text):
        for char in text:
            self.press(Qt.Key_unknown, char)

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

    def toast(self, text):
        self.message.emit(text)

    def _invoke(self, name, *args):
        if self._window is not None:
            QMetaObject.invokeMethod(self._window, name, *args)

    def go_home(self):
        self._invoke("showRoot")

    def open_search(self):
        self._invoke("openSearch")

    def open_settings(self):
        self._invoke("openSettings")

    def open_item(self, item_id):
        self.runner.run(lambda: self.library.item(item_id), self._open_loaded, lambda _e: None)

    def _open_loaded(self, item):
        if item and item.get("Id"):
            entry = {"itemId": item["Id"], "itemType": item.get("Type", ""), "name": item.get("Name", "")}
            self._invoke("openItem", Q_ARG("QVariant", entry))

    @Slot(str, float)
    def play(self, item_id, start_ticks):
        self.playSource(item_id, start_ticks, "")

    @Slot(str, float, str)
    def playSource(self, item_id, start_ticks, source_id):
        if self._syncplay.active:
            self._syncplay.set_queue(item_id, start_ticks)
            return
        self.player.play(item_id, start_ticks, source_id)

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
        self.remote_socket.stop()
        self._trailers.shutdown()
        self._inhibitor.release_all()
        self.player.shutdown()
        self.runner.shutdown()
