"""Calcula rècords històrics i els publica a fcbillar.records.

La modalitat autèntica d'una partida és la del rànquing enllaçat
(ranking_game_links), no el modalitat_codi (que pot estar mal posat en
duplicats de l'scrape de competició). Els rècords de joc filtren per
partides enllaçades a un rànquing de 3 bandes.
"""

from __future__ import annotations

import sqlite3

from fcbillar.cloud_sync import _upsert, get_client
from fcbillar.config import get_settings

# Partides genuïnament de 3 bandes: enllaçades a un rànquing de 3 bandes.
G3B = (
    "games g JOIN ranking_game_links rgl ON rgl.game_id=g.id "
    "JOIN rankings rk ON rk.id=rgl.ranking_id JOIN modalitats m ON m.id=rk.modalitat_id "
    "AND m.codi_fcb=1"
)
NO3B = (
    "AND UPPER(ti.nom) NOT LIKE '%FEMENI%' AND UPPER(ti.nom) NOT LIKE '%QUADRE%' "
    "AND UPPER(ti.nom) NOT LIKE '%LLIURE%' AND UPPER(ti.nom) NOT LIKE '%BANDA %'"
)


def main() -> None:
    s = get_settings()
    conn = sqlite3.connect(str(s.db_path))
    conn.row_factory = sqlite3.Row
    rows = []

    def add(cat, q, fmt, lim=5):
        for i, r in enumerate(conn.execute(q), start=1):
            if i > lim:
                break
            rows.append({
                "categoria": cat, "ordre": i, "player_fcb_id": r["fcb"],
                "jugador": r["nom"], "valor": fmt(r), "detall": None,
            })

    add(
        "Millor mitjana al rànquing (3B)",
        """SELECT p.fcb_id fcb, p.nom, MAX(re.mitjana_general) v
        FROM ranking_entries re JOIN rankings rk ON rk.id=re.ranking_id
        JOIN modalitats m ON m.id=rk.modalitat_id JOIN players p ON p.id=re.player_id
        WHERE m.codi_fcb=1 AND p.fcb_id NOT LIKE 'name:%'
        GROUP BY p.id HAVING COUNT(*) >= 5 ORDER BY v DESC LIMIT 5""",
        lambda r: f"{r['v']:.3f}",
    )
    add(
        "Millor mitjana en una partida (3B)",
        f"""SELECT p.fcb_id fcb, p.nom, MAX(CAST(x.car AS REAL)/x.ent) v FROM (
            SELECT DISTINCT g.id gid, g.player1_id pid, g.caramboles1 car, g.entrades ent FROM {G3B} WHERE g.entrades>=15 AND g.caramboles1 IS NOT NULL
            UNION SELECT DISTINCT g.id, g.player2_id, g.caramboles2, g.entrades FROM {G3B} WHERE g.entrades>=15 AND g.caramboles2 IS NOT NULL
        ) x JOIN players p ON p.id=x.pid WHERE p.fcb_id NOT LIKE 'name:%' GROUP BY p.id ORDER BY v DESC LIMIT 5""",
        lambda r: f"{r['v']:.3f}",
    )
    add(
        "Millor sèrie (3B)",
        f"""SELECT p.fcb_id fcb, p.nom, MAX(x.s) v FROM (
            SELECT DISTINCT g.id gid, g.player1_id pid, g.serie_max1 s FROM {G3B} WHERE g.serie_max1 IS NOT NULL AND g.serie_max1 <= 20
            UNION SELECT DISTINCT g.id, g.player2_id, g.serie_max2 FROM {G3B} WHERE g.serie_max2 IS NOT NULL AND g.serie_max2 <= 20
        ) x JOIN players p ON p.id=x.pid WHERE p.fcb_id NOT LIKE 'name:%' GROUP BY p.id ORDER BY v DESC LIMIT 5""",
        lambda r: str(r["v"]),
    )
    add(
        "Més partides (3B)",
        f"""SELECT p.fcb_id fcb, p.nom, COUNT(*) v FROM (
            SELECT DISTINCT g.id gid, g.player1_id pid FROM {G3B}
            UNION SELECT DISTINCT g.id, g.player2_id FROM {G3B}
        ) x JOIN players p ON p.id=x.pid WHERE p.fcb_id NOT LIKE 'name:%' GROUP BY p.id ORDER BY v DESC LIMIT 5""",
        lambda r: str(r["v"]),
    )
    add(
        "Opens guanyats (3B)",
        f"""SELECT p.fcb_id fcb, p.nom, COUNT(*) v
        FROM torneig_participants tp JOIN torneigs_individuals ti ON ti.id=tp.torneig_id
        JOIN players p ON p.id=tp.player_id
        WHERE tp.posicio=1 AND UPPER(ti.nom) LIKE '%OPEN%' {NO3B} AND p.fcb_id NOT LIKE 'name:%'
        GROUP BY p.id ORDER BY v DESC LIMIT 5""",
        lambda r: str(r["v"]),
    )
    conn.close()

    sb = get_client()
    sb.table("records").delete().neq("categoria", "").execute()
    n = _upsert(sb, "records", rows, "categoria,ordre", lambda l, m: None)
    print(f"records: {n} ({len(set(r['categoria'] for r in rows))} categories)")


if __name__ == "__main__":
    main()
