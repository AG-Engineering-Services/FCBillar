"""Executor de comandes `fcbillar` en segon pla per a la web.

Permet disparar actualitzacions de dades (scraping/ingest) des del frontend.
Un sol job alhora; el log es captura línia a línia i s'exposa via /api/sync/status.
Les comandes que requereixen interacció (login amb captcha) NO s'ofereixen aquí.
"""
from __future__ import annotations

import subprocess
import sys
import threading
from collections import deque
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Tasques permeses: clau → (etiqueta, args, requereix_login).
# Només lectura/ingest; res destructiu ni interactiu (el login amb captcha
# s'ha de fer des del terminal: `uv run fcbillar login`).
TASKS: dict[str, tuple[str, list[str], bool]] = {
    "sync": ("Sincronitza rànquings nous", ["sync"], True),
    "backfill-3b": ("Backfill 3 bandes (top 20)", ["backfill", "1", "--top", "20"], True),
    "import-clubs": ("Importa clubs oficials", ["import-clubs"], False),
    "individuals": ("Ingest torneigs individuals (temporada actual)", ["ingest-individuals"], False),
    "lliga-noms": ("Actualitza noms de lliga", ["discover-lliga-noms"], False),
    "status": ("Estat de la BD", ["status"], False),
}


class JobRunner:
    """Executa una comanda fcbillar en un thread i en captura la sortida."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False
        self._task_key: str | None = None
        self._label: str | None = None
        self._lines: deque[str] = deque(maxlen=500)
        self._exit_code: int | None = None
        self._finished_at: str | None = None

    # ------------------------------------------------------------------

    def status(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "task": self._task_key,
                "label": self._label,
                "exit_code": self._exit_code,
                "finished_at": self._finished_at,
                "log": list(self._lines),
            }

    def start(self, task_key: str) -> tuple[bool, str]:
        """Inicia una tasca. Retorna (acceptada, missatge)."""
        if task_key not in TASKS:
            return False, f"Tasca desconeguda: {task_key}"
        with self._lock:
            if self._running:
                return False, "Ja hi ha una actualització en curs."
            label, args, _needs_login = TASKS[task_key]
            self._running = True
            self._task_key = task_key
            self._label = label
            self._exit_code = None
            self._finished_at = None
            self._lines.clear()
            self._lines.append(f"$ fcbillar {' '.join(args)}")
        self._thread = threading.Thread(target=self._run, args=(args,), daemon=True)
        self._thread.start()
        return True, "Iniciada"

    # ------------------------------------------------------------------

    def _run(self, args: list[str]) -> None:
        cmd = ["uv", "run", "fcbillar", *args]
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as e:
            with self._lock:
                self._lines.append(f"ERROR: {e}")
                self._running = False
                self._exit_code = -1
                self._finished_at = _now()
            return
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                with self._lock:
                    self._lines.append(line.rstrip())
            code = proc.wait()
        except Exception as e:  # noqa: BLE001
            with self._lock:
                self._lines.append(f"EXCEPTION: {e}")
            code = -1
        with self._lock:
            self._running = False
            self._exit_code = code
            self._finished_at = _now()
            self._lines.append(f"— Finalitzat (codi {code}) —")


def _now() -> str:
    # Import local per no dependre de Date a nivell de mòdul.
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


# Singleton compartit per l'app.
runner = JobRunner()


def task_list() -> list[dict]:
    return [
        {"key": k, "label": label, "needs_login": needs_login}
        for k, (label, _args, needs_login) in TASKS.items()
    ]


def session_info() -> dict:
    """Estat de la sessió desada (per avisar si cal re-login)."""
    state = PROJECT_ROOT / "session" / "storage_state.json"
    if not state.exists():
        return {"exists": False, "mtime": None}
    from datetime import datetime

    return {
        "exists": True,
        "mtime": datetime.fromtimestamp(state.stat().st_mtime).isoformat(timespec="seconds"),
    }
