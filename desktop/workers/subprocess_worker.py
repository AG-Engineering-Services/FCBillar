"""Background worker per a subprocess (no bloquegen UI).

Executa `uv run fcbillar ...` (o qualsevol comanda) i emet l'stdout línia a
línia perquè la UI pugui mostrar el log en viu.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Claus que els subprocessos (en especial `fcb_opens`, que NOMÉS llegeix l'entorn,
# no el .env) necessiten per publicar al núvol. Les carreguem del .env a l'entorn
# del subprocés perquè els botons de publicació funcionin com ho fa weekly_reingest.ps1.
_ENV_KEYS = (
    "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
    "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET",
)


def _subprocess_env() -> dict[str, str]:
    """os.environ + claus rellevants del .env del projecte (sense sobreescriure-les)."""
    env = dict(os.environ)
    dotenv = PROJECT_ROOT / ".env"
    if dotenv.exists():
        for raw in dotenv.read_text(encoding="utf-8").splitlines():
            t = raw.strip()
            if not t or t.startswith("#") or "=" not in t:
                continue
            name, _, val = t.partition("=")
            name = name.strip()
            val = val.strip().strip('"').strip("'")
            if name in _ENV_KEYS and val and not env.get(name):
                env[name] = val
    return env


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
                env=_subprocess_env(),
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
