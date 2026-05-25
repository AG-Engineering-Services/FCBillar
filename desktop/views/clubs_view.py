"""Vista de clubs: llista + drill-down per club."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from desktop.controllers import MainController
from desktop.models import ClubKpi, PlayerKpi
from desktop.views.widgets import KpiRow, SectionTitle, make_table, populate_table

CLUBS_HEADERS = ["Club", "Jugadors", "Equips", "Partides"]
PLAYERS_HEADERS = ["fcb_id", "Jugador", "Partides", "Seguit"]
KPI_LABELS = ["Total clubs", "Total jugadors", "Total partides"]


class ClubsView(QWidget):
    def __init__(self, controller: MainController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._selected_club: str | None = None
        self._build_ui()
        self._controller.clubs_loaded.connect(self._on_clubs_loaded)
        self._controller.club_players_loaded.connect(self._on_club_players_loaded)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)
        root.addWidget(SectionTitle("Clubs"))
        self._kpis = KpiRow(KPI_LABELS)
        root.addWidget(self._kpis)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, stretch=1)

        # Esquerra: taula de clubs
        left = QWidget()
        lay_left = QVBoxLayout(left)
        lay_left.setContentsMargins(0, 0, 0, 0)
        lay_left.addWidget(QLabel("Llistat (clica per veure jugadors)"))
        self._clubs_table = make_table(CLUBS_HEADERS)
        self._clubs_table.itemSelectionChanged.connect(self._on_club_selected)
        lay_left.addWidget(self._clubs_table, stretch=1)

        # Dreta: jugadors del club seleccionat
        right = QWidget()
        lay_right = QVBoxLayout(right)
        lay_right.setContentsMargins(0, 0, 0, 0)
        self._right_title = QLabel("Selecciona un club")
        self._right_title.setObjectName("sectionTitle")
        lay_right.addWidget(self._right_title)
        self._players_table = make_table(PLAYERS_HEADERS)
        lay_right.addWidget(self._players_table, stretch=1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

    def request_data(self) -> None:
        self._controller.request_clubs()

    # ---------- slots ----------

    def _on_clubs_loaded(self, clubs: list[ClubKpi]) -> None:
        self._kpis.set_values(
            {
                "Total clubs": len(clubs),
                "Total jugadors": sum(c.num_jugadors for c in clubs),
                "Total partides": sum(c.num_partides for c in clubs),
            }
        )
        rows = [[c.nom, c.num_jugadors, c.num_equips, c.num_partides] for c in clubs]
        populate_table(self._clubs_table, rows)
        # Guardo el fcb_id a la primera columna com a UserData per recuperar-lo en selecció.
        for i, c in enumerate(clubs):
            self._clubs_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, c.fcb_id)

    def _on_club_selected(self) -> None:
        items = self._clubs_table.selectedItems()
        if not items:
            return
        # La 1a cel·la de la fila té el fcb_id a UserRole.
        row = items[0].row()
        cell = self._clubs_table.item(row, 0)
        fcb_id = cell.data(Qt.ItemDataRole.UserRole)
        if not fcb_id:
            return
        self._selected_club = fcb_id
        self._right_title.setText(f"Jugadors de '{fcb_id}' (carregant…)")
        self._controller.request_club_players(fcb_id)

    def _on_club_players_loaded(self, club_fcb_id: str, players: list[PlayerKpi]) -> None:
        if club_fcb_id != self._selected_club:
            return  # selecció ha canviat mentrestant
        self._right_title.setText(f"Jugadors de '{club_fcb_id}' ({len(players)})")
        rows = [
            [p.fcb_id, p.nom, p.num_partides, "★" if p.seguiment else ""]
            for p in players
        ]
        populate_table(self._players_table, rows)
