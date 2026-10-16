import unittest
from pathlib import Path

from PySide6.QtGui import QColor, QImage

from jellyfin_tv.tests.helpers import app
from jellyfin_tv.api import trickplay

INFO = {"Width": 4, "Height": 2, "TileWidth": 3, "TileHeight": 2, "ThumbnailCount": 8, "Interval": 10000}


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


class FakeHttp:
    def __init__(self, tiles):
        self.tiles = tiles
        self.urls = []

    def get(self, url, headers=None, timeout=None):
        self.urls.append(url)
        number = int(url.split("/")[-1].split(".")[0])
        return FakeResponse(self.tiles[number])


class FakeSession:
    def __init__(self, http):
        self._http = http

    def http(self):
        return self._http

    def url(self, path, **params):
        return "http://h/" + path

    def auth_header(self):
        return "x"


def tile(colors):
    image = QImage(12, 4, QImage.Format_RGB32)
    for i, color in enumerate(colors):
        column, row = i % 3, i // 3
        for x in range(4):
            for y in range(2):
                image.setPixelColor(column * 4 + x, row * 2 + y, QColor(color))
    from PySide6.QtCore import QBuffer, QByteArray
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


class TrickplayTest(unittest.TestCase):
    def setUp(self):
        app()

    def test_locate(self):
        self.assertEqual(trickplay.locate(INFO, 0), (0, 0, 0, 0))
        self.assertEqual(trickplay.locate(INFO, 45), (4, 0, 1, 1))
        self.assertEqual(trickplay.locate(INFO, 61), (6, 1, 0, 0))
        self.assertEqual(trickplay.locate(INFO, 9999), (7, 1, 1, 0))
        self.assertEqual(trickplay.locate(INFO, -5), (0, 0, 0, 0))

    def test_pick_prefers_source_and_width(self):
        item = {"Trickplay": {"abc": {"160": dict(INFO, Width=160), "320": dict(INFO, Width=320)}, "zzz": {"640": dict(INFO, Width=640)}}}
        self.assertEqual(trickplay.pick(item, "a-b-c")["Width"], 320)
        self.assertEqual(trickplay.pick(item, "a-b-c")["key"], "abc")
        self.assertEqual(trickplay.pick(item, "missing")["Width"], 320)
        self.assertIsNone(trickplay.pick({}, "abc"))

    def test_frame_crops_tile_to_bgra(self):
        http = FakeHttp({0: tile(["#ff0000", "#00ff00", "#0000ff", "#ffffff", "#000000", "#808080"]), 1: tile(["#123456"] * 6)})
        provider = trickplay.Trickplay(FakeSession(http), "item", "src", INFO)
        try:
            path, width, height = provider.frame(15)
            raw = Path(path).read_bytes()
            self.assertEqual((width, height, len(raw)), (4, 2, 4 * 2 * 4))
            self.assertEqual(raw[:4], bytes([0, 255, 0, 255]))
            for _ in range(3):
                provider.frame(12)
            path, _, _ = provider.frame(65)
            self.assertEqual(Path(path).read_bytes()[:4], bytes([0x56, 0x34, 0x12, 255]))
            self.assertEqual(len(http.urls), 2)
        finally:
            provider.close()
        self.assertFalse(Path(path).exists())


if __name__ == "__main__":
    unittest.main()
