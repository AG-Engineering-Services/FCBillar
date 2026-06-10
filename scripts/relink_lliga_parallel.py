"""Re-enllaça els games de lliga al seu encontre (per etiquetar 3 bandes vs 4
modalitats), en PARAL·LEL. Enrich-only: NO crea games ni toca la modalitat;
només assigna encontre_lliga_id (+ equips) a la partida que ja existeix de
partideshome, casant per signatura.
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from datetime import date

from playwright.async_api import async_playwright

from fcbillar.config import get_settings
from fcbillar.db.migrations import ensure_schema
from fcbillar.db.repository import Repository
from fcbillar.pipeline import _build_game_from_lliga_row, _lliga_partides_url
from fcbillar.scraper.parsers import parse_lliga_partides

N_TABS = 6
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def load_encontres(s):
    conn = sqlite3.connect(f"file:{s.db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT id, lliga_id, divisio_id, grup_id, jornada_id, encontre_id_extern,
                  data, temporada_id, equip_local_id, equip_visitant_id
           FROM encontres_lliga ORDER BY id"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def worker(tab, context, queue, repo, base, state, emit):
    page = await context.new_page()
    while not state["dead"]:
        try:
            e = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        state["i"] += 1
        url = _lliga_partides_url(
            base, e["lliga_id"], e["divisio_id"], e["grup_id"], e["jornada_id"], e["encontre_id_extern"]
        )
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            html = await page.content()
            rows = parse_lliga_partides(html)
            d = date.fromisoformat(e["data"]) if e["data"] else None
            matched = 0
            for row in rows:
                try:
                    game = _build_game_from_lliga_row(
                        row,
                        encontre_data=d,
                        modalitat_codi_fcb=1,  # no s'usa per casar (signatura modalitat-agnòstica)
                        competicio_nom="LLIGA",
                        local_equip_id=e["equip_local_id"] or 0,
                        visitant_equip_id=e["equip_visitant_id"] or 0,
                        encontre_lliga_id=e["id"],
                        temporada_id=e["temporada_id"],
                        repo=repo,
                        create_missing_players=False,
                    )
                except Exception:  # noqa: BLE001
                    game = None
                if game and repo.enrich_game_by_signature(game):
                    matched += 1
            repo.conn.commit()
            state["ok"] += 1
            state["consec"] = 0
            emit(f"[{state['i']}/{state['total']}] T{tab} lliga{e['lliga_id']:<3} enc{e['encontre_id_extern']:<6} → {matched}/{len(rows)} enllaçats")
        except Exception:  # noqa: BLE001
            state["err"] += 1
            state["consec"] += 1
            emit(f"[{state['i']}/{state['total']}] T{tab} enc{e['encontre_id_extern']} → (error)")
            if state["consec"] >= 25:
                state["dead"] = True
                emit("⚠️  Massa errors seguits — sessió morta? Re-logina i torna a llançar.")
    await page.close()


async def main():
    s = get_settings()
    encs = load_encontres(s)
    total = len(encs)
    logf = open(s.db_path.parent / "relink_progress.log", "a", encoding="utf-8")

    def emit(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    emit(f"=== RELINK LLIGA ({N_TABS} pestanyes) · encontres: {total} ===")
    queue: asyncio.Queue = asyncio.Queue()
    for e in encs:
        queue.put_nowait(e)

    conn = ensure_schema(s.db_path)
    repo = Repository(conn)
    state = {"i": 0, "ok": 0, "err": 0, "consec": 0, "total": total, "dead": False}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=str(s.storage_state_path), user_agent=UA, locale="ca-ES"
        )
        await asyncio.gather(
            *[worker(t + 1, context, queue, repo, s.base_url, state, emit) for t in range(N_TABS)]
        )
        await browser.close()

    emit(f"=== FET ({state['ok']} ok / {state['err']} err de {total}) ===")
    logf.close()
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        N_TABS = int(sys.argv[1])
    asyncio.run(main())
