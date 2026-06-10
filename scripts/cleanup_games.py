"""Neteja de games després d'un repàs de partideshome (idempotent).

A executar SEMPRE després del repàs, perquè partideshome (FCB) pot reintroduir:
 - duplicats d'ordre invertit (mateix joc des de dos partideshome),
 - sèries impossibles (sèrie > caramboles, error de la font),
 - mitjanes de joc impossibles a 3 bandes (entrades mal informades per la FCB).

La modalitat NO es toca mai: ve del rànquing enllaçat (autèntica).
"""

from __future__ import annotations

import collections
import sqlite3

from fcbillar.config import get_settings


def main() -> None:
    s = get_settings()
    c = sqlite3.connect(str(s.db_path))
    c.row_factory = sqlite3.Row

    # 1. Fusiona duplicats de MATEIXA modalitat (ordre de jugadors invertit).
    rows = c.execute(
        """SELECT g.id, g.player1_id p1, g.player2_id p2, g.data_partida d,
                  g.caramboles1 c1, g.caramboles2 c2, g.entrades e, m.codi_fcb mod,
                  (SELECT COUNT(*) FROM ranking_game_links r WHERE r.game_id=g.id) nl
           FROM games g JOIN modalitats m ON m.id=g.modalitat_id"""
    ).fetchall()
    grp = collections.defaultdict(list)
    for r in rows:
        a, b = sorted([(r["p1"], r["c1"]), (r["p2"], r["c2"])])
        grp[(r["d"], a, b, r["e"], r["mod"])].append(r)
    merged = 0
    for v in grp.values():
        if len(v) < 2:
            continue
        v.sort(key=lambda x: -x["nl"])
        keep = v[0]["id"]
        for m in v[1:]:
            c.execute("UPDATE OR IGNORE ranking_game_links SET game_id=? WHERE game_id=?", (keep, m["id"]))
            c.execute("DELETE FROM ranking_game_links WHERE game_id=?", (m["id"],))
            c.execute("DELETE FROM games WHERE id=?", (m["id"],))
            merged += 1

    # 2. Sèrie impossible: no pot superar les caramboles del jugador.
    s1 = c.execute("SELECT COUNT(*) FROM games WHERE serie_max1>caramboles1").fetchone()[0]
    s2 = c.execute("SELECT COUNT(*) FROM games WHERE serie_max2>caramboles2").fetchone()[0]
    c.execute("UPDATE games SET serie_max1=NULL WHERE serie_max1>caramboles1")
    c.execute("UPDATE games SET serie_max2=NULL WHERE serie_max2>caramboles2")

    # 3. A 3 bandes la sèrie no pot superar ~20 (error de parsing si ho fa).
    c.execute(
        "UPDATE games SET serie_max1=NULL WHERE serie_max1>20 AND modalitat_id IN(SELECT id FROM modalitats WHERE codi_fcb=1)"
    )
    c.execute(
        "UPDATE games SET serie_max2=NULL WHERE serie_max2>20 AND modalitat_id IN(SELECT id FROM modalitats WHERE codi_fcb=1)"
    )

    # 4. Mitjana de joc impossible a 3 bandes (>2.7 → entrades mal informades).
    bad = [
        r[0]
        for r in c.execute(
            """SELECT g.id FROM games g JOIN modalitats m ON m.id=g.modalitat_id AND m.codi_fcb=1
               WHERE g.entrades>0 AND (CAST(g.caramboles1 AS REAL)/g.entrades>2.7 OR CAST(g.caramboles2 AS REAL)/g.entrades>2.7)"""
        )
    ]
    for i in bad:
        c.execute("DELETE FROM ranking_game_links WHERE game_id=?", (i,))
        c.execute("DELETE FROM games WHERE id=?", (i,))

    c.commit()
    tot = c.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    print(f"fusionats {merged} | sèries netejades {s1+s2} | avg-impossibles esborrats {len(bad)} | total games {tot}")
    c.close()


if __name__ == "__main__":
    main()
