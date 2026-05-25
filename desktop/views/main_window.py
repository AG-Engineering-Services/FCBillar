"""Finestra principal amb sidebar de navegació + stack de vistes."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from desktop.controllers import MainController
from desktop.views.banyoles_view import BanyolesView
from desktop.views.clubs_view import ClubsView
from desktop.views.overview_view import OverviewView
from desktop.views.players_view import PlayersView

SIDEBAR_ITEMS = [
    ("Inici", "🏠"),
    ("Clubs", "🏛"),
    ("Jugadors", "👤"),
    ("Banyoles", "⭐"),
]


class MainWindow(QMainWindow):
    def __init__(self, controller: MainController) -> None:
        super().__init__()
        self._controller = controller
        self.setWindowTitle("FCBillar — Dashboard")
        self.resize(1280, 800)
        self._build_ui()
        # Errors centralitzats
        self._controller.error_occurred.connect(self._on_error)
        # Càrrega inicial
        self._on_nav_changed(0)

    def _build_ui(self) -> None:
        # Layout: sidebar | stack de vistes
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        self._sidebar = QListWidget()
        self._sidebar.setObjectName("sidebar")
        self._sidebar.setFixedWidth(200)
        self._sidebar.setSpacing(2)
        for label, icon in SIDEBAR_ITEMS:
            item = QListWidgetItem(f"  {icon}   {label}")
            self._sidebar.addItem(item)
        self._sidebar.currentRowChanged.connect(self._on_nav_changed)
        root.addWidget(self._sidebar)

        # Stack
        self._stack = QStackedWidget()
        self._overview = OverviewView(self._controller)
        self._clubs = ClubsView(self._controller)
        self._players = PlayersView(self._controller)
        self._banyoles = BanyolesView(self._controller)
        self._stack.addWidget(self._overview)
        self._stack.addWidget(self._clubs)
        self._stack.addWidget(self._players)
        self._stack.addWidget(self._banyoles)
        root.addWidget(self._stack, stretch=1)

        self.setCentralWidget(central)
        self._sidebar.setCurrentRow(0)

        # Status bar
        status = QStatusBar()
        self.setStatusBar(status)
        status.showMessage("Llest")

    # ---------- slots ----------

    def _on_nav_changed(self, idx: int) -> None:
        if idx < 0:
            return
        self._stack.setCurrentIndex(idx)
        # Trigger càrrega de dades de la vista seleccionada.
        view = self._stack.currentWidget()
        request = getattr(view, "request_data", None)
        if callable(request):
            request()

    def _on_error(self, msg: str) -> None:
        self.statusBar().showMessage(f"Error: {msg}", 8000)
        QMessageBox.warning(self, "Error", msg)
