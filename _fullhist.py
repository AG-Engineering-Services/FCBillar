"""Ingesta historica completa: ranquings 97..2 (els que falten sota 98) per a
totes les modalitats + partides de cada jugador. Idempotent i re-executable.
"""
import sqlite3, sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from fcbillar.config import get_settings
from fcbillar.scraper.client import ScraperClient
from fcbillar.pipeline import ingest_ranking, ingest_partides

MODS = [1, 2, 3, 4, 6]
SEQS = list(range(97, 1, -1))  # 97..2
s = get_settings()
db = sqlite3.connect("data/fcbillar.db"); db.row_factory = sqlite3.Row
g0 = db.execute("select count(*) from games").fetchone()[0]
r0 = db.execute("select count(*) from rankings").fetchone()[0]
print(f"[init] seqs 97..2 x {len(MODS)} mods | games={g0} rankings={r0}", flush=True)

t0 = time.time()
rk_ok = rk_none = ph_ok = ph_fail = ph_add = 0
with ScraperClient(s) as cl:
    for si, num_seq in enumerate(SEQS, 1):
        for mod in MODS:
            # 1) Rànquing (format històric). ingest_ranking prova els formats.
            try:
                res = ingest_ranking(cl, num_seq, mod, settings=s)
            except Exception as e:
                res = None
            if not res or not getattr(res, "entries_upserted", 0):
                rk_none += 1
                continue
            rk_ok += 1
            # 2) Partides de cada jugador d'aquest rànquing/modalitat
            pids = db.execute("""
                SELECT p.fcb_id FROM ranking_entries e
                JOIN rankings r ON r.id=e.ranking_id
                JOIN modalitats m ON m.id=r.modalitat_id
                JOIN players p ON p.id=e.player_id
                WHERE r.num_seq=? AND m.codi_fcb=? AND p.fcb_id NOT LIKE 'name:%'
            """, (num_seq, mod)).fetchall()
            for row in pids:
                try:
                    pr = ingest_partides(cl, num_seq, mod, row["fcb_id"],
                                         settings=s, create_missing_players=True)
                    ph_add += pr.games_upserted; ph_ok += 1
                except Exception:
                    ph_fail += 1
        el = time.time() - t0
        gnow = db.execute("select count(*) from games").fetchone()[0]
        print(f"[seq {num_seq}] ({si}/{len(SEQS)}) rk_ok={rk_ok} rk_none={rk_none} "
              f"ph_ok={ph_ok} ph_fail={ph_fail} games={gnow} {el:.0f}s", flush=True)

# fix-winners de seguretat
bad = db.execute("""SELECT id,player1_id,player2_id,caramboles1,caramboles2 FROM games
  WHERE caramboles1 IS NOT NULL AND caramboles2 IS NOT NULL AND caramboles1<>caramboles2
  AND (guanyador_id IS NULL OR (caramboles1>caramboles2 AND guanyador_id<>player1_id)
    OR (caramboles2>caramboles1 AND guanyador_id<>player2_id))""").fetchall()
for r in bad:
    db.execute("UPDATE games SET guanyador_id=? WHERE id=?", (r[1] if r[3]>r[4] else r[2], r[0]))
db.commit()
g1 = db.execute("select count(*) from games").fetchone()[0]
r1 = db.execute("select count(*) from rankings").fetchone()[0]
print(f"[FINAL] rankings {r0}->{r1} | games {g0}->{g1} (+{g1-g0}) | "
      f"rk_ok={rk_ok} ph_ok={ph_ok} ph_fail={ph_fail} fixwin={len(bad)} | {time.time()-t0:.0f}s", flush=True)
print("[OK]", flush=True)
