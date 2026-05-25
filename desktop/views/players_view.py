"""Vista de jugadors: cerca + fitxa amb últimes partides."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from desktop.controllers import MainController
from desktop.models import GameRow, PlayerKpi
from desktop.views.widgets import SectionTitle, make_table, populate_table

PLAYERS_HEADERS = ["fcb_id", "Jugador", "Club", "Partides", "Seguit"]
GAMES_HEADERS = [
    "Data", "Modalitat", "Competicio",
    "Local", "C₁", "Visitant", "C₂", "E", "Àrbitre",
    "Club local", "Club visitant",
]


class PlayersView(QWidget):
    def __init__(self, controller: MainController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._selected_fcb: str | None = None
        self._build_ui()
        self._controller.players_loaded.connect(self._on_players_loaded)
        self._controller.player_games_loaded.connect(self._on_games_loaded)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)
        root.addWidget(SectionTitle("Jugadors"))

        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Cerca per nom o fcb_id…")
        self._search.returnPressed.connect(self._on_search_clicked)
        search_btn = QPushButton("Cercar")
        search_btn.clicked.connect(self._on_search_clicked)
        search_row.addWidget(self._search, stretch=1)
        search_row.addWidget(search_btn)
        root.addLayout(search_row)

        splitter = QSplitter(Qt.Orientation.Vertical)
        root.addWidget(splitter, stretch=1)

        # Dalt: taula de jugadors
        top = QWidget()
        lay_top = QVBoxLayout(top)
        lay_top.setContentsMargins(0, 0, 0, 0)
        lay_top.addWidget(QLabel("Resultats (clica per veure partides)"))
        self._players_table = make_table(PLAYERS_HEADERS)
        self._players_table.itemSelectionChanged.connect(self._on_player_selected)
        lay_top.addWidget(self._players_table)

        # Baix: partides del jugador seleccionat
        bottom = QWidget()
        lay_bot = QVBoxLayout(bottom)
        lay_bot.setContentsMargins(0, 0, 0, 0)
        self._games_title = QLabel("Selecciona un jugador per veure les seves partides")
        self._games_title.setObjectName("sectionTitle")
        lay_bot.addWidget(self._games_title)
        self._games_table = make_table(GAMES_HEADERS)
        lay_bot.addWidget(self._games_table)

        splitter.addWidget(top)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

    def request_data(self) -> None:
        self._controller.request_players(query="")

    # ---------- slots ----------

    def _on_search_clicked(self) -> None:
        self._controller.request_players(query=self._search.text(), limit=500)

    def _on_players_loaded(self, players: list[PlayerKpi]) -> None:
        rows = [
            [p.fcb_id, p.nom, p.club or "", p.num_partides, "★" if p.seguiment else ""]
            for p in players
        ]
        populate_table(self._players_table, rows)
        for i, p in enumerate(players):
            self._players_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, (p.fcb_id, p.nom))

    def _on_player_selected(self) -> None:
        items = self._players_table.selectedItems()
        if not items:
            return
        row = items[0].row()
        cell = self._players_table.item(row, 0)
        data = cell.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        fcb_id, nom = data
        self._selected_fcb = fcb_id
        self._games_title.setText(f"Últimes partides de {nom} (carregant…)")
        self._controller.request_player_games(fcb_id, limit=100)

    def _on_games_loaded(self, fcb_id: str, games: list[GameRow]) -> None:
        if fcb_id != self._selected_fcb:
            return
        self._games_title.setText(f"Últimes {len(games)} partides ({fcb_id})")
        rows = [
            [
                g.data, g.modalitat, g.competicio,
                g.local, g.cara1, g.visitant, g.cara2,
                g.entrades, g.arbitre,
                g.club_local, g.club_visitant,
            ]
            for g in games
        ]
        populate_table(self._games_table, rows)
