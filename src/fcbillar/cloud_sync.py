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

    import re as _re
    import unicodedata as _ud

    def _nm(s):
        s = "".join(c for c in _ud.normalize("NFD", s or "") if _ud.category(c) != "Mn")
        return " ".join(s.strip().lower().split())

    # Lligues multi-modalitat (4 modalitats / Catalana) vs 3 bandes pures.
    multimod = {3, 7, 9, 13, 18, 22, 25, 27, 31, 33, 35, 37}

    # Signatura de partida d'open → nom de l'open (per etiquetar les INDIVIDUAL).
    open_nom = {
        (r["torneig_id_extern"], r["divisio_id_extern"]): r["nom"]
        for r in conn.execute(
            "SELECT torneig_id_extern, divisio_id_extern, nom FROM torneigs_individuals"
        )
    }
    def _sigkey(p1n, c1, p2n, c2, ent):
        return (frozenset({(_nm(p1n), c1), (_nm(p2n), c2)}), ent)

    open_sig: dict = {}  # key -> (nom_open, {norm_nom: serie})
    try:
        tp_rows = conn.execute("SELECT * FROM torneig_partides").fetchall()
    except sqlite3.OperationalError:
        tp_rows = []
    for r in tp_rows:
        nom = open_nom.get((r["torneig_id_extern"], r["divisio_id_extern"]))
        if not nom:
            continue
        nom = _re.sub(r"\s*-\s*[ÚU]NICA\s*$", "", nom, flags=_re.I).strip()
        key = _sigkey(r["player1_nom"], r["caramboles1"], r["player2_nom"], r["caramboles2"], r["entrades"])
        open_sig[key] = (nom, {_nm(r["player1_nom"]): r["serie1"], _nm(r["player2_nom"]): r["serie2"]})

    copa_sig: dict = {}  # key -> {norm_nom: serie}
    try:
        cp_rows = conn.execute(
            "SELECT local_nom, local_caramboles, local_serie, visitant_nom, "
            "visitant_caramboles, visitant_serie, entrades FROM copa_partides"
        ).fetchall()
    except sqlite3.OperationalError:
        cp_rows = []
    for r in cp_rows:
        key = _sigkey(r["local_nom"], r["local_caramboles"], r["visitant_nom"], r["visitant_caramboles"], r["entrades"])
        copa_sig[key] = {_nm(r["local_nom"]): r["local_serie"], _nm(r["visitant_nom"]): r["visitant_serie"]}

    def enrich(r):
        """Retorna (etiqueta_competicio, serie1, serie2) enriquint des d'opens/copa."""
        comp, lliga_id = r["competicio"], r["lliga_id"]
        s1, s2 = r["serie_max1"], r["serie_max2"]
        label = comp
        if comp == "LLIGA":
            label = "Lliga 4 Modalitats" if lliga_id in multimod else "Lliga 3 Bandes"
        elif comp == "INDIVIDUAL":
            hit = open_sig.get(
                _sigkey(r["player1_nom"], r["caramboles1"], r["player2_nom"], r["caramboles2"], r["entrades"])
            )
            if hit:
                label = hit[0]
                if s1 is None:
                    s1 = hit[1].get(_nm(r["player1_nom"]))
                if s2 is None:
                    s2 = hit[1].get(_nm(r["player2_nom"]))
        elif comp == "COPA":
            sm = copa_sig.get(
                _sigkey(r["player1_nom"], r["caramboles1"], r["player2_nom"], r["caramboles2"], r["entrades"])
            )
            if sm:
                if s1 is None:
                    s1 = sm.get(_nm(r["player1_nom"]))
                if s2 is None:
                    s2 = sm.get(_nm(r["player2_nom"]))
        return label, s1, s2

    games = []
    for r in conn.execute(
        """
        SELECT g.id, g.data_partida, m.codi_fcb AS modalitat_codi,
               comp.nom AS competicio, en.lliga_id AS lliga_id,
               p1.fcb_id AS player1_fcb_id, p1.nom AS player1_nom,
               g.caramboles1, g.serie_max1,
               p2.fcb_id AS player2_fcb_id, p2.nom AS player2_nom,
               g.caramboles2, g.serie_max2,
               g.entrades, pw.fcb_id AS guanyador_fcb_id
        FROM games g
        JOIN modalitats m ON m.id = g.modalitat_id
        LEFT JOIN competicions comp ON comp.id = g.competicio_id
        LEFT JOIN encontres_lliga en ON en.id = g.encontre_lliga_id
        JOIN players p1 ON p1.id = g.player1_id
        JOIN players p2 ON p2.id = g.player2_id
        LEFT JOIN players pw ON pw.id = g.guanyador_id
        """
    ):
        label, s1, s2 = enrich(r)
        games.append({
            "id": r["id"], "data_partida": r["data_partida"], "modalitat_codi": r["modalitat_codi"],
            "competicio": label,
            "player1_fcb_id": r["player1_fcb_id"], "player1_nom": r["player1_nom"],
            "caramboles1": r["caramboles1"], "serie_max1": s1,
            "player2_fcb_id": r["player2_fcb_id"], "player2_nom": r["player2_nom"],
            "caramboles2": r["caramboles2"], "serie_max2": s2,
            "entrades": r["entrades"], "guanyador_fcb_id": r["guanyador_fcb_id"],
        })
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
        if r["equip"] and str(r["equip"]).strip() not in ("0", "")
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


def _rank_players(acc: dict) -> list[tuple]:
    """Ordena per (punts desc, mitjana desc) i assigna posició. acc: key->stats."""
    from collections import defaultdict

    groups: dict = defaultdict(list)
    for key, a in acc.items():
        groups[key[:-1]].append((key[-1], a))
    out = []
    for gkey, lst in groups.items():
        ranked = sorted(
            lst,
            key=lambda kv: (kv[1]["punts"], (kv[1]["car"] / kv[1]["ent"]) if kv[1]["ent"] else 0),
            reverse=True,
        )
        for pos, (who, a) in enumerate(ranked, start=1):
            out.append((gkey, pos, who, a))
    return out


def publish_lliga_player_rankings(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Rànquing individual de jugadors per grup de la lliga 3 bandes (punts + mitjana)."""
    import json

    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    tr = conn.execute("SELECT id FROM temporades ORDER BY nom DESC LIMIT 1").fetchone()
    season_id = tr["id"] if tr else None
    players = {r["id"]: (r["fcb_id"], r["nom"]) for r in conn.execute("SELECT id, fcb_id, nom FROM players")}
    equip_club = {
        r["id"]: r["nom"]
        for r in conn.execute("SELECT e.id, c.nom FROM equips e JOIN clubs c ON c.id = e.club_id")
    }

    acc: dict = {}
    for r in conn.execute(
        """
        SELECT en.divisio_id AS div, en.grup_id AS grup,
               g.player1_id AS p1, g.player2_id AS p2,
               g.caramboles1 AS c1, g.caramboles2 AS c2, g.entrades AS e,
               g.equip1_id AS eq1, g.equip2_id AS eq2, g.extras_json AS ex
        FROM games g JOIN encontres_lliga en ON en.id = g.encontre_lliga_id
        WHERE en.lliga_id = ? AND en.temporada_id = ? AND g.entrades > 0
        """,
        (LLIGA_3B_ID, season_id),
    ):
        try:
            ex = json.loads(r["ex"] or "{}")
        except (ValueError, TypeError):
            ex = {}
        for pid, car, pu, eq in (
            (r["p1"], r["c1"], ex.get("punts1"), r["eq1"]),
            (r["p2"], r["c2"], ex.get("punts2"), r["eq2"]),
        ):
            a = acc.setdefault((r["div"], r["grup"], pid), {"pj": 0, "punts": 0, "car": 0, "ent": 0, "eq": eq})
            a["pj"] += 1
            a["punts"] += pu or 0
            a["car"] += car or 0
            a["ent"] += r["e"] or 0
            a["eq"] = eq

    rows = []
    for (div, grup), pos, pid, a in _rank_players(acc):
        fcb, nom = players.get(pid, (None, "?"))
        if not fcb:
            continue
        rows.append({
            "lliga_id": LLIGA_3B_ID, "divisio_id": div, "grup_id": grup, "posicio": pos,
            "player_fcb_id": fcb, "jugador": nom, "club": equip_club.get(a["eq"]),
            "partides": a["pj"], "punts": a["punts"], "caramboles": a["car"], "entrades": a["ent"],
            "mitjana": (a["car"] / a["ent"]) if a["ent"] else None,
        })
    n = _upsert(sb, "lliga_player_rankings", rows, "lliga_id,divisio_id,grup_id,player_fcb_id", prog)
    conn.close()
    return {"lliga_player_rankings": n}


def publish_copa_player_rankings(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Rànquing individual de jugadors per grup de la Copa (punts + mitjana)."""
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    ed_row = conn.execute("SELECT MAX(edicio_id) AS m FROM copa_classificacio").fetchone()
    edicio = ed_row["m"] if ed_row else None
    name_to_fcb = {r["nom"]: r["fcb_id"] for r in conn.execute("SELECT nom, fcb_id FROM players")}

    # Rànquing de TOTA la competició (no per grup): s'agrega per jugador i es
    # desa amb jornada=0, grup_id=0 com a sentinella de "competició sencera".
    acc: dict = {}
    for r in conn.execute(
        """
        SELECT cp.local_nom AS ln, cp.local_caramboles AS lc, cp.punts_local AS lp,
               cp.visitant_nom AS vn, cp.visitant_caramboles AS vc, cp.punts_visitant AS vp,
               cp.entrades AS e
        FROM copa_partides cp JOIN copa_encontres ce ON ce.id = cp.encontre_copa_id
        WHERE ce.edicio_id = ?
        """,
        (edicio,),
    ):
        if not r["e"]:
            continue
        for nom, car, pu in ((r["ln"], r["lc"], r["lp"]), (r["vn"], r["vc"], r["vp"])):
            if not nom or str(nom).strip() in ("0", ""):
                continue
            a = acc.setdefault(nom, {"pj": 0, "punts": 0, "car": 0, "ent": 0})
            a["pj"] += 1
            a["punts"] += pu or 0
            a["car"] += car or 0
            a["ent"] += r["e"] or 0

    ranked = sorted(
        acc.items(),
        key=lambda kv: (kv[1]["punts"], (kv[1]["car"] / kv[1]["ent"]) if kv[1]["ent"] else 0),
        reverse=True,
    )
    rows = []
    pos = 0
    for nom, a in ranked:
        fcb = name_to_fcb.get(nom)
        if not fcb:
            continue
        pos += 1
        rows.append({
            "edicio_id": edicio, "jornada": 0, "grup_id": 0, "posicio": pos,
            "player_fcb_id": fcb, "jugador": nom, "club": None,
            "partides": a["pj"], "punts": a["punts"], "caramboles": a["car"], "entrades": a["ent"],
            "mitjana": (a["car"] / a["ent"]) if a["ent"] else None,
        })
    n = _upsert(sb, "copa_player_rankings", rows, "edicio_id,jornada,grup_id,player_fcb_id", prog)
    conn.close()
    return {"copa_player_rankings": n}


def publish_lliga_encontres(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Encontres de lliga 3 bandes (per jornada) + les seves partides individuals."""
    from collections import defaultdict

    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    tr = conn.execute("SELECT id FROM temporades ORDER BY nom DESC LIMIT 1").fetchone()
    season_id = tr["id"] if tr else None
    equips = {
        r["id"]: (r["nom"], r["lletra"])
        for r in conn.execute("SELECT e.id, c.nom, e.lletra FROM equips e JOIN clubs c ON c.id = e.club_id")
    }

    def eqname(eid):
        nom, lletra = equips.get(eid, ("?", ""))
        return nom if (lletra or "").strip().upper() in ("", "UNICO") else f"{nom} {lletra}".strip()

    encs = conn.execute(
        """
        SELECT id, divisio_id, grup_id, jornada_id, data,
               equip_local_id, equip_visitant_id, p_match_local, p_match_visitant
        FROM encontres_lliga WHERE lliga_id = ? AND temporada_id = ?
        """,
        (LLIGA_3B_ID, season_id),
    ).fetchall()

    # Ordre de jornada per grup: rang del jornada_id per data mínima.
    jdates: dict = defaultdict(dict)
    for e in encs:
        key = (e["divisio_id"], e["grup_id"])
        cur = jdates[key].get(e["jornada_id"])
        if cur is None or (e["data"] and e["data"] < cur):
            jdates[key][e["jornada_id"]] = e["data"]
    jorder: dict = {}
    for (div, grup), jmap in jdates.items():
        for i, (jid, _) in enumerate(sorted(jmap.items(), key=lambda kv: (kv[1] or "")), start=1):
            jorder[(div, grup, jid)] = i

    enc_rows = [{
        "encontre_id": e["id"], "divisio_id": e["divisio_id"], "grup_id": e["grup_id"],
        "jornada": jorder.get((e["divisio_id"], e["grup_id"], e["jornada_id"])),
        "data": e["data"], "equip_local": eqname(e["equip_local_id"]),
        "equip_visitant": eqname(e["equip_visitant_id"]),
        "gols_local": e["p_match_local"], "gols_visitant": e["p_match_visitant"],
    } for e in encs]

    part_rows = []
    counter: dict = defaultdict(int)
    for r in conn.execute(
        """
        SELECT g.encontre_lliga_id AS eid, m.codi_fcb AS mod,
               p1.nom AS j1, g.caramboles1 AS c1, p2.nom AS j2, g.caramboles2 AS c2, g.entrades AS e
        FROM games g JOIN encontres_lliga en ON en.id = g.encontre_lliga_id
        JOIN modalitats m ON m.id = g.modalitat_id
        JOIN players p1 ON p1.id = g.player1_id JOIN players p2 ON p2.id = g.player2_id
        WHERE en.lliga_id = ? AND en.temporada_id = ?
        ORDER BY g.encontre_lliga_id, m.codi_fcb
        """,
        (LLIGA_3B_ID, season_id),
    ):
        counter[r["eid"]] += 1
        part_rows.append({
            "encontre_id": r["eid"], "ordre": counter[r["eid"]], "modalitat_codi": r["mod"],
            "jugador_local": r["j1"], "caramboles_local": r["c1"],
            "jugador_visitant": r["j2"], "caramboles_visitant": r["c2"], "entrades": r["e"],
        })

    counts = {}
    counts["lliga_encontres"] = _upsert(sb, "lliga_encontres", enc_rows, "encontre_id", prog)
    counts["lliga_partides"] = _upsert(sb, "lliga_partides", part_rows, "encontre_id,ordre", prog)
    conn.close()
    return counts


def publish_copa_encontres(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Encontres de copa (edició actual) + les seves partides individuals."""
    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    ed = conn.execute("SELECT MAX(edicio_id) AS m FROM copa_encontres").fetchone()["m"]
    enc_rows = [{
        "encontre_id": r["id"], "jornada": r["jornada"], "grup_id": r["grup_id"], "grup_nom": r["grup_nom"],
        "equip_local": r["equip_local"], "equip_visitant": r["equip_visitant"],
        "gols_local": r["p_match_local"], "gols_visitant": r["p_match_visitant"],
    } for r in conn.execute(
        """
        SELECT id, jornada, grup_id, grup_nom, equip_local, equip_visitant,
               p_match_local, p_match_visitant
        FROM copa_encontres WHERE edicio_id = ?
        """, (ed,))
    ]
    part_rows = [{
        "encontre_id": r["encontre_copa_id"], "ordre": r["ordre"],
        "jugador_local": r["local_nom"], "caramboles_local": r["local_caramboles"],
        "jugador_visitant": r["visitant_nom"], "caramboles_visitant": r["visitant_caramboles"],
        "entrades": r["entrades"],
    } for r in conn.execute(
        """
        SELECT cp.encontre_copa_id, cp.ordre, cp.local_nom, cp.local_caramboles,
               cp.visitant_nom, cp.visitant_caramboles, cp.entrades
        FROM copa_partides cp JOIN copa_encontres ce ON ce.id = cp.encontre_copa_id
        WHERE ce.edicio_id = ?
        """, (ed,))
    ]
    counts = {}
    counts["copa_encontres"] = _upsert(sb, "copa_encontres", enc_rows, "encontre_id", prog)
    counts["copa_partides"] = _upsert(sb, "copa_partides", part_rows, "encontre_id,ordre", prog)
    conn.close()
    return counts


def publish_open_partides(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Puja les partides (eliminatòries) dels opens, mapejades a l'open_id intern."""
    from collections import defaultdict

    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    idmap = {
        (r["torneig_id_extern"], r["divisio_id_extern"]): r["id"]
        for r in conn.execute(
            "SELECT id, torneig_id_extern, divisio_id_extern FROM torneigs_individuals"
        )
    }
    counter: dict = defaultdict(int)
    rows = []
    for r in conn.execute("SELECT * FROM torneig_partides"):
        oid = idmap.get((r["torneig_id_extern"], r["divisio_id_extern"]))
        if oid is None:
            continue
        key = (oid, r["fase_id"])
        counter[key] += 1
        rows.append({
            "open_id": oid, "fase_id": r["fase_id"], "ordre": counter[key],
            "jugador_local": r["player1_nom"], "caramboles_local": r["caramboles1"],
            "jugador_visitant": r["player2_nom"], "caramboles_visitant": r["caramboles2"],
            "entrades": r["entrades"],
        })
    n = _upsert(sb, "open_partides", rows, "open_id,fase_id,ordre", prog)
    conn.close()
    return {"open_partides": n}


def publish_open_ranking(
    db_path: Path | None = None, on_progress: Progress | None = None
) -> dict[str, int]:
    """Rànquing Català d'Opens 3 bandes (Art. XVIII: suma dels 5 millors opens)."""
    from collections import defaultdict

    from fcb_opens.reglament.puntuacio import points_for_position

    prog: Progress = on_progress or (lambda level, msg: None)
    db_path = db_path or get_settings().db_path
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    sb = get_client()

    import unicodedata as _ud

    def _nm(s):
        s = "".join(c for c in _ud.normalize("NFD", s or "") if _ud.category(c) != "Mn")
        return " ".join(s.strip().lower().split())

    def _sig(p1, c1, p2, c2, e):
        return (frozenset({(_nm(p1), c1), (_nm(p2), c2)}), e)

    open_rows = conn.execute(
        "SELECT id, nom FROM torneigs_individuals WHERE UPPER(nom) LIKE '%OPEN%' AND UPPER(nom) LIKE '%TRES BANDES%'"
    ).fetchall()
    if not open_rows:
        conn.close()
        return {"open_ranking": 0}
    open_ids = {o["id"] for o in open_rows}

    # Data de cada partida individual (per signatura) → data de cada open.
    gdate: dict = {}
    for r in conn.execute(
        """
        SELECT g.data_partida d, p1.nom n1, g.caramboles1 c1, p2.nom n2, g.caramboles2 c2, g.entrades e
        FROM games g JOIN competicions comp ON comp.id = g.competicio_id
        JOIN players p1 ON p1.id = g.player1_id JOIN players p2 ON p2.id = g.player2_id
        WHERE comp.nom = 'INDIVIDUAL'
        """
    ):
        gdate[_sig(r["n1"], r["c1"], r["n2"], r["c2"], r["e"])] = r["d"]
    idmap = {
        (r["torneig_id_extern"], r["divisio_id_extern"]): r["id"]
        for r in conn.execute("SELECT id, torneig_id_extern, divisio_id_extern FROM torneigs_individuals")
    }
    open_date: dict = defaultdict(str)
    for r in conn.execute("SELECT * FROM torneig_partides"):
        tid = idmap.get((r["torneig_id_extern"], r["divisio_id_extern"]))
        if tid not in open_ids:
            continue
        d = gdate.get(_sig(r["player1_nom"], r["caramboles1"], r["player2_nom"], r["caramboles2"], r["entrades"]))
        if d and d > open_date[tid]:
            open_date[tid] = d

    import re as _re

    onom = {
        o["id"]: _re.sub(r"\s*-\s*[ÚU]NICA\s*$", "", o["nom"], flags=_re.I).strip() for o in open_rows
    }
    ordered = sorted(open_ids, key=lambda t: open_date.get(t, ""))  # cronològic ascendent

    # Participants per open
    parts: dict = defaultdict(list)
    ph = ",".join("?" * len(open_ids))
    for r in conn.execute(
        f"""
        SELECT tp.torneig_id AS oid, p.fcb_id, p.nom, tp.posicio, tp.club_text
        FROM torneig_participants tp JOIN players p ON p.id = tp.player_id
        WHERE tp.torneig_id IN ({ph}) AND tp.posicio IS NOT NULL
        """,
        list(open_ids),
    ):
        parts[r["oid"]].append((r["fcb_id"], r["nom"], r["club_text"], r["posicio"]))

    # Un snapshot per ronda: finestra mòbil dels últims 5 opens fins a la ronda i.
    all_rows = []
    for i in range(1, len(ordered) + 1):
        window = ordered[max(0, i - 5):i]
        acc: dict = {}
        for oid in window:
            for fcb, nom, club, pos in parts.get(oid, []):
                a = acc.setdefault(fcb, {"pts": 0, "n": 0, "nom": nom, "club": club})
                a["pts"] += points_for_position(pos)
                a["n"] += 1
        last_open = ordered[i - 1]
        ranked = sorted(acc.items(), key=lambda kv: -kv[1]["pts"])
        for posicio, (fcb, a) in enumerate(ranked, start=1):
            all_rows.append({
                "ronda": i, "ronda_nom": onom.get(last_open),
                "ronda_data": open_date.get(last_open) or None,
                "posicio": posicio, "player_fcb_id": fcb, "jugador": a["nom"],
                "club": a["club"], "opens_jugats": a["n"], "punts": a["pts"],
            })
    n = _upsert(sb, "open_ranking", all_rows, "ronda,player_fcb_id", prog)
    conn.close()
    return {"open_ranking": n}
