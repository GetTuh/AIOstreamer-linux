import logging

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from jellyfin_tv.api.meta import episode_label
from jellyfin_tv.models.sources import binge_group, describe, find, pick, remember, short_label, stream_id
from jellyfin_tv.player.mpv_runner import MpvPlayer, build_options
from jellyfin_tv.player.tracks import canonical, choose_audio, choose_subtitle, preferred

log = logging.getLogger("jellyfin_tv.playback")

PROGRESS_INTERVAL_MS = 10_000
UPNEXT_LEAD = 30
SUBS_PER_LANGUAGE = 2


def media_title(item):
    if item.get("type") == "Episode":
        season = item.get("season")
        number = item.get("episode")
        label = "S%02dE%02d" % (season, number) if season is not None and number is not None else ""
        return " - ".join(p for p in (item.get("seriesName"), label, item.get("name")) if p)
    year = (item.get("year") or "")[:4]
    return "%s (%s)" % (item.get("name", ""), year) if year else item.get("name", "")


def up_next_at(duration, outro, countdown):
    if not duration:
        return None
    if outro and 0 < outro < duration - countdown:
        return outro
    return max(duration - max(UPNEXT_LEAD, countdown + 5), 0)


def proxy_headers(stream):
    headers = (((stream.get("behaviorHints") or {}).get("proxyHeaders")) or {}).get("request") or {}
    return ",".join("%s: %s" % (k, str(v).replace(",", r"\,")) for k, v in headers.items())


def pick_subtitles(subs, languages):
    wanted = [canonical(lang) for lang in languages if canonical(lang)]
    out, counts, seen = [], {}, set()
    for sub in subs:
        lang = canonical(sub.get("lang"))
        if lang not in wanted or sub["url"] in seen or counts.get(lang, 0) >= SUBS_PER_LANGUAGE:
            continue
        seen.add(sub["url"])
        counts[lang] = counts.get(lang, 0) + 1
        out.append(sub)
    return out


def wants_external(tracks, sub_langs, mode, audio_lang):
    if mode == "off" or not sub_langs:
        return False
    if mode != "always" and canonical(audio_lang) in sub_langs:
        return False
    return not any(t.get("type") == "sub" and canonical(t.get("lang")) in sub_langs for t in tracks)


class PlaybackController(QObject):
    busyChanged = Signal()
    playbackStarted = Signal(str)
    playbackEnded = Signal(str, bool)
    playbackAdvanced = Signal(str)
    errorOccurred = Signal(str)

    _position = Signal(float)
    _paused = Signal(bool)
    _duration = Signal(float)
    _restart = Signal()
    _fileLoaded = Signal()
    _endFile = Signal(str)
    _exited = Signal()
    _message = Signal(list)

    def __init__(self, runner, session, library, settings, parent=None):
        super().__init__(parent)
        self._runner = runner
        self._session = session
        self._library = library
        self._settings = settings
        self._busy = False
        self._active = None
        self.last_item = None
        self._switching = False
        self.theme = {}
        self._timer = QTimer(self)
        self._timer.setInterval(PROGRESS_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self._position.connect(self._on_position)
        self._paused.connect(self._on_paused)
        self._duration.connect(self._on_duration)
        self._restart.connect(self._on_restart)
        self._fileLoaded.connect(self._on_file_loaded)
        self._endFile.connect(self._on_end_file)
        self._exited.connect(self._on_exited)
        self._message.connect(self._on_message)

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    @Property(bool, notify=busyChanged)
    def active(self):
        return self._active is not None

    def _set_busy(self, value):
        if self._busy != value:
            self._busy = value
            self.busyChanged.emit()

    @Slot(str, float)
    @Slot(str, float, str)
    def play(self, item_id, start=0.0, source_id="", paused=False):
        if self._busy or self._active is not None:
            return
        if not MpvPlayer.available():
            self.errorOccurred.emit("mpv is not installed")
            return
        self._set_busy(True)
        start = max(float(start or 0), 0.0)
        self._runner.run(lambda: self._prepare(item_id, start, source_id or None, paused), self._launched, self._failed)

    def _resolve(self, item_id, start, source_id, item=None, group=""):
        item = item or self._library.item(item_id)
        streams = self._library.streams(item)
        same_group = next((s for s in streams if group and binge_group(s) == group), None)
        stream = find(streams, source_id) or same_group or pick(streams, item)
        if stream is None:
            raise RuntimeError("No playable versions found")
        return {
            "item": item,
            "item_id": item_id,
            "stream": stream,
            "streams": streams,
            "url": stream["url"],
            "headers": proxy_headers(stream),
            "start": start,
            "position": start,
            "paused": False,
            "duration": float(item.get("runtime") or 0),
            "completed": False,
            "playing": False,
            "error": False,
            "next_item": None,
            "outro": None,
            "upnext": "idle",
            "next_state": None,
            "fetching": False,
            "advance": False,
        }

    def _prepare(self, item_id, start, source_id, paused=False):
        state = self._resolve(item_id, start, source_id)
        state["paused"] = paused
        item = state["item"]
        player = MpvPlayer(
            on_position=self._position.emit,
            on_pause=self._paused.emit,
            on_duration=self._duration.emit,
            on_restart=self._restart.emit,
            on_file_loaded=self._fileLoaded.emit,
            on_end=self._endFile.emit,
            on_exit=self._exited.emit,
            on_message=self._message.emit,
        )
        state["player"] = player
        self._active = state
        extra = {"pause": "yes"} if paused else {}
        if state["headers"]:
            extra["http-header-fields"] = state["headers"]
        player.start(build_options(self._settings, media_title(item), start, extra=extra or None, theme=self.theme))
        player.load(state["url"])
        return state

    def _launched(self, state):
        self._active = state
        self.busyChanged.emit()
        self._find_next(state)

    def _find_next(self, state):
        item = state["item"]
        if item.get("type") != "Episode":
            return
        self._runner.run(
            lambda: self._library.next_episode(item),
            lambda next_item: self._next_found(state, next_item),
            lambda exc: log.info("no next episode: %s", exc))

    def _next_found(self, state, next_item):
        state["next_item"] = next_item
        self._check_up_next(state)

    def _countdown(self):
        return int(self._settings.get("upnext_seconds") or 10)

    def _check_up_next(self, state):
        if state is not self._active or not state["next_item"] or not state["playing"]:
            return
        trigger = up_next_at(state["duration"], state["outro"], self._countdown())
        if trigger is None:
            return
        position = state["position"]
        if position >= trigger and state["upnext"] == "idle":
            state["upnext"] = "shown"
            nxt = state["next_item"]
            label = " · ".join(p for p in (episode_label(nxt), nxt.get("name")) if p)
            state["player"].show_up_next(nxt.get("seriesName") or "", label, self._countdown(), bool(self._settings.get("autoplay_next")), self.theme.get("accent", ""))
            self._prefetch_next(state)
        elif position < trigger - 2 and state["upnext"] != "idle":
            if state["upnext"] == "shown":
                state["player"].hide_up_next()
            state["upnext"] = "idle"
            state["advance"] = False

    def _history_start(self, item_id):
        history = self._session.history
        return float(history.progress(item_id)[0]) if history is not None else 0.0

    def _prefetch_next(self, state):
        if state["next_state"] or state["fetching"] or not state["next_item"]:
            return
        state["fetching"] = True
        nxt = state["next_item"]
        start = self._history_start(nxt["id"])
        group = binge_group(state["stream"])
        self._runner.run(
            lambda: self._resolve(nxt["id"], start, None, nxt, group),
            lambda ready: self._next_ready(state, ready),
            lambda exc: self._next_failed(state, exc))

    def _next_ready(self, state, ready):
        state["fetching"] = False
        state["next_state"] = ready
        if state["advance"]:
            self._advance(state)

    def _next_failed(self, state, exc):
        state["fetching"] = False
        log.warning("could not prepare next episode: %s", exc)
        if state["advance"] and state is self._active:
            self.errorOccurred.emit("Could not play next episode: %s" % exc)
            state["player"].quit()

    def _request_advance(self, state):
        state["advance"] = True
        if state["next_state"]:
            self._advance(state)
        else:
            self._prefetch_next(state)

    def _advance(self, state):
        if state is not self._active:
            return
        ready = state["next_state"]
        self._swap(state, ready, True)
        self.playbackAdvanced.emit(state["item_id"])
        self._find_next(ready)

    @Slot(list)
    def _on_message(self, args):
        state = self._active
        if not state or not args:
            return
        if args[0] == "jftv-upnext-play" and state["next_item"]:
            self._request_advance(state)
        elif args[0] == "jftv-upnext-dismiss":
            state["upnext"] = "dismissed"
        elif args[0] == "jftv-version" and len(args) > 1:
            self._switch_version(state, args[1])

    def _versions(self, state):
        current = stream_id(state["stream"])
        versions = []
        for stream in state["streams"]:
            info = describe(stream)
            versions.append({"id": info["id"], "title": short_label(stream) or info["title"][:60], "hint": info["title"][:70], "active": info["id"] == current})
        return versions

    def _switch_version(self, state, source_id):
        if state is not self._active or source_id == stream_id(state["stream"]) or state.get("switching_version"):
            return
        stream = find(state["streams"], source_id)
        if stream is None:
            return
        state["switching_version"] = True
        remember(state["item"], stream)
        state["player"].command("show-text", "Switching version…", 3000)
        item, position = state["item"], state["position"]
        self._runner.run(
            lambda: self._resolve(item["id"], position, source_id, item),
            lambda ready: self._version_ready(state, ready),
            lambda exc: self._version_failed(state, exc))

    def _version_ready(self, state, ready):
        state["switching_version"] = False
        if state is not self._active:
            return
        for key in ("next_item", "outro", "upnext", "next_state", "fetching"):
            ready[key] = state[key]
        self._swap(state, ready)

    def _swap(self, state, ready, completed=False):
        player = state["player"]
        self._timer.stop()
        self._record(state, state["duration"] if completed else None)
        ready["player"] = player
        self._switching = not state["completed"]
        self._active = ready
        alang = ",".join(preferred(self._settings.get("audio_language")))
        player.command("set_property", "http-header-fields", ready["headers"])
        player.load_next(ready["url"], media_title(ready["item"]), ready["start"], alang)

    @Slot(str, float, str)
    def play_now(self, item_id, start=0.0, source_id="", paused=False):
        state = self._active
        if state is None:
            self.play(item_id, start, source_id, paused)
            return
        if paused:
            self.command("set_property", "pause", True)
        start = max(float(start or 0), 0.0)
        state["player"].command("show-text", "Loading…", 3000)
        self._runner.run(
            lambda: self._resolve(item_id, start, source_id or None),
            lambda ready: self._play_now_ready(state, ready),
            lambda exc: self._version_failed(state, exc))

    def _play_now_ready(self, state, ready):
        if state is not self._active:
            return
        self._swap(state, ready)
        self.playbackAdvanced.emit(state["item_id"])
        self._find_next(ready)

    def command(self, *args):
        if self._active:
            self._active["player"].command(*args)

    def _version_failed(self, state, exc):
        state["switching_version"] = False
        log.warning("version switch failed: %s", exc)
        if state is self._active:
            state["player"].command("show-text", "Could not switch version", 3000)

    def _failed(self, exc):
        state = self._active
        self._active = None
        if state:
            state["player"].terminate()
        self._set_busy(False)
        self.busyChanged.emit()
        self.errorOccurred.emit("Playback failed: %s" % exc)

    def _record(self, state, position=None):
        history = self._session.history
        if history is None or not state.get("playing"):
            return
        item = state["item"]
        position = state["position"] if position is None else position
        history.record(item, position, state["duration"])

    @Slot(float)
    def _on_position(self, value):
        if self._active:
            self._active["position"] = value
            self._check_up_next(self._active)

    @Slot(float)
    def _on_duration(self, value):
        if self._active and value > 0:
            self._active["duration"] = value

    @Slot(bool)
    def _on_paused(self, value):
        state = self._active
        if not state or state["paused"] == value:
            return
        state["paused"] = value
        if value:
            self._record(state)

    @Slot()
    def _on_file_loaded(self):
        self._switching = False
        state = self._active
        if not state:
            return
        player = state["player"]
        state["loaded"] = True
        player.set_versions(self._versions(state))
        item, stream = state["item"], state["stream"]
        self._runner.run(lambda: self._setup_tracks(player, item, stream))

    def _setup_tracks(self, player, item, stream):
        tracks = player.get("track-list", []) or []
        aid = choose_audio(tracks, preferred(self._settings.get("audio_language")))
        if aid is not None:
            player.command("set_property", "aid", aid)
        audio = next((t for t in tracks if t.get("type") == "audio" and (t.get("id") == aid or (aid is None and t.get("selected")))), None)
        sub_langs = preferred(self._settings.get("subtitle_language"))
        mode = self._settings.get("subtitle_mode")
        if wants_external(tracks, sub_langs, mode, (audio or {}).get("lang")):
            for sub in pick_subtitles(self._library.subtitles(item, stream), sub_langs):
                player.add_subtitle(sub["url"], sub.get("title") or "Addon", sub["lang"])
            tracks = player.get("track-list", []) or []
        sid = choose_subtitle(tracks, sub_langs, mode, (audio or {}).get("lang"))
        if sid is not None:
            player.command("set_property", "sid", sid)

    @Slot()
    def _on_restart(self):
        state = self._active
        if not state:
            return
        if not state["playing"]:
            state["playing"] = True
            self._timer.start()
            self._set_busy(False)
            self.playbackStarted.emit(state["item_id"])

    @Slot()
    def _tick(self):
        state = self._active
        if state and state["playing"] and not state["paused"]:
            self._record(state)

    @Slot(str)
    def _on_end_file(self, reason):
        state = self._active
        if not state:
            return
        if self._switching and reason == "stop":
            return
        if reason == "eof":
            state["completed"] = True
            if state["next_item"] and state["upnext"] != "dismissed" and (state["advance"] or self._settings.get("autoplay_next")):
                self._request_advance(state)
                return
        elif reason == "error":
            state["error"] = True
        if reason in ("eof", "error", "stop"):
            state["player"].quit()

    @Slot()
    def _on_exited(self):
        state = self._active
        if not state:
            return
        self._timer.stop()
        self._active = None
        runtime = state["duration"] or 0
        self._record(state, runtime if state["completed"] else None)
        state["player"].terminate()
        self._set_busy(False)
        self.busyChanged.emit()
        if state["error"] and not state["playing"]:
            self.errorOccurred.emit("mpv could not play this version, try another one")
        finished = state["completed"] or (runtime > 0 and state["playing"] and state["position"] / runtime >= 0.9)
        self.last_item = state["item"]
        self.playbackEnded.emit(state["item_id"], bool(finished))

    def press_key(self, name):
        if self._active:
            self._active["player"].command("keypress", name)

    @Slot()
    def stop(self):
        if self._active:
            self._active["player"].quit()

    def shutdown(self):
        state = self._active
        if not state:
            return
        self._timer.stop()
        history = self._session.history
        if history is not None and state.get("playing"):
            history.record(state["item"], state["position"], state["duration"])
        state["player"].terminate()
        self._active = None
