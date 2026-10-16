import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError

log = logging.getLogger("jellyfin_tv.reporter")

TICKS = 10_000_000


class PlaybackReporter:
    def __init__(self, client, item_id, source_id, play_session_id, play_method="DirectPlay"):
        self._client = client
        self._item_id = item_id
        self._source_id = source_id
        self._session_id = play_session_id
        self._method = play_method
        self._queue = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jftv-report")
        self._last = None
        self._started = False
        self._stopped = False

    @property
    def started(self):
        return self._started

    def _payload(self, position, paused, event=None, audio_index=None, subtitle_index=None):
        data = {
            "ItemId": self._item_id,
            "MediaSourceId": self._source_id,
            "PlaySessionId": self._session_id,
            "PlayMethod": self._method,
            "PositionTicks": int(max(position or 0, 0) * TICKS),
            "IsPaused": bool(paused),
            "IsMuted": False,
            "CanSeek": True,
            "RepeatMode": "RepeatNone",
        }
        if event:
            data["EventName"] = event
        if audio_index is not None:
            data["AudioStreamIndex"] = audio_index
        if subtitle_index is not None:
            data["SubtitleStreamIndex"] = subtitle_index
        return data

    def start(self, position, paused=False):
        if self._started:
            return
        self._started = True
        payload = self._payload(position, paused)
        self._send("Sessions/Playing", payload)

    def progress(self, position, paused, event="TimeUpdate"):
        if not self._started or self._stopped:
            return
        payload = self._payload(position, paused, event)
        self._send("Sessions/Playing/Progress", payload)

    def stop(self, position, completed=False, runtime=None):
        if not self._started or self._stopped:
            self._retire()
            return
        self._stopped = True
        if completed and runtime:
            position = max(position or 0, runtime)
        payload = self._payload(position, False)
        self._send("Sessions/Playing/Stopped", payload)
        self._retire()

    def _send(self, path, payload):
        def post():
            try:
                self._client.post(path, json=payload)
            except Exception as exc:
                log.warning("%s failed: %s", path, exc)
        try:
            self._last = self._queue.submit(post)
        except RuntimeError:
            log.debug("%s dropped after stop", path)

    def _retire(self):
        self._queue.shutdown(wait=False)

    def flush(self, timeout=5.0):
        if self._last is None:
            return True
        try:
            self._last.result(timeout)
        except TimeoutError:
            return False
        return True
