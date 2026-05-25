"""Widgets reutilitzables."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class KpiCard(QFrame):
    """Targeta de KPI amb label + valor."""

    def __init__(self, label: str, value: str | int = "—", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("kpiCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        self._label = QLabel(label)
        self._label.setObjectName("kpiLabel")
        self._value = QLabel(str(value))
        self._value.setObjectName("kpiValue")
        layout.addWidget(self._label)
        layout.addWidget(self._value)

    def set_value(self, value: str | int) -> None:
        self._value.setText(str(value))


class KpiRow(QWidget):
    """Fila horitzontal de KpiCards."""

    def __init__(self, labels: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self._cards: dict[str, KpiCard] = {}
        for label in labels:
            card = KpiCard(label)
            self._cards[label] = card
            layout.addWidget(card, stretch=1)

    def set_values(self, values: dict[str, str | int]) -> None:
        for label, value in values.items():
            if label in self._cards:
                self._cards[label].set_value(value)


class SectionTitle(QLabel):
    """Títol de secció amb estil consistent."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("sectionTitle")
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)


def make_table(headers: list[str]) -> QTableWidget:
    """Crea una QTableWidget pre-configurada amb headers."""
    table = QTableWidget()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setStretchLastSection(True)
    table.setSortingEnabled(True)
    return table


def populate_table(table: QTableWidget, rows: list[list[str | int | None]]) -> None:
    """Omple una taula amb dades (str/int/None). Re-renderitza."""
    table.setSortingEnabled(False)  # evitar reorder mentre s'omple
    table.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            text = "" if val is None else str(val)
            item = QTableWidgetItem(text)
            if isinstance(val, (int, float)):
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(i, j, item)
    table.setSortingEnabled(True)
    table.resizeColumnsToContents()
