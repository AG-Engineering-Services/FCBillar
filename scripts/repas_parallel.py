"""Repàs PARAL·LEL: N pestanyes concurrents a la MATEIXA sessió (async).

Les pestanyes comparteixen una sola sessió (com un usuari amb pestanyes), cosa
que la FCB tolera (a diferència de navegadors separats). Fetch en paral·lel
(coll d'ampolla = xarxa); ingest a la BD inline amb un sol conn (l'event loop
és d'un sol fil → escriptures serialitzades, sense locks).

Resumible (done-set + empty-skip), verbós i amb el mateix log estable.
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys

from playwright.async_api import async_playwright

from fcbillar.config import get_settings
from fcbillar.db.migrations import ensure_schema
from fcbillar.db.repository import Repository
from fcbillar.pipeline import RankingGameLink, _build_game_from_raw_row, _partides_url
from fcbillar.scraper.parsers import parse_partides_jugador

N_TABS = 3
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def load_pending(s):
    conn = sqlite3.connect(str(s.db_path))
    conn.row_factory = sqlite3.Row
    done = {
        (r["ranking_id"], r["player_id_origen"])
        for r in conn.execute("SELECT DISTINCT ranking_id, player_id_origen FROM ranking_game_links")
    }
    empty = set()
    ep = s.db_path.parent / "repas_empty.txt"
    if ep.exists():
        for line in ep.read_text(encoding="utf-8").splitlines():
            if "," in line:
                a, b = line.split(",", 1)
                empty.add((int(a), int(b)))
    rows = conn.execute(
        """SELECT rk.num_seq num, m.codi_fcb mod, p.fcb_id fcb, p.nom nom, m.nom modnom,
                  rk.format_url fmt, re.ranking_id rid, re.player_id pid
           FROM ranking_entries re JOIN rankings rk ON rk.id=re.ranking_id
           JOIN modalitats m ON m.id=rk.modalitat_id JOIN players p ON p.id=re.player_id
           WHERE p.fcb_id NOT LIKE 'name:%'
           ORDER BY rk.num_seq DESC, m.codi_fcb, p.fcb_id"""
    ).fetchall()
    conn.close()
    return [
        (r["num"], r["mod"], r["fcb"], r["nom"], r["modnom"], r["fmt"], r["rid"], r["pid"])
        for r in rows
        if (r["rid"], r["pid"]) not in done and (r["rid"], r["pid"]) not in empty
    ]


async def worker(tab, context, queue, repo, base, state, emit, emptyf):
    page = await context.new_page()
    while not state["dead"]:
        try:
            num, mod, fcb, nom, modnom, fmt, rid, pid = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        state["i"] += 1
        et = f"[{state['i']}/{state['total']}] T{tab} {modnom:<11} R{num:<3} {nom[:24]:<24}"
        url = _partides_url(base, num, mod, fcb, fmt)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            html = await page.content()
            parsed = parse_partides_jugador(html)  # peta si és pàgina de login
            owner = repo.get_player_nom_by_fcb_id(fcb)
            tot = new = 0
            for row in parsed.rows:
                game = _build_game_from_raw_row(row, mod, owner, repo, create_missing_players=True)
                if game is None:
                    continue
                if not repo.game_exists(game.id_natural):
                    new += 1
                repo.upsert_game(game)
                repo.link_game_to_ranking(RankingGameLink(num, mod, game.id_natural, fcb))
                tot += 1
            repo.conn.commit()
            state["ok"] += 1
            state["consec"] = 0
            if tot == 0:
                emptyf.write(f"{rid},{pid}\n")
                emptyf.flush()
                emit(f"{et} → sense partides")
            elif new == 0:
                emit(f"{et} → {tot} ja descarregades")
            elif new == tot:
                emit(f"{et} → {new} partides noves")
            else:
                emit(f"{et} → {new} noves (+{tot - new} ja hi eren)")
        except Exception:  # noqa: BLE001
            state["err"] += 1
            state["consec"] += 1
            emit(f"{et} → (buit)")
            if state["consec"] >= 25:
                state["dead"] = True
                emit("⚠️  Massa errors seguits — sessió morta? Re-logina i torna a llançar.")
    await page.close()


async def main():
    s = get_settings()
    pending = load_pending(s)
    total = len(pending)
    logf = open(s.db_path.parent / "repas_progress.log", "a", encoding="utf-8")
    emptyf = open(s.db_path.parent / "repas_empty.txt", "a", encoding="utf-8")

    def emit(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    emit(f"=== PARAL·LEL ({N_TABS} pestanyes) · combos pendents: {total} ===")
    queue: asyncio.Queue = asyncio.Queue()
    for c in pending:
        queue.put_nowait(c)

    conn = ensure_schema(s.db_path)
    repo = Repository(conn)
    state = {"i": 0, "ok": 0, "err": 0, "consec": 0, "total": total, "dead": False}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=str(s.storage_state_path), user_agent=UA, locale="ca-ES"
        )
        await asyncio.gather(
            *[worker(t + 1, context, queue, repo, s.base_url, state, emit, emptyf) for t in range(N_TABS)]
        )
        await browser.close()

    emit(f"=== FET ({state['ok']} ok / {state['err']} err de {total}) ===")
    logf.close()
    emptyf.close()
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        N_TABS = int(sys.argv[1])
    asyncio.run(main())
