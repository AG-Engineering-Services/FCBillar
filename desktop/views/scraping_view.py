"""Vista Scraping: botons per executar comandes `fcbillar` amb log en viu."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop.workers import SubprocessWorker
from desktop.views.widgets import SectionTitle


class ScrapingView(QWidget):
    """Botons per scraping + log en viu de l'output del subprocess."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: SubprocessWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)
        root.addWidget(SectionTitle("Scraping & actualitzacions"))

        info = QLabel(
            "Llança operacions de scraping contra fcbillar.cat. Cada botó executa "
            "una comanda `uv run fcbillar …` i mostra l'output en viu sota. "
            "Operacions interactives (login amb captcha) obriran una finestra de "
            "Chromium fora d'aquesta app."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        # Grid de botons
        grid = QGridLayout()
        grid.setSpacing(10)
        buttons = [
            ("🔄 Sync rànquings", ["uv", "run", "fcbillar", "sync"],
             "Detecta i ingest els rànquings nous publicats a la home"),
            ("🔑 Re-login", ["uv", "run", "fcbillar", "login"],
             "Obre Chromium per fer login (resol captcha manualment)"),
            ("📥 Import clubs oficials", ["uv", "run", "fcbillar", "import-clubs"],
             "Descarrega el listing oficial de clubs"),
            ("📊 Status BD", ["uv", "run", "fcbillar", "status"],
             "Mostra comptadors de cada taula"),
            ("🎯 Backfill TRES BANDES top 20",
             ["uv", "run", "fcbillar", "backfill", "1", "--top", "20"],
             "Ingest del rànquing actual de Tres bandes + partides dels top 20"),
            ("🌐 Discover lliga 3 bandes",
             ["uv", "run", "fcbillar", "discover-lliga", "36", "--depth", "2"],
             "Mostra divisions i grups de la lliga actual de 3 bandes"),
        ]
        for i, (label, args, tooltip) in enumerate(buttons):
            btn = QPushButton(label)
            btn.setToolTip(tooltip)
            btn.setMinimumHeight(48)
            btn.clicked.connect(
                lambda _checked=False, a=args, l=label: self._run_command(a, l)
            )
            grid.addWidget(btn, i // 2, i % 2)
        root.addLayout(grid)

        # Status bar (interna a la vista)
        self._status = QLabel("Llest")
        self._status.setObjectName("scrapingStatus")
        root.addWidget(self._status)

        # Log
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 10))
        self._log.setObjectName("scrapingLog")
        root.addWidget(self._log, stretch=1)

        # Botó per netejar log
        controls = QHBoxLayout()
        clear_btn = QPushButton("Netejar log")
        clear_btn.clicked.connect(self._log.clear)
        controls.addStretch()
        controls.addWidget(clear_btn)
        root.addLayout(controls)

    def request_data(self) -> None:
        # Aquesta vista no carrega dades; no fa res en navegar-hi.
        pass

    def _run_command(self, args: list[str], label: str) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._append("⚠ Ja hi ha una comanda corrent. Espera que acabi.")
            return
        self._append(f"\n=== {label} ===")
        self._append(f"$ {' '.join(args)}")
        self._status.setText(f"Corrent: {label}…")
        self._worker = SubprocessWorker(args)
        self._worker.line_received.connect(self._append)
        self._worker.finished_with_code.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self, code: int) -> None:
        suffix = "OK" if code == 0 else f"FAIL (codi {code})"
        self._append(f"=== {suffix} ===\n")
        self._status.setText(f"Llest. Darrera: {suffix}")

    def _append(self, line: str) -> None:
        self._log.appendPlainText(line)
        # Auto-scroll
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())
