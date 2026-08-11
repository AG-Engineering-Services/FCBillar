"""Auditoria de completesa: encontres del C.B. BANYOLES al portal vs la BD local.

Recorre, per a cada (lliga, divisio, grup) on hi ha algun equip del Banyoles,
totes les jornades del portal federatiu i tots els encontres de cada jornada,
i els compara amb encontres_lliga.
"""

import json
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path("src").resolve()))
from fcbillar.scraper.parsers import parse_lliga_encontres, parse_lliga_jornades  # noqa: E402

BASE = "https://www.fcbillar.cat/ca/lligues"
CACHE = Path(sys.argv[1] if len(sys.argv) > 1 else "cache_audit")
CACHE.mkdir(exist_ok=True)


def fetch(url: str) -> str:
    key = CACHE / (url.replace("https://www.fcbillar.cat/ca/lligues/", "").replace("/", "_") + ".html")
    if key.exists():
        return key.read_text(encoding="utf-8")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(3):
        try:
            html = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
            key.write_text(html, encoding="utf-8")
            time.sleep(0.3)
            return html
        except Exception as exc:  # noqa: BLE001
            if attempt == 2:
                raise
            print(f"  reintent {attempt + 1} {url}: {exc}", file=sys.stderr)
            time.sleep(2)
    raise RuntimeError


conn = sqlite3.connect("data/fcbillar.db")
conn.row_factory = sqlite3.Row

grups = conn.execute(
    """
    SELECT DISTINCT t.nom AS temp, el.lliga_id AS L, el.divisio_id AS D, el.grup_id AS G
    FROM encontres_lliga el
    JOIN temporades t ON t.id = el.temporada_id
    JOIN equips e ON e.id IN (el.equip_local_id, el.equip_visitant_id) AND e.club_id = 7
    WHERE t.nom >= '2020-2021'
    ORDER BY t.nom, el.lliga_id, el.divisio_id, el.grup_id
    """
).fetchall()

equip_nom = {
    r["id"]: f"{r['nom']} {r['lletra']}"
    for r in conn.execute(
        "SELECT e.id, cl.nom, e.lletra FROM equips e JOIN clubs cl ON cl.id = e.club_id"
    )
}

report = []
for g in grups:
    L, D, G = g["L"], g["D"], g["G"]
    jhtml = fetch(f"{BASE}/jornades/{L}/{D}/{G}")
    jornades = parse_lliga_jornades(jhtml)
    portal, dates = {}, {}
    for j in jornades:
        dates[j.jornada_id] = j.data.isoformat() if j.data else None
        for e in parse_lliga_encontres(fetch(f"{BASE}/encontres/{L}/{D}/{G}/{j.jornada_id}")):
            portal[(j.jornada_id, e.encontre_id)] = e

    db = {
        (r["jornada_id"], r["encontre_id_extern"]): r
        for r in conn.execute(
            "SELECT * FROM encontres_lliga WHERE lliga_id=? AND divisio_id=? AND grup_id=?",
            (L, D, G),
        )
    }

    nomes_portal = sorted(set(portal) - set(db))
    nomes_db = sorted(set(db) - set(portal))
    diff_data = [
        (k, db[k]["data"], dates.get(k[0]))
        for k in sorted(set(portal) & set(db))
        if db[k]["data"] != dates.get(k[0])
    ]
    report.append(
        {
            "temp": g["temp"], "L": L, "D": D, "G": G,
            "n_jornades": len(jornades), "n_portal": len(portal), "n_db": len(db),
            "nomes_portal": [
                {"jornada": k[0], "enc": k[1], "data": dates.get(k[0]),
                 "local": portal[k].equip_local, "visitant": portal[k].equip_visitant,
                 "res": f"{portal[k].p_parcials_local}-{portal[k].p_parcials_visitant} "
                        f"({portal[k].p_match_local}-{portal[k].p_match_visitant})"}
                for k in nomes_portal
            ],
            "nomes_db": [
                {"jornada": k[0], "enc": k[1], "data": db[k]["data"],
                 "local": equip_nom.get(db[k]["equip_local_id"]),
                 "visitant": equip_nom.get(db[k]["equip_visitant_id"])}
                for k in nomes_db
            ],
            "dates_divergents": diff_data,
        }
    )
    print(
        f"{g['temp']} L{L} D{D} G{G}: jornades={len(jornades)} "
        f"portal={len(portal)} db={len(db)} "
        f"nomes_portal={len(nomes_portal)} nomes_db={len(nomes_db)} datesdiff={len(diff_data)}",
        flush=True,
    )

Path("audit_banyoles.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
)
print("\n-> audit_banyoles.json")
