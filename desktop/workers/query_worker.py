"""Background worker per a queries SQL.

Encara que SQLite local és ràpid, encapsulem tot en QThread per:
- No bloquejar la UI mai (iron law #2).
- Patró extensible quan afegim consultes que escanegen taules grans
  o invocacions a `fcbillar` que truquen al portal.
"""
from __future__ import annotations

from typing import Any, Callable

from PyQt6.QtCore import QObject, QThread, pyqtSignal


class QueryWorker(QThread):
    """Executa un callable arbitrari en thread separat i emet el resultat."""

    finished_with_result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, task: Callable[[], Any], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._task = task

    def run(self) -> None:  # noqa: D401 - Qt signature
        try:
            result = self._task()
        except Exception as e:  # pragma: no cover - propaga al UI via signal
            self.error.emit(f"{type(e).__name__}: {e}")
            return
        self.finished_with_result.emit(result)
