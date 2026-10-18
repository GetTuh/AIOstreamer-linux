import json
import re

from aiostreamer.models.services import services

MBPS = 1_000_000
HDR_TAGS = ("DV", "HDR10+", "HDR10", "HDR", "HLG")
CODEC_LABEL = {"AVC": "H.264", "HEVC": "HEVC", "AV1": "AV1", "XVID": "XviD", "VP9": "VP9"}
SERVICE_LABEL = {
    "realdebrid": "RD", "alldebrid": "AD", "premiumize": "PM", "torbox": "TB", "debridlink": "DL",
    "easydebrid": "ED", "offcloud": "OC", "pikpak": "PP", "seedr": "SR", "putio": "PIO", "easynews": "EN",
}
RES_RE = re.compile(r"\b(2160|1440|1080|720|576|480)p\b|\b(4k|uhd)\b", re.I)
SEP = r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])"
AUDIO_SEP = r"(?<![A-Za-z0-9])%s(?![A-Za-z])"
QUALITY_RES = [
    ("Remux", r"(?:BD|UHD)?REMUX"), ("BluRay", r"Blu-?Ray|BDRip|BRRip|BD"), ("WEB-DL", r"WEB-?DL|WEB"),
    ("WEBRip", r"WEB-?Rip"), ("HDTV", r"HDTV"), ("DVD", r"DVD(?:Rip)?"),
]
HDR_RES = [("DV", r"DV|DoVi|Dolby[ .]?Vision"), ("HDR10+", r"HDR10(?:\+|Plus)"), ("HDR10", r"HDR10"), ("HDR", r"HDR"), ("HLG", r"HLG")]
CODEC_RES = [("HEVC", r"HEVC|[xh][ .]?265"), ("AVC", r"AVC|[xh][ .]?264"), ("AV1", r"AV1"), ("XVID", r"XviD"), ("VP9", r"VP9")]
AUDIO_RES = [
    ("Atmos", r"Atmos"), ("TrueHD", r"TrueHD"), ("DTS:X", r"DTS[-:]?X"), ("DTS-HD", r"DTS-?HD(?:[ .-]?MA)?"), ("DTS", r"DTS"),
    ("DD+", r"DDP|DD\+|E-?AC-?3"), ("DD", r"DD|AC-?3"), ("Opus", r"Opus"), ("AAC", r"AAC"), ("FLAC", r"FLAC"),
]
CHANNELS_RE = re.compile(r"(?<!\d)([2-7])[ .]([01])(?!\d)")
SERVICE_TAG_RE = re.compile(r"\[(%s)\]" % "|".join(sorted(set(SERVICE_LABEL.values()), key=len, reverse=True)))


def _matches(table, text, sep=SEP):
    return [label for label, pattern in table if re.search(sep % "(?:%s)" % pattern, text, re.I)]


def text_of(stream):
    hints = stream.get("behaviorHints") or {}
    parts = [hints.get("filename"), (hints.get("bingeGroup") or "").replace("|", " "), stream.get("description"), stream.get("name")]
    return re.sub("[\u200b-\u200d\u2060\ufeff]", "", " ".join(str(p) for p in parts if p))


def guessed(stream):
    text = text_of(stream)
    res = RES_RE.search(text)
    hdr = _matches(HDR_RES, text)
    if "HDR10+" in hdr or "HDR10" in hdr:
        hdr = [t for t in hdr if t != "HDR"]
    if "HDR10+" in hdr:
        hdr = [t for t in hdr if t != "HDR10"]
    audio = _matches(AUDIO_RES, text, AUDIO_SEP)
    for wider, narrower in (("DTS-HD", "DTS"), ("DTS:X", "DTS"), ("DD+", "DD")):
        if wider in audio:
            audio = [a for a in audio if a != narrower]
    channels = CHANNELS_RE.search(text)
    return {
        "resolution": res.group(0) if res else "",
        "quality": (_matches(QUALITY_RES, text) or [""])[0],
        "visualTags": hdr,
        "encode": (_matches(CODEC_RES, text) or [""])[0],
        "audioTags": audio,
        "audioChannels": ["%s.%s" % channels.groups()] if channels else [],
    }


def parsed(stream):
    found = (stream.get("streamData") or {}).get("parsedFile")
    return found if found else guessed(stream)


def stream_id(stream):
    data_id = (stream.get("streamData") or {}).get("id")
    if data_id:
        return data_id
    name = filename(stream)
    if name:
        return "file:%s|%s" % (name, (stream.get("behaviorHints") or {}).get("videoSize") or "")
    return stream.get("url") or ""


def service_label(stream):
    service = (stream.get("streamData") or {}).get("service") or {}
    if service:
        label = SERVICE_LABEL.get(service.get("id"), service.get("id") or "")
        return label + " ⚡" if label and service.get("cached") else label
    match = SERVICE_TAG_RE.search(stream.get("description") or "")
    if not match:
        return ""
    return match.group(1) + (" ⚡" if "⚡" in (stream.get("name") or "") else "")


def filename(stream):
    return (stream.get("behaviorHints") or {}).get("filename") or (stream.get("streamData") or {}).get("filename") or ""


def binge_group(stream):
    return (stream.get("behaviorHints") or {}).get("bingeGroup") or ""


def resolution(stream):
    text = parsed(stream).get("resolution") or ""
    match = RES_RE.search(text) or RES_RE.search(" ".join(str(stream.get(k) or "") for k in ("name", "description")) + " " + filename(stream))
    if not match:
        return 0
    return int(match.group(1)) if match.group(1) else 2160


def quality(stream):
    value = parsed(stream).get("quality") or ""
    if not value:
        value = guessed(stream)["quality"]
    return "Remux" if "remux" in value.lower() else value


def size_bytes(stream):
    data = stream.get("streamData") or {}
    return int(data.get("size") or (stream.get("behaviorHints") or {}).get("videoSize") or 0)


def bitrate(stream, runtime):
    size = size_bytes(stream)
    return int(size * 8 / runtime) if size and runtime else 0


def format_size(size):
    if size >= 100 * 1000 ** 3:
        return "%d GB" % round(size / 1000 ** 3)
    if size >= 10 * 1000 ** 3:
        return "%.1f GB" % (size / 1000 ** 3)
    if size >= 1000 ** 3:
        return "%.2f GB" % (size / 1000 ** 3)
    return "%d MB" % round(size / 1000 ** 2) if size else ""


def clean_lines(text):
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in re.sub("[​‌‍⁠﻿]", "", text or "").splitlines()]
    return [line for line in lines if line]


def describe(stream):
    info = parsed(stream)
    data = stream.get("streamData") or {}
    res = resolution(stream)
    tags = [t for t in info.get("visualTags") or [] if t in HDR_TAGS]
    audio = " ".join((info.get("audioTags") or [])[:2] + (info.get("audioChannels") or [])[:1])
    size = size_bytes(stream)
    folder = int(data.get("folderSize") or 0)
    name_lines = clean_lines(stream.get("name"))
    return {
        "id": stream_id(stream),
        "resolution": ("4K" if res >= 2160 else "%dp" % res) if res else "",
        "quality": quality(stream),
        "hdr": " ".join(tags[:2]) if tags else ("SDR" if res else ""),
        "codec": CODEC_LABEL.get((info.get("encode") or "").upper(), info.get("encode") or ""),
        "audio": audio,
        "size": format_size(size) + (" of %s" % format_size(folder) if size and folder > size * 1.2 else ""),
        "service": service_label(stream),
        "title": filename(stream) or " · ".join(clean_lines(stream.get("description"))[:2]),
        "name": " ".join(name_lines[:2]) or data.get("addon") or "",
        "languages": ", ".join((info.get("languages") or [])[:4]),
    }


def short_label(stream):
    info = describe(stream)
    return " · ".join(p for p in (info["resolution"], info["quality"], info["hdr"], info["codec"], info["audio"], info["size"], info["service"]) if p)


def _caps():
    settings = services.settings
    if settings is None:
        return 0, 0
    return int(settings.get("max_resolution") or 0), int(settings.get("max_bitrate") or 0)


def fits(stream, runtime, max_res, max_rate):
    res = resolution(stream)
    if max_res and res > max_res:
        return False
    rate = bitrate(stream, runtime)
    return not (max_rate and rate and rate > max_rate * MBPS)


def memory_keys(item):
    keys = [item.get("id", "")]
    if item.get("seriesId"):
        keys.append("series:" + item["seriesId"])
    return [k for k in keys if k]


def remembered(item):
    settings = services.settings
    if settings is None:
        return []
    out = []
    for key in memory_keys(item):
        raw = settings.get_source(key)
        if not raw:
            continue
        try:
            value = json.loads(raw)
        except ValueError:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


def remember(item, stream):
    settings = services.settings
    if settings is None or not stream:
        return
    value = json.dumps({"file": filename(stream), "group": binge_group(stream)})
    for key in memory_keys(item):
        settings.set_source(key, value)


def pick(streams, item=None, runtime=0):
    if not streams:
        return None
    item = item or {}
    runtime = runtime or item.get("runtime") or 0
    for memory in remembered(item):
        if memory.get("file"):
            for stream in streams:
                if filename(stream) == memory["file"]:
                    return stream
        if memory.get("group"):
            for stream in streams:
                if binge_group(stream) == memory["group"]:
                    return stream
    max_res, max_rate = _caps()
    for stream in streams:
        if fits(stream, runtime, max_res, max_rate):
            return stream
    return streams[0]


def find(streams, wanted_id):
    return next((s for s in streams if stream_id(s) == wanted_id), None) if wanted_id else None
