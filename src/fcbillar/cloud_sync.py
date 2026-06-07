"""Publica la BD SQLite local al núvol (Supabase, schema `fcbillar`).

Aquesta és la meitat d'"escriptura" del model desktop→núvol: el desktop és
l'únic que baixa dades (scraping) i les desa a SQLite; aquí les puja a Supabase,
des d'on el frontend desplegat a Vercel les llegeix (només lectura, RLS).

Auth: SUPABASE_URL i SUPABASE_SERVICE_ROLE_KEY (la service_role salta RLS i pot
escriure; mai s'ha de publicar). Es llegeixen de l'entorn o del fitxer .env.

FASE 1: només la llesca de rànquings (modalitats, clubs, jugadors, rankings,
ranking_entries). Idempotent via upsert sobre claus naturals.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable
from pathlib import Path

from fcbillar.config import PROJECT_ROOT, get_settings

SCHEMA = "fcbillar"
Progress = Callable[[str, str], None]


def _env(name: str) -> str | None:
    """Llegeix una variable de l'entorn o, si no hi és, del .env del projecte."""
    import os

    val = os.environ.get(name)
    if val:
        return val.strip()
    env = PROJECT_ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith(name + "="):
                return line.partition("=")[2].strip().strip('"').strip("'") or None
    return None


def get_client():
    """Client Supabase amb la service_role, fixat al schema `fcbillar`."""
    from supabase import create_client

    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    if not url:
        raise RuntimeError("Falta SUPABASE_URL (entorn o .env).")
    if not key:
        raise RuntimeError("Falta SUPABASE_SERVICE_ROLE_KEY (entorn o .env).")
    return create_client(url, key).schema(SCHEMA)


def _chunks(rows: list[dict], n: int = 500) -> Iterable[list[dict]]:
    for i in range(0, len(rows), n):
        yield rows[i : i + n]


def _upsert(sb, table: str, rows: list[dict], on_conflict: str, prog: Progress) -> int:
    total = 0
    for chunk in _chunks(rows):
        sb.table(table).upsert(chunk, on_conflict=on_conflict).execute()
        total += len(chunk)
    prog("ok", f"{table}: {total} files")
    return total


def publish_rankings(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Puja la llesca de rànquings de la BD SQLite a Supabase. Retorna comptadors."""
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()
    counts: dict[str, int] = {}

    # 1. modalitats
    mods = [
        {"codi_fcb": r["codi_fcb"], "nom": r["nom"]}
        for r in conn.execute("SELECT codi_fcb, nom FROM modalitats")
    ]
    counts["modalitats"] = _upsert(sb, "modalitats", mods, "codi_fcb", prog)

    # 2. clubs
    clubs = [
        {"fcb_id": r["fcb_id"], "nom": r["nom"]}
        for r in conn.execute("SELECT fcb_id, nom FROM clubs")
    ]
    club_ids = {c["fcb_id"] for c in clubs}
    counts["clubs"] = _upsert(sb, "clubs", clubs, "fcb_id", prog)

    # 3. players (club_fcb_id null si el club no és a la taula → respecta la FK)
    players = []
    for r in conn.execute(
        """
        SELECT p.fcb_id, p.nom, c.fcb_id AS club_fcb_id, p.seguiment
        FROM players p LEFT JOIN clubs c ON c.id = p.club_id
        """
    ):
        club = r["club_fcb_id"] if r["club_fcb_id"] in club_ids else None
        players.append({
            "fcb_id": r["fcb_id"],
            "nom": r["nom"],
            "club_fcb_id": club,
            "seguiment": bool(r["seguiment"]),
        })
    counts["players"] = _upsert(sb, "players", players, "fcb_id", prog)

    # 4. rankings
    rankings = [
        {
            "modalitat_codi": r["modalitat_codi"],
            "num_seq": r["num_seq"],
            "any_pub": r["any_pub"],
            "mes_pub": r["mes_pub"],
        }
        for r in conn.execute(
            """
            SELECT m.codi_fcb AS modalitat_codi, r.num_seq, r.any_pub, r.mes_pub
            FROM rankings r JOIN modalitats m ON m.id = r.modalitat_id
            """
        )
    ]
    counts["rankings"] = _upsert(sb, "rankings", rankings, "modalitat_codi,num_seq", prog)

    # 5. ranking_entries
    entries = [
        {
            "modalitat_codi": r["modalitat_codi"],
            "num_seq": r["num_seq"],
            "player_fcb_id": r["player_fcb_id"],
            "posicio": r["posicio"],
            "mitjana_general": r["mitjana_general"],
            "mitjana_particular": r["mitjana_particular"],
            "partides": r["partides"],
        }
        for r in conn.execute(
            """
            SELECT m.codi_fcb AS modalitat_codi, r.num_seq,
                   p.fcb_id AS player_fcb_id, re.posicio,
                   re.mitjana_general, re.mitjana_particular, re.partides
            FROM ranking_entries re
            JOIN rankings r ON r.id = re.ranking_id
            JOIN modalitats m ON m.id = r.modalitat_id
            JOIN players p ON p.id = re.player_id
            """
        )
    ]
    counts["ranking_entries"] = _upsert(
        sb, "ranking_entries", entries, "modalitat_codi,num_seq,player_fcb_id", prog
    )

    conn.close()
    return counts
