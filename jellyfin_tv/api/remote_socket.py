import json
import logging
import threading

import requests
import websocket
from PySide6.QtCore import QObject, Signal

log = logging.getLogger("jellyfin_tv.remote")

SUPPORTED_COMMANDS = [
    "MoveUp", "MoveDown", "MoveLeft", "MoveRight", "Select", "Back", "GoHome", "GoToSettings", "GoToSearch",
    "PageUp", "PageDown", "SendString", "DisplayContent", "DisplayMessage", "SetAudioStreamIndex",
    "SetSubtitleStreamIndex", "VolumeUp", "VolumeDown", "SetVolume", "Mute", "Unmute", "ToggleMute",
    "ToggleFullscreen", "PlayState", "Play", "PlayNext", "PlayMediaSource",
]
KEEPALIVE_S = 30
RETRY_S = (2, 5, 10, 30)


def socket_url(server, token, device_id):
    scheme = "wss" if server.startswith("https") else "ws"
    return "%s://%s/socket?api_key=%s&deviceId=%s" % (scheme, server.split("://", 1)[1], token, device_id)


def capabilities(enabled):
    return {
        "PlayableMediaTypes": ["Video"],
        "SupportsMediaControl": enabled,
        "SupportedCommands": SUPPORTED_COMMANDS if enabled else [],
    }


class RemoteSocket(QObject):
    message = Signal(dict)
    connectedChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop = threading.Event()
        self._thread = None
        self._ws = None

    def start(self, server, token, device_id, auth_header, enabled=True):
        self.stop()
        self._stop = threading.Event()
        stop = self._stop
        self._thread = threading.Thread(target=self._run, args=(stop, server, token, device_id, auth_header, enabled), daemon=True, name="jftv-remote")
        self._thread.start()

    def stop(self):
        self._stop.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def _run(self, stop, server, token, device_id, auth_header, enabled):
        attempt = 0
        while not stop.is_set():
            ws = websocket.WebSocketApp(
                socket_url(server, token, device_id),
                on_open=lambda w: self._opened(w, stop, server, auth_header, enabled),
                on_message=lambda w, raw: self._received(w, raw),
                on_error=lambda w, exc: log.debug("remote socket error: %s", exc),
            )
            self._ws = ws
            ws.run_forever(ping_interval=KEEPALIVE_S, ping_timeout=10)
            self._ws = None
            self.connectedChanged.emit(False)
            if stop.wait(RETRY_S[min(attempt, len(RETRY_S) - 1)]):
                break
            attempt += 1

    def _opened(self, ws, stop, server, auth_header, enabled):
        try:
            requests.post(server + "/Sessions/Capabilities/Full", json=capabilities(enabled),
                          headers={"Authorization": auth_header}, timeout=10).raise_for_status()
        except requests.RequestException as exc:
            log.warning("could not announce remote control: %s", exc)
        self.connectedChanged.emit(True)

        def keepalive():
            while not stop.wait(KEEPALIVE_S):
                try:
                    ws.send(json.dumps({"MessageType": "KeepAlive"}))
                except Exception:
                    return
        threading.Thread(target=keepalive, daemon=True, name="jftv-keepalive").start()

    def _received(self, ws, raw):
        try:
            data = json.loads(raw)
        except ValueError:
            return
        kind = data.get("MessageType")
        if kind in ("KeepAlive", "ForceKeepAlive"):
            return
        self.message.emit(data)
