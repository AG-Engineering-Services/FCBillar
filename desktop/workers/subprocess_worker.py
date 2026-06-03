"""Background worker per a subprocess (no bloquegen UI).

Executa `uv run fcbillar ...` (o qualsevol comanda) i emet l'stdout línia a
línia perquè la UI pugui mostrar el log en viu.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SubprocessWorker(QThread):
    """Executa una comanda i emet stdout línia a línia."""

    line_received = pyqtSignal(str)
    finished_with_code = pyqtSignal(int)

    def __init__(self, args: list[str], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._args = args

    def run(self) -> None:  # noqa: D401 - Qt signature
        try:
            proc = subprocess.Popen(
                self._args,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as e:
            self.line_received.emit(f"ERROR: {e}")
            self.finished_with_code.emit(-1)
            return
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                self.line_received.emit(line.rstrip())
            code = proc.wait()
        except Exception as e:
            self.line_received.emit(f"EXCEPTION: {e}")
            code = -1
        self.finished_with_code.emit(code)
