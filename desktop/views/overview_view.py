"""Vista d'inici: KPIs globals + top jugadors per modalitat."""
from __future__ import annotations

from collections import defaultdict

from PyQt6.QtWidgets import QHBoxLayout, QScrollArea, QTabWidget, QVBoxLayout, QWidget

from desktop.controllers import MainController
from desktop.models import Counts, RankingEntry
from desktop.views.widgets import KpiRow, SectionTitle, make_table, populate_table

KPI_LABELS = ["Clubs", "Jugadors", "Rànquings", "Partides", "Encontres lliga", "Temporades"]
RANKING_HEADERS = ["Pos", "Jugador", "fcb_id", "MJ", "MR", "C", "E", "P/PT", "Def"]


class OverviewView(QWidget):
    def __init__(self, controller: MainController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._build_ui()
        # Connexió signals (controller → view)
        self._controller.counts_loaded.connect(self._on_counts_loaded)
        self._controller.top_rankings_loaded.connect(self._on_rankings_loaded)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        root.addWidget(SectionTitle("Visió general"))
        self._kpis = KpiRow(KPI_LABELS)
        root.addWidget(self._kpis)

        root.addWidget(SectionTitle("Top 10 jugadors per modalitat (rànquing actual)"))
        self._tabs = QTabWidget()
        self._tabs.setObjectName("rankingTabs")
        root.addWidget(self._tabs, stretch=1)

    def request_data(self) -> None:
        """Es crida quan la pàgina es mostra. Demana dades al controller."""
        self._controller.request_counts()
        self._controller.request_top_rankings(top_n=10)

    # ---------- slots ----------

    def _on_counts_loaded(self, counts: Counts) -> None:
        self._kpis.set_values(
            {
                "Clubs": counts.clubs,
                "Jugadors": counts.players,
                "Rànquings": counts.rankings,
                "Partides": counts.games,
                "Encontres lliga": counts.encontres_lliga,
                "Temporades": counts.temporades,
            }
        )

    def _on_rankings_loaded(self, rankings: list[RankingEntry]) -> None:
        # Agrupar per modalitat
        by_mod: dict[str, list[RankingEntry]] = defaultdict(list)
        for r in rankings:
            by_mod[r.modalitat].append(r)
        # Reset tabs
        self._tabs.clear()
        for modalitat, entries in by_mod.items():
            table = make_table(RANKING_HEADERS)
            rows = [
                [
                    e.posicio,
                    e.nom,
                    e.fcb_id,
                    f"{e.mitjana:.4f}" if e.mitjana is not None else None,
                    f"{e.mitjana_contraris:.4f}" if e.mitjana_contraris is not None else None,
                    e.caramboles,
                    e.entrades,
                    f"{e.punts}/{e.punts_totals}"
                    if e.punts is not None and e.punts_totals is not None
                    else None,
                    "Sí" if e.definitiva else "No",
                ]
                for e in entries
            ]
            populate_table(table, rows)
            self._tabs.addTab(table, modalitat)
