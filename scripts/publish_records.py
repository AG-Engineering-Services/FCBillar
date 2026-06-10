"""Calcula rècords per modalitat i els publica a fcbillar.records.

5 KPIs × 5 modalitats. Les dades de joc (sèrie, mitjana de partida, partides)
es prenen dels games del NÚVOL (que ja tenen la sèrie enriquida d'opens/copa);
la mitjana al rànquing i els títols, de la BD local.
"""

from __future__ import annotations

import collections
import sqlite3

import httpx

from fcbillar.cloud_sync import _env, _upsert, get_client
from fcbillar.config import get_settings

MODS = [(1, "Tres Bandes"), (2, "Lliure"), (3, "Quadre 47/2"), (4, "Banda"), (6, "Quadre 71/2")]

# Cap de mitjana de partida realista per modalitat: per damunt = partida
# guanyada en molt poques entrades (un run, no una mitjana real) o error de font.
AVG_CAP = {1: 2.7, 2: 15.0, 3: 20.0, 4: 5.0, 6: 30.0}


def fetch_cloud_games():
    url, anon = _env("SUPABASE_URL"), _env("PUBLIC_SUPABASE_ANON_KEY")
    h = {"apikey": anon, "Accept-Profile": "fcbillar"}
    cols = ("modalitat_codi,player1_fcb_id,player1_nom,caramboles1,serie_max1,"
            "player2_fcb_id,player2_nom,caramboles2,serie_max2,entrades")
    out = []
    for frm in range(0, 80000, 1000):
        r = httpx.get(f"{url}/rest/v1/games", params={"select": cols},
                      headers={**h, "Range": f"{frm}-{frm + 999}"}, timeout=40)
        d = r.json()
        if not d:
            break
        out.extend(d)
        if len(d) < 1000:
            break
    return out


def main() -> None:
    s = get_settings()
    conn = sqlite3.connect(str(s.db_path))
    conn.row_factory = sqlite3.Row
    games = fetch_cloud_games()
    rows = []

    def push(cat, ranking, fmt):
        for i, (fcb, nom, val) in enumerate(ranking[:5], start=1):
            rows.append({"categoria": cat, "ordre": i, "player_fcb_id": fcb,
                         "jugador": nom, "valor": fmt(val), "detall": None})

    for codi, mnom in MODS:
        # ---- KPIs de joc (núvol): mitjana de partida, sèrie major, més partides ----
        n = collections.Counter()
        best_avg: dict = {}
        best_ser: dict = {}
        noms: dict = {}
        for g in games:
            if g["modalitat_codi"] != codi:
                continue
            ent = g["entrades"]
            for side in (1, 2):
                fcb = g[f"player{side}_fcb_id"]
                if not fcb or fcb.startswith("name:"):
                    continue
                noms[fcb] = g[f"player{side}_nom"]
                n[fcb] += 1
                car, ser = g[f"caramboles{side}"], g[f"serie_max{side}"]
                if ent and ent >= 10 and car is not None:
                    avg = car / ent
                    if avg <= AVG_CAP.get(codi, 99):
                        best_avg[fcb] = max(best_avg.get(fcb, 0.0), avg)
                if ser is not None:
                    best_ser[fcb] = max(best_ser.get(fcb, 0), ser)

        push(f"{mnom} · Mitjana partida",
             sorted(((f, noms[f], v) for f, v in best_avg.items()), key=lambda x: -x[2]),
             lambda v: f"{v:.3f}")
        push(f"{mnom} · Sèrie major",
             sorted(((f, noms[f], v) for f, v in best_ser.items()), key=lambda x: -x[2]),
             lambda v: str(v))
        push(f"{mnom} · Més partides",
             sorted(((f, noms[f], v) for f, v in n.items()), key=lambda x: -x[2]),
             lambda v: str(v))

        # ---- Mitjana al rànquing (local) ----
        rk = [
            (r["fcb"], r["nom"], r["v"])
            for r in conn.execute(
                """SELECT p.fcb_id fcb, p.nom, MAX(re.mitjana_general) v
                   FROM ranking_entries re JOIN rankings rk ON rk.id=re.ranking_id
                   JOIN modalitats m ON m.id=rk.modalitat_id JOIN players p ON p.id=re.player_id
                   WHERE m.codi_fcb=? AND p.fcb_id NOT LIKE 'name:%'
                   GROUP BY p.id HAVING COUNT(*)>=5 ORDER BY v DESC LIMIT 5""",
                (codi,),
            )
        ]
        push(f"{mnom} · Mitjana rànquing", rk, lambda v: f"{v:.3f}")

        # ---- Títols (1rs llocs en competicions individuals d'aquesta modalitat) ----
        # Només OPENS (no campionats). Si una modalitat no en té, la categoria
        # queda buida i no s'ensenya.
        ti = [
            (r["fcb"], r["nom"], r["v"])
            for r in conn.execute(
                """SELECT p.fcb_id fcb, p.nom, COUNT(*) v
                   FROM torneig_participants tp JOIN torneigs_individuals t ON t.id=tp.torneig_id
                   JOIN modalitats m ON m.id=t.modalitat_id JOIN players p ON p.id=tp.player_id
                   WHERE tp.posicio=1 AND m.codi_fcb=? AND p.fcb_id NOT LIKE 'name:%'
                     AND UPPER(t.nom) LIKE '%OPEN%'
                   GROUP BY p.id ORDER BY v DESC LIMIT 5""",
                (codi,),
            )
        ]
        push(f"{mnom} · Opens guanyats", ti, lambda v: str(v))

    conn.close()
    sb = get_client()
    sb.table("records").delete().neq("categoria", "").execute()
    nrec = _upsert(sb, "records", rows, "categoria,ordre", lambda l, m: None)
    print(f"records: {nrec} ({len(set(r['categoria'] for r in rows))} categories)")


if __name__ == "__main__":
    main()
