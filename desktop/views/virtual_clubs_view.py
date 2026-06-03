"""Vista de clubs virtuals: seleccions arbitràries de jugadors."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from desktop.controllers import MainController
from desktop.models import PlayerKpi, VirtualClub
from desktop.views.widgets import SectionTitle, make_table, populate_table

_VC_HEADERS = ["Club", "Membres"]
_MEMBER_HEADERS = ["fcb_id", "Jugador", "Club real", "Partides"]
_SEARCH_HEADERS = ["fcb_id", "Jugador", "Club real", "Partides"]


class VirtualClubsView(QWidget):
    """Gestió de clubs virtuals: crear, renombrar, esborrar i gestionar membres."""

    def __init__(self, controller: MainController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._selected_vc: VirtualClub | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # Construcció UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)
        root.addWidget(SectionTitle("Clubs virtuals"))

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, stretch=1)

        splitter.addWidget(self._build_left_pane())
        splitter.addWidget(self._build_right_pane())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        self._update_right_enabled()

    def _build_left_pane(self) -> QWidget:
        pane = QWidget()
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self._vc_table = make_table(_VC_HEADERS)
        self._vc_table.itemSelectionChanged.connect(self._on_vc_selected)
        lay.addWidget(self._vc_table, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._btn_nou = QPushButton("Nou")
        self._btn_nou.setToolTip("Crea un nou club virtual")
        self._btn_nou.clicked.connect(self._on_nou)

        self._btn_rename = QPushButton("Reanomena")
        self._btn_rename.setToolTip("Canvia el nom del club virtual seleccionat")
        self._btn_rename.clicked.connect(self._on_rename)

        self._btn_delete = QPushButton("Esborra")
        self._btn_delete.setToolTip("Esborra el club virtual seleccionat")
        self._btn_delete.clicked.connect(self._on_delete)

        btn_row.addWidget(self._btn_nou)
        btn_row.addWidget(self._btn_rename)
        btn_row.addWidget(self._btn_delete)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        return pane

    def _build_right_pane(self) -> QWidget:
        pane = QWidget()
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Títol del club seleccionat
        self._right_title = QLabel("Selecciona un club virtual")
        self._right_title.setObjectName("sectionTitle")
        lay.addWidget(self._right_title)

        # Taula de membres
        members_label = QLabel("Membres del club:")
        lay.addWidget(members_label)

        self._members_table = make_table(_MEMBER_HEADERS)
        lay.addWidget(self._members_table, stretch=2)

        remove_row = QHBoxLayout()
        self._btn_remove = QPushButton("Treu del club")
        self._btn_remove.setToolTip("Elimina el jugador seleccionat del club virtual")
        self._btn_remove.clicked.connect(self._on_remove_member)
        remove_row.addWidget(self._btn_remove)
        remove_row.addStretch()
        lay.addLayout(remove_row)

        # Àrea d'afegir jugadors
        lay.addWidget(QLabel("Afegir jugador:"))

        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Nom o fcb_id del jugador…")
        self._search_input.returnPressed.connect(self._on_search)
        self._btn_search = QPushButton("Cerca")
        self._btn_search.clicked.connect(self._on_search)
        search_row.addWidget(self._search_input, stretch=1)
        search_row.addWidget(self._btn_search)
        lay.addLayout(search_row)

        self._search_table = make_table(_SEARCH_HEADERS)
        self._search_table.itemDoubleClicked.connect(self._on_add_member_from_double_click)
        lay.addWidget(self._search_table, stretch=1)

        add_row = QHBoxLayout()
        self._btn_add = QPushButton("Afegeix")
        self._btn_add.setToolTip("Afegeix el jugador seleccionat al club virtual")
        self._btn_add.clicked.connect(self._on_add_member)
        add_row.addWidget(self._btn_add)
        add_row.addStretch()
        lay.addLayout(add_row)

        return pane

    # ------------------------------------------------------------------
    # Dades públiques
    # ------------------------------------------------------------------

    def request_data(self) -> None:
        """Carrega la llista de clubs virtuals (i refresca membres si n'hi ha un de seleccionat)."""
        self._controller.run_query(
            lambda: self._controller.ds.list_virtual_clubs(),
            self._on_vc_list_loaded,
        )

    # ------------------------------------------------------------------
    # Càrrega de dades (callbacks run_query)
    # ------------------------------------------------------------------

    def _on_vc_list_loaded(self, clubs: list[VirtualClub]) -> None:
        populate_table(self._vc_table, [[c.nom, c.num_membres] for c in clubs])
        for i, c in enumerate(clubs):
            self._vc_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, c)

        # Reseleccionem el club que estava seleccionat, si segueix existint.
        if self._selected_vc is not None:
            prev_id = self._selected_vc.id
            for row in range(self._vc_table.rowCount()):
                vc: VirtualClub | None = self._vc_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                if vc is not None and vc.id == prev_id:
                    self._vc_table.selectRow(row)
                    return
            # El club ja no existeix: netegem la selecció.
            self._selected_vc = None
            self._right_title.setText("Selecciona un club virtual")
            populate_table(self._members_table, [])
            self._update_right_enabled()

    def _on_members_loaded(self, members: list[PlayerKpi]) -> None:
        rows = [
            [p.fcb_id, p.nom, p.club or "", p.num_partides]
            for p in members
        ]
        populate_table(self._members_table, rows)
        for i, p in enumerate(members):
            self._members_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, p.fcb_id)

    def _on_search_loaded(self, players: list[PlayerKpi]) -> None:
        rows = [
            [p.fcb_id, p.nom, p.club or "", p.num_partides]
            for p in players
        ]
        populate_table(self._search_table, rows)
        for i, p in enumerate(players):
            self._search_table.item(i, 0).setData(Qt.ItemDataRole.UserRole, p.fcb_id)

    # ------------------------------------------------------------------
    # Slots interns
    # ------------------------------------------------------------------

    def _on_vc_selected(self) -> None:
        items = self._vc_table.selectedItems()
        if not items:
            return
        cell = self._vc_table.item(items[0].row(), 0)
        vc: VirtualClub | None = cell.data(Qt.ItemDataRole.UserRole)
        if vc is None:
            return
        self._selected_vc = vc
        self._right_title.setText(f"{vc.nom}  ({vc.num_membres} membres)")
        self._update_right_enabled()
        self._reload_members()

    def _reload_members(self) -> None:
        if self._selected_vc is None:
            return
        vc_id = self._selected_vc.id
        self._controller.run_query(
            lambda: self._controller.ds.virtual_club_members(vc_id),
            self._on_members_loaded,
        )

    # ---- Botons clubs ----

    def _on_nou(self) -> None:
        nom, ok = QInputDialog.getText(
            self, "Nou club virtual", "Nom del club virtual:"
        )
        if not ok or not nom.strip():
            return
        nom = nom.strip()
        ds = self._controller.ds

        def _create():
            return ds.create_virtual_club(nom)

        def _after_create(_vc_id: int) -> None:
            self.request_data()

        self._controller.run_query(_create, _after_create)

    def _on_rename(self) -> None:
        if self._selected_vc is None:
            return
        vc = self._selected_vc
        nou_nom, ok = QInputDialog.getText(
            self,
            "Reanomena club virtual",
            "Nou nom:",
            text=vc.nom,
        )
        if not ok or not nou_nom.strip():
            return
        nou_nom = nou_nom.strip()
        ds = self._controller.ds

        def _update():
            ds.update_virtual_club(vc.id, nou_nom, vc.descripcio)

        def _after_update(_=None) -> None:
            self.request_data()

        self._controller.run_query(_update, _after_update)

    def _on_delete(self) -> None:
        if self._selected_vc is None:
            return
        vc = self._selected_vc
        resp = QMessageBox.question(
            self,
            "Esborra club virtual",
            f"Segur que vols esborrar '{vc.nom}'?\nAquesta acció no es pot desfer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        ds = self._controller.ds

        def _delete():
            ds.delete_virtual_club(vc.id)

        def _after_delete(_=None) -> None:
            self._selected_vc = None
            self._right_title.setText("Selecciona un club virtual")
            populate_table(self._members_table, [])
            self._update_right_enabled()
            self.request_data()

        self._controller.run_query(_delete, _after_delete)

    # ---- Membres ----

    def _on_remove_member(self) -> None:
        if self._selected_vc is None:
            return
        items = self._members_table.selectedItems()
        if not items:
            return
        cell = self._members_table.item(items[0].row(), 0)
        fcb_id: str | None = cell.data(Qt.ItemDataRole.UserRole)
        if not fcb_id:
            return
        vc_id = self._selected_vc.id
        ds = self._controller.ds

        def _remove():
            ds.remove_virtual_club_member(vc_id, fcb_id)

        def _after_remove(_=None) -> None:
            self._reload_members()
            self.request_data()  # actualitza comptador de membres al panell esquerra

        self._controller.run_query(_remove, _after_remove)

    # ---- Cerca i afegir ----

    def _on_search(self) -> None:
        query = self._search_input.text().strip()
        ds = self._controller.ds

        def _search():
            return ds.search_players(query)

        self._controller.run_query(_search, self._on_search_loaded)

    def _on_add_member_from_double_click(self) -> None:
        self._on_add_member()

    def _on_add_member(self) -> None:
        if self._selected_vc is None:
            return
        items = self._search_table.selectedItems()
        if not items:
            return
        cell = self._search_table.item(items[0].row(), 0)
        fcb_id: str | None = cell.data(Qt.ItemDataRole.UserRole)
        if not fcb_id:
            return
        vc_id = self._selected_vc.id
        ds = self._controller.ds

        def _add():
            return ds.add_virtual_club_member(vc_id, fcb_id)

        def _after_add(added: bool) -> None:
            if not added:
                QMessageBox.information(
                    self,
                    "Jugador ja membre",
                    "Aquest jugador ja és membre del club virtual.",
                )
            self._reload_members()
            self.request_data()  # actualitza comptador al panell esquerra

        self._controller.run_query(_add, _after_add)

    # ------------------------------------------------------------------
    # Helpers d'estat
    # ------------------------------------------------------------------

    def _update_right_enabled(self) -> None:
        """Activa/desactiva els controls del panell dret segons si hi ha selecció."""
        enabled = self._selected_vc is not None
        self._btn_rename.setEnabled(enabled)
        self._btn_delete.setEnabled(enabled)
        self._btn_remove.setEnabled(enabled)
        self._btn_search.setEnabled(enabled)
        self._search_input.setEnabled(enabled)
        self._btn_add.setEnabled(enabled)
