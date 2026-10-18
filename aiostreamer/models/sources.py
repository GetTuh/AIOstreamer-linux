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


def parsed(stream):
    return ((stream.get("streamData") or {}).get("parsedFile")) or {}


def stream_id(stream):
    return (stream.get("streamData") or {}).get("id") or stream.get("url") or ""


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
    service = data.get("service") or {}
    label = SERVICE_LABEL.get(service.get("id"), service.get("id") or "")
    if label and service.get("cached"):
        label += " ⚡"
    name_lines = clean_lines(stream.get("name"))
    return {
        "id": stream_id(stream),
        "resolution": ("4K" if res >= 2160 else "%dp" % res) if res else "",
        "hdr": " ".join(tags[:2]) if tags else ("SDR" if res else ""),
        "codec": CODEC_LABEL.get((info.get("encode") or "").upper(), info.get("encode") or ""),
        "audio": audio,
        "size": format_size(size) + (" of %s" % format_size(folder) if size and folder > size * 1.2 else ""),
        "service": label,
        "title": filename(stream) or " · ".join(clean_lines(stream.get("description"))[:2]),
        "name": " ".join(name_lines[:2]) or data.get("addon") or "",
        "languages": ", ".join((info.get("languages") or [])[:4]),
    }


def short_label(stream):
    info = describe(stream)
    return " · ".join(p for p in (info["resolution"], info["hdr"], info["codec"], info["audio"], info["size"], info["service"]) if p)


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
