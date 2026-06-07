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


def publish_games(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Puja les partides (per a la fitxa de jugador) a Supabase. FASE 2."""
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    games = [
        {
            "id": r["id"],
            "data_partida": r["data_partida"],
            "modalitat_codi": r["modalitat_codi"],
            "competicio": r["competicio"],
            "player1_fcb_id": r["player1_fcb_id"],
            "player1_nom": r["player1_nom"],
            "caramboles1": r["caramboles1"],
            "serie_max1": r["serie_max1"],
            "player2_fcb_id": r["player2_fcb_id"],
            "player2_nom": r["player2_nom"],
            "caramboles2": r["caramboles2"],
            "serie_max2": r["serie_max2"],
            "entrades": r["entrades"],
            "guanyador_fcb_id": r["guanyador_fcb_id"],
        }
        for r in conn.execute(
            """
            SELECT g.id, g.data_partida, m.codi_fcb AS modalitat_codi,
                   comp.nom AS competicio,
                   p1.fcb_id AS player1_fcb_id, p1.nom AS player1_nom,
                   g.caramboles1, g.serie_max1,
                   p2.fcb_id AS player2_fcb_id, p2.nom AS player2_nom,
                   g.caramboles2, g.serie_max2,
                   g.entrades, pw.fcb_id AS guanyador_fcb_id
            FROM games g
            JOIN modalitats m ON m.id = g.modalitat_id
            LEFT JOIN competicions comp ON comp.id = g.competicio_id
            JOIN players p1 ON p1.id = g.player1_id
            JOIN players p2 ON p2.id = g.player2_id
            LEFT JOIN players pw ON pw.id = g.guanyador_id
            """
        )
    ]
    n = _upsert(sb, "games", games, "id", prog)
    conn.close()
    return {"games": n}


# Lliga Catalana Tres Bandes = competició/portal lliga_id 36.
LLIGA_3B_ID = 36


def publish_lliga(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Calcula i puja les classificacions de la lliga 3 bandes (temporada actual)."""
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    tr = conn.execute("SELECT id FROM temporades ORDER BY nom DESC LIMIT 1").fetchone()
    season_id = tr["id"] if tr else None

    noms = {
        (r["divisio_id"], r["grup_id"]): r["nom"]
        for r in conn.execute(
            "SELECT divisio_id, grup_id, nom FROM lliga_noms WHERE lliga_id = ?",
            (LLIGA_3B_ID,),
        )
    }
    equips = {
        r["id"]: (r["nom"], r["fcb_id"], r["lletra"])
        for r in conn.execute(
            "SELECT e.id, e.lletra, c.nom, c.fcb_id FROM equips e JOIN clubs c ON c.id = e.club_id"
        )
    }

    groups = conn.execute(
        """
        SELECT DISTINCT divisio_id, grup_id FROM encontres_lliga
        WHERE lliga_id = ? AND temporada_id = ? AND grup_id <> 0
        """,
        (LLIGA_3B_ID, season_id),
    ).fetchall()

    group_rows: list[dict] = []
    standing_rows: list[dict] = []
    for grp in groups:
        div, gid = grp["divisio_id"], grp["grup_id"]
        group_rows.append({
            "lliga_id": LLIGA_3B_ID, "divisio_id": div, "grup_id": gid,
            "divisio_nom": noms.get((div, 0)), "grup_nom": noms.get((div, gid)),
        })
        enc = conn.execute(
            """
            SELECT equip_local_id AS loc, equip_visitant_id AS vis,
                   p_match_local AS pml, p_match_visitant AS pmv
            FROM encontres_lliga
            WHERE lliga_id = ? AND divisio_id = ? AND grup_id = ? AND temporada_id = ?
            """,
            (LLIGA_3B_ID, div, gid, season_id),
        ).fetchall()
        stats: dict[int, dict] = {}

        def _s(eid):
            return stats.setdefault(eid, {"pj": 0, "g": 0, "e": 0, "p": 0, "pf": 0, "pc": 0})

        for r in enc:
            pml, pmv = r["pml"], r["pmv"]
            if pml is None or pmv is None:
                continue
            sl, sv = _s(r["loc"]), _s(r["vis"])
            sl["pj"] += 1; sv["pj"] += 1
            sl["pf"] += pml; sl["pc"] += pmv
            sv["pf"] += pmv; sv["pc"] += pml
            if pml > pmv:
                sl["g"] += 1; sv["p"] += 1
            elif pml < pmv:
                sv["g"] += 1; sl["p"] += 1
            else:
                sl["e"] += 1; sv["e"] += 1

        ranked = sorted(
            stats.items(),
            key=lambda kv: (3 * kv[1]["g"] + kv[1]["e"], kv[1]["pf"] - kv[1]["pc"]),
            reverse=True,
        )
        for pos, (eid, s) in enumerate(ranked, start=1):
            nom, fcb_id, lletra = equips.get(eid, ("?", None, ""))
            # "UNICO" = club amb un sol equip → no es mostra la lletra.
            equip = nom if (lletra or "").strip().upper() in ("", "UNICO") else f"{nom} {lletra}".strip()
            standing_rows.append({
                "lliga_id": LLIGA_3B_ID, "divisio_id": div, "grup_id": gid,
                "posicio": pos, "equip": equip, "club_fcb_id": fcb_id,
                "pj": s["pj"], "g": s["g"], "e": s["e"], "p": s["p"],
                "punts": 3 * s["g"] + s["e"], "pf": s["pf"], "pc": s["pc"],
            })

    counts = {}
    counts["lliga_groups"] = _upsert(
        sb, "lliga_groups", group_rows, "lliga_id,divisio_id,grup_id", prog
    )
    counts["lliga_standings"] = _upsert(
        sb, "lliga_standings", standing_rows, "lliga_id,divisio_id,grup_id,equip", prog
    )
    conn.close()
    return counts


def publish_copa(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Puja les classificacions de la Copa (edició actual) a Supabase. FASE 4."""
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    ed_row = conn.execute("SELECT MAX(edicio_id) AS m FROM copa_classificacio").fetchone()
    edicio = ed_row["m"] if ed_row else None

    jornades = {
        r["jornada"]: (r["nom"], r["ordre"])
        for r in conn.execute(
            "SELECT jornada, nom, ordre FROM copa_jornades WHERE edicio_id = ?", (edicio,)
        )
    }

    group_rows = [
        {
            "edicio_id": edicio, "jornada": r["jornada"], "grup_id": r["grup_id"],
            "grup_nom": r["grup_nom"],
            "jornada_nom": jornades.get(r["jornada"], (None, None))[0],
            "ordre": jornades.get(r["jornada"], (None, None))[1],
        }
        for r in conn.execute(
            """
            SELECT DISTINCT jornada, grup_id, grup_nom FROM copa_classificacio
            WHERE edicio_id = ?
            """,
            (edicio,),
        )
    ]
    standing_rows = [
        {
            "edicio_id": edicio, "jornada": r["jornada"], "grup_id": r["grup_id"],
            "posicio": r["posicio"], "equip": r["equip"],
            "punts": r["punts"], "parcials": r["parcials"], "mitjana": r["mitjana"],
        }
        for r in conn.execute(
            """
            SELECT jornada, grup_id, posicio, equip, punts, parcials, mitjana
            FROM copa_classificacio WHERE edicio_id = ?
            """,
            (edicio,),
        )
    ]

    counts = {}
    counts["copa_groups"] = _upsert(
        sb, "copa_groups", group_rows, "edicio_id,jornada,grup_id", prog
    )
    counts["copa_standings"] = _upsert(
        sb, "copa_standings", standing_rows, "edicio_id,jornada,grup_id,equip", prog
    )
    conn.close()
    return counts


def publish_opens(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Puja els opens (torneigs individuals) + classificacions a Supabase. FASE 5."""
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    # open_id = id intern (únic: torneig_id_extern es repeteix per divisions).
    opens = [
        {"open_id": r["id"], "nom": r["nom"], "temporada_id": r["temporada_id"]}
        for r in conn.execute("SELECT id, nom, temporada_id FROM torneigs_individuals")
    ]
    seen: set[tuple[int, str]] = set()
    classifs = []
    for r in conn.execute(
        """
        SELECT tp.torneig_id AS open_id, tp.posicio,
               p.fcb_id AS player_fcb_id, p.nom AS jugador, tp.club_text AS club,
               tp.partides_jugades AS partides, tp.punts, tp.caramboles, tp.entrades,
               tp.mitjana_general, tp.mitjana_particular, tp.serie_max
        FROM torneig_participants tp
        JOIN players p ON p.id = tp.player_id
        ORDER BY tp.torneig_id, tp.posicio
        """
    ):
        key = (r["open_id"], r["player_fcb_id"])
        if key in seen:
            continue
        seen.add(key)
        classifs.append({
            "open_id": r["open_id"], "posicio": r["posicio"],
            "player_fcb_id": r["player_fcb_id"], "jugador": r["jugador"], "club": r["club"],
            "partides": r["partides"], "punts": r["punts"], "caramboles": r["caramboles"],
            "entrades": r["entrades"], "mitjana_general": r["mitjana_general"],
            "mitjana_particular": r["mitjana_particular"], "serie_max": r["serie_max"],
        })

    counts = {}
    counts["opens"] = _upsert(sb, "opens", opens, "open_id", prog)
    counts["open_classifications"] = _upsert(
        sb, "open_classifications", classifs, "open_id,player_fcb_id", prog
    )
    conn.close()
    return counts
