"""FCBillar Desktop — entrypoint.

Executar amb:
    uv run python -m desktop.app
"""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from desktop.controllers import MainController
from desktop.models import DataSource
from desktop.styles import full_estils
from desktop.views import MainWindow


def main() -> int:
    # High-DPI ja és default a PyQt6 (no cal AA_UseHighDpiPixmaps).
    app = QApplication(sys.argv)
    app.setApplicationName("FCBillar Dashboard")
    app.setOrganizationName("FCBillar")
    # QSS aplicat a nivell de QApplication (iron law #3). El full surt dels
    # tokens d'AGenginyeria; vegeu desktop/styles/__init__.py.
    app.setStyleSheet(full_estils())

    data_source = DataSource()
    controller = MainController(data_source)
    window = MainWindow(controller)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
