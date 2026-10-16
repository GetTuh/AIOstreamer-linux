import logging

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from jellyfin_tv.api import trickplay
from jellyfin_tv.api.session import same_origin
from jellyfin_tv.models.items import episode_label
from jellyfin_tv.models.sources import describe, pick_source, preferred_source_id, sort_sources
from jellyfin_tv.player.mpv_runner import MpvPlayer, build_options
from jellyfin_tv.player.reporter import PlaybackReporter
from jellyfin_tv.player.tracks import choose_audio, choose_subtitle, preferred

log = logging.getLogger("jellyfin_tv.playback")

TICKS = 10_000_000
PROGRESS_INTERVAL_MS = 10_000
UPNEXT_LEAD = 30


def media_title(item):
    if item.get("Type") == "Episode":
        season = item.get("ParentIndexNumber")
        number = item.get("IndexNumber")
        label = "S%02dE%02d" % (season, number) if season is not None and number is not None else ""
        return " - ".join(p for p in (item.get("SeriesName"), label, item.get("Name")) if p)
    year = item.get("ProductionYear")
    return "%s (%s)" % (item.get("Name", ""), year) if year else item.get("Name", "")


def up_next_at(duration, outro, countdown):
    if not duration:
        return None
    if outro and 0 < outro < duration - countdown:
        return outro
    return max(duration - max(UPNEXT_LEAD, countdown + 5), 0)


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
        self.observer = None
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
    def play(self, item_id, start_ticks=0.0, source_id="", paused=False):
        if self._busy or self._active is not None:
            return
        if not MpvPlayer.available():
            self.errorOccurred.emit("mpv is not installed")
            return
        self._set_busy(True)
        start = max(float(start_ticks or 0) / TICKS, 0.0)
        self._runner.run(lambda: self._prepare(item_id, start, source_id or None, paused), self._launched, self._failed)

    def _resolve(self, item_id, start, source_id):
        item = self._library.item(item_id)
        source_id = source_id or self._settings.get_source(item_id) or None
        info = self._library.playback_info(item_id, source_id) or {}
        sources = info.get("MediaSources") or self._library.sources(item_id)
        source = pick_source(sources, source_id or preferred_source_id(item_id, sources, item.get("OriginalLanguage")), item.get("OriginalLanguage"))
        if source is None:
            raise RuntimeError("No playable source")
        url, method = self._stream_url(item_id, source, info.get("PlaySessionId"))
        state = {
            "item": item,
            "item_id": item_id,
            "source": source,
            "sources": sort_sources(sources, item.get("OriginalLanguage") or ""),
            "url": url,
            "subs": self._external_subtitles(source),
            "start": start,
            "position": start,
            "paused": False,
            "duration": (source.get("RunTimeTicks") or item.get("RunTimeTicks") or 0) / TICKS,
            "completed": False,
            "playing": False,
            "error": False,
            "reporter": PlaybackReporter(self._session.client, item_id, source.get("Id"), info.get("PlaySessionId"), method),
            "next_item": None,
            "outro": None,
            "upnext": "idle",
            "next_state": None,
            "fetching": False,
            "advance": False,
        }
        return state

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
        player.start(build_options(self._settings, media_title(item), start, extra={"pause": "yes"} if paused else None,
                                   original=item.get("OriginalLanguage") or "", theme=self.theme))
        player.load(state["url"])
        return state

    def _stream_url(self, item_id, source, play_session_id):
        path = source.get("Path") or ""
        if source.get("Protocol") == "Http" and path.startswith(("http://", "https://")) and not same_origin(path, self._session.server):
            return path, "DirectPlay"
        if source.get("SupportsDirectStream", True) or source.get("SupportsDirectPlay"):
            return self._session.url(
                "Videos/%s/stream" % item_id,
                static="true",
                MediaSourceId=source.get("Id"),
                PlaySessionId=play_session_id,
                DeviceId=self._settings.device_id,
                ApiKey=self._session.token,
            ), "DirectPlay"
        if source.get("TranscodingUrl"):
            return self._absolute(source["TranscodingUrl"]), "Transcode"
        raise RuntimeError("Source cannot be streamed")

    def _absolute(self, url):
        if url.startswith(("http://", "https://")):
            if same_origin(url, self._session.server) and "apikey=" not in url.lower():
                url += ("&" if "?" in url else "?") + "ApiKey=" + self._session.token
            return url
        url = self._session.server + "/" + url.lstrip("/")
        if "apikey=" not in url.lower():
            url += ("&" if "?" in url else "?") + "ApiKey=" + self._session.token
        return url

    def _external_subtitles(self, source):
        subs = []
        for stream in source.get("MediaStreams") or []:
            if stream.get("Type") != "Subtitle" or not stream.get("IsExternal"):
                continue
            url = stream.get("DeliveryUrl")
            if not url:
                continue
            subs.append({
                "url": self._absolute(url),
                "title": stream.get("Title") or stream.get("DisplayTitle") or "",
                "lang": stream.get("Language") or "",
            })
        return subs

    def _launched(self, state):
        self._active = state
        self.busyChanged.emit()
        self._find_next(state)
        self._load_segments(state)

    def _find_next(self, state):
        item = state["item"]
        if item.get("Type") != "Episode" or not item.get("SeriesId"):
            return
        series_id, item_id = item["SeriesId"], state["item_id"]
        self._runner.run(
            lambda: self._library.next_episode(series_id, item_id),
            lambda next_item: self._next_found(state, next_item),
            lambda exc: log.info("no next episode: %s", exc))

    def _next_found(self, state, next_item):
        state["next_item"] = next_item
        self._check_up_next(state)

    def _load_segments(self, state):
        item_id = state["item_id"]
        self._runner.run(lambda: self._library.segments(item_id), lambda found: self._segments_loaded(state, found), lambda _e: None)

    def _segments_loaded(self, state, segments):
        state["segments"] = segments
        outros = [s["start"] for s in segments if s["kind"] == "Outro"]
        state["outro"] = min(outros) if outros else None
        self._send_segments(state)
        self._check_up_next(state)

    def _send_segments(self, state):
        if state is self._active and state.get("loaded") and state.get("segments") is not None:
            state["player"].set_segments(state["segments"])

    def _countdown(self):
        return int(self._settings.get("upnext_seconds") or 10)

    def _check_up_next(self, state):
        if state is not self._active or not state["next_item"] or not state["playing"] or self.observer:
            return
        trigger = up_next_at(state["duration"], state["outro"], self._countdown())
        if trigger is None:
            return
        position = state["position"]
        if position >= trigger and state["upnext"] == "idle":
            state["upnext"] = "shown"
            nxt = state["next_item"]
            label = " · ".join(p for p in (episode_label(nxt), nxt.get("Name")) if p)
            state["player"].show_up_next(nxt.get("SeriesName") or "", label, self._countdown(), bool(self._settings.get("autoplay_next")), self.theme.get("accent", ""))
            self._prefetch_next(state)
        elif position < trigger - 2 and state["upnext"] != "idle":
            if state["upnext"] == "shown":
                state["player"].hide_up_next()
            state["upnext"] = "idle"
            state["advance"] = False

    def _prefetch_next(self, state):
        if state["next_state"] or state["fetching"] or not state["next_item"]:
            return
        state["fetching"] = True
        nxt = state["next_item"]
        start = float((nxt.get("UserData") or {}).get("PlaybackPositionTicks") or 0) / TICKS
        self._runner.run(
            lambda: self._resolve(nxt["Id"], start, None),
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
        self.playbackAdvanced.emit(state["item_id"])
        self._swap(state, ready, True)
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
        elif args[0] == "jftv-thumb" and len(args) > 1 and state.get("trickplay"):
            self._thumbnail(state, args[1])

    def _start_trickplay(self, state):
        old = state.pop("trickplay", None)
        if old:
            old.close()
        info = trickplay.pick(state["item"], state["source"].get("Id"))
        if info:
            state["trickplay"] = trickplay.Trickplay(self._session, state["item_id"], state["source"].get("Id"), info)
            state["player"].command("script-message", "jftv-trickplay", str(info["Width"]), str(info["Height"]))
        else:
            state["player"].command("script-message", "jftv-trickplay", "0", "0")

    def _thumbnail(self, state, seconds):
        provider = state["trickplay"]
        player = state["player"]

        def done(result):
            path, width, height = result
            player.command("script-message-to", "thumbfast", "jftv-thumb-ready", seconds, path, str(width), str(height))
        self._runner.run(lambda: provider.frame(float(seconds)), done, lambda exc: log.debug("thumbnail failed: %s", exc))

    def _versions(self, state):
        current = state["source"].get("Id")
        versions = []
        for source in state["sources"]:
            info = describe(source)
            title = " · ".join(p for p in (info["resolution"], info["hdr"], info["codec"], info["audio"], info["size"]) if p)
            versions.append({"id": info["id"], "title": title or info["title"][:60], "hint": info["title"][:70], "active": info["id"] == current})
        return versions

    def _switch_version(self, state, source_id):
        if state is not self._active or source_id == state["source"].get("Id") or state.get("switching_version"):
            return
        state["switching_version"] = True
        item_id, position = state["item_id"], state["position"]
        self._settings.set_source(item_id, source_id)
        state["player"].command("show-text", "Switching version…", 3000)
        self._runner.run(
            lambda: self._resolve(item_id, position, source_id),
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
        if state.get("trickplay"):
            state.pop("trickplay").close()
        player = state["player"]
        self._timer.stop()
        state["reporter"].stop(state["position"], completed, state["duration"] or 0)
        ready["player"] = player
        self._switching = not state["completed"]
        self._active = ready
        alang = ",".join(preferred(self._settings.get("audio_language"), ready["item"].get("OriginalLanguage")))
        player.load_next(ready["url"], media_title(ready["item"]), ready["start"], alang)
        self._load_segments(ready)

    @Slot(str, float, str)
    def play_now(self, item_id, start_ticks=0.0, source_id="", paused=False):
        state = self._active
        if state is None:
            self.play(item_id, start_ticks, source_id, paused)
            return
        if paused:
            self.command("set_property", "pause", True)
        start = max(float(start_ticks or 0) / TICKS, 0.0)
        state["player"].command("show-text", "Loading…", 3000)
        self._runner.run(
            lambda: self._resolve(item_id, start, source_id or None),
            lambda ready: self._play_now_ready(state, ready),
            lambda exc: self._version_failed(state, exc))

    def _play_now_ready(self, state, ready):
        if state is not self._active:
            return
        self.playbackAdvanced.emit(state["item_id"])
        self._swap(state, ready)
        self._find_next(ready)

    def command(self, *args):
        if self._active:
            self._active["player"].command(*args)

    def set_paused(self, value=None):
        if self._active:
            self.command("set_property", "pause", (not self._active["paused"]) if value is None else bool(value))

    def seek_to(self, seconds):
        self.command("seek", "%.3f" % max(seconds, 0.0), "absolute")

    def position(self):
        return self._active["position"] if self._active else 0.0

    def seek_by(self, seconds):
        self.command("seek", "%.3f" % seconds, "relative")

    def next(self):
        state = self._active
        if state and state["next_item"]:
            self._request_advance(state)

    def _track_id(self, kind, index):
        state = self._active
        if not state:
            return None
        streams = state["source"].get("MediaStreams") or []
        internal = [s for s in streams if s.get("Type") == kind and not s.get("IsExternal")]
        external = [s for s in streams if s.get("Type") == kind and s.get("IsExternal")]
        for position, stream in enumerate(internal + external):
            if stream.get("Index") == index:
                return position + 1
        return None

    def set_audio_index(self, index):
        track = self._track_id("Audio", index)
        if track is not None:
            self.command("set_property", "aid", track)

    def set_subtitle_index(self, index):
        if index is None or int(index) < 0:
            self.command("set_property", "sid", "no")
            return
        track = self._track_id("Subtitle", int(index))
        if track is not None:
            self.command("set_property", "sid", track)

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
        if state["playing"]:
            state["reporter"].progress(state["position"], value, "Pause" if value else "Unpause")
            if self.observer:
                self.observer.on_pause(state, value)

    @Slot()
    def _on_file_loaded(self):
        self._switching = False
        state = self._active
        if not state:
            return
        subs = list(state["subs"])
        player = state["player"]
        state["loaded"] = True
        self._send_segments(state)
        self._start_trickplay(state)
        player.set_versions(self._versions(state))
        original = state["item"].get("OriginalLanguage") or ""
        self._runner.run(lambda: self._setup_tracks(player, subs, original))

    def _setup_tracks(self, player, subs, original=""):
        for sub in subs:
            player.add_subtitle(sub["url"], sub["title"], sub["lang"])
        tracks = player.get("track-list", []) or []
        audio_langs = preferred(self._settings.get("audio_language"), original)
        aid = choose_audio(tracks, audio_langs)
        if aid is not None:
            player.command("set_property", "aid", aid)
        audio = next((t for t in tracks if t.get("type") == "audio" and (t.get("id") == aid or (aid is None and t.get("selected")))), None)
        sid = choose_subtitle(tracks, preferred(self._settings.get("subtitle_language")), self._settings.get("subtitle_mode"), (audio or {}).get("lang"))
        if sid is not None:
            player.command("set_property", "sid", sid)

    @Slot()
    def _on_restart(self):
        state = self._active
        if not state:
            return
        if not state["playing"]:
            state["playing"] = True
            state["reporter"].start(state["position"], state["paused"])
            self._timer.start()
            self._set_busy(False)
            self.playbackStarted.emit(state["item_id"])
            if self.observer:
                self.observer.on_loaded(state)
        else:
            state["reporter"].progress(state["position"], state["paused"], "TimeUpdate")
            if self.observer:
                self.observer.on_restart(state)

    @Slot()
    def _tick(self):
        state = self._active
        if state and state["playing"]:
            state["reporter"].progress(state["position"], state["paused"], "TimeUpdate")

    @Slot(str)
    def _on_end_file(self, reason):
        state = self._active
        if not state:
            return
        if self._switching and reason == "stop":
            return
        if reason == "eof":
            state["completed"] = True
            if state["next_item"] and not self.observer and state["upnext"] != "dismissed" and (state["advance"] or self._settings.get("autoplay_next")):
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
        if state.get("trickplay"):
            state["trickplay"].close()
        self._timer.stop()
        self._active = None
        runtime = state["duration"] or 0
        state["reporter"].stop(state["position"], state["completed"], runtime)
        state["player"].terminate()
        self._set_busy(False)
        self.busyChanged.emit()
        if state["error"] and not state["playing"]:
            self.errorOccurred.emit("mpv could not play this source")
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
        state["reporter"].stop(state["position"], False)
        state["reporter"].flush(3.0)
        state["player"].terminate()
        self._active = None
