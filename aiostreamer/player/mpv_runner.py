import json
import logging
import os
import shlex
import shutil
import threading
from pathlib import Path

from aiostreamer.player.mpv_ipc import MpvIpc
from aiostreamer.player.tracks import preferred

log = logging.getLogger("aiostreamer.mpv")

REMOTE_SCRIPT = Path(__file__).with_name("remote.lua")
UPNEXT_SCRIPT = Path(__file__).with_name("upnext.lua")
SKIP_SCRIPT = Path(__file__).with_name("skip.lua")
UOSC_DIR = Path(__file__).with_name("uosc")
UOSC_SCRIPT = UOSC_DIR / "scripts" / "uosc"
SUB_TIMEOUT = 30.0
UOSC_FONTS = UOSC_DIR / "fonts"
DEFAULT_THEME = {"accent": "#3daee9", "surface": "#1a1f29", "background": "#0f1218", "text": "#f3f5f9"}
PASSTHROUGH = "ac3,eac3,dts,dts-hd,truehd"
AUDIO_OUTPUTS = {
    "stereo": {"audio-channels": "stereo"},
    "passthrough": {"audio-spdif": PASSTHROUGH, "audio-channels": "auto"},
}
UOSC_OPTIONS = {
    "scale_fullscreen": "1.6",
    "font_scale": "1.25",
    "timeline_size": "46",
    "volume": "none",
    "controls": "<video,audio>subtitles,<has_many_audio>audio,<has_chapter>chapters,space",
    "top_bar_controls": "no",
    "top_bar_flash_on": "video,audio",
    "pause_indicator": "flash",
}

DEFAULT_OPTIONS = {
    "vo": "gpu-next",
    "gpu-api": "vulkan",
    "hwdec": "auto-safe",
    "target-colorspace-hint": "yes",
    "fullscreen": "yes",
}


def parse_overrides(text):
    options = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.lstrip("-")
        if "=" in line:
            key, value = line.split("=", 1)
            options[key.strip()] = value.strip()
        else:
            options[line] = "yes"
    return options


def mpv_config_dir():
    return Path(os.environ.get("MPV_HOME") or Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "mpv")


def user_has_script(name):
    scripts = mpv_config_dir() / "scripts"
    return (scripts / name).exists() or (scripts / (name + ".lua")).exists()


def user_has_uosc():
    return user_has_script("uosc")


def _hex(color):
    return (color or "").lstrip("#")[-6:]


def uosc_script_opts(theme):
    colors = {
        "foreground": _hex(theme["accent"]),
        "foreground_text": _hex(theme["background"]),
        "background": _hex(theme["surface"]),
        "background_text": _hex(theme["text"]),
        "curtain": _hex(theme["background"]),
        "match": _hex(theme["accent"]),
    }
    opts = dict(UOSC_OPTIONS, color="[%s]" % ",".join("%s=%s" % kv for kv in colors.items()))
    return ",".join("uosc-%s=%s" % (k, "[%s]" % v if "," in v and not v.startswith("[") else v) for k, v in opts.items())


def build_options(settings, title="", start=0.0, extra=None, theme=None):
    theme = dict(DEFAULT_THEME, **(theme or {}))
    overlay = settings.get("player_ui") != "native"
    scripts = [str(REMOTE_SCRIPT), str(UPNEXT_SCRIPT), str(SKIP_SCRIPT)]
    options = dict(DEFAULT_OPTIONS)
    options.update({
        "idle": "yes",
        "keep-open": "no",
        "force-window": "immediate",
        "input-default-bindings": "yes",
        "osc": "no" if overlay else "yes",
        "force-media-title": title or " ",
    })
    if overlay:
        options["osd-bar"] = "no"
        if not user_has_uosc():
            scripts.append(str(UOSC_SCRIPT))
            options["osd-fonts-dir"] = str(UOSC_FONTS)
        options["script-opts"] = uosc_script_opts(theme)
    else:
        options["script-opts"] = "aios-overlay=no"
    options["script-opts"] += ",aios-skip=%s,aios-accent=%s" % (settings.get("skip_segments") or "ask", _hex(theme["accent"]))
    options["scripts"] = ":".join(scripts)
    if start and start > 1:
        options["start"] = "%.3f" % start
    options.update(AUDIO_OUTPUTS.get(settings.get("audio_output"), {}))
    audio = ",".join(preferred(settings.get("audio_language")))
    subs = settings.get("subtitle_language")
    if audio:
        options["alang"] = audio
    if subs:
        options["slang"] = subs
    mode = settings.get("subtitle_mode")
    if mode == "off":
        options["sid"] = "no"
    elif mode == "always" and subs:
        options["subs-with-matching-audio"] = "yes"
    if extra:
        options.update(extra)
    conf = settings.mpv_conf_path
    if conf.exists():
        options["include"] = str(conf)
    options.update(parse_overrides(settings.get("mpv_extra")))
    return options


class MpvPlayer:
    def __init__(self, on_position, on_pause, on_duration, on_restart, on_file_loaded, on_end, on_exit, on_message=None):
        self._mpv = None
        self._on_position = on_position
        self._on_pause = on_pause
        self._on_duration = on_duration
        self._on_restart = on_restart
        self._on_file_loaded = on_file_loaded
        self._on_end = on_end
        self._on_exit = on_exit
        self._on_message = on_message
        self._exited = threading.Event()

    @staticmethod
    def available():
        return shutil.which("mpv") is not None

    def start(self, options):
        log.info("starting mpv: %s", " ".join("--%s=%s" % (k, shlex.quote(str(v))) for k, v in options.items()))
        mpv = MpvIpc(options, on_exit=self._quit)
        mpv.bind_event("playback-restart", lambda _d: self._on_restart())
        mpv.bind_event("file-loaded", lambda _d: self._on_file_loaded())
        mpv.bind_event("end-file", lambda d: self._on_end((d or {}).get("reason", "")))
        if self._on_message:
            mpv.bind_event("client-message", lambda d: self._on_message([str(a) for a in (d or {}).get("args") or []]))
        mpv.start()
        self._mpv = mpv
        mpv.observe("time-pos", lambda _n, v: v is not None and self._on_position(float(v)))
        mpv.observe("pause", lambda _n, v: v is not None and self._on_pause(bool(v)))
        mpv.observe("duration", lambda _n, v: v is not None and self._on_duration(float(v)))

    def load(self, url):
        self._mpv.command("loadfile", url, "replace")

    def load_next(self, url, title, start, alang=None):
        self.command("set_property", "start", "%.3f" % start if start and start > 1 else "none")
        if alang is not None:
            self.command("set_property", "alang", alang)
        self.command("set_property", "force-media-title", title or " ")
        self.command("loadfile", url, "replace")

    def show_up_next(self, series, title, seconds, autoplay, accent=""):
        self.command("script-message-to", "upnext", "aios-upnext-show", series, title, str(int(seconds)), "yes" if autoplay else "no", _hex(accent))

    def set_versions(self, versions):
        self.command("script-message-to", "remote", "aios-versions", json.dumps(versions))

    def hide_up_next(self):
        self.command("script-message-to", "upnext", "aios-upnext-hide")

    def add_subtitle(self, url, title="", lang=""):
        if self._mpv is None or self._exited.is_set():
            return
        try:
            self._mpv.command("sub-add", url, "auto", title or "", lang or "", background=True, timeout=SUB_TIMEOUT)
        except Exception as exc:
            if not self._exited.is_set():
                log.warning("sub-add failed: %s", exc)

    def command(self, *args):
        if self._mpv is None:
            return None
        try:
            return self._mpv.command(*args)
        except Exception as exc:
            log.debug("mpv command %s failed: %s", args, exc)
            return None

    def get(self, name, default=None):
        value = self.command("get_property", name)
        return default if value is None else value

    def quit(self):
        if self._mpv is None or self._exited.is_set():
            return
        self.command("quit")

    def terminate(self):
        if self._mpv is not None:
            try:
                self._mpv.terminate()
            except Exception:
                pass

    def _quit(self):
        if self._exited.is_set():
            return
        self._exited.set()
        self._on_exit()
