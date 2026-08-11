"""Escaneja TOT el portal de lligues de la FCB buscant el C.B. Banyoles.

Recorre lliga -> divisio -> grup, mira la classificacio per saber si hi ha el
Banyoles i, nomes en aquest cas, baixa totes les jornades i encontres del grup
amb data. La temporada es dedueix de les dates (la competicio va de setembre a
juliol).
"""

import json
import re
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path("src").resolve()))
from fcbillar.scraper.parsers import parse_lliga_encontres, parse_lliga_jornades  # noqa: E402

BASE = "https://www.fcbillar.cat/ca/lligues"
SP = Path(sys.argv[1])
CACHE = SP / "cache_hist"
CACHE.mkdir(exist_ok=True, parents=True)
LLIGUES = range(int(sys.argv[2]), int(sys.argv[3]) + 1)

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
            time.sleep(0.2)
            return html
        except Exception as exc:  # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(2)
    raise RuntimeError


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def es_banyoles(nom: str) -> bool:
    return "BANYOLES" in norm(nom)


def temporada_de(iso: str) -> str:
    y, m = int(iso[:4]), int(iso[5:7])
    return f"{y}-{y + 1}" if m >= 8 else f"{y - 1}-{y}"


trobats = []
for L in LLIGUES:
    try:
        soup = BeautifulSoup(fetch(f"{BASE}/divisions/{L}"), "lxml")
    except Exception as exc:  # noqa: BLE001
        print(f"L{L}: no accessible ({exc})", flush=True)
        continue
    h2 = soup.select_one("section.three.fourths.padded h2")
    lliga_nom = h2.get_text(strip=True) if h2 else "?"
    divs = sorted({int(m.group(2)) for m in RE_DIV.finditer(str(soup))})
    if not divs:
        print(f"L{L}: «{lliga_nom}» sense divisions", flush=True)
        continue
    n_grups = 0
    for D in divs:
        gs = BeautifulSoup(fetch(f"{BASE}/grups/{L}/{D}"), "lxml")
        sec = gs.select_one("section.three.fourths.padded")
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
            n_grups += 1
            # La classificacio d'alguns grups antics no llista tots els equips, aixi que
            # el filtre es fa sobre els encontres, que si que son sempre complets.
            csoup = BeautifulSoup(fetch(f"{BASE}/classificacio/{L}/{D}/{G}"), "lxml")
            csec = csoup.select_one("section.three.fourths.padded")
            equips = [c.get_text(" ", strip=True)
                      for c in csec.select("div.row.box.info div.eight.twelfths.mobile")]
            encontres = []
            for j in parse_lliga_jornades(fetch(f"{BASE}/jornades/{L}/{D}/{G}")):
                data = j.data.isoformat() if j.data else None
                for e in parse_lliga_encontres(fetch(f"{BASE}/encontres/{L}/{D}/{G}/{j.jornada_id}")):
                    if not (es_banyoles(e.equip_local) or es_banyoles(e.equip_visitant)):
                        continue
                    encontres.append({
                        "jornada": j.jornada_id, "jornada_nom": j.nom, "data": data,
                        "encontre": e.encontre_id,
                        "local": e.equip_local, "visitant": e.equip_visitant,
                        "pp_local": e.p_parcials_local, "pm_local": e.p_match_local,
                        "pp_visitant": e.p_parcials_visitant, "pm_visitant": e.p_match_visitant,
                    })
            if not encontres:
                continue
            dates = [x["data"] for x in encontres if x["data"]]
            trobats.append({
                "L": L, "D": D, "G": G, "lliga": lliga_nom, "divisio": div_nom, "grup": gnom,
                "equips_banyoles": [e for e in equips if es_banyoles(e)],
                "n_equips": len(equips), "n_encontres": len(encontres),
                "temporada": temporada_de(min(dates)) if dates else None,
                "encontres": encontres,
            })
            print(f"  L{L} D{D} G{G} · {lliga_nom} / {div_nom} / {gnom} · "
                  f"{[e for e in equips if es_banyoles(e)]} · {len(encontres)} encontres · "
                  f"{trobats[-1]['temporada']}", flush=True)
    print(f"L{L}: «{lliga_nom}» {len(divs)} divisions, {n_grups} grups revisats", flush=True)

(SP / "hist_banyoles2.json").write_text(json.dumps(trobats, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
print(f"\n-> {len(trobats)} grups amb Banyoles, "
      f"{sum(t['n_encontres'] for t in trobats)} encontres")
