"""Explora el panell de jugador logat de la intranet nova de la FCB.

Tot el que ingerim avui és públic (vegeu `docs/canvi-web-fcb-2026.md`), però el
panell de jugador continua darrere del login. Aquest script serveix per veure
QUÈ hi ha a dins i decidir si val la pena ingerir-ne res.

El login té captcha, o sigui que no s'automatitza: obre un Chromium visible,
espera que hi entris tu i, quan hi ets, recorre el panell i desa cada pàgina a
`tests/fixtures/nou/jugador/` amb un resum de les taules que hi troba.

    uv run python scripts/explora_jugador.py

La sessió es desa a `session/storage_state_intranet.json` per si es vol tornar a
entrar sense repetir el captcha mentre duri.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import time
import urllib.parse as up
from pathlib import Path

ARREL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ARREL / "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright  # noqa: E402

from fcbillar.config import get_settings  # noqa: E402
from fcbillar.scraper.taules import taules  # noqa: E402

BASE = "https://intranet.fcbillar.cat"
LOGIN = f"{BASE}/jugador/login"
DESTI = ARREL / "tests" / "fixtures" / "nou" / "jugador"
SESSIO = ARREL / "session" / "storage_state_intranet.json"

# Mentre el formulari de login sigui al DOM no estem dins. El demanem absent uns
# quants cops seguits: durant la navegació desapareix un instant i tornaria un
# fals positiu.
FORM_LOGIN = "form#formLogin"
ESPERA_MAX_S = 5 * 60
TICS_ABSENT = 3


def patro(url: str) -> str:
    p = up.urlsplit(url)
    cami = re.sub(r"/\d+", "/{id}", p.path)
    consulta = "&".join(sorted(f"{k}=" for k in up.parse_qs(p.query)))
    return cami + (f"?{consulta}" if consulta else "")


def nom_fitxer(url: str) -> str:
    p = up.urlsplit(url)
    base = (p.path.strip("/") + ("_" + p.query if p.query else "")).replace("/", "_")
    base = re.sub(r"[^A-Za-z0-9_.=-]", "_", base)
    return (base or "arrel")[:100] + ".html"


def espera_login(page) -> bool:
    print(f"\n  Entra al panell (usuari, contrasenya i captcha). Espero fins a "
          f"{ESPERA_MAX_S // 60} minuts...\n")
    limit = time.monotonic() + ESPERA_MAX_S
    absent = 0
    while time.monotonic() < limit:
        try:
            hi_es = page.locator(FORM_LOGIN).count() > 0
        except Exception:
            hi_es = True
        absent = 0 if hi_es else absent + 1
        if absent >= TICS_ABSENT:
            return True
        time.sleep(1.0)
    return False


def explora(page, max_pagines: int) -> dict[str, dict]:
    DESTI.mkdir(parents=True, exist_ok=True)
    pendents = [(page.url, 0)]
    vistos: set[str] = set()
    mapa: dict[str, dict] = {}

    while pendents and len(vistos) < max_pagines:
        url, fondaria = pendents.pop(0)
        if url in vistos:
            continue
        vistos.add(url)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            print(f"  ! {url}: {e}")
            continue
        html = page.content()
        (DESTI / nom_fitxer(url)).write_text(html, encoding="utf-8")

        info = mapa.setdefault(patro(url), {"exemple": url, "taules": []})
        for t in taules(html):
            info["taules"].append(
                {"titol": t.titol, "columnes": list(t.capcaleres), "files": len(t)}
            )
        print(f"  OK {url}  ({len(html):,} car., {len(info['taules'])} taules)")

        if fondaria >= 3:
            continue
        for href in page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)"):
            if not href.startswith(f"{BASE}/jugador"):
                continue
            if "logout" in href or "sortir" in href.lower():
                continue  # no ens desconnectem sols a mitja exploració
            if patro(href) in mapa or href in vistos:
                continue
            pendents.append((href, fondaria + 1))
    return mapa


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max", type=int, default=60, help="Pàgines màximes a visitar")
    args = ap.parse_args()

    settings = get_settings()
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(headless=False)
        context = (
            navegador.new_context(storage_state=str(SESSIO))
            if SESSIO.exists()
            else navegador.new_context()
        )
        page = context.new_page()
        page.goto(LOGIN, wait_until="domcontentloaded")

        if page.locator(FORM_LOGIN).count() > 0:
            if settings.user:
                try:
                    page.fill("#user", settings.user)
                    print(f"  Usuari pre-omplert: {settings.user}")
                except Exception:
                    pass
            if not espera_login(page):
                print("  No s'ha completat el login a temps.")
                navegador.close()
                return 1
        print("  Dins del panell.")
        context.storage_state(path=str(SESSIO))

        mapa = explora(page, args.max)
        navegador.close()

    print(f"\n{len(mapa)} menes de pàgina al panell de jugador:\n")
    for p in sorted(mapa):
        info = mapa[p]
        print(f"  {p}")
        for t in info["taules"]:
            print(f"      taula {t['titol']!r}: {t['columnes']} ({t['files']} files)")
    print(f"\nPagines desades a {DESTI}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
