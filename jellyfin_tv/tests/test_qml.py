import unittest
from pathlib import Path

from jellyfin_tv.tests.helpers import app
from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine

from jellyfin_tv.app import AppController

UI = Path(__file__).resolve().parent.parent / "ui"


class QmlCompileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app()
        AppController.register_types()

    def test_every_qml_file_compiles(self):
        files = sorted(p for p in UI.rglob("*.qml") if p.name not in ("KirigamiTheme.qml",))
        self.assertGreater(len(files), 15)
        engine = QQmlEngine()
        for path in files:
            with self.subTest(qml=str(path.relative_to(UI))):
                component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
                errors = [e.toString() for e in component.errors()]
                self.assertFalse(component.isError(), "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
