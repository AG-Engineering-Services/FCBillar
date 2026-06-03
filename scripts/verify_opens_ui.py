#!/usr/bin/env python3
"""Headless browser check for the Opens pages (run against a live dev server).

The agent sandbox can't keep a Vite dev server alive long enough for a
Playwright pass, so this is a standalone helper you run locally once both
servers are up:

    # terminal 1
    uv run python -m api                 # backend on :8000
    # terminal 2
    cd frontend && npm run dev           # Vite on :5173

    # terminal 3
    uv run python scripts/verify_opens_ui.py

It drives a headless Chromium through /opens, /opens/projection/1 and
/opens/ranking, asserts the expected rendered content, saves screenshots to
scripts/opens_ui_shots/, and exits non-zero if any check fails.

Options:
    --front URL   frontend base (default http://localhost:5173)
    --headed      show the browser window
    --proj-id N   projection id to open (default 1)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SHOTS = Path(__file__).resolve().parent / "opens_ui_shots"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--front", default="http://localhost:5173")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--proj-id", type=int, default=1)
    args = ap.parse_args()
    front = args.front.rstrip("/")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed. Run: uv run playwright install chromium")
        return 2

    SHOTS.mkdir(exist_ok=True)
    checks: list[tuple[str, bool]] = []
    errs: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        pg = browser.new_page()
        pg.set_default_timeout(60_000)  # Vite compiles each route on first hit
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(f"PAGEERROR: {e}"))

        def check(name: str, cond: bool) -> None:
            checks.append((name, bool(cond)))
            print(("  PASS  " if cond else "  FAIL  ") + name)

        # 1) Hub
        print("\n/opens (hub)")
        pg.goto(f"{front}/opens", wait_until="commit")
        pg.get_by_text("IV OPEN COSTA DAURADA").first.wait_for()
        hub = pg.inner_text("body")
        check("hub shows the open name", "IV OPEN COSTA DAURADA" in hub)
        check("hub shows 'Quadre projectat'", "Quadre projectat" in hub)
        check("hub shows inscrits count", "76 inscrits" in hub)
        pg.screenshot(path=str(SHOTS / "hub.png"), full_page=True)

        # 2) Projection detail
        print(f"\n/opens/projection/{args.proj_id}")
        pg.goto(f"{front}/opens/projection/{args.proj_id}", wait_until="commit")
        pg.get_by_text("Projecció provisional").first.wait_for()
        det = pg.inner_text("body")
        check("projection shows the open name", "IV OPEN COSTA DAURADA" in det)
        check("projection shows Prèvies phase", "Prèvies" in det)
        check("projection shows Pre-prèvies phase", "Pre-prèvies" in det)
        check("projection shows Grup A", "Grup A" in det)
        check("projection shows warnings banner", "sense posició al rànquing" in det)
        pg.get_by_role("button", name="Fase Final").click()
        pg.wait_for_timeout(500)
        check("Fase Final tab shows group winners", "Guanyador Grup" in pg.inner_text("body"))
        pg.get_by_role("button", name="Per club").click()
        pg.wait_for_timeout(400)
        check("Per club tab groups by club", "LLEIDA" in pg.inner_text("body"))
        pg.get_by_role("button", name="Caps de sèrie").click()
        pg.wait_for_timeout(500)
        check("Caps de sèrie tab lists the top seed", "MORENO" in pg.inner_text("body"))
        check("seeds tab shows opens-points column", "punts opens" in pg.inner_text("body").lower())
        pg.screenshot(path=str(SHOTS / "projection.png"), full_page=True)

        # 2b) Click a player -> player profile, then Back -> returns to projection
        print("\nplayer click-through + back")
        proj_url = pg.url
        pg.locator("table tbody tr").first.get_by_role("link").first.click()
        pg.wait_for_url("**/players/**")
        check("clicking a player opens /players/<id>", "/players/" in pg.url)
        pg.get_by_role("button", name="Enrere").wait_for()  # player profile loaded
        check("player profile rendered", "/players/" in pg.url)
        pg.wait_for_timeout(900)
        check("player profile shows opens-ranking block", "Rànquing Català d'Opens" in pg.inner_text("body"))
        pg.screenshot(path=str(SHOTS / "player.png"), full_page=True)
        pg.get_by_role("button", name="Enrere").click()
        pg.wait_for_url("**/opens/projection/**")
        check("Back returns to the opens projection", pg.url.rstrip("/") == proj_url.rstrip("/"))

        # 3) Ranking
        print("\n/opens/ranking")
        pg.goto(f"{front}/opens/ranking", wait_until="commit")
        pg.wait_for_timeout(3000)
        check("ranking page rendered", len(pg.inner_text("body")) > 300)
        pg.screenshot(path=str(SHOTS / "ranking.png"), full_page=True)

        browser.close()

    print("\nconsole/page errors:", "none" if not errs else "")
    for e in errs[:12]:
        print("  ", e[:200])

    failed = [n for n, ok in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed. Screenshots in {SHOTS}")
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    print("ALL OPENS UI CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
