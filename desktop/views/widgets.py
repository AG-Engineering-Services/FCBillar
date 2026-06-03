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


# Paleta de colors per a sèries de gràfics (consistent amb el tema).
_SERIES_COLORS = [
    "#2d6cdf", "#e8554e", "#37b679", "#f2b134", "#9b5de5", "#00bbf9",
    "#f15bb5", "#fee440", "#8ac926", "#ff924c", "#4cc9f0", "#b5179e",
]


def make_line_chart(
    title: str,
    x_labels: list[str],
    series: list[tuple[str, list[float | int | None]]],
    *,
    invert_y: bool = False,
    y_title: str = "",
    integer_y: bool = False,
) -> QWidget:
    """Crea un gràfic de línies (QtCharts) reutilitzable.

    - `x_labels`: etiquetes de l'eix X (p.ex. num_seq dels rànquings).
    - `series`: llista de (nom, valors alineats a x_labels; None = forat).
    - `invert_y`: True per a rànquings/ordre (1 a dalt = millor).
    - `integer_y`: força marques enteres.

    Si QtCharts no està disponible, retorna un QLabel informatiu.
    """
    try:
        from PyQt6.QtCharts import (
            QChart,
            QChartView,
            QLineSeries,
            QValueAxis,
        )
        from PyQt6.QtGui import QColor, QPainter, QPen
    except Exception:  # noqa: BLE001 — fallback sense charts
        lbl = QLabel(f"[Gràfic no disponible: PyQt6-Charts no instal·lat]\n{title}")
        lbl.setWordWrap(True)
        return lbl

    chart = QChart()
    chart.setTitle(title)
    chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
    chart.setBackgroundBrush(QColor("#272d36"))
    chart.setTitleBrush(QColor("#f0f3f8"))
    chart.legend().setVisible(True)
    chart.legend().setLabelColor(QColor("#c0c6cf"))

    n = len(x_labels)
    y_min, y_max = None, None
    for idx, (name, values) in enumerate(series):
        s = QLineSeries()
        s.setName(name)
        color = QColor(_SERIES_COLORS[idx % len(_SERIES_COLORS)])
        pen = QPen(color)
        pen.setWidth(2)
        s.setPen(pen)
        s.setPointsVisible(True)
        for xi, v in enumerate(values):
            if v is None:
                continue
            s.append(float(xi), float(v))
            y_min = v if y_min is None else min(y_min, v)
            y_max = v if y_max is None else max(y_max, v)
        chart.addSeries(s)

    ax = QValueAxis()
    ax.setRange(0, max(1, n - 1))
    ax.setTickCount(min(n, 12) if n > 1 else 2)
    ax.setLabelFormat("%d")
    ax.setLabelsColor(QColor("#93a0b3"))
    ax.setGridLineColor(QColor("#353c47"))
    chart.addAxis(ax, Qt.AlignmentFlag.AlignBottom)

    ay = QValueAxis()
    if y_min is None:
        y_min, y_max = 0, 1
    pad = max(0.5, (y_max - y_min) * 0.1)
    if invert_y:
        ay.setRange(y_max + pad, max(0.5, y_min - pad))  # invertit: petit a dalt
    else:
        ay.setRange(max(0, y_min - pad), y_max + pad)
    if integer_y:
        ay.setLabelFormat("%d")
    if y_title:
        ay.setTitleText(y_title)
        ay.setTitleBrush(QColor("#93a0b3"))
    ay.setLabelsColor(QColor("#93a0b3"))
    ay.setGridLineColor(QColor("#353c47"))
    chart.addAxis(ay, Qt.AlignmentFlag.AlignLeft)

    for s in chart.series():
        s.attachAxis(ax)
        s.attachAxis(ay)

    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setMinimumHeight(320)
    return view
