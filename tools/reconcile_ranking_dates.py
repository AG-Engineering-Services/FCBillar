"""Reconcilia num_seq → mes de publicació amb les DATES REALS de l'historial.

L'historial (`/ca/jugador/ranking/historial`) és l'única font autoritativa que
lliga cada `num_seq` amb la seva data de publicació exacta. La taula `rankings`
guarda `mes_pub`/`any_pub`, però es van omplir amb una heurística monòtona
("un rànquing per mes, salta l'agost") que pot derivar quan la federació
publica dos rànquings el mateix mes o salta un mes diferent de l'agost.

Aquest script (READ-ONLY) parseja un HTML d'historial i compara la data real
amb el mes que té la BD, marcant discrepàncies per a revisió humana.

Ús:
    python tools/reconcile_ranking_dates.py [historial.html]
    # sense argument: prova la sessió viva i, si falla, cau al fixture.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

from fcbillar.config import get_settings
from fcbillar.ranking_dates import month_for_publication_date as derived_month
from fcbillar.scraper.parsers import parse_ranking_historial

FIXTURE = Path("tests/fixtures/ranking_historial.html")


def load_historial_html(arg: str | None) -> str:
    if arg:
        return Path(arg).read_text(encoding="utf-8", errors="replace")
    # Prova la sessió viva; si peta, cau al fixture.
    try:
        from fcbillar.scraper.client import ScraperClient

        s = get_settings()
        url = f"{s.base_url.rstrip('/')}/ca/jugador/ranking/historial"
        with ScraperClient(s) as cl:
            html = cl.fetch_html(url, use_cache=False)
        print(f"[font] sessió viva: {url}\n")
        return html
    except Exception as ex:  # noqa: BLE001
        print(f"[avís] no s'ha pogut llegir la sessió viva ({type(ex).__name__}); "
              f"uso el fixture {FIXTURE}\n")
        return FIXTURE.read_text(encoding="utf-8", errors="replace")


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    html = load_historial_html(arg)
    entries = parse_ranking_historial(html)

    conn = sqlite3.connect(str(get_settings().db_path))
    conn.row_factory = sqlite3.Row

    # num_seq -> data real (la data és global, compartida per totes les modalitats)
    by_seq: dict[int, date] = {}
    for e in entries:
        for _mod, (_fmt, num_seq) in e.rankings.items():
            by_seq[num_seq] = e.data

    print(f"{'num_seq':>7}  {'data real':>10}  {'derivat':>8}  {'BD mod1':>8}  estat")
    print("-" * 56)
    mismatches = 0
    for num_seq in sorted(by_seq):
        d = by_seq[num_seq]
        dy, dm = derived_month(d)
        row = conn.execute(
            """SELECT r.any_pub, r.mes_pub
               FROM rankings r JOIN modalitats m ON m.id = r.modalitat_id
               WHERE m.codi_fcb = 1 AND r.num_seq = ?""",
            (num_seq,),
        ).fetchone()
        db = f"{row['any_pub']}-{row['mes_pub']:02d}" if row and row["any_pub"] else "—"
        derived = f"{dy}-{dm:02d}"
        if row and row["any_pub"]:
            ok = (row["any_pub"], row["mes_pub"]) == (dy, dm)
            estat = "OK" if ok else "‼ DISCREPÀNCIA"
            if not ok:
                mismatches += 1
        else:
            estat = "(no a la BD)"
        print(f"{num_seq:>7}  {d.isoformat():>10}  {derived:>8}  {db:>8}  {estat}")

    print("-" * 56)
    print(f"Discrepàncies (mod 1, finestra historial): {mismatches}")
    conn.close()


if __name__ == "__main__":
    main()
