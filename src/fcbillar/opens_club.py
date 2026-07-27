"""Club d'un jugador als rànquings d'opens.

El club de cada fila surt de la classificació de l'open (`torneig_participants
.club_text`), que és el que hi publica la FCB. Però a algunes classificacions
hi posen **"Cap"** —literalment 'cap club'— encara que el jugador en tingui un
de tota la vida: cas MORUNO RAYA a l'Open Costa Daurada de 2026, que per això
sortia sense club al rànquing d'opens i sí amb club al de 3 bandes. Com que el
rànquing es queda el club del darrer open de la finestra, n'hi ha prou amb un
"Cap" per perdre'l.

D'aquí les dues peces d'aquest mòdul, compartides pel rànquing general
(`cloud_sync.publish_open_ranking`) i pel femení (`opens_femeni`):
  • `real_club` — descarta "Cap" i els buits, perquè no esborrin el que ja
    sabíem d'un open anterior;
  • `club_master` — l'afiliació federativa (`players.club_id`), com a últim
    recurs quan cap open de la finestra no en porta.
"""

from __future__ import annotations

import sqlite3

# Valors de la FCB que volen dir "sense club" (no són noms de club).
_NO_CLUB = {"CAP"}


def real_club(value: str | None) -> str | None:
    """El club tal com el publica la FCB, o None si allà no n'hi consta cap."""
    s = (value or "").strip()
    return None if not s or s.upper() in _NO_CLUB else s


def club_master(conn: sqlite3.Connection) -> dict[str, str]:
    """`{fcb_id → nom del club}` per l'afiliació federativa de `players`."""
    return {
        r["fcb_id"]: r["club"]
        for r in conn.execute(
            "SELECT p.fcb_id, c.nom AS club FROM players p JOIN clubs c ON c.id = p.club_id"
        )
        if r["fcb_id"] and r["club"]
    }
