import os
import re
import subprocess
import sys

MARKERS = ("SteamGameId", "SteamAppId", "SteamClientLaunch", "STEAM_RUNTIME")
CLEANED = "AIOSTREAMER_STEAM_CLEANED"
DROP = ("LD_PRELOAD", "LD_LIBRARY_PATH", "STEAM_RUNTIME", "STEAM_RUNTIME_LIBRARY_PATH", "PRESSURE_VESSEL_RUNTIME")
SESSION_FILL = ("LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "XDG_DATA_DIRS", "XDG_CONFIG_DIRS",
                "XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE", "QT_QPA_PLATFORMTHEME", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH")
STEAM_PATH = re.compile(r"(/Steam/|/steam-runtime|/\.steam/|/SteamLinuxRuntime|pressure-vessel)", re.I)


def launched_by_steam(env):
    return any(env.get(key) for key in MARKERS) and not env.get(CLEANED)


def _strip_paths(value):
    parts = [p for p in value.split(":") if p and not STEAM_PATH.search(p)]
    return ":".join(parts)


def session_environment():
    try:
        out = subprocess.run(["systemctl", "--user", "show-environment"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    env = {}
    for line in out.splitlines():
        key, sep, value = line.partition("=")
        if sep and not value.startswith("$'"):
            env[key] = value
    return env


def _is_utf8(value):
    return bool(value) and "utf" in value.lower().replace("-", "")


def clean_environment(env, session):
    clean = {}
    for key, value in env.items():
        if key in DROP:
            continue
        if value.startswith("/") and STEAM_PATH.search(value):
            value = _strip_paths(value)
            if not value:
                continue
        clean[key] = value
    system_libs = _strip_paths(env.get("SYSTEM_LD_LIBRARY_PATH", ""))
    if system_libs:
        clean["LD_LIBRARY_PATH"] = system_libs
    if env.get("SYSTEM_PATH"):
        clean["PATH"] = env["SYSTEM_PATH"]
    for key in SESSION_FILL:
        if session.get(key) and (key not in clean or (key.startswith("L") and not _is_utf8(clean[key]))):
            clean[key] = session[key]
    if not _is_utf8(clean.get("LC_ALL") or clean.get("LANG")):
        clean.pop("LC_ALL", None)
        clean["LANG"] = "C.UTF-8"
    clean[CLEANED] = "1"
    return clean


def reexec_clean(argv):
    if not launched_by_steam(os.environ):
        return
    env = clean_environment(dict(os.environ), session_environment())
    os.execve(sys.executable, [sys.executable, "-m", "aiostreamer", *argv], env)
