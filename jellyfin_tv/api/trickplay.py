import shutil
import tempfile
from pathlib import Path

from PySide6.QtGui import QImage

PREFERRED_WIDTH = 320
TILE_CACHE = 4


def pick(item, source_id):
    data = item.get("Trickplay") or {}
    if not data:
        return None
    key = (source_id or "").replace("-", "")
    widths = data.get(key) or next(iter(data.values()))
    if not widths:
        return None
    width = min(widths, key=lambda w: abs(int(w) - PREFERRED_WIDTH))
    info = dict(widths[width])
    info["key"] = key if key in data else next(iter(data))
    return info


def locate(info, seconds):
    count = int(info["ThumbnailCount"])
    index = min(max(int(seconds * 1000 // int(info["Interval"])), 0), count - 1)
    per_tile = int(info["TileWidth"]) * int(info["TileHeight"])
    within = index % per_tile
    return index, index // per_tile, within % int(info["TileWidth"]), within // int(info["TileWidth"])


class Trickplay:
    def __init__(self, session, item_id, source_id, info):
        self.session = session
        self.item_id = item_id
        self.source_id = source_id
        self.info = info
        self.width = int(info["Width"])
        self.height = int(info["Height"])
        self.dir = Path(tempfile.mkdtemp(prefix="jftv-trickplay-"))
        self._tiles = {}

    def _tile(self, number):
        if number in self._tiles:
            return self._tiles[number]
        url = self.session.url("Videos/%s/Trickplay/%d/%d.jpg" % (self.item_id, self.width, number), mediaSourceId=self.source_id)
        resp = self.session.http().get(url, headers={"Authorization": self.session.auth_header()}, timeout=15)
        resp.raise_for_status()
        image = QImage.fromData(resp.content)
        if image.isNull():
            raise ValueError("trickplay tile %d is not an image" % number)
        if len(self._tiles) >= TILE_CACHE:
            self._tiles.pop(next(iter(self._tiles)))
        self._tiles[number] = image
        return image

    def frame(self, seconds):
        index, tile, column, row = locate(self.info, seconds)
        path = self.dir / ("%d.bgra" % index)
        if not path.exists():
            image = self._tile(tile).copy(column * self.width, row * self.height, self.width, self.height)
            image = image.convertToFormat(QImage.Format_ARGB32)
            path.write_bytes(bytes(image.constBits())[: self.width * self.height * 4])
        return str(path), self.width, self.height

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)
