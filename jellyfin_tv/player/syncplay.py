import datetime
import logging
import statistics
import time

import requests
from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

log = logging.getLogger("jellyfin_tv.syncplay")

TICKS = 10_000_000
TIME_SAMPLES = 5
RESYNC_MS = 60_000
LOAD_REASONS = ("NewPlaylist", "SetCurrentItem", "NextItem", "PreviousItem")


def parse_time(text):
    text = (text or "").rstrip("Z")
    if "." in text:
        head, fraction = text.split(".", 1)
        text = head + "." + fraction[:6]
    stamp = datetime.datetime.fromisoformat(text).replace(tzinfo=datetime.timezone.utc)
    return stamp.timestamp() * 1000


def format_time(ms):
    stamp = datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def offset_from(samples):
    best = sorted(samples, key=lambda s: s[1])[: max(1, len(samples) // 2 + 1)]
    return statistics.median(o for o, _ in best)


class SyncPlay(QObject):
    changed = Signal()
    groupsChanged = Signal()
    notice = Signal(str)

    def __init__(self, session, player, runner, parent=None):
        super().__init__(parent)
        self.session = session
        self.player = player
        self.runner = runner
        self._group = None
        self._groups = []
        self._state = ""
        self.offset_ms = 0.0
        self.playlist_item = ""
        self.expect_pause = None
        self.expect_seek = 0
        self.ready_after_seek = False
        self._scheduled = []
        self._resync = QTimer(self)
        self._resync.setInterval(RESYNC_MS)
        self._resync.timeout.connect(self.sync_time)
        self.clock = time.time

    @Property(bool, notify=changed)
    def active(self):
        return self._group is not None

    @Property(str, notify=changed)
    def groupName(self):
        return (self._group or {}).get("GroupName", "")

    @Property(str, notify=changed)
    def groupState(self):
        return self._state

    @Property("QVariantList", notify=changed)
    def participants(self):
        return list((self._group or {}).get("Participants") or [])

    @Property("QVariantList", notify=groupsChanged)
    def groups(self):
        return self._groups

    def now(self):
        return self.clock() * 1000 + self.offset_ms

    def _request(self, method, path, body=None):
        resp = requests.request(method, self.session.server + "/" + path, json=body,
                                headers={"Authorization": self.session.auth_header()}, timeout=10)
        resp.raise_for_status()
        return resp.json() if resp.content else None

    def _post(self, path, body=None):
        self.runner.run(lambda: self._request("POST", "SyncPlay/" + path, body or {}), None,
                        lambda exc: self.notice.emit("SyncPlay: %s" % exc))

    @Slot()
    def refresh(self):
        self.runner.run(lambda: self._request("GET", "SyncPlay/List") or [], self._groups_loaded, lambda _e: self._groups_loaded([]))

    def _groups_loaded(self, groups):
        self._groups = [{"id": g.get("GroupId"), "name": g.get("GroupName"), "state": g.get("State"),
                         "participants": len(g.get("Participants") or [])} for g in groups]
        self.groupsChanged.emit()

    @Slot(str)
    def create(self, name):
        self._post("New", {"GroupName": name or "%s's group" % self.session.username})

    @Slot(str)
    def join(self, group_id):
        self._post("Join", {"GroupId": group_id})

    @Slot()
    def leave(self):
        self._post("Leave")
        self._left()

    def _left(self):
        self._cancel_scheduled()
        self._resync.stop()
        self._group = None
        self._state = ""
        self.player.observer = None
        self.changed.emit()

    @Slot()
    def sync_time(self):
        def measure():
            samples = []
            for _ in range(TIME_SAMPLES):
                sent = time.time() * 1000
                data = self._request("GET", "GetUtcTime")
                received = time.time() * 1000
                server_in, server_out = parse_time(data["RequestReceptionTime"]), parse_time(data["ResponseTransmissionTime"])
                samples.append((((server_in - sent) + (server_out - received)) / 2, (received - sent) - (server_out - server_in)))
            return samples
        self.runner.run(measure, self._time_measured, lambda exc: log.warning("time sync failed: %s", exc))

    def _time_measured(self, samples):
        self.offset_ms = offset_from(samples)
        delay = min(d for _, d in samples)
        self.runner.run(lambda: self._request("POST", "SyncPlay/Ping", {"Ping": int(delay)}), None, lambda _e: None)

    def set_queue(self, item_id, start_ticks=0.0):
        self._post("SetNewQueue", {"PlayingQueue": [item_id], "PlayingItemPosition": 0, "StartPositionTicks": int(start_ticks or 0)})

    @Slot(dict)
    def handle(self, message):
        kind = message.get("MessageType")
        data = message.get("Data") or {}
        if kind == "SyncPlayGroupUpdate":
            self._group_update(data.get("Type"), data.get("Data"))
        elif kind == "SyncPlayCommand":
            self._command(data)

    def _group_update(self, kind, data):
        if kind == "GroupJoined":
            self._group = data or {}
            self._state = (data or {}).get("State", "")
            self.player.observer = self
            self.sync_time()
            self._resync.start()
            self.changed.emit()
            self.notice.emit("Joined SyncPlay group %s" % self.groupName)
        elif kind in ("UserJoined", "UserLeft") and self._group is not None:
            people = set(self._group.get("Participants") or [])
            (people.add if kind == "UserJoined" else people.discard)(data)
            self._group["Participants"] = sorted(people)
            self.changed.emit()
            self.notice.emit("%s %s the group" % (data, "joined" if kind == "UserJoined" else "left"))
        elif kind in ("GroupLeft", "NotInGroup", "GroupDoesNotExist"):
            self._left()
        elif kind == "StateUpdate":
            self._state = (data or {}).get("State", "")
            self.changed.emit()
        elif kind == "PlayQueue":
            self._play_queue(data or {})

    def _play_queue(self, data):
        playlist = data.get("Playlist") or []
        index = data.get("PlayingItemIndex", -1)
        if not playlist or not (0 <= index < len(playlist)):
            return
        entry = playlist[index]
        changed_item = entry.get("PlaylistItemId") != self.playlist_item
        if not changed_item and data.get("Reason") not in LOAD_REASONS:
            return
        self.playlist_item = entry.get("PlaylistItemId", "")
        self.expect_pause = True
        self.player.play_now(entry["ItemId"], float(data.get("StartPositionTicks") or 0), "", True)
        self._post("Buffering", self._status(False, float(data.get("StartPositionTicks") or 0) / TICKS))

    def _status(self, playing, position=None):
        if position is None:
            position = self.player.position()
        return {"When": format_time(self.now()), "PositionTicks": int(position * TICKS), "IsPlaying": playing,
                "PlaylistItemId": self.playlist_item}

    def _cancel_scheduled(self):
        for timer in self._scheduled:
            timer.stop()
        self._scheduled = []

    def _at(self, server_ms, action):
        delay = max(0, int(server_ms - self.now()))
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(action)
        timer.start(delay)
        self._scheduled.append(timer)
        return delay

    def _command(self, data):
        if self._group is None or not self.player.active:
            return
        command = data.get("Command")
        when = parse_time(data.get("When")) if data.get("When") else self.now()
        position = float(data.get("PositionTicks") or 0) / TICKS
        self._cancel_scheduled()
        if command == "Unpause":
            late = max(0.0, (self.now() - when) / 1000)
            self._seek(position + late)
            self._at(when, lambda: self._set_paused(False))
        elif command == "Pause":
            def pause():
                self._set_paused(True)
                self._seek(position)
            self._at(when, pause)
        elif command == "Seek":
            self._set_paused(True)
            self.ready_after_seek = True
            self._seek(position)
        elif command == "Stop":
            self.player.stop()

    def _set_paused(self, value):
        if self.player.active:
            self.expect_pause = value
            self.player.set_paused(value)

    def _seek(self, seconds):
        self.expect_seek += 1
        self.player.seek_to(seconds)

    def on_loaded(self, state):
        self._post("Ready", self._status(False))

    def on_restart(self, state):
        if self.expect_seek > 0:
            self.expect_seek -= 1
            if self.ready_after_seek:
                self.ready_after_seek = False
                self._post("Ready", self._status(False))
            return
        self._post("Seek", {"PositionTicks": int(state["position"] * TICKS)})

    def on_pause(self, state, value):
        if self.expect_pause is not None and self.expect_pause == value:
            self.expect_pause = None
            return
        self.expect_pause = None
        if value:
            self._post("Pause")
        else:
            self._set_paused(True)
            self._post("Unpause")
