"""FCBillar Desktop — entrypoint.

Executar amb:
    uv run python -m desktop.app
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from desktop.controllers import MainController
from desktop.models import DataSource
from desktop.views import MainWindow

STYLES_PATH = Path(__file__).resolve().parent / "styles" / "theme.qss"


def main() -> int:
    # High-DPI rendering correcte a Windows; cal abans del QApplication.
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("FCBillar Dashboard")
    app.setOrganizationName("FCBillar")
    # QSS aplicat a nivell de QApplication (iron law #3).
    app.setStyleSheet(STYLES_PATH.read_text(encoding="utf-8"))

    data_source = DataSource()
    controller = MainController(data_source)
    window = MainWindow(controller)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
