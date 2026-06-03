"""Finestra principal amb sidebar de navegació + stack de vistes."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QWidget,
)

from desktop.controllers import MainController
from desktop.views.club_focus_view import ClubFocusView
from desktop.views.clubs_view import ClubsView
from desktop.views.overview_view import OverviewView
from desktop.views.partides_view import PartidesView
from desktop.views.players_view import PlayersView
from desktop.views.rankings_view import RankingsView
from desktop.views.results_view import ResultsView
from desktop.views.scraping_view import ScrapingView
from desktop.views.virtual_clubs_view import VirtualClubsView

SIDEBAR_ITEMS = [
    ("Inici", "🏠"),
    ("Rànquings", "🏆"),
    ("Jugadors", "👤"),
    ("Partides", "🎱"),
    ("Resultats", "📊"),
    ("Clubs", "🏛"),
    ("Focus club", "⭐"),
    ("Clubs virtuals", "🧩"),
    ("Scraping", "🔄"),
]


class MainWindow(QMainWindow):
    def __init__(self, controller: MainController) -> None:
        super().__init__()
        self._controller = controller
        self.setWindowTitle("FCBillar — Dashboard")
        self.resize(1360, 860)
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
        self._sidebar.setFixedWidth(210)
        self._sidebar.setSpacing(2)
        for label, icon in SIDEBAR_ITEMS:
            item = QListWidgetItem(f"  {icon}   {label}")
            self._sidebar.addItem(item)
        self._sidebar.currentRowChanged.connect(self._on_nav_changed)
        root.addWidget(self._sidebar)

        # Stack — mateix ordre que SIDEBAR_ITEMS
        self._stack = QStackedWidget()
        self._views = [
            OverviewView(self._controller),
            RankingsView(self._controller),
            PlayersView(self._controller),
            PartidesView(self._controller),
            ResultsView(self._controller),
            ClubsView(self._controller),
            ClubFocusView(self._controller),
            VirtualClubsView(self._controller),
            ScrapingView(),
        ]
        for view in self._views:
            self._stack.addWidget(view)
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
