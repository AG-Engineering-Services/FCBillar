"""Vista de resultats: classificació de lliga, copa i individuals."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from desktop.controllers import MainController
from desktop.models import GameRow, StandingRow, TorneigRow
from desktop.views.widgets import SectionTitle, make_table, populate_table

# ── Lliga ────────────────────────────────────────────────────────────────────
LLIGA_HEADERS = ["Pos", "Equip", "PJ", "G", "E", "P", "Punts", "PF", "PC"]

# ── Copa ─────────────────────────────────────────────────────────────────────
COPA_HEADERS = [
    "Data", "Modalitat", "Local", "C₁", "Visitant", "C₂",
    "E", "Club local", "Club visitant",
]

# ── Individuals ───────────────────────────────────────────────────────────────
INDIV_HEADERS = [
    "Pos", "Jugador", "Club", "PJ", "Punts", "C", "E",
    "MG", "MP", "Sèrie",
]


class ResultsView(QWidget):
    """Vista de resultats esportius: Lliga, Copa i Individuals."""

    def __init__(
        self, controller: MainController, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._build_ui()

    # ──────────────────────────────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)
        root.addWidget(SectionTitle("Resultats"))

        self._tabs = QTabWidget()
        root.addWidget(self._tabs, stretch=1)

        self._tabs.addTab(self._build_lliga_tab(), "Lliga")
        self._tabs.addTab(self._build_copa_tab(), "Copa")
        self._tabs.addTab(self._build_individuals_tab(), "Individuals")

    # ── Tab 1: Lliga ──────────────────────────────────────────────────────────

    def _build_lliga_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # Controls
        controls = QHBoxLayout()
        self._lliga_season_chk = QCheckBox("Només temporada actual")
        self._lliga_season_chk.setChecked(True)
        self._lliga_season_chk.toggled.connect(self._on_lliga_season_toggled)

        self._lliga_group_combo = QComboBox()
        self._lliga_group_combo.setMinimumWidth(320)
        self._lliga_group_combo.currentIndexChanged.connect(
            self._on_lliga_group_changed
        )

        controls.addWidget(self._lliga_season_chk)
        controls.addWidget(self._lliga_group_combo, stretch=1)
        controls.addStretch()
        lay.addLayout(controls)

        # Standings table
        self._lliga_table = make_table(LLIGA_HEADERS)
        lay.addWidget(self._lliga_table, stretch=1)
        return w

    # ── Tab 2: Copa ───────────────────────────────────────────────────────────

    def _build_copa_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # Controls
        controls = QHBoxLayout()
        self._copa_season_chk = QCheckBox("Només temporada actual")
        self._copa_season_chk.setChecked(True)
        self._copa_season_chk.toggled.connect(self._on_copa_season_toggled)

        self._copa_count_lbl = QLabel("0 partides")

        controls.addWidget(self._copa_season_chk)
        controls.addStretch()
        controls.addWidget(self._copa_count_lbl)
        lay.addLayout(controls)

        self._copa_table = make_table(COPA_HEADERS)
        lay.addWidget(self._copa_table, stretch=1)
        return w

    # ── Tab 3: Individuals ────────────────────────────────────────────────────

    def _build_individuals_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # Selectors
        sel_row = QHBoxLayout()

        self._indiv_season_combo = QComboBox()
        self._indiv_season_combo.setMinimumWidth(140)
        self._indiv_season_combo.currentIndexChanged.connect(
            self._on_indiv_season_changed
        )

        self._indiv_torneig_combo = QComboBox()
        self._indiv_torneig_combo.setMinimumWidth(320)
        self._indiv_torneig_combo.currentIndexChanged.connect(
            self._on_indiv_torneig_changed
        )

        sel_row.addWidget(QLabel("Temporada:"))
        sel_row.addWidget(self._indiv_season_combo)
        sel_row.addWidget(QLabel("Torneig:"))
        sel_row.addWidget(self._indiv_torneig_combo, stretch=1)
        sel_row.addStretch()
        lay.addLayout(sel_row)

        self._indiv_table = make_table(INDIV_HEADERS)
        lay.addWidget(self._indiv_table, stretch=1)
        return w

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def request_data(self) -> None:
        """Inicia la carrega inicial de totes les pestanyes."""
        self._load_lliga_groups()
        self._load_copa()
        self._load_indiv_seasons()

    # ──────────────────────────────────────────────────────────────────────────
    # Lliga helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _load_lliga_groups(self) -> None:
        season_only = self._lliga_season_chk.isChecked()
        ds = self._controller.ds
        self._controller.run_query(
            lambda: ds.lliga_groups(season_only=season_only),
            self._on_lliga_groups_loaded,
        )

    def _on_lliga_groups_loaded(self, groups: list[dict]) -> None:
        combo = self._lliga_group_combo
        combo.blockSignals(True)
        combo.clear()
        for g in groups:
            label = (
                f"Lliga {g['lliga_id']} · Div {g['divisio_id']} "
                f"· Grup {g['grup_id']} ({g['n_encontres']} enc.)"
            )
            combo.addItem(label, (g["lliga_id"], g["divisio_id"], g["grup_id"]))
        combo.blockSignals(False)

        # Carrega les standings del primer grup si n'hi ha
        if combo.count() > 0:
            self._load_lliga_standings(combo.currentData())

    def _load_lliga_standings(self, key: tuple[int, int, int] | None) -> None:
        if key is None:
            return
        lliga_id, divisio_id, grup_id = key
        ds = self._controller.ds
        self._controller.run_query(
            lambda: ds.lliga_standings(lliga_id, divisio_id, grup_id),
            self._on_lliga_standings_loaded,
        )

    def _on_lliga_standings_loaded(self, standings: list[StandingRow]) -> None:
        rows = [
            [
                s.posicio, s.equip, s.pj, s.g, s.e, s.p,
                s.punts, s.parcials_favor, s.parcials_contra,
            ]
            for s in standings
        ]
        populate_table(self._lliga_table, rows)

    # ──────────────────────────────────────────────────────────────────────────
    # Copa helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _load_copa(self) -> None:
        season_only = self._copa_season_chk.isChecked()
        ds = self._controller.ds
        self._controller.run_query(
            lambda: ds.copa_games(season_only=season_only),
            self._on_copa_loaded,
        )

    def _on_copa_loaded(self, games: list[GameRow]) -> None:
        rows = [
            [
                g.data, g.modalitat, g.local, g.cara1,
                g.visitant, g.cara2, g.entrades,
                g.club_local, g.club_visitant,
            ]
            for g in games
        ]
        populate_table(self._copa_table, rows)
        self._copa_count_lbl.setText(f"{len(games)} partides")

    # ──────────────────────────────────────────────────────────────────────────
    # Individuals helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _load_indiv_seasons(self) -> None:
        ds = self._controller.ds
        self._controller.run_query(
            ds.individuals_seasons,
            self._on_indiv_seasons_loaded,
        )

    def _on_indiv_seasons_loaded(self, seasons: list[str]) -> None:
        combo = self._indiv_season_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Totes", None)
        for s in seasons:
            combo.addItem(s, s)
        combo.blockSignals(False)

        # Despres de carregar temporades, carreguem la llista de torneigs
        selected_season = combo.currentData()
        self._load_indiv_torneigs(selected_season)

    def _load_indiv_torneigs(self, temporada: str | None) -> None:
        ds = self._controller.ds
        self._controller.run_query(
            lambda: ds.individuals_list(temporada=temporada),
            self._on_indiv_torneigs_loaded,
        )

    def _on_indiv_torneigs_loaded(self, torneigs: list[TorneigRow]) -> None:
        combo = self._indiv_torneig_combo
        combo.blockSignals(True)
        combo.clear()
        for t in torneigs:
            label = f"{t.nom} ({t.num_participants})"
            combo.addItem(label, t.id)
        combo.blockSignals(False)

        # Carrega la classificacio del primer torneig si n'hi ha
        if combo.count() > 0:
            torneig_id = combo.currentData()
            if torneig_id is not None:
                self._load_indiv_classification(torneig_id)
        else:
            populate_table(self._indiv_table, [])

    def _load_indiv_classification(self, torneig_id: int) -> None:
        ds = self._controller.ds
        self._controller.run_query(
            lambda: ds.individual_classification(torneig_id),
            self._on_indiv_classification_loaded,
        )

    def _on_indiv_classification_loaded(self, entries: list[dict]) -> None:
        rows = []
        for e in entries:
            mg = e.get("mitjana_general")
            mp = e.get("mitjana_particular")
            rows.append([
                e.get("posicio"),
                e.get("nom"),
                e.get("club_text"),
                e.get("partides_jugades"),
                e.get("punts"),
                e.get("caramboles"),
                e.get("entrades"),
                f"{mg:.4f}" if mg is not None else None,
                f"{mp:.4f}" if mp is not None else None,
                e.get("serie_max"),
            ])
        populate_table(self._indiv_table, rows)

    # ──────────────────────────────────────────────────────────────────────────
    # Slots (combo / checkbox changes)
    # ──────────────────────────────────────────────────────────────────────────

    def _on_lliga_season_toggled(self, _checked: bool) -> None:
        populate_table(self._lliga_table, [])
        self._load_lliga_groups()

    def _on_lliga_group_changed(self, _index: int) -> None:
        key = self._lliga_group_combo.currentData()
        if key is not None:
            self._load_lliga_standings(key)

    def _on_copa_season_toggled(self, _checked: bool) -> None:
        self._load_copa()

    def _on_indiv_season_changed(self, _index: int) -> None:
        temporada = self._indiv_season_combo.currentData()
        populate_table(self._indiv_table, [])
        self._load_indiv_torneigs(temporada)

    def _on_indiv_torneig_changed(self, _index: int) -> None:
        torneig_id = self._indiv_torneig_combo.currentData()
        if torneig_id is not None:
            self._load_indiv_classification(torneig_id)
        else:
            populate_table(self._indiv_table, [])
