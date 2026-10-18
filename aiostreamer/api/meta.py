import re
from datetime import datetime, timezone

SERIES_TYPES = ("series", "anime")
TYPE_LABELS = {"movie": "Movies", "series": "Shows", "anime": "Anime", "tv": "TV", "channel": "Channels"}
RUNTIME_RE = re.compile(r"(?:(\d+)\s*h(?:ours?|rs?)?)?\s*(?:(\d+)\s*m(?:in(?:utes?)?)?)?", re.I)
YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def kind_for(stremio_type, videos=None, default_video=""):
    if stremio_type in SERIES_TYPES:
        return "Series"
    if stremio_type == "movie" or default_video:
        return "Movie"
    if videos and any(v.get("season") is not None for v in videos):
        return "Series"
    return "Movie"


def runtime_seconds(text):
    if text is None:
        return 0
    if isinstance(text, (int, float)):
        return int(text) * 60
    text = str(text).strip()
    if text.isdigit():
        return int(text) * 60
    match = RUNTIME_RE.match(text)
    if not match or not (match.group(1) or match.group(2)):
        return 0
    return int(match.group(1) or 0) * 3600 + int(match.group(2) or 0) * 60


def runtime_text(seconds):
    minutes = int((seconds or 0) / 60)
    if not minutes:
        return ""
    hours, mins = divmod(minutes, 60)
    return "%dh %dm" % (hours, mins) if hours else "%dm" % mins


def year_text(meta):
    text = meta.get("releaseInfo") or meta.get("year") or ""
    text = str(text).strip()
    if not text and meta.get("released"):
        text = str(meta["released"])[:4]
    return text.replace("–", " – ").replace("  ", " ").strip() if text else ""


def parse_date(text):
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def released(video, now=None):
    when = parse_date(video.get("released") or video.get("firstAired"))
    if when is None:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when <= (now or datetime.now(timezone.utc))


def trailer_ids(meta):
    ids = []
    for trailer in meta.get("trailerStreams") or []:
        ids.append(trailer.get("ytId"))
    for trailer in meta.get("trailers") or []:
        if (trailer.get("type") or "Trailer") == "Trailer":
            ids.append(trailer.get("source"))
    out = []
    for value in ids:
        if value and YT_ID_RE.match(value) and value not in out:
            out.append(value)
    return out


def _genres(meta):
    genres = meta.get("genres") or meta.get("genre") or []
    if not genres:
        genres = [link.get("name") for link in meta.get("links") or [] if (link.get("category") or "").lower() == "genres"]
    return [g for g in genres if isinstance(g, str)]


def _rating(meta):
    value = meta.get("imdbRating")
    try:
        return "%.1f" % float(value) if value not in (None, "") else ""
    except (TypeError, ValueError):
        return ""


def default_video(meta):
    return str((meta.get("behaviorHints") or {}).get("defaultVideoId") or "")


def direct_type(stremio_type):
    return stremio_type in ("movie",) + SERIES_TYPES


def from_meta(meta):
    stremio_type = meta.get("type") or "movie"
    videos = meta.get("videos") or []
    video = default_video(meta)
    item = {
        "id": meta.get("id", ""),
        "type": kind_for(stremio_type, videos, video),
        "stremioType": stremio_type,
        "name": meta.get("name") or "",
        "poster": meta.get("poster") or "",
        "background": meta.get("background") or "",
        "logo": meta.get("logo") or "",
        "year": year_text(meta),
        "overview": meta.get("description") or "",
        "genres": _genres(meta)[:3],
        "rating": _rating(meta),
        "runtime": runtime_seconds(meta.get("runtime")),
        "status": meta.get("status") or "",
        "released": meta.get("released") or "",
        "trailers": trailer_ids(meta),
    }
    if video and video != item["id"]:
        item["videoId"] = video
    return item


def episode_number(video):
    value = video.get("episode")
    if value is None:
        value = video.get("number")
    return value


def from_video(series, video):
    season = video.get("season")
    number = episode_number(video)
    when = video.get("released") or video.get("firstAired") or ""
    return {
        "id": video.get("id", ""),
        "type": "Episode",
        "stremioType": series.get("stremioType") or "series",
        "seriesId": series.get("id", ""),
        "seriesName": series.get("name", ""),
        "season": season,
        "episode": number,
        "name": video.get("name") or video.get("title") or "",
        "overview": video.get("overview") or video.get("description") or "",
        "thumbnail": video.get("thumbnail") or "",
        "poster": series.get("poster", ""),
        "background": series.get("background", ""),
        "logo": series.get("logo", ""),
        "runtime": runtime_seconds(video.get("runtime")) or series.get("runtime", 0),
        "released": when,
        "year": str(when)[:4],
        "rating": series.get("rating", ""),
        "genres": series.get("genres", []),
        "trailers": [],
    }


def order_key(video):
    season = video.get("season")
    number = episode_number(video)
    return (season if season is not None else 0, number if number is not None else 0, str(video.get("released") or ""))


def episodes(meta):
    series = from_meta(meta)
    videos = sorted(meta.get("videos") or [], key=order_key)
    return [from_video(series, v) for v in videos if v.get("id")]


def seasons(items):
    numbers = []
    for item in items:
        season = item.get("season")
        if season is not None and season not in numbers:
            numbers.append(season)
    regular = sorted(n for n in numbers if n != 0)
    return regular + ([0] if 0 in numbers else [])


def season_name(number):
    return "Specials" if number == 0 else "Season %d" % number


def episode_label(item):
    season = item.get("season")
    number = item.get("episode")
    if season is None and number is None:
        return ""
    if season is None:
        return "E%d" % number
    if number is None:
        return "S%d" % season
    return "S%d:E%d" % (season, number)


def catalog_title(catalog):
    name = (catalog.get("name") or catalog.get("id") or "").strip()
    label = TYPE_LABELS.get(catalog.get("type"), (catalog.get("type") or "").title())
    lowered = name.lower()
    if not label or any(word in lowered for word in (label.lower(), "movie", "show", "series", "anime", "tv")):
        return name
    return "%s %s" % (name, label)


def catalog_extra(catalog, name):
    for extra in catalog.get("extra") or []:
        if extra.get("name") == name:
            return extra
    for extra in catalog.get("extraSupported") or []:
        if extra == name:
            return {"name": name}
    return None


def browsable(catalog):
    required = [e for e in catalog.get("extra") or [] if e.get("isRequired")]
    required += [{"name": n} for n in catalog.get("extraRequired") or []]
    return all(e.get("name") == "genre" and (e.get("options") or []) for e in required)


def home_extra(catalog):
    extra = catalog_extra(catalog, "genre")
    if extra and extra.get("isRequired") and extra.get("options"):
        return {"genre": extra["options"][0]}
    return None


def searchable(catalog):
    return catalog_extra(catalog, "search") is not None
