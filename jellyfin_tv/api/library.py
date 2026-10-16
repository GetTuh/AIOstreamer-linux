LIST_FIELDS = "PrimaryImageAspectRatio,MediaSourceCount"
IMAGE_TYPES = "Primary,Backdrop,Thumb,Logo"
DETAIL_FIELDS = "Overview,Genres,Taglines,People,MediaSourceCount,Trickplay"

COLLECTION_TYPES = {
    "movies": "Movie",
    "tvshows": "Series",
    "boxsets": "BoxSet",
    "homevideos": "Video",
    "musicvideos": "MusicVideo",
}

SUBTITLE_FORMATS = ("srt", "subrip", "ass", "ssa", "vtt", "webvtt", "sub", "smi", "ttml")
EMBED_FORMATS = SUBTITLE_FORMATS + ("pgssub", "pgs", "dvdsub", "dvbsub", "vobsub")

DEVICE_PROFILE = {
    "Name": "Jellyfin TV (mpv)",
    "MaxStreamingBitrate": 400000000,
    "MaxStaticBitrate": 400000000,
    "MusicStreamingTranscodingBitrate": 1280000,
    "DirectPlayProfiles": [{"Type": "Video"}, {"Type": "Audio"}],
    "TranscodingProfiles": [{
        "Type": "Video",
        "Container": "mkv",
        "Protocol": "http",
        "VideoCodec": "hevc,h264,av1",
        "AudioCodec": "aac,mp3,ac3,eac3,opus,flac",
    }],
    "CodecProfiles": [],
    "ContainerProfiles": [],
    "SubtitleProfiles": [{"Format": f, "Method": "Embed"} for f in EMBED_FORMATS]
    + [{"Format": f, "Method": "External"} for f in SUBTITLE_FORMATS],
}


class Library:
    def __init__(self, session):
        self.session = session

    @property
    def api(self):
        return self.session.client

    def _get(self, path, params=None):
        return self.api.get(path, params)

    @staticmethod
    def _list_params(**extra):
        params = {
            "UserId": "{UserId}",
            "Fields": LIST_FIELDS,
            "EnableImageTypes": IMAGE_TYPES,
            "ImageTypeLimit": 1,
        }
        params.update({k: v for k, v in extra.items() if v is not None})
        return params

    def views(self):
        return self._get("UserViews", {"UserId": "{UserId}"}).get("Items", [])

    def resume(self, limit=24):
        params = self._list_params(Limit=limit, MediaTypes="Video", EnableTotalRecordCount="false")
        return self._get("UserItems/Resume", params).get("Items", [])

    def next_up(self, limit=24):
        params = self._list_params(Limit=limit, EnableTotalRecordCount="false", EnableResumable="false")
        return self._get("Shows/NextUp", params).get("Items", [])

    def items(self, parent_id, collection_type=None, start=0, limit=60, sort_by=None, sort_order=None):
        item_type = COLLECTION_TYPES.get(collection_type or "")
        params = self._list_params(
            ParentId=parent_id,
            IncludeItemTypes=item_type,
            Recursive="true" if item_type and item_type != "BoxSet" else None,
            StartIndex=start,
            Limit=limit,
            SortBy=sort_by,
            SortOrder=(sort_order or "Ascending") if sort_by else None,
        )
        data = self._get("Items", params)
        return data.get("Items", []), data.get("TotalRecordCount", 0)

    def favorites(self, limit=24):
        params = self._list_params(
            Filters="IsFavorite",
            IncludeItemTypes="Movie,Series,Episode",
            Recursive="true",
            Limit=limit,
            SortBy="SortName",
            SortOrder="Ascending",
            EnableTotalRecordCount="false",
        )
        return self._get("Items", params).get("Items", [])

    def seasons(self, series_id):
        params = self._list_params()
        params.pop("Fields")
        return self._get("Shows/%s/Seasons" % series_id, params).get("Items", [])

    def episodes(self, series_id, season_id):
        params = self._list_params(SeasonId=season_id, Fields="Overview,PrimaryImageAspectRatio,MediaSourceCount")
        return self._get("Shows/%s/Episodes" % series_id, params).get("Items", [])

    def series_next_up(self, series_id):
        params = self._list_params(SeriesId=series_id, Limit=1, EnableTotalRecordCount="false", EnableResumable="true")
        items = self._get("Shows/NextUp", params).get("Items", [])
        return items[0] if items else None

    def next_episode(self, series_id, item_id):
        params = self._list_params(StartItemId=item_id, Limit=2, Fields="Overview,PrimaryImageAspectRatio")
        items = self._get("Shows/%s/Episodes" % series_id, params).get("Items", [])
        if len(items) == 2 and items[0].get("Id") == item_id:
            return items[1]
        return None

    def segments(self, item_id):
        try:
            items = self._get("MediaSegments/%s" % item_id).get("Items", [])
        except Exception:
            return []
        return [{"kind": s.get("Type"), "start": (s.get("StartTicks") or 0) / 10_000_000, "end": (s.get("EndTicks") or 0) / 10_000_000}
                for s in items if s.get("Type") and (s.get("EndTicks") or 0) > (s.get("StartTicks") or 0)]

    def similar(self, item_id, limit=16):
        params = self._list_params(Limit=limit)
        return self._get("Items/%s/Similar" % item_id, params).get("Items", [])

    def search(self, term, item_types="Movie,Series", limit=60):
        params = self._list_params(
            searchTerm=term,
            IncludeItemTypes=item_types,
            Recursive="true",
            Limit=limit,
            EnableTotalRecordCount="false",
        )
        return self._get("Items", params).get("Items", [])

    def set_played(self, item_id, played):
        path = "UserPlayedItems/%s" % item_id
        params = {"UserId": "{UserId}"}
        return self.api.post(path, params=params) if played else self.api.delete(path, params=params)

    def set_favorite(self, item_id, favorite):
        path = "UserFavoriteItems/%s" % item_id
        params = {"UserId": "{UserId}"}
        return self.api.post(path, params=params) if favorite else self.api.delete(path, params=params)

    def item(self, item_id):
        item = self._get("Items/%s" % item_id, {"UserId": "{UserId}", "Fields": DETAIL_FIELDS})
        if item and not item.get("OriginalLanguage") and item.get("SeriesId"):
            try:
                series = self._get("Items/%s" % item["SeriesId"], {"UserId": "{UserId}"})
                item["OriginalLanguage"] = series.get("OriginalLanguage")
            except Exception:
                pass
        return item

    def trailers(self, item_id):
        item = self._get("Items/%s" % item_id, {"UserId": "{UserId}", "Fields": "RemoteTrailers"}) or {}
        local = []
        if item.get("LocalTrailerCount"):
            found = self._get("Items/%s/LocalTrailers" % item_id, {"UserId": "{UserId}"}) or []
            local = [t["Id"] for t in found if t.get("Id")]
        return {
            "local": local,
            "remote": [t["Url"] for t in item.get("RemoteTrailers") or [] if t.get("Url")],
            "title": item.get("Name") or "",
            "year": item.get("ProductionYear"),
        }

    def sources(self, item_id):
        return self._get("Items/%s" % item_id, {"UserId": "{UserId}"}).get("MediaSources") or []

    def playback_info(self, item_id, source_id=None):
        return self.api.playback_info(item_id, DEVICE_PROFILE, source_id)
