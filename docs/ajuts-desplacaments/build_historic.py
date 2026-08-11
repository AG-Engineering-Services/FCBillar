"""Converteix l'escaneig historic del portal (hist_banyoles2.json) en files de
desplacament, amb la divisio llegida del portal i el club rival normalitzat al
nom del directori de la FCB.

Cobreix les temporades 2014-2015 a 2019-2020, que la base de dades local no te
completes. Hi afegeix les jornades de Copa de les edicions 1 i 2.
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup

SP = Path(sys.argv[1])
CACHE = SP / "cache_hist"
RE_DIV = re.compile(r"lligues/grups/(\d+)/(\d+)")


def clau(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).upper()
    s = re.sub(r"^\d+\s*", "", s)
    s = re.sub(r"\b(C\.?B\.?|S\.?B\.?|B\.?C\.?|S\.?E\.?|SBPE|CLUB|BILLAR|SOCIETAT)\b", " ", s)
    s = re.sub(r'"\s*[A-E]\s*"', "", s)
    s = re.sub(r"\s+[A-E]\s*$", "", s)
    return re.sub(r"[^A-Z]", "", s)


# nom al portal -> nom canonic (el del directori de clubs de la FCB)
MAP = {
    "ALBA": "C.B.ALBA", "BARCELONA": "C.B.BARCELONA", "BLANES": "C.B.BLANES",
    "CANET": "C.B.CANET DE MAR", "CASALCERVERA": "S.E.CASAL CERVERA",
    "CERVERA": "S.E.CASAL CERVERA", "CENTELLES": "S.B.P.E.CENTELLES",
    "FOMENTMOLINS": "S.B.F.MOLINS", "GRANOLLERS": "B.C.GRANOLLERS", "LLEIDA": "C.B.LLEIDA",
    "LLICADAMUNT": "C.B.LLIÇÀ D'AMUNT", "LLINARS": "C.B.LLINARS", "MANRESA": "C.B.MANRESA",
    "MATADEPERA": "C.B.MATADEPERA", "MATARO": "C.B.MATARÓ", "MOLLET": "C.B.MOLLET",
    "MONFORTE": "C.B.MONFORTE", "MONTROIG": "C.B.MONT-ROIG", "PRAT": "C.B.PRAT",
    "PREMIA": "C.B.PREMIÀ", "PUNTDATAC": "C.B.PUNT D'ATAC", "SANTADRIA": "C.B.SANT ADRIÀ",
    "SANTBOI": "C.B.SANT BOI", "SANTFELIU": "C.B.SANT FELIU", "SANTS": "C.B.SANTS",
    "TARRAGONA": "C.B.TARRAGONA", "VIC": "C.B.VIC", "MONTMELO": "C.B.MONTMELÓ",
    "CASINOOLOTI": "CASINO OLOTÍ", "DANYELLS": "DANY-ELLS C.B.", "LACOLMENA": "S.B.LA COLMENA",
    "CORALCOLON": "S.B.CORAL COLÓN", "BANYOLES": "C.B.BANYOLES",
}

# Copa, edicions 1 i 2: (temporada, data, jornada, grup, seu). Seu = club responsable
# del grup segons el portal; dates recuperades creuant copa_partides amb games.
COPA_HIST = [
    ("2017-2018", "2018-05-05", "1a Jornada", "H", "C.B.BANYOLES"),
    ("2017-2018", "2018-05-19", "2a Jornada", "I", "C.B.SANT BOI"),
    ("2018-2019", "2019-04-27", "1a Jornada", "G", "C.B.BANYOLES"),
    ("2018-2019", "2019-05-25", "2a Jornada", "C", "S.B.LA GRAN PENYA"),
    ("2018-2019", "2019-06-01", "3a Jornada", "D", "C.B.BANYOLES"),
    ("2018-2019", "2019-06-15", "4a Jornada", "A", "S.B.F.MOLINS"),
]


def divisions_de(L: int) -> dict[int, str]:
    """Noms oficials de divisio d'una lliga, llegits de la pagina del portal."""
    soup = BeautifulSoup((CACHE / f"divisions_{L}.html").read_text(encoding="utf-8"), "lxml")
    sec = soup.select_one("section.three.fourths.padded")
    out = {}
    for box in sec.select("div.row.box.info"):
        a = box.select_one("a[href]")
        m = RE_DIV.search(a["href"]) if a else None
        if m:
            nom = a.get_text(" ", strip=True)
            # el portal barreja "1ª", "1a" i "1º" segons l'any
            nom = re.sub(r"^(\d)[ªº°]", r"\1a", nom)
            out[int(m.group(2))] = nom
    return out


def lletra(nom: str) -> str:
    m = re.search(r'BANYOLES\s*"?\s*([A-E])\s*"?\s*$',
                  unicodedata.normalize("NFKD", nom).upper())
    return m.group(1) if m else ""


hist = json.loads((SP / "hist_banyoles2.json").read_text(encoding="utf-8"))
divs_cache: dict[int, dict[int, str]] = {}
files = []
for t in hist:
    divs_cache.setdefault(t["L"], divisions_de(t["L"]))
    divisio = divs_cache[t["L"]].get(t["D"], "?")
    grup = re.sub(r"^Grup\s+", "", t["grup"]).strip()
    grup = {"Unic": "ÚNIC", "Únic": "ÚNIC"}.get(grup, grup).upper()
    tipus = "final" if re.search(r"FINAL|PROMOC", divisio + " " + grup, re.I) else "regular"
    for e in t["encontres"]:
        casa = "BANYOLES" in clau(e["local"])
        ban = e["local"] if casa else e["visitant"]
        rival = e["visitant"] if casa else e["local"]
        files.append({
            "temporada": t["temporada"], "data": e["data"],
            "equip": f'Banyoles "{lletra(ban)}"' if lletra(ban) else "Banyoles",
            "competicio": "Lliga Catalana Tres Bandes", "divisio": divisio, "grup": grup,
            "tipus": tipus, "casa": casa, "club": MAP[clau(rival)],
            "font": f"portal L{t['L']}/D{t['D']}/G{t['G']}",
        })

for temp, data, jornada, grup, seu in COPA_HIST:
    files.append({
        "temporada": temp, "data": data, "equip": "Banyoles",
        "competicio": "Copa Catalana per equips", "divisio": jornada, "grup": grup,
        "tipus": "copa", "casa": seu == "C.B.BANYOLES", "club": seu,
        "font": "portal copa",
    })

files.sort(key=lambda x: (x["data"], x["equip"]))
(SP / "historic_files.json").write_text(json.dumps(files, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
fora = [f for f in files if not f["casa"]]
print(f"{len(files)} encontres històrics · {len(fora)} desplaçaments")
for temp in sorted({f["temporada"] for f in files}):
    sel = [f for f in files if f["temporada"] == temp]
    d = sorted({(f["divisio"], f["grup"]) for f in sel if f["tipus"] != "copa"})
    print(f"  {temp}: {sum(1 for f in sel if not f['casa']):2d} fora · "
          + " · ".join(f"{a} {b}" for a, b in d))
