"""Vista de partides: cercador global amb filtres per jugador, club, modalitat i competició."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.controllers import MainController
from desktop.models import GameRow
from desktop.views.widgets import SectionTitle, make_table, populate_table

GAMES_HEADERS = [
    "Data", "Modalitat", "Competició",
    "Local", "C₁", "Visitant", "C₂", "E",
    "Club local", "Club visitant",
]

_COMPETICIONS = [
    ("Totes", ""),
    ("LLIGA", "LLIGA"),
    ("INDIVIDUAL", "INDIVIDUAL"),
    ("COPA", "COPA"),
]


class PartidesView(QWidget):
    def __init__(self, controller: MainController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)
        root.addWidget(SectionTitle("Partides"))

        # ── Barra de filtres ──────────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        # Jugador
        filter_row.addWidget(QLabel("Jugador:"))
        self._jugador_edit = QLineEdit()
        self._jugador_edit.setPlaceholderText("Nom (substring)…")
        self._jugador_edit.setMinimumWidth(140)
        self._jugador_edit.returnPressed.connect(self._on_search)
        filter_row.addWidget(self._jugador_edit)

        # Club
        filter_row.addWidget(QLabel("Club:"))
        self._club_edit = QLineEdit()
        self._club_edit.setPlaceholderText("Club (substring)…")
        self._club_edit.setMinimumWidth(130)
        self._club_edit.returnPressed.connect(self._on_search)
        filter_row.addWidget(self._club_edit)

        # Modalitat
        filter_row.addWidget(QLabel("Modalitat:"))
        self._modalitat_combo = QComboBox()
        self._modalitat_combo.addItem("Totes", None)
        # Poblarem amb ds.modalitats() en request_data()
        filter_row.addWidget(self._modalitat_combo)

        # Competició
        filter_row.addWidget(QLabel("Competició:"))
        self._competicio_combo = QComboBox()
        for label, value in _COMPETICIONS:
            self._competicio_combo.addItem(label, value)
        filter_row.addWidget(self._competicio_combo)

        # Checkbox temporada actual
        self._season_check = QCheckBox("Només temporada actual")
        filter_row.addWidget(self._season_check)

        # Botó Cercar
        cercar_btn = QPushButton("Cercar")
        cercar_btn.clicked.connect(self._on_search)
        filter_row.addWidget(cercar_btn)

        filter_row.addStretch()
        root.addLayout(filter_row)

        # ── Comptador ─────────────────────────────────────────────────────
        self._count_label = QLabel("0 partides")
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        root.addWidget(self._count_label)

        # ── Taula de resultats ────────────────────────────────────────────
        self._table = make_table(GAMES_HEADERS)
        root.addWidget(self._table, stretch=1)

    def request_data(self) -> None:
        """Càrrega inicial quan es mostra la vista: cerca sense filtres (limit 300)."""
        # Poblar el combo de modalitats la primera vegada
        if self._modalitat_combo.count() == 1:
            try:
                mods = self._controller.ds.modalitats()
            except Exception:
                mods = []
            for codi, nom in mods:
                self._modalitat_combo.addItem(nom, codi)

        self._run_search()

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_search(self) -> None:
        self._run_search()

    def _run_search(self) -> None:
        player = self._jugador_edit.text().strip()
        club = self._club_edit.text().strip()
        modalitat_codi: int | None = self._modalitat_combo.currentData()
        competicio: str = self._competicio_combo.currentData() or ""
        season_only: bool = self._season_check.isChecked()

        def task() -> list[GameRow]:
            return self._controller.ds.search_games(
                player=player,
                club=club,
                modalitat_codi_fcb=modalitat_codi,
                competicio=competicio,
                season_only=season_only,
                limit=300,
            )

        self._count_label.setText("Carregant…")
        self._controller.run_query(task, self._on_results)

    def _on_results(self, games: list[GameRow]) -> None:
        n = len(games)
        self._count_label.setText(f"{n} partida{'s' if n != 1 else ''}")
        rows = [
            [
                g.data,
                g.modalitat,
                g.competicio or "",
                g.local,
                g.cara1,
                g.visitant,
                g.cara2,
                g.entrades,
                g.club_local or "",
                g.club_visitant or "",
            ]
            for g in games
        ]
        populate_table(self._table, rows)
