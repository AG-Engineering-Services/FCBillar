"""Escaneja TOTES les lligues/divisions/grups del portal (2020-21 -> 2025-26)
i detecta on apareix el C.B. BANYOLES, comparant-ho amb la BD local."""

import json
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

BASE = "https://www.fcbillar.cat/ca/lligues"
SP = Path(sys.argv[1])
CACHE = SP / "cache_scan"
CACHE.mkdir(exist_ok=True, parents=True)

RE_DIV = re.compile(r"lligues/grups/(\d+)/(\d+)")
RE_GRP = re.compile(r"lligues/(?:classificacio|jornades)/(\d+)/(\d+)/(\d+)")


def fetch(url: str) -> str:
    key = CACHE / (url.split("/lligues/")[1].replace("/", "_") + ".html")
    if key.exists():
        return key.read_text(encoding="utf-8")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(3):
        try:
            html = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
            key.write_text(html, encoding="utf-8")
            time.sleep(0.25)
            return html
        except Exception as exc:  # noqa: BLE001
            if attempt == 2:
                raise
            print(f"  reintent {url}: {exc}", file=sys.stderr)
            time.sleep(2)
    raise RuntimeError


LLIGUES = {
    "2020-2021": [24, 25], "2021-2022": [26, 27], "2022-2023": [30, 31],
    "2023-2024": [32, 33], "2024-2025": [34, 35], "2025-2026": [36, 37],
}

conn = sqlite3.connect("data/fcbillar.db")
conn.row_factory = sqlite3.Row
db_grups = {
    (r["L"], r["D"], r["G"]): r["n"]
    for r in conn.execute(
        """SELECT lliga_id L, divisio_id D, grup_id G, COUNT(*) n
           FROM encontres_lliga el
           WHERE EXISTS (SELECT 1 FROM equips e WHERE e.club_id=7
                         AND e.id IN (el.equip_local_id, el.equip_visitant_id))
           GROUP BY 1,2,3"""
    )
}

found = []
for temp, lligues in LLIGUES.items():
    for L in lligues:
        soup = BeautifulSoup(fetch(f"{BASE}/divisions/{L}"), "lxml")
        lliga_nom = ""
        h2 = soup.select_one("section.three.fourths.padded h2")
        if h2:
            lliga_nom = h2.get_text(strip=True)
        divs = sorted({int(m.group(2)) for m in RE_DIV.finditer(str(soup))})
        for D in divs:
            gsoup = BeautifulSoup(fetch(f"{BASE}/grups/{L}/{D}"), "lxml")
            sec = gsoup.select_one("section.three.fourths.padded")
            div_nom = ""
            crumbs = sec.select("div.path a") if sec else []
            if crumbs:
                div_nom = crumbs[-1].get_text(strip=True)
            grups = {}
            for box in sec.select("div.row.box.info"):
                a = box.select_one("a[href]")
                m = RE_GRP.search(a["href"]) if a else None
                if m:
                    grups[int(m.group(3))] = a.get_text(strip=True)
            for G, gnom in sorted(grups.items()):
                html = fetch(f"{BASE}/classificacio/{L}/{D}/{G}")
                csoup = BeautifulSoup(html, "lxml")
                csec = csoup.select_one("section.three.fourths.padded")
                equips = [
                    c.get_text(" ", strip=True)
                    for c in csec.select("div.row.box.info div.eight.twelfths.mobile")
                ]
                ban = [e for e in equips if "ANYOLE" in e.upper()]
                if ban:
                    found.append({
                        "temp": temp, "lliga": lliga_nom, "L": L, "D": D, "G": G,
                        "divisio": div_nom, "grup": gnom, "equips_banyoles": ban,
                        "n_equips": len(equips), "db_encontres": db_grups.get((L, D, G), 0),
                    })
                    print(f"  {temp} L{L} D{D} G{G} {div_nom} / {gnom}: {ban} "
                          f"(BD={db_grups.get((L, D, G), 0)})", flush=True)
        print(f"{temp} lliga {L} ({lliga_nom}) fet: {len(divs)} divisions", flush=True)

(SP / "scan_all_grups.json").write_text(
    json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8"
)
print(f"\n-> {len(found)} grups amb Banyoles")
extra = [f for f in found if f["db_encontres"] == 0]
print(f"!! grups amb Banyoles que la BD NO té gens: {len(extra)}")
for e in extra:
    print("   ", e)
