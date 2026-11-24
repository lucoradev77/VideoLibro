"""Entry point for VideoLibro Studio."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg*=false")

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from videolibro.ui.main_window import MainWindow


def main() -> int:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("videolibro.studio.app")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("VideoLibro Studio")
    workspace = Path(__file__).resolve().parent
    icon_path = workspace / "assets" / "videolibro.ico"
    if not icon_path.exists():
        icon_path = workspace / "assets" / "videolibro.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    win = MainWindow(workspace)
    if icon_path.exists():
        win.setWindowIcon(QIcon(str(icon_path)))
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
