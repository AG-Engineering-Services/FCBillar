"""Experiment: 2 pestanyes concurrents (MATEIXA sessió) — 3 bandes vs resta.

Mesura velocitat i, sobretot, si la sessió sobreviu a l'accés concurrent.
Read-only sobre la BD; només fetch + parse (no escriu res).
"""

from __future__ import annotations

import asyncio
import sqlite3
import time

from playwright.async_api import async_playwright

from fcbillar.config import get_settings
from fcbillar.pipeline import _partides_url
from fcbillar.scraper.parsers import parse_partides_jugador

PER_TAB = 150


def load_combos(s):
    conn = sqlite3.connect(f"file:{s.db_path}?mode=ro", uri=True)
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
        """SELECT rk.num_seq num, m.codi_fcb mod, p.fcb_id fcb, rk.format_url fmt,
                  re.ranking_id rid, re.player_id pid
           FROM ranking_entries re JOIN rankings rk ON rk.id=re.ranking_id
           JOIN modalitats m ON m.id=rk.modalitat_id JOIN players p ON p.id=re.player_id
           WHERE p.fcb_id NOT LIKE 'name:%'
           ORDER BY rk.num_seq DESC, m.codi_fcb, p.fcb_id"""
    ).fetchall()
    conn.close()
    pend = [
        (r["num"], r["mod"], r["fcb"], r["fmt"])
        for r in rows
        if (r["rid"], r["pid"]) not in done and (r["rid"], r["pid"]) not in empty
    ]
    tres = [c for c in pend if c[1] == 1][:PER_TAB]
    rest = [c for c in pend if c[1] != 1][:PER_TAB]
    return tres, rest


async def worker(context, combos, base, stats):
    page = await context.new_page()
    for (num, mod, fcb, fmt) in combos:
        url = _partides_url(base, num, mod, fcb, fmt)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            html = await page.content()
            n = len(parse_partides_jugador(html).rows)
            stats["ok"] += 1
            stats["rows"] += n
        except Exception:  # noqa: BLE001
            stats["err"] += 1
    await page.close()


async def main():
    s = get_settings()
    tres, rest = load_combos(s)
    print(f"tab1 (3 bandes): {len(tres)} combos | tab2 (resta): {len(rest)} combos", flush=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        ctx = await b.new_context(
            storage_state=str(s.storage_state_path),
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            locale="ca-ES",
        )
        stats = {"ok": 0, "err": 0, "rows": 0}
        t0 = time.time()
        await asyncio.gather(
            worker(ctx, tres, s.base_url, stats),
            worker(ctx, rest, s.base_url, stats),
        )
        dt = time.time() - t0
        tot = len(tres) + len(rest)
        print(f"\n{tot} combos en {dt:.0f}s = {tot / dt:.2f} combos/s", flush=True)
        print(f"ok={stats['ok']} err={stats['err']} rows(partides trobades)={stats['rows']}", flush=True)
        print(f"seqüencial ~1/s → speedup observat: {tot / dt:.1f}x", flush=True)
        print(
            "SESSIÓ: "
            + ("VIVA ✓ (troba partides)" if stats["rows"] > 50 else "MORTA ✗ (concurrència l'ha tombat)"),
            flush=True,
        )
        await b.close()


if __name__ == "__main__":
    asyncio.run(main())
