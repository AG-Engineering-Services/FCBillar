"""Depuració de partides duplicades per modalitat mal associada.

La modalitat autèntica ve del rànquing enllaçat (partideshome). Les versions
SENSE enllaç a rànquing que coincideixen físicament (mateixos jugadors, data,
caramboles, entrades) amb una versió ENLLAÇADA són duplicats de l'scrape de
competició amb la modalitat mal posada → s'esborren, transferint la competició
a la versió enllaçada.

Ús:  uv run python scripts/dedup_games.py [--execute]   (per defecte dry-run)
"""

from __future__ import annotations

import collections
import sqlite3
import sys

from fcbillar.config import get_settings


def main(execute: bool) -> None:
    s = get_settings()
    conn = sqlite3.connect(str(s.db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT g.id, g.player1_id p1, g.player2_id p2, g.data_partida d,
               g.caramboles1 c1, g.caramboles2 c2, g.entrades e, g.competicio_id comp,
               (SELECT GROUP_CONCAT(DISTINCT md.codi_fcb) FROM ranking_game_links rgl
                JOIN rankings rk ON rk.id=rgl.ranking_id JOIN modalitats md ON md.id=rk.modalitat_id
                WHERE rgl.game_id=g.id) rmods
        FROM games g
        """
    ).fetchall()

    grp: dict = collections.defaultdict(list)
    for r in rows:
        a, b = sorted([(r["p1"], r["c1"]), (r["p2"], r["c2"])])
        grp[(r["d"], a, b, r["e"])].append(r)

    to_delete: list[str] = []
    transfers: list[tuple[str, int]] = []  # (survivor_id, competicio_id)
    conflicts = 0
    for members in grp.values():
        if len(members) < 2:
            continue
        mods = {m["rmods"] for m in members if m["rmods"]}
        if len(mods) > 1:
            conflicts += 1  # modalitats enllaçades en conflicte: no toquem
            continue
        linked = [m for m in members if m["rmods"]]
        if not linked:
            continue  # cap versió enllaçada: no sabem quina és bona, no toquem
        survivor = linked[0]
        comp = survivor["comp"] or next((m["comp"] for m in members if m["comp"]), None)
        if comp and not survivor["comp"]:
            transfers.append((survivor["id"], comp))
        for m in members:
            if m["id"] != survivor["id"]:
                to_delete.append(m["id"])

    print(f"grups totals {len(grp)} | a esborrar {len(to_delete)} | "
          f"transferències comp {len(transfers)} | conflictes (saltats) {conflicts}")

    if not execute:
        print("DRY-RUN (cap canvi). Afegeix --execute per aplicar.")
        conn.close()
        return

    cur = conn.cursor()
    for sid, comp in transfers:
        cur.execute("UPDATE games SET competicio_id=? WHERE id=? AND competicio_id IS NULL", (comp, sid))
    # esborra enllaços orfes (per si de cas) i les partides duplicades
    cur.executemany("DELETE FROM ranking_game_links WHERE game_id=?", [(i,) for i in to_delete])
    cur.executemany("DELETE FROM games WHERE id=?", [(i,) for i in to_delete])
    conn.commit()
    print(f"FET. esborrades {len(to_delete)} partides, {len(transfers)} competicions transferides.")
    conn.close()


if __name__ == "__main__":
    main("--execute" in sys.argv)
