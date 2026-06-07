"""Importa tots els rànquings antics (des de l'#1 fins al mínim que ja tenim)."""

from __future__ import annotations

import sqlite3

from fcbillar.config import get_settings
from fcbillar.pipeline import ingest_ranking
from fcbillar.scraper.client import ScraperClient


def main() -> None:
    s = get_settings()
    conn = sqlite3.connect(str(s.db_path))
    combos: list[tuple[int, int]] = []
    for codi in (1, 2, 3, 4, 6):
        mid = conn.execute("SELECT id FROM modalitats WHERE codi_fcb=?", (codi,)).fetchone()
        if mid is None:
            continue
        mn = conn.execute("SELECT MIN(num_seq) FROM rankings WHERE modalitat_id=?", (mid[0],)).fetchone()[0]
        for seq in range(1, mn or 1):
            combos.append((seq, codi))
    conn.close()
    print(f"Rànquings a importar: {len(combos)}", flush=True)
    ok = 0
    with ScraperClient(s) as cl:
        for i, (seq, mod) in enumerate(combos, 1):
            try:
                ingest_ranking(cl, seq, mod, settings=s)
                ok += 1
            except Exception:  # noqa: BLE001
                pass
            if i % 25 == 0:
                print(f"  {i}/{len(combos)} (ok={ok})", flush=True)
    print(f"FET ({ok}/{len(combos)})", flush=True)


if __name__ == "__main__":
    main()
