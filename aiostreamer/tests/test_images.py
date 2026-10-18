import tempfile
import unittest

from aiostreamer.tests import helpers
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage

from aiostreamer.api.images import ImageProvider, decode_url, image_source

helpers.app()

STILL = "https://episodes.example/tt1/2/1/w780.jpg"
BACKDROP = "https://img.example/background.jpg"


class ImagesTest(unittest.TestCase):
    def test_source_lists_fallbacks_in_order(self):
        episode = {"type": "Episode", "thumbnail": STILL, "background": BACKDROP, "poster": BACKDROP}
        src = image_source(episode, "thumb")
        self.assertTrue(src.startswith("image://img/thumb/"))
        self.assertEqual([decode_url(p) for p in src.split("/")[4:]], [STILL, BACKDROP])
        self.assertEqual(image_source({"type": "Episode"}, "thumb"), "")

    def test_provider_falls_back_when_first_url_fails(self):
        provider = ImageProvider(tempfile.mkdtemp(prefix="aios-img-"))
        fetched = []

        def download(url, path):
            fetched.append(url)
            if url == STILL:
                raise RuntimeError("404")
            image = QImage(8, 4, QImage.Format_RGB32)
            image.fill(Qt.red)
            image.save(str(path), "PNG")

        provider._download = download
        image_id = image_source({"type": "Episode", "thumbnail": STILL, "background": BACKDROP}, "thumb")[len("image://img/"):]
        image = provider.load(image_id, QSize())
        self.assertEqual((image.width(), image.height()), (8, 4))
        self.assertEqual(fetched, [STILL, BACKDROP])
        provider.load(image_id, QSize())
        self.assertEqual(fetched, [STILL, BACKDROP])
