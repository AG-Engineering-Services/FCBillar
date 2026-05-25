"""Vista dedicada a C.B. BANYOLES."""
from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from desktop.controllers import MainController
from desktop.models import PlayerKpi
from desktop.views.widgets import KpiRow, SectionTitle, make_table, populate_table

CLUB_FCB_ID = "C.B.BANYOLES"
KPI_LABELS = ["Jugadors", "Partides totals", "Seguits"]
PLAYERS_HEADERS = ["fcb_id", "Jugador", "Partides", "Seguit"]


class BanyolesView(QWidget):
    def __init__(self, controller: MainController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._build_ui()
        self._controller.club_players_loaded.connect(self._on_players_loaded)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)
        root.addWidget(SectionTitle(f"Focus: {CLUB_FCB_ID}"))
        info = QLabel(
            "Aquesta pàgina mostra els jugadors detectats com a equip de Banyoles a la "
            "lliga catalana (via games.equip_id). Requereix ingest previ "
            "(`ingest-lliga-grup` o `import-temporada`)."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        self._kpis = KpiRow(KPI_LABELS)
        root.addWidget(self._kpis)

        root.addWidget(SectionTitle("Jugadors"))
        self._table = make_table(PLAYERS_HEADERS)
        root.addWidget(self._table, stretch=1)

    def request_data(self) -> None:
        self._controller.request_club_players(CLUB_FCB_ID)

    # ---------- slots ----------

    def _on_players_loaded(self, club_fcb_id: str, players: list[PlayerKpi]) -> None:
        if club_fcb_id != CLUB_FCB_ID:
            return
        self._kpis.set_values(
            {
                "Jugadors": len(players),
                "Partides totals": sum(p.num_partides for p in players),
                "Seguits": sum(1 for p in players if p.seguiment),
            }
        )
        rows = [
            [p.fcb_id, p.nom, p.num_partides, "★" if p.seguiment else ""]
            for p in players
        ]
        populate_table(self._table, rows)
