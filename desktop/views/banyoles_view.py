"""Vista dedicada a C.B. BANYOLES enriquida.

KPIs agregats de la temporada actual + jugadors actius + millors/pitjors
partides (del conjunt del club).
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from desktop.controllers import MainController
from desktop.models import PlayerKpi
from desktop.workers import QueryWorker
from desktop.views.widgets import KpiCard, KpiRow, SectionTitle, make_table, populate_table

MODALITATS = [(1, "Tres bandes"), (2, "Lliure"), (4, "Banda"), (3, "Quadre 47/2"), (6, "Quadre 71/2")]

CLUB_FCB_ID = "C.B.BANYOLES"
KPI_LABELS = ["Jugadors actius", "Partides", "Guanyades", "Perdudes", "% Victòria"]
PLAYERS_HEADERS = ["fcb_id", "Jugador", "Partides", "Seguit"]
GAMES_HEADERS = ["Data", "Modalitat", "Jugador", "Car", "E", "Mitj"]


class BanyolesView(QWidget):
    def __init__(self, controller: MainController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._workers: list[QueryWorker] = []
        self._evolution_tables: dict[int, "QTableWidget"] = {}  # modalitat → taula
        self._build_ui()
        self._controller.club_players_loaded.connect(self._on_players_loaded)
        self._controller.club_evolution_loaded.connect(self._on_evolution_loaded)

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("banyolesScroll")
        inner = QWidget()
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        root = QVBoxLayout(inner)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        root.addWidget(SectionTitle(f"Focus: {CLUB_FCB_ID} — temporada en curs"))
        info = QLabel(
            "KPIs agregats de tots els equips de Banyoles a la temporada més recent "
            "registrada. Inclou jugadors actius, balanç global de partides i les "
            "actuacions destacades."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        self._kpis = KpiRow(KPI_LABELS)
        root.addWidget(self._kpis)

        # 4 taules de millors/pitjors partides en grid 2x2
        root.addWidget(SectionTitle("Actuacions destacades (temporada actual)"))
        grid = QGridLayout()
        grid.setSpacing(12)
        self._tbl_best = self._make_titled_table("🏆 Millors mitjanes", grid, 0, 0)
        self._tbl_best_won = self._make_titled_table("✅ Millors victòries", grid, 0, 1)
        self._tbl_worst = self._make_titled_table("📉 Pitjors mitjanes", grid, 1, 0)
        self._tbl_worst_lost = self._make_titled_table("❌ Pitjors derrotes", grid, 1, 1)
        root.addLayout(grid)

        # Evolució de mitjanes per rànquing — pestanyes per modalitat
        root.addWidget(SectionTitle("Evolució de mitjana per rànquing"))
        info_evol = QLabel(
            "Files = jugadors actius del club. Columnes = num_seq dels rànquings "
            "publicats (16 més recents). Cel·les = mitjana general del jugador."
        )
        info_evol.setWordWrap(True)
        root.addWidget(info_evol)
        self._evolution_tabs = QTabWidget()
        self._evolution_tabs.setObjectName("evolutionTabs")
        self._evolution_tabs.setMinimumHeight(300)
        root.addWidget(self._evolution_tabs)

        # Jugadors actius
        root.addWidget(SectionTitle("Jugadors actius aquesta temporada"))
        self._table_players = make_table(PLAYERS_HEADERS)
        self._table_players.setMinimumHeight(300)
        root.addWidget(self._table_players)
        root.addStretch(1)

    def _make_titled_table(self, title: str, grid: QGridLayout, row: int, col: int):
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        lbl = QLabel(title)
        lbl.setObjectName("subSectionTitle")
        v.addWidget(lbl)
        table = make_table(GAMES_HEADERS)
        table.setMinimumHeight(170)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        v.addWidget(table)
        grid.addWidget(container, row, col)
        return table

    def request_data(self) -> None:
        # Jugadors actius via signal global del controller.
        self._controller.request_club_players(CLUB_FCB_ID, current_season_only=True)
        # Summary + best/worst via workers locals que llegeixen DataSource.
        ds = self._controller._ds  # accés directe al DS (read-only)
        # Summary
        w = QueryWorker(lambda: ds.club_summary(CLUB_FCB_ID, current_season_only=True))
        w.finished_with_result.connect(self._on_summary_loaded)
        w.finished.connect(lambda: self._workers.remove(w))
        self._workers.append(w)
        w.start()
        # Best/worst
        w2 = QueryWorker(
            lambda: ds.club_best_worst_games(CLUB_FCB_ID, current_season_only=True, top=10)
        )
        w2.finished_with_result.connect(self._on_best_worst_loaded)
        w2.finished.connect(lambda: self._workers.remove(w2))
        self._workers.append(w2)
        w2.start()
        # Evolució per modalitat
        for mod, _label in MODALITATS:
            self._controller.request_club_evolution(CLUB_FCB_ID, mod)

    # ---------- slots ----------

    def _on_players_loaded(self, club_fcb_id: str, players: list[PlayerKpi]) -> None:
        if club_fcb_id != CLUB_FCB_ID:
            return
        rows = [
            [p.fcb_id, p.nom, p.num_partides, "★" if p.seguiment else ""]
            for p in players
        ]
        populate_table(self._table_players, rows)
        # Si encara no tenim summary, actualitzem només el comptador de jugadors.
        if self._kpis._cards["Jugadors actius"]._value.text() == "—":
            self._kpis.set_values({"Jugadors actius": len(players)})

    def _on_summary_loaded(self, summary: dict) -> None:
        total = summary.get("total", 0)
        g = summary.get("guanyades", 0)
        p = summary.get("perdudes", 0)
        pct = f"{(g / total * 100):.1f}%" if total else "—"
        # Jugadors actius pot venir del signal players (mantenim si ja calculat).
        cards = {
            "Partides": total,
            "Guanyades": g,
            "Perdudes": p,
            "% Victòria": pct,
        }
        self._kpis.set_values(cards)

    def _on_evolution_loaded(self, club_fcb_id: str, modalitat: int, data: dict) -> None:
        if club_fcb_id != CLUB_FCB_ID:
            return
        seqs = data.get("num_seqs", [])
        rows = data.get("rows", [])
        if not seqs or not rows:
            return
        # Crear/actualitzar la pestanya per a aquesta modalitat.
        # Si ja existeix taula per a aquesta modalitat, només actualitzem dades.
        if modalitat in self._evolution_tables:
            table = self._evolution_tables[modalitat]
        else:
            headers = ["Jugador"] + [str(s) for s in seqs]
            table = make_table(headers)
            table.setAlternatingRowColors(True)
            self._evolution_tables[modalitat] = table
            label = next((l for m, l in MODALITATS if m == modalitat), str(modalitat))
            self._evolution_tabs.addTab(table, label)
        # Format de fila: nom + mitjanes (4 decimals si presents)
        data_rows = []
        for r in rows:
            vals = [r["player"]]
            for v in r["mitjanes"]:
                vals.append(f"{v:.4f}" if v is not None else "—")
            data_rows.append(vals)
        populate_table(table, data_rows)

    def _on_best_worst_loaded(self, bw: dict) -> None:
        for key, table in (
            ("best", self._tbl_best),
            ("best_won", self._tbl_best_won),
            ("worst", self._tbl_worst),
            ("worst_lost", self._tbl_worst_lost),
        ):
            games = bw.get(key, [])
            rows = [
                [
                    g["data"], g["modalitat"], g["jugador_club"],
                    g["car_club"], g["entrades"],
                    f"{g['mitj']:.3f}" if g.get("mitj") is not None else "—",
                ]
                for g in games
            ]
            populate_table(table, rows)
