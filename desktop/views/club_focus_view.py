"""Vista genèrica "Club Focus": dashboard per a un club real o virtual.

Generalitza BanyolesView. Funciona per a qualsevol selecció de jugadors:
- Club real  → prefixat amb 🏛
- Club virtual (selecció manual) → prefixat amb ⭐

Seccions:
1. Selector (focus + temporada actual).
2. KPIs agregats.
3. Llista de membres.
4. Actuacions destacades (grid 2×2 millors/pitjors).
5. Evolució de l'ordre al rànquing (QTabWidget per modalitat, gràfic + taula).
"""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from desktop.views.widgets import (
    KpiRow,
    SectionTitle,
    make_line_chart,
    make_table,
    populate_table,
)

# Tipus de selecció al combo
_KIND_REAL = "real"
_KIND_VIRTUAL = "virtual"

KPI_LABELS = ["Jugadors", "Partides", "Guanyades", "Perdudes", "% Victòria"]
PLAYERS_HEADERS = ["fcb_id", "Jugador", "Club", "Partides", "Seguit"]
GAMES_HEADERS = ["Data", "Modalitat", "Jugador", "Car", "E", "Mitj"]

DEFAULT_CLUB = "C.B.BANYOLES"


class ClubFocusView(QWidget):
    """Dashboard genèric de focus per a club real o virtual."""

    def __init__(
        self, controller: MainController, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller

        # Clau del focus carregat (evita resultats obsolets de workers anteriors).
        # Format: ("real", fcb_id) | ("virtual", vc_id:int)
        self._current_focus_key: tuple | None = None
        # Indica si el combo ja ha estat omplert
        self._combo_populated: bool = False

        self._build_ui()

    # ------------------------------------------------------------------
    # Construcció de la UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("clubFocusScroll")
        inner = QWidget()
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        root = QVBoxLayout(inner)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # ── Selector ──────────────────────────────────────────────────
        root.addWidget(SectionTitle("Focus de Club"))

        selector_row = QHBoxLayout()
        selector_row.setSpacing(12)

        lbl_focus = QLabel("Focus:")
        lbl_focus.setObjectName("fieldLabel")
        selector_row.addWidget(lbl_focus)

        self._combo = QComboBox()
        self._combo.setObjectName("focusCombo")
        self._combo.setMinimumWidth(280)
        self._combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        selector_row.addWidget(self._combo)

        self._chk_season = QCheckBox("Només temporada actual")
        self._chk_season.setChecked(True)
        selector_row.addWidget(self._chk_season)

        selector_row.addStretch(1)
        root.addLayout(selector_row)

        # ── KPIs ──────────────────────────────────────────────────────
        self._kpis = KpiRow(KPI_LABELS)
        root.addWidget(self._kpis)

        # ── Membres ───────────────────────────────────────────────────
        root.addWidget(SectionTitle("Membres del focus"))
        self._table_players = make_table(PLAYERS_HEADERS)
        self._table_players.setMinimumHeight(240)
        root.addWidget(self._table_players)

        # ── Actuacions destacades ──────────────────────────────────────
        root.addWidget(SectionTitle("Actuacions destacades"))
        grid = QGridLayout()
        grid.setSpacing(12)
        self._tbl_best = self._make_titled_table("🏆 Millors mitjanes", grid, 0, 0)
        self._tbl_best_won = self._make_titled_table("✅ Millors victòries", grid, 0, 1)
        self._tbl_worst = self._make_titled_table("📉 Pitjors mitjanes", grid, 1, 0)
        self._tbl_worst_lost = self._make_titled_table("❌ Pitjors derrotes", grid, 1, 1)
        root.addLayout(grid)

        # ── Evolució de l'ordre al rànquing ───────────────────────────
        root.addWidget(SectionTitle("Evolució de l'ordre al rànquing"))
        info_lbl = QLabel(
            "Ordre intern entre els jugadors del focus per cada publicació del rànquing "
            "(1 = el millor). Aquest ordre determina la composició dels equips per a la "
            "temporada vinent."
        )
        info_lbl.setWordWrap(True)
        root.addWidget(info_lbl)

        self._evolution_tabs = QTabWidget()
        self._evolution_tabs.setObjectName("evolutionTabs")
        self._evolution_tabs.setMinimumHeight(400)
        root.addWidget(self._evolution_tabs)

        root.addStretch(1)

        # Conectar senyals DESPRÉS de construir la UI
        self._combo.currentIndexChanged.connect(self._on_focus_changed)
        self._chk_season.toggled.connect(self._on_season_toggled)

    # ------------------------------------------------------------------
    # Helpers de construcció
    # ------------------------------------------------------------------

    def _make_titled_table(
        self, title: str, grid: QGridLayout, row: int, col: int
    ):
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        lbl = QLabel(title)
        lbl.setObjectName("subSectionTitle")
        v.addWidget(lbl)
        table = make_table(GAMES_HEADERS)
        table.setMinimumHeight(160)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        v.addWidget(table)
        grid.addWidget(container, row, col)
        return table

    # ------------------------------------------------------------------
    # Entrada pública
    # ------------------------------------------------------------------

    def request_data(self) -> None:
        """Crida inicial: omple el combo i dispara la càrrega del focus."""
        if self._combo_populated:
            # Ja poblat: només refresca el focus actual.
            self._trigger_focus_load()
            return
        # Poblar combo (necessita clubs reals + virtuals → dos workers en paral·lel).
        ds = self._controller.ds
        self._controller.run_query(
            lambda: (ds.clubs_with_kpis(), ds.list_virtual_clubs()),
            self._on_clubs_loaded,
        )

    # ------------------------------------------------------------------
    # Slots privats
    # ------------------------------------------------------------------

    def _on_clubs_loaded(self, result: tuple) -> None:
        """Rebut (clubs_reals, clubs_virtuals). Omple el combo."""
        real_clubs, virtual_clubs = result
        # Bloquejar signals mentre poblem per evitar disparar _on_focus_changed
        # per a cada addItem.
        self._combo.blockSignals(True)
        self._combo.clear()
        default_idx = 0
        idx = 0
        for club in real_clubs:
            self._combo.addItem(f"🏛 {club.nom}", userData=(_KIND_REAL, club.fcb_id))
            if club.fcb_id == DEFAULT_CLUB:
                default_idx = idx
            idx += 1
        for vc in virtual_clubs:
            self._combo.addItem(f"⭐ {vc.nom}", userData=(_KIND_VIRTUAL, vc.id))
            idx += 1
        self._combo_populated = True
        self._combo.blockSignals(False)
        # Seleccionar el default (dispara _on_focus_changed via setCurrentIndex)
        if self._combo.count() > 0:
            self._combo.setCurrentIndex(default_idx)
            # Si ja era a l'índex 0, currentIndexChanged no dispara → forçar.
            if default_idx == 0:
                self._on_focus_changed(0)

    def _on_focus_changed(self, _idx: int) -> None:
        """L'usuari ha canviat el focus al combo."""
        self._trigger_focus_load()

    def _on_season_toggled(self, _checked: bool) -> None:
        """L'usuari ha canviat el checkbox de temporada."""
        self._trigger_focus_load()

    def _trigger_focus_load(self) -> None:
        """Resol els player_ids del focus seleccionat i inicia les càrregues."""
        if self._combo.count() == 0:
            return
        data: Any = self._combo.currentData()
        if data is None:
            return
        kind, key = data
        season_only = self._chk_season.isChecked()

        focus_key = (kind, key, season_only)
        self._current_focus_key = focus_key

        ds = self._controller.ds

        if kind == _KIND_REAL:
            self._controller.run_query(
                lambda fid=key, so=season_only: ds.real_club_player_ids(fid, season_only=so),
                lambda ids, fk=focus_key: self._on_player_ids_resolved(ids, fk),
            )
        else:
            self._controller.run_query(
                lambda vid=key: ds.virtual_club_player_ids(vid),
                lambda ids, fk=focus_key: self._on_player_ids_resolved(ids, fk),
            )

    def _on_player_ids_resolved(
        self, player_ids: list[int], focus_key: tuple
    ) -> None:
        """Tenim els player_ids: llancem les càrregues paral·leles."""
        if focus_key != self._current_focus_key:
            return  # resultat obsolet
        if not player_ids:
            self._show_empty()
            return

        season_only = focus_key[2]
        ds = self._controller.ds

        # KPIs + best/worst en paral·lel
        self._controller.run_query(
            lambda ids=player_ids, so=season_only: ds.focus_summary(ids, season_only=so),
            lambda result, fk=focus_key: self._on_summary_loaded(result, fk),
        )
        self._controller.run_query(
            lambda ids=player_ids: ds.focus_players(ids),
            lambda result, fk=focus_key: self._on_players_loaded(result, fk),
        )
        self._controller.run_query(
            lambda ids=player_ids, so=season_only: ds.focus_best_worst_games(
                ids, season_only=so, top=10
            ),
            lambda result, fk=focus_key: self._on_best_worst_loaded(result, fk),
        )

        # Evolució per modalitat → primer cal les modalitats
        self._controller.run_query(
            ds.modalitats,
            lambda mods, ids=player_ids, fk=focus_key: self._on_modalitats_for_evolution(
                mods, ids, fk
            ),
        )

    def _on_modalitats_for_evolution(
        self,
        modalitats: list[tuple[int, str]],
        player_ids: list[int],
        focus_key: tuple,
    ) -> None:
        """Rebudes les modalitats: neteja les pestanyes i llança un worker per cadascuna."""
        if focus_key != self._current_focus_key:
            return
        # Netejar les pestanyes existents (hem de fer-ho al thread principal,
        # però aquest slot s'executa via signal des del worker thread → OK perquè
        # run_query usa connected signals i PyQt6 els emet al main thread).
        self._clear_evolution_tabs()

        ds = self._controller.ds
        for codi_fcb, nom_mod in modalitats:
            self._controller.run_query(
                lambda ids=player_ids, mod=codi_fcb: ds.focus_order_evolution(ids, mod),
                lambda result, mod_name=nom_mod, fk=focus_key: self._on_evolution_loaded(
                    result, mod_name, fk
                ),
            )

    def _clear_evolution_tabs(self) -> None:
        """Elimina totes les pestanyes de l'evolution_tabs."""
        while self._evolution_tabs.count() > 0:
            widget = self._evolution_tabs.widget(0)
            self._evolution_tabs.removeTab(0)
            if widget is not None:
                widget.deleteLater()

    def _show_empty(self) -> None:
        """Posa zeros a tots els widgets quan no hi ha jugadors."""
        self._kpis.set_values(
            {"Jugadors": 0, "Partides": 0, "Guanyades": 0, "Perdudes": 0, "% Victòria": "—"}
        )
        populate_table(self._table_players, [])
        populate_table(self._tbl_best, [])
        populate_table(self._tbl_best_won, [])
        populate_table(self._tbl_worst, [])
        populate_table(self._tbl_worst_lost, [])
        self._clear_evolution_tabs()

    # ── Slots de resultats ────────────────────────────────────────────

    def _on_summary_loaded(self, summary: dict, focus_key: tuple) -> None:
        if focus_key != self._current_focus_key:
            return
        total = summary.get("total", 0)
        g = summary.get("guanyades", 0)
        p = summary.get("perdudes", 0)
        num_j = summary.get("num_jugadors", 0)
        pct = f"{(g / total * 100):.1f}%" if total else "—"
        self._kpis.set_values(
            {
                "Jugadors": num_j,
                "Partides": total,
                "Guanyades": g,
                "Perdudes": p,
                "% Victòria": pct,
            }
        )

    def _on_players_loaded(
        self, players: list[PlayerKpi], focus_key: tuple
    ) -> None:
        if focus_key != self._current_focus_key:
            return
        rows = [
            [
                p.fcb_id,
                p.nom,
                p.club or "—",
                p.num_partides,
                "★" if p.seguiment else "",
            ]
            for p in players
        ]
        populate_table(self._table_players, rows)

    def _on_best_worst_loaded(self, bw: dict, focus_key: tuple) -> None:
        if focus_key != self._current_focus_key:
            return
        for key, table in (
            ("best", self._tbl_best),
            ("best_won", self._tbl_best_won),
            ("worst", self._tbl_worst),
            ("worst_lost", self._tbl_worst_lost),
        ):
            games = bw.get(key, [])
            rows = [
                [
                    g.get("data", ""),
                    g.get("modalitat", ""),
                    g.get("jugador_club", ""),
                    g.get("car_club", ""),
                    g.get("entrades", ""),
                    (
                        f"{g['mitj']:.3f}"
                        if g.get("mitj") is not None
                        else "—"
                    ),
                ]
                for g in games
            ]
            populate_table(table, rows)

    def _on_evolution_loaded(
        self, data: dict, mod_name: str, focus_key: tuple
    ) -> None:
        if focus_key != self._current_focus_key:
            return
        num_seqs: list[int] = data.get("num_seqs", [])
        rows: list[dict] = data.get("rows", [])

        # Crear sempre un widget nou (substituïm, no mutem)
        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setContentsMargins(8, 8, 8, 8)
        tab_layout.setSpacing(8)

        x_labels = [str(s) for s in num_seqs]

        if not num_seqs or not rows:
            empty_lbl = QLabel("Sense dades de rànquing per a aquest focus i modalitat.")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tab_layout.addWidget(empty_lbl)
        else:
            # Gràfic d'ordre intern (1 = millor → invert_y=True)
            series = [
                (r["player"], r["ordre_intern"])
                for r in rows
            ]
            chart_widget = make_line_chart(
                f"Ordre intern — {mod_name}",
                x_labels,
                series,
                invert_y=True,
                integer_y=True,
                y_title="Ordre",
            )
            tab_layout.addWidget(chart_widget)

            # Taula d'ordre intern
            tbl_headers = ["Jugador"] + x_labels
            tbl = make_table(tbl_headers)
            tbl.setMinimumHeight(160)
            tbl_rows = []
            for r in rows:
                row_vals: list = [r["player"]]
                for v in r["ordre_intern"]:
                    row_vals.append(v if v is not None else "—")
                tbl_rows.append(row_vals)
            populate_table(tbl, tbl_rows)
            tab_layout.addWidget(tbl)

        self._evolution_tabs.addTab(tab_widget, mod_name)
