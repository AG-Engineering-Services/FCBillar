"""Gestió simple d'esquema via PRAGMA user_version.

Versions:
- 1: schema inicial (clubs, players, modalitats, competicions, rankings,
     ranking_entries, games, ranking_game_links).
- 2: club per-partida — afegides taules temporades, equips, encontres_lliga;
     i columnes a games (equip1_id, equip2_id, encontre_lliga_id, temporada_id,
     arbitre, assistencia).
- 3: unificació de noms de clubs — taula club_aliases per mapejar noms
     alternatius a un mateix club canònic.
- 4: torneigs individuals (opens, catalans, etc.) — taules torneigs_individuals
     i torneig_participants per saber quin jugador va participar a quin torneig
     per temporada.
- 5: clubs virtuals (virtual_clubs, virtual_club_members).
- 6: lliga_noms — noms llegibles de divisions/grups de lliga.
- 7: estructura de la COPA (copa_jornades, copa_encontres, copa_classificacio,
     copa_partides) i fases dels individuals (torneig_fases). Taules noves.
- 8: composició de grups de les fases d'individuals (torneig_fase_grups). El
     portal no publica classificacions amb punts per fase, només l'assignació
     jugador→grup. S'elimina la taula buida torneig_fase_classif del v7.
"""

from __future__ import annotations

import logging
import sqlite3
from importlib.resources import files
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA_VERSION = 8


def _read_schema_sql() -> str:
    return (files("fcbillar.db") / "schema.sql").read_text(encoding="utf-8")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def current_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


_V2_NEW_COLUMNS_GAMES = [
    ("equip1_id", "INTEGER REFERENCES equips(id)"),
    ("equip2_id", "INTEGER REFERENCES equips(id)"),
    ("encontre_lliga_id", "INTEGER REFERENCES encontres_lliga(id)"),
    ("temporada_id", "INTEGER REFERENCES temporades(id)"),
    ("arbitre", "TEXT"),
    ("assistencia", "TEXT"),
]


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Afegeix les columnes noves a `games`. Les taules noves (CREATE TABLE
    IF NOT EXISTS) ja les crearà el `executescript(schema.sql)` posterior."""
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(games)").fetchall()}
    for col_name, col_def in _V2_NEW_COLUMNS_GAMES:
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE games ADD COLUMN {col_name} {col_def}")
            log.info("v1→v2: afegida columna games.%s", col_name)


def ensure_schema(db_path: Path) -> sqlite3.Connection:
    conn = connect(db_path)
    version = current_version(conn)
    if version >= SCHEMA_VERSION:
        return conn

    # BD existent: aplicar migracions incrementals abans del executescript.
    if 1 <= version < 2:
        _migrate_v1_to_v2(conn)
    # v7 → v8: la taula torneig_fase_classif (mai poblada) es substitueix per
    # torneig_fase_grups. La fem fora; executescript crearà la nova.
    if version == 7:
        conn.execute("DROP TABLE IF EXISTS torneig_fase_classif")
    # v2 → v3 no necessita ALTER (només afegeix taula nova que crearà
    # executescript via CREATE TABLE IF NOT EXISTS).
    # v3 → v4 tampoc (afegeix torneigs_individuals + torneig_participants).

    # executescript és idempotent (CREATE TABLE IF NOT EXISTS, INSERT OR IGNORE,
    # CREATE INDEX IF NOT EXISTS) — segur per a BDs noves i ja migrades.
    conn.executescript(_read_schema_sql())
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return conn
