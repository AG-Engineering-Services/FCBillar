"""Vista de rànquings: selector de modalitat + snapshot + taula completa."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from desktop.controllers import MainController
from desktop.models import RankingEntry
from desktop.views.widgets import SectionTitle, make_table, populate_table

RANKING_HEADERS = ["Pos", "Jugador", "fcb_id", "MJ", "MR", "C", "E", "P/PT", "Def"]


def _fmt_float(v: float | None) -> str:
    return f"{v:.4f}" if v is not None else ""


def _fmt_int(v: int | None) -> str:
    return str(v) if v is not None else ""


def _fmt_punts(punts: int | None, punts_totals: int | None) -> str:
    if punts is not None and punts_totals is not None:
        return f"{punts}/{punts_totals}"
    if punts is not None:
        return str(punts)
    return ""


def _entry_to_row(e: RankingEntry) -> list[str]:
    return [
        _fmt_int(e.posicio),
        e.nom,
        e.fcb_id,
        _fmt_float(e.mitjana),
        _fmt_float(e.mitjana_contraris),
        _fmt_int(e.caramboles),
        _fmt_int(e.entrades),
        _fmt_punts(e.punts, e.punts_totals),
        "Sí" if e.definitiva else "No",
    ]


class RankingsView(QWidget):
    def __init__(self, controller: MainController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        # (codi_fcb, nom) per a la modalitat seleccionada
        self._modalitats: list[tuple[int, str]] = []
        # Indica si les modalitats ja han estat carregades per evitar recàrrega
        self._modalitats_loaded = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)
        root.addWidget(SectionTitle("Rànquings"))

        # Fila de selectors
        selectors_row = QHBoxLayout()
        selectors_row.setSpacing(10)

        selectors_row.addWidget(QLabel("Modalitat:"))
        self._mod_combo = QComboBox()
        self._mod_combo.setMinimumWidth(180)
        self._mod_combo.currentIndexChanged.connect(self._on_modalitat_changed)
        selectors_row.addWidget(self._mod_combo)

        selectors_row.addWidget(QLabel("Rànquing:"))
        self._snap_combo = QComboBox()
        self._snap_combo.setMinimumWidth(140)
        self._snap_combo.currentIndexChanged.connect(self._on_snapshot_changed)
        selectors_row.addWidget(self._snap_combo)

        selectors_row.addStretch(1)
        root.addLayout(selectors_row)

        # Taula principal
        self._table = make_table(RANKING_HEADERS)
        root.addWidget(self._table, stretch=1)

    # ------------------------------------------------------------------
    # Entrada pública: cridada quan la vista es fa visible
    # ------------------------------------------------------------------

    def request_data(self) -> None:
        if self._modalitats_loaded:
            # Ja tenim les modalitats; refresquem el rànquing actual
            self._load_ranking()
            return
        # Primera càrrega: obtenim les modalitats via run_query
        self._controller.run_query(
            self._controller.ds.modalitats,
            self._on_modalitats_loaded,
        )

    # ------------------------------------------------------------------
    # Callbacks de dades (cridades al fil UI per run_query)
    # ------------------------------------------------------------------

    def _on_modalitats_loaded(self, modalitats: list[tuple[int, str]]) -> None:
        self._modalitats = modalitats
        self._modalitats_loaded = True

        self._mod_combo.blockSignals(True)
        self._mod_combo.clear()
        for _, nom in modalitats:
            self._mod_combo.addItem(nom)
        self._mod_combo.blockSignals(False)

        # Carreguem snapshots i rànquing per a la primera modalitat
        if modalitats:
            self._load_snapshots_then_ranking()

    def _on_snapshots_loaded(self, snapshots: list[int]) -> None:
        self._snap_combo.blockSignals(True)
        self._snap_combo.clear()
        for seq in snapshots:
            self._snap_combo.addItem(f"Rànquing {seq}", userData=seq)
        self._snap_combo.blockSignals(False)

        # Un cop tenim els snapshots, carreguem el rànquing del primer (més recent)
        self._load_ranking()

    def _on_ranking_loaded(self, entries: list[RankingEntry]) -> None:
        rows = [_entry_to_row(e) for e in entries]
        populate_table(self._table, rows)

    # ------------------------------------------------------------------
    # Slots dels combos
    # ------------------------------------------------------------------

    def _on_modalitat_changed(self, _index: int) -> None:
        self._load_snapshots_then_ranking()

    def _on_snapshot_changed(self, _index: int) -> None:
        self._load_ranking()

    # ------------------------------------------------------------------
    # Helpers interns
    # ------------------------------------------------------------------

    def _current_codi_fcb(self) -> int | None:
        idx = self._mod_combo.currentIndex()
        if idx < 0 or idx >= len(self._modalitats):
            return None
        return self._modalitats[idx][0]

    def _current_num_seq(self) -> int | None:
        idx = self._snap_combo.currentIndex()
        if idx < 0:
            return None
        data = self._snap_combo.itemData(idx)
        return data  # int o None si el combo és buit

    def _load_snapshots_then_ranking(self) -> None:
        codi = self._current_codi_fcb()
        if codi is None:
            return
        self._controller.run_query(
            lambda: self._controller.ds.ranking_snapshots(codi),
            self._on_snapshots_loaded,
        )

    def _load_ranking(self) -> None:
        codi = self._current_codi_fcb()
        if codi is None:
            return
        num_seq = self._current_num_seq()
        # num_seq pot ser None si el combo de snapshots és buit;
        # ranking_full accepta None (retorna el més recent)
        self._controller.run_query(
            lambda: self._controller.ds.ranking_full(codi, num_seq),
            self._on_ranking_loaded,
        )
