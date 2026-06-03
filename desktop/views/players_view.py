"""Vista de jugadors: cerca + fitxa completa del jugador seleccionat."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from desktop.controllers import MainController
from desktop.models import GameRow, PlayerKpi
from desktop.views.widgets import (
    KpiRow,
    SectionTitle,
    make_line_chart,
    make_table,
    populate_table,
)

# ─── capçaleres de les taules ────────────────────────────────────────────────

PLAYERS_HEADERS = ["fcb_id", "Jugador", "Club", "Partides", "Seguit"]
GAMES_HEADERS = [
    "Data", "Modalitat", "Competició",
    "Local", "C₁", "Visitant", "C₂", "E",
    "Club local", "Club visitant",
]
BW_HEADERS = ["Data", "Modalitat", "Local", "C₁", "Visitant", "C₂", "E"]


def _gamerow_to_bw_row(g: GameRow) -> list:
    return [g.data, g.modalitat, g.local, g.cara1, g.visitant, g.cara2, g.entrades]


def _gamerow_to_full_row(g: GameRow) -> list:
    return [
        g.data, g.modalitat, g.competicio,
        g.local, g.cara1, g.visitant, g.cara2, g.entrades,
        g.club_local, g.club_visitant,
    ]


# ─── vista principal ──────────────────────────────────────────────────────────

class PlayersView(QWidget):
    def __init__(self, controller: MainController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._selected_fcb: str | None = None
        # (codi_fcb, nom) de cada ítem del combo; —1 = totes
        self._modalitats: list[tuple[int, str]] = []
        # widget del gràfic d'evolució actual (per poder-lo substituir)
        self._chart_widget: QWidget | None = None
        self._build_ui()
        # Connectem els signals clàssics per a la llista de jugadors
        self._controller.players_loaded.connect(self._on_players_loaded)

    # ──────────────────────────────────────────────────────────────────────────
    # Construcció de la UI
    # ──────────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)
        root.addWidget(SectionTitle("Jugadors"))

        # Fila de cerca
        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Cerca per nom o fcb_id…")
        self._search.returnPressed.connect(self._on_search_clicked)
        search_btn = QPushButton("Cercar")
        search_btn.clicked.connect(self._on_search_clicked)
        search_row.addWidget(self._search, stretch=1)
        search_row.addWidget(search_btn)
        root.addLayout(search_row)

        # Divisor vertical: dalt = taula resultats, baix = perfil (scroll)
        splitter = QSplitter(Qt.Orientation.Vertical)
        root.addWidget(splitter, stretch=1)

        # ── Part superior: taula de resultats ────────────────────────────────
        top_widget = QWidget()
        lay_top = QVBoxLayout(top_widget)
        lay_top.setContentsMargins(0, 0, 0, 0)
        lay_top.addWidget(QLabel("Resultats (clica un jugador per veure el seu perfil)"))
        self._players_table = make_table(PLAYERS_HEADERS)
        self._players_table.itemSelectionChanged.connect(self._on_player_selected)
        lay_top.addWidget(self._players_table)

        # ── Part inferior: scroll amb el perfil ──────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(self._scroll.Shape.NoFrame)

        # Missatge d'espera inicial
        placeholder = QLabel("Selecciona un jugador per veure el seu perfil.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setObjectName("sectionTitle")
        self._scroll.setWidget(placeholder)

        splitter.addWidget(top_widget)
        splitter.addWidget(self._scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    # ──────────────────────────────────────────────────────────────────────────
    # Construcció del perfil (zona dins el QScrollArea)
    # ──────────────────────────────────────────────────────────────────────────

    def _build_profile_widget(self) -> QWidget:
        """Crea (o recrea) el widget de perfil buit. Guarda refs als sub-widgets."""
        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 8, 0, 8)
        lay.setSpacing(16)

        # 1. Capçalera del jugador
        self._profile_header = QLabel()
        self._profile_header.setObjectName("sectionTitle")
        self._profile_header.setWordWrap(True)
        lay.addWidget(self._profile_header)

        # 2. KPI row
        kpi_labels = ["Partides", "Guanyades", "Perdudes", "% Victòria", "Sèrie màx"]
        self._kpi_row = KpiRow(kpi_labels)
        lay.addWidget(self._kpi_row)

        # 3. Evolució al rànquing
        lay.addWidget(SectionTitle("Evolució al rànquing"))

        mod_row = QHBoxLayout()
        mod_row.addWidget(QLabel("Modalitat:"))
        self._mod_combo = QComboBox()
        self._mod_combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._mod_combo.currentIndexChanged.connect(self._on_modalitat_changed)
        mod_row.addWidget(self._mod_combo)
        mod_row.addStretch()
        lay.addLayout(mod_row)

        # Placeholder per al gràfic
        self._chart_container = QVBoxLayout()
        self._chart_widget = None
        chart_wrapper = QWidget()
        chart_wrapper.setLayout(self._chart_container)
        lay.addWidget(chart_wrapper)

        # 4. Millors i pitjors partides
        lay.addWidget(SectionTitle("Millors i pitjors partides"))
        bw_grid = QGridLayout()
        bw_grid.setSpacing(8)

        titles = [
            "Millors mitjanes", "Millors victòries",
            "Pitjors mitjanes",  "Pitjors derrotes",
        ]
        self._bw_tables: dict[str, object] = {}
        positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
        keys = ["best", "best_won", "worst", "worst_lost"]
        for (row, col), key, title in zip(positions, keys, titles):
            cell = QVBoxLayout()
            cell.addWidget(QLabel(title))
            t = make_table(BW_HEADERS)
            t.setMinimumHeight(130)
            cell.addWidget(t)
            self._bw_tables[key] = t
            w = QWidget()
            w.setLayout(cell)
            bw_grid.addWidget(w, row, col)

        bw_grid.setColumnStretch(0, 1)
        bw_grid.setColumnStretch(1, 1)
        lay.addLayout(bw_grid)

        # 5. Últimes partides
        lay.addWidget(SectionTitle("Últimes partides"))
        self._games_table = make_table(GAMES_HEADERS)
        lay.addWidget(self._games_table)

        lay.addStretch()
        return container

    # ──────────────────────────────────────────────────────────────────────────
    # Punt d'entrada inicial
    # ──────────────────────────────────────────────────────────────────────────

    def request_data(self) -> None:
        """Carrega la llista inicial de jugadors i les modalitats disponibles."""
        self._controller.request_players(query="")
        # Carrega modalitats en background (per al combo del rànquing)
        self._controller.run_query(
            lambda: self._controller.ds.modalitats(),
            self._on_modalitats_loaded,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Slots: llista de jugadors
    # ──────────────────────────────────────────────────────────────────────────

    def _on_search_clicked(self) -> None:
        self._controller.request_players(query=self._search.text(), limit=500)

    def _on_players_loaded(self, players: list[PlayerKpi]) -> None:
        rows = [
            [p.fcb_id, p.nom, p.club or "", p.num_partides, "★" if p.seguiment else ""]
            for p in players
        ]
        populate_table(self._players_table, rows)
        for i, p in enumerate(players):
            self._players_table.item(i, 0).setData(
                Qt.ItemDataRole.UserRole, (p.fcb_id, p.nom)
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Slots: selecció d'un jugador → carrega perfil complet
    # ──────────────────────────────────────────────────────────────────────────

    def _on_player_selected(self) -> None:
        items = self._players_table.selectedItems()
        if not items:
            return
        row_idx = items[0].row()
        cell = self._players_table.item(row_idx, 0)
        data = cell.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        fcb_id, nom = data
        if fcb_id == self._selected_fcb:
            return  # ja seleccionat, no recarreguem
        self._selected_fcb = fcb_id

        # Reconstrueix la zona de perfil
        profile_widget = self._build_profile_widget()
        self._scroll.setWidget(profile_widget)

        # Capçalera provisional
        self._profile_header.setText(f"{nom}  [{fcb_id}]  — carregant…")

        # Omple el combo de modalitats (ja disponibles)
        self._populate_mod_combo()

        # Llança les 4 queries en paral·lel (run_query és no bloquejant)
        self._load_player_summary(fcb_id)
        self._load_best_worst(fcb_id)
        self._load_games(fcb_id)
        # El gràfic es carrega quan l'usuari (o el combo init) tria modalitat
        self._rebuild_chart(fcb_id)

    # ──────────────────────────────────────────────────────────────────────────
    # Modalitats
    # ──────────────────────────────────────────────────────────────────────────

    def _on_modalitats_loaded(self, mods: list[tuple[int, str]]) -> None:
        self._modalitats = mods
        # Si ja hi ha un perfil obert, actualitza el combo
        if self._selected_fcb:
            self._populate_mod_combo()

    def _populate_mod_combo(self) -> None:
        """Omple el combo bloqueant temporalment el signal per evitar disparar
        _on_modalitat_changed mentre es construeix."""
        if not hasattr(self, "_mod_combo"):
            return
        self._mod_combo.blockSignals(True)
        self._mod_combo.clear()
        self._mod_combo.addItem("Totes", userData=None)
        for codi, nom in self._modalitats:
            self._mod_combo.addItem(nom, userData=codi)
        self._mod_combo.blockSignals(False)

    def _on_modalitat_changed(self, _index: int) -> None:
        if self._selected_fcb:
            self._rebuild_chart(self._selected_fcb)

    def _current_codi_fcb(self) -> int | None:
        if not hasattr(self, "_mod_combo"):
            return None
        return self._mod_combo.currentData()

    # ──────────────────────────────────────────────────────────────────────────
    # Càrregues de dades del perfil
    # ──────────────────────────────────────────────────────────────────────────

    def _load_player_summary(self, fcb_id: str) -> None:
        snapshot = fcb_id

        def task():
            return self._controller.ds.player_summary(fcb_id)

        def on_result(summary: dict) -> None:
            if snapshot != self._selected_fcb:
                return
            nom = summary.get("nom", fcb_id)
            self._profile_header.setText(f"{nom}  [{fcb_id}]")
            total = summary.get("total", 0)
            guanyades = summary.get("guanyades", 0)
            pct = f"{guanyades / total * 100:.1f}" if total else "—"
            serie = summary.get("serie_max")
            self._kpi_row.set_values({
                "Partides":    total,
                "Guanyades":   guanyades,
                "Perdudes":    summary.get("perdudes", 0),
                "% Victòria":  pct,
                "Sèrie màx":   serie if serie is not None else "—",
            })

        self._controller.run_query(task, on_result)

    def _rebuild_chart(self, fcb_id: str) -> None:
        """Carrega l'historial de rànquing i reconstrueix el gràfic."""
        snapshot = fcb_id
        codi = self._current_codi_fcb()

        def task():
            return self._controller.ds.player_ranking_history(fcb_id, codi)

        def on_result(history: list[dict]) -> None:
            if snapshot != self._selected_fcb:
                return
            if not hasattr(self, "_chart_container"):
                return

            # Elimina el gràfic anterior
            if self._chart_widget is not None:
                self._chart_container.removeWidget(self._chart_widget)
                self._chart_widget.deleteLater()
                self._chart_widget = None

            if not history:
                lbl = QLabel("No hi ha dades de rànquing per a aquesta modalitat.")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._chart_container.addWidget(lbl)
                self._chart_widget = lbl
                return

            x_labels = [str(d["num_seq"]) for d in history]
            valores = [d["mitjana"] for d in history]
            chart = make_line_chart(
                title="Evolució de la mitjana al rànquing",
                x_labels=x_labels,
                series=[("Mitjana", valores)],
                invert_y=False,
                y_title="Mitjana",
            )
            self._chart_container.addWidget(chart)
            self._chart_widget = chart

        self._controller.run_query(task, on_result)

    def _load_best_worst(self, fcb_id: str) -> None:
        snapshot = fcb_id

        def task():
            return self._controller.ds.player_best_worst_games(fcb_id, top=5)

        def on_result(data: dict) -> None:
            if snapshot != self._selected_fcb:
                return
            if not hasattr(self, "_bw_tables"):
                return
            for key in ("best", "best_won", "worst", "worst_lost"):
                games: list[GameRow] = data.get(key, [])
                table = self._bw_tables.get(key)
                if table is not None:
                    populate_table(table, [_gamerow_to_bw_row(g) for g in games])

        self._controller.run_query(task, on_result)

    def _load_games(self, fcb_id: str) -> None:
        snapshot = fcb_id

        def task():
            return self._controller.ds.player_games(fcb_id, limit=100)

        def on_result(games: list[GameRow]) -> None:
            if snapshot != self._selected_fcb:
                return
            if not hasattr(self, "_games_table"):
                return
            populate_table(self._games_table, [_gamerow_to_full_row(g) for g in games])

        self._controller.run_query(task, on_result)
