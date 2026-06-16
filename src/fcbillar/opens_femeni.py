"""Rànquing del Circuit Català de Tres Bandes Femení (Reglament 23-Oct-2025).

És **independent** del Rànquing Català d'Opens (general): les proves femenines
—Campionat de Catalunya Femení + Opens Femenins— tenen una taula de punts
pròpia (Art. XVI, dues variants segons el tipus de prova) i el rànquing suma
les puntuacions de les **últimes 5 proves disputades** (Art. XVII). No es
trepitgen amb el circuit general.

Computa des de la BD SQLite de FCBillar (torneigs_individuals /
torneig_participants), la mateixa font que el rànquing general a `cloud_sync`.
Reutilitzat per:
  - cloud_sync.publish_open_ranking_femeni → Supabase open_ranking (genere='femeni')
  - DataSource.player_opens_femeni         → fitxa de jugador (app local)

Reglament: https://www.fcbillar.cat/media/2025-2026/REGLAMENTACIONS/Reglament-CircuitCatalaTresBandesFemeni-25-26.pdf
"""

from __future__ import annotations

import re as _re
import sqlite3
import unicodedata as _ud
from collections import defaultdict

from fcb_opens.reglament.puntuacio import points_for_position_femeni

# Modalitats que descarten una prova com a "tres bandes" pel nom.
_NO3B = ("QUADRE", "LLIURE", "BANDA", "QUILLES", "ARTISTIC", "BIATHL", "600", "71/2", "47/2")
WINDOW = 5  # Art. XVII: el rànquing suma les últimes 5 proves


def _nm(s: str | None) -> str:
    s = "".join(c for c in _ud.normalize("NFD", s or "") if _ud.category(c) != "Mn")
    return " ".join(s.strip().lower().split())


def _sig(p1, c1, p2, c2, e):
    return (frozenset({(_nm(p1), c1), (_nm(p2), c2)}), e)


def femeni_provas(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Proves del circuit femení (tres bandes), ordenades cronològicament.

    Cronologia: `divisio_id_extern` (la FCB l'assigna creixent per prova
    disputada), igual que el rànquing general.
    """
    rows = [
        o
        for o in conn.execute(
            "SELECT id, nom, divisio_id_extern, temporada_id FROM torneigs_individuals"
        ).fetchall()
        if "FEMENI" in (o["nom"] or "").upper()
        and not any(b in (o["nom"] or "").upper() for b in _NO3B)
    ]
    return sorted(rows, key=lambda o: o["divisio_id_extern"] or 0)


def _derive_standings_from_partides(
    conn: sqlite3.Connection, tor_ext: int, div_ext: int, nom2fcb: dict[str, str]
) -> list[tuple[str, str, str | None, int]]:
    """Deriva la classificació d'una prova des de les PARTIDES (torneig_partides)
    quan la federació encara no n'ha publicat la classificació final però els
    resultats ja hi són. Ordena per punts de matx (suma) i, com a desempat, per
    mitjana general (Σcaramboles / Σentrades). Retorna [(fcb_id, nom, None, posicio)].
    """
    agg: dict[str, dict] = {}
    for r in conn.execute(
        "SELECT player1_nom, caramboles1, punts1, player2_nom, caramboles2, punts2, entrades "
        "FROM torneig_partides WHERE torneig_id_extern = ? AND divisio_id_extern = ?",
        (tor_ext, div_ext),
    ):
        ent = r["entrades"] or 0
        for nom, car, pts in (
            (r["player1_nom"], r["caramboles1"], r["punts1"]),
            (r["player2_nom"], r["caramboles2"], r["punts2"]),
        ):
            a = agg.setdefault(_nm(nom), {"nom": nom, "pts": 0, "car": 0, "ent": 0})
            a["pts"] += pts or 0
            a["car"] += car or 0
            a["ent"] += ent
    ranked = sorted(
        agg.values(),
        key=lambda a: (-a["pts"], -(a["car"] / a["ent"] if a["ent"] else 0.0), a["nom"]),
    )
    out: list[tuple[str, str, str | None, int]] = []
    for pos, a in enumerate(ranked, start=1):
        fcb = nom2fcb.get(_nm(a["nom"]))
        if fcb is not None:
            out.append((fcb, a["nom"], None, pos))
    return out


def femeni_ranking_rows(conn: sqlite3.Connection) -> list[dict]:
    """Files del rànquing femení: un snapshot per ronda (finestra mòbil de 5).

    Cada fila és `{genere, ronda, ronda_nom, ronda_data, ronda_temp, posicio,
    player_fcb_id, jugador, club, opens_jugats, punts, detall}`, amb la mateixa
    forma que el rànquing general a `cloud_sync.publish_open_ranking`.
    """
    provas = femeni_provas(conn)
    if not provas:
        return []
    ids = [o["id"] for o in provas]
    id_set = set(ids)
    ordered = list(ids)  # ja ordenats cronològicament
    # Tipus de prova: sense "OPEN" al nom → Campionat de Catalunya Femení.
    is_camp = {o["id"]: "OPEN" not in (o["nom"] or "").upper() for o in provas}
    onom = {
        o["id"]: _re.sub(r"\s*-\s*[ÚU]NICA\s*$", "", o["nom"] or "", flags=_re.I).strip()
        for o in provas
    }
    tnom = {
        r["id"]: r["temp"]
        for r in conn.execute(
            "SELECT ti.id, te.nom AS temp FROM torneigs_individuals ti "
            "LEFT JOIN temporades te ON te.id = ti.temporada_id"
        )
    }

    # Data de cada prova (millor esforç: creuant la partida amb `games` per signatura).
    gdate: dict = {}
    for r in conn.execute(
        "SELECT g.data_partida d, p1.nom n1, g.caramboles1 c1, p2.nom n2, g.caramboles2 c2, g.entrades e "
        "FROM games g JOIN competicions comp ON comp.id = g.competicio_id "
        "JOIN players p1 ON p1.id = g.player1_id JOIN players p2 ON p2.id = g.player2_id "
        "WHERE comp.nom = 'INDIVIDUAL'"
    ):
        gdate[_sig(r["n1"], r["c1"], r["n2"], r["c2"], r["e"])] = r["d"]
    idmap = {
        (r["torneig_id_extern"], r["divisio_id_extern"]): r["id"]
        for r in conn.execute(
            "SELECT id, torneig_id_extern, divisio_id_extern FROM torneigs_individuals"
        )
    }
    open_date: dict = defaultdict(str)
    for r in conn.execute("SELECT * FROM torneig_partides"):
        tid = idmap.get((r["torneig_id_extern"], r["divisio_id_extern"]))
        if tid not in id_set:
            continue
        d = gdate.get(
            _sig(r["player1_nom"], r["caramboles1"], r["player2_nom"], r["caramboles2"], r["entrades"])
        )
        if d and d > open_date[tid]:
            open_date[tid] = d

    # Desempat: mitjana 3 bandes més recent per jugadora.
    mitj: dict = {}
    for r in conn.execute(
        "SELECT p.fcb_id, re.mitjana_general FROM ranking_entries re "
        "JOIN rankings rk ON rk.id = re.ranking_id JOIN players p ON p.id = re.player_id "
        "JOIN modalitats m ON m.id = rk.modalitat_id WHERE m.codi_fcb = 1 ORDER BY rk.num_seq DESC"
    ):
        if r["fcb_id"] not in mitj and r["mitjana_general"] is not None:
            mitj[r["fcb_id"]] = r["mitjana_general"]

    # Participants per prova.
    parts: dict = defaultdict(list)
    ph = ",".join("?" * len(ids))
    for r in conn.execute(
        f"SELECT tp.torneig_id oid, p.fcb_id, p.nom, tp.posicio, tp.club_text "
        f"FROM torneig_participants tp JOIN players p ON p.id = tp.player_id "
        f"WHERE tp.torneig_id IN ({ph}) AND tp.posicio IS NOT NULL",
        ids,
    ):
        parts[r["oid"]].append((r["fcb_id"], r["nom"], r["club_text"], r["posicio"]))

    # Fallback: proves amb partides però SENSE classificació oficial publicada
    # (la federació triga a penjar-la) → deriva-la dels resultats.
    missing = [oid for oid in ids if not parts.get(oid)]
    if missing:
        nom2fcb: dict[str, str] = {}
        for r in conn.execute("SELECT nom, fcb_id FROM players"):
            nom2fcb.setdefault(_nm(r["nom"]), r["fcb_id"])
        ext_by_oid = {oid: ext for ext, oid in idmap.items()}  # oid → (tor_ext, div_ext)
        for oid in missing:
            ext = ext_by_oid.get(oid)
            if not ext:
                continue
            derived = _derive_standings_from_partides(conn, ext[0], ext[1], nom2fcb)
            if derived:
                parts[oid] = derived

    def _ddet(oid, pos, pp):
        return {
            "open": onom.get(oid), "temp": tnom.get(oid),
            "data": open_date.get(oid) or None, "pos": pos, "punts": pp,
        }

    rows: list[dict] = []
    for i in range(1, len(ordered) + 1):
        window = ordered[max(0, i - WINDOW):i]
        pp_player: dict = defaultdict(dict)
        info: dict = {}
        for oid in window:
            for fcb, nom, club, pos in parts.get(oid, []):
                pp_player[fcb][oid] = (pos, points_for_position_femeni(pos, is_camp[oid]))
                info[fcb] = (nom, club)
        last = ordered[i - 1]
        rr = []
        for fcb, (nom, club) in info.items():
            det, total, njug, maxs = [], 0, 0, 0
            for oid in window:
                if oid in pp_player[fcb]:
                    pos, pp = pp_player[fcb][oid]
                    det.append(_ddet(oid, pos, pp))
                    total += pp
                    njug += 1
                    maxs = max(maxs, pp)
                else:
                    det.append(_ddet(oid, None, 0))
            rr.append((fcb, nom, club, total, njug, det, maxs))
        # Desempat: punts ↓, millor prova ↓, mitjana 3b ↓, nom ↑
        rr.sort(key=lambda x: (-x[3], -x[6], -mitj.get(x[0], 0.0), x[1] or ""))
        for posicio, (fcb, nom, club, total, njug, det, _maxs) in enumerate(rr, start=1):
            rows.append({
                "genere": "femeni", "ronda": i, "ronda_nom": onom.get(last),
                "ronda_data": open_date.get(last) or None, "ronda_temp": tnom.get(last),
                "posicio": posicio, "player_fcb_id": fcb, "jugador": nom,
                "club": club, "opens_jugats": njug, "punts": total, "detall": det,
            })
    return rows
