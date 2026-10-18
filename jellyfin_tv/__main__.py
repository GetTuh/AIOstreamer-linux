import argparse
import logging
import os
import signal
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from jellyfin_tv import __version__
from jellyfin_tv.api.images import PROVIDER_ID, ImageProvider
from jellyfin_tv.app import AppController
from jellyfin_tv.models.settings import Settings, cache_dir
from jellyfin_tv.steam import reexec_clean

UI_DIR = Path(__file__).with_name("ui")


def kirigami_available(engine):
    for path in engine.importPathList():
        if (Path(path) / "org" / "kde" / "kirigami").is_dir():
            return True
    return False


def main(argv=None):
    if argv is None:
        reexec_clean(sys.argv[1:])
    parser = argparse.ArgumentParser(prog="jellyfin-tv")
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args, qt_args = parser.parse_known_args(argv if argv is not None else sys.argv[1:])

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for noisy in ("JELLYFIN", "urllib3", "requests"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    QQuickStyle.setStyle("Basic")
    QGuiApplication.setApplicationName("jellyfin-tv")
    QGuiApplication.setApplicationDisplayName("Jellyfin TV")
    QGuiApplication.setApplicationVersion(__version__)
    QGuiApplication.setDesktopFileName(os.environ.get("FLATPAK_ID") or "jellyfin-tv")
    app = QGuiApplication([sys.argv[0]] + qt_args)
    app.setWindowIcon(QIcon.fromTheme(os.environ.get("FLATPAK_ID") or "jellyfin-tv", QIcon(str(UI_DIR / "icon.svg"))))
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    pulse = QTimer()
    pulse.timeout.connect(lambda: None)
    pulse.start(500)

    settings = Settings()
    AppController.register_types()
    engine = QQmlApplicationEngine()
    controller = AppController(settings, kirigami_available(engine))
    engine.addImageProvider(PROVIDER_ID, ImageProvider(cache_dir()))
    engine.rootContext().setContextProperty("app", controller)
    engine.rootContext().setContextProperty("startWindowed", args.windowed)
    engine.load(QUrl.fromLocalFile(str(UI_DIR / "Main.qml")))
    if not engine.rootObjects():
        return 1
    controller.attach_window(engine.rootObjects()[0])
    controller.start_gamepad()
    controller.restore()
    code = app.exec()
    controller.shutdown()
    del engine
    return code


if __name__ == "__main__":
    sys.exit(main())
