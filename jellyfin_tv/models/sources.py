import re

from jellyfin_tv.models.services import services
from jellyfin_tv.player.tracks import canonical, wants_original

HDR_RANK = {"DOVI": 4, "DOVIWithHDR10": 4, "DOVIWithHLG": 4, "DOVIWithSDR": 3, "HDR10Plus": 3, "HDR10": 2, "HLG": 1}
HDR_LABEL = {"DOVI": "DV", "DOVIWithHDR10": "DV", "DOVIWithHLG": "DV", "DOVIWithSDR": "DV", "HDR10Plus": "HDR10+", "HDR10": "HDR10", "HLG": "HLG"}
VIDEO_RANK = {"av1": 3, "hevc": 2, "h265": 2, "vp9": 1, "h264": 1}
AUDIO_RANK = {"truehd": 5, "dts": 4, "eac3": 3, "flac": 3, "pcm": 3, "ac3": 2, "opus": 2, "aac": 1}
AUDIO_LABEL = {"truehd": "TrueHD", "eac3": "DD+", "ac3": "DD", "dts": "DTS", "aac": "AAC", "flac": "FLAC", "opus": "Opus", "pcm": "PCM"}
NUMBER = r"(\d+(?:[.,]\d+)?)"
UNIT = r"(TB|GB|MB)"
PAIR_RE = re.compile(NUMBER + r"\s*" + UNIT + r"?\s*/\s*" + NUMBER + r"\s*" + UNIT, re.I)
SIZE_RE = re.compile(NUMBER + r"\s*" + UNIT, re.I)
RATE_RE = re.compile(NUMBER + r"\s*(ᴹᵇᵖˢ|Mbps|ᴷᵇᵖˢ|Kbps)")
MBPS = 1_000_000
MIN_SIZE = 10 * 1000 ** 2
MIN_RATE = 100_000
UNITS = {"tb": 1000 ** 4, "gb": 1000 ** 3, "mb": 1000 ** 2}


def _streams(source, kind):
    return [s for s in source.get("MediaStreams") or [] if s.get("Type") == kind]


def _name_text(source):
    return (source.get("Name") or "") + " " + (source.get("Path") or "")


INVISIBLE_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
SPACE_RE = re.compile(r"[ \t\u00a0]+")


def clean_lines(text):
    text = INVISIBLE_RE.sub("", text or "")
    lines = [SPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    return [line for line in lines if line]


def release_text(source):
    lines = clean_lines(source.get("Name"))
    if not lines:
        return ""
    body = [line for line in lines[1:] if not line.startswith("✎")] if len(lines) > 1 else lines
    return " · ".join(body) or lines[0]


def _name_resolution(source):
    match = re.search(r"(2160|1440|1080|720|576|480)p|\b(4k|uhd)\b", _name_text(source), re.I)
    if not match:
        return 0
    return int(match.group(1)) if match.group(1) else 2160


def resolution(source):
    named = _name_resolution(source)
    if named:
        return named
    video = _streams(source, "Video")
    height = video[0].get("Height") if video else None
    width = video[0].get("Width") if video else None
    if height or width:
        if (width or 0) >= 3200 or (height or 0) >= 2000:
            return 2160
        if (width or 0) >= 1800 or (height or 0) >= 1000:
            return 1080
        if (width or 0) >= 1200 or (height or 0) >= 700:
            return 720
        return height or 480
    return 0


def hdr_type(source):
    video = _streams(source, "Video")
    kind = video[0].get("VideoRangeType") if video else None
    if kind and kind in HDR_RANK:
        return kind
    text = _name_text(source).upper()
    if re.search(r"\bDV\b|DOVI|DOLBY ?VISION", text):
        return "DOVI"
    if "HDR10+" in text or "HDR10PLUS" in text:
        return "HDR10Plus"
    if "HDR" in text:
        return "HDR10"
    return ""


def video_codec(source):
    video = _streams(source, "Video")
    codec = (video[0].get("Codec") or "").lower() if video else ""
    if codec:
        return codec
    text = _name_text(source).upper()
    for key, value in (("AV1", "av1"), ("HEVC", "hevc"), ("X265", "hevc"), ("H.265", "hevc"), ("H265", "hevc"), ("AVC", "h264"), ("X264", "h264"), ("H264", "h264")):
        if key in text:
            return value
    return ""


def audio_info(source):
    audio = _streams(source, "Audio")
    if not audio:
        return "", 0
    best = max(audio, key=lambda s: (AUDIO_RANK.get((s.get("Codec") or "").lower(), 0), s.get("Channels") or 0))
    codec = (best.get("Codec") or "").lower()
    profile = (best.get("Profile") or "").lower()
    if "atmos" in (best.get("DisplayTitle") or "").lower() or "atmos" in profile:
        return codec + "+atmos", best.get("Channels") or 0
    return codec, best.get("Channels") or 0


def _amount(number, unit):
    return round(float(number.replace(",", ".")) * UNITS[unit.lower()])


def _name_sizes(source):
    name = INVISIBLE_RE.sub("", source.get("Name") or "")
    pair = PAIR_RE.search(name)
    if pair:
        return _amount(pair.group(1), pair.group(2) or pair.group(4)), _amount(pair.group(3), pair.group(4))
    single = SIZE_RE.search(name)
    return (_amount(single.group(1), single.group(2)), 0) if single else (0, 0)


def size_bytes(source):
    named = _name_sizes(source)[0]
    field = int(source.get("Size") or 0)
    if field >= MIN_SIZE and (not named or named / 2 <= field <= named * 2):
        return field
    return named or (field if field >= MIN_SIZE else 0)


def pack_bytes(source):
    file_size, pack = _name_sizes(source)
    return pack if pack > file_size else 0


def _name_rate(source):
    match = RATE_RE.search(INVISIBLE_RE.sub("", source.get("Name") or ""))
    if not match:
        return 0
    value = float(match.group(1).replace(",", "."))
    return int(value * (1000 if match.group(2).lower().startswith(("k", "ᴷ")) else MBPS))


def format_size(size):
    if size >= 100 * 1000 ** 3:
        return "%d GB" % round(size / 1000 ** 3)
    if size >= 10 * 1000 ** 3:
        return "%.1f GB" % (size / 1000 ** 3)
    if size >= 1000 ** 3:
        return "%.2f GB" % (size / 1000 ** 3)
    return "%d MB" % round(size / 1000 ** 2) if size else ""


def bitrate(source):
    if int(source.get("Bitrate") or 0) >= MIN_RATE:
        return int(source["Bitrate"])
    named = _name_rate(source)
    if named:
        return named
    seconds = (source.get("RunTimeTicks") or 0) / 10_000_000
    size = size_bytes(source)
    return int(size * 8 / seconds) if size and seconds else 0


def audio_languages(source):
    return {canonical(s.get("Language")) for s in _streams(source, "Audio")} - {""}


def has_language(source, lang):
    lang = canonical(lang)
    known = audio_languages(source)
    return not lang or not known or lang in known


def describe(source):
    codec, channels = audio_info(source)
    res = resolution(source)
    hdr = hdr_type(source)
    base_codec = codec.replace("+atmos", "")
    audio = AUDIO_LABEL.get(base_codec, base_codec.upper())
    if codec.endswith("+atmos"):
        audio += " Atmos"
    if channels:
        audio += " %s" % {1: "1.0", 2: "2.0", 6: "5.1", 8: "7.1"}.get(channels, "%dch" % channels)
    size = size_bytes(source)
    pack = pack_bytes(source)
    return {
        "id": source.get("Id"),
        "resolution": ("4K" if res >= 2160 else "%dp" % res) if res else "",
        "hdr": HDR_LABEL.get(hdr, "SDR" if res else ""),
        "codec": video_codec(source).upper().replace("H264", "H.264"),
        "audio": audio.strip(),
        "size": format_size(size) + (" of %s" % format_size(pack) if size and pack else ""),
        "title": release_text(source),
        "name": source.get("Name") or "",
    }


def score(source, max_resolution=0, prefer_hdr=True, max_bitrate=0, original=""):
    codec, channels = audio_info(source)
    res = resolution(source)
    rate = bitrate(source)
    within = not max_resolution or res <= max_resolution
    affordable = not max_bitrate or not rate or rate <= max_bitrate * MBPS
    return (
        within,
        has_language(source, original),
        affordable,
        res,
        HDR_RANK.get(hdr_type(source), 0) if prefer_hdr else -HDR_RANK.get(hdr_type(source), 0),
        size_bytes(source) if affordable else -size_bytes(source),
        AUDIO_RANK.get(codec.replace("+atmos", ""), 0) + (1 if codec.endswith("+atmos") else 0),
        channels,
        VIDEO_RANK.get(video_codec(source), 0),
    )


def _prefs():
    settings = services.settings
    if settings is None:
        return 0, True, 0, False
    return (
        int(settings.get("max_resolution") or 0),
        bool(settings.get("prefer_hdr")),
        int(settings.get("max_bitrate") or 0),
        wants_original(settings.get("audio_language")),
    )


def sort_sources(sources, original=""):
    max_res, prefer_hdr, max_bitrate, use_original = _prefs()
    original = original if use_original else ""
    return sorted(sources or [], key=lambda s: score(s, max_res, prefer_hdr, max_bitrate, original), reverse=True)


def remember_source(item_id, source_id):
    if services.settings is not None and item_id:
        services.settings.set_source(item_id, source_id)


def preferred_source_id(item_id, sources, original=""):
    remembered = services.settings.get_source(item_id) if services.settings is not None and item_id else ""
    if remembered and any(s.get("Id") == remembered for s in sources):
        return remembered
    ordered = sort_sources(sources, original)
    return ordered[0].get("Id", "") if ordered else ""


def pick_source(sources, preferred_id=None, original=""):
    if not sources:
        return None
    if preferred_id:
        for source in sources:
            if source.get("Id") == preferred_id:
                return source
    return sort_sources(sources, original)[0]
