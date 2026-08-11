"""Construeix el detall de desplaçaments del C.B. Banyoles (2020-21 -> 2025-26).

Fonts:
  - encontres_lliga / copa_encontres de data/fcbillar.db, verificats contra
    www.fcbillar.cat (portal FCB) grup a grup i jornada a jornada.
  - adreces: directori oficial de clubs de la FCB.
  - coordenades: Nominatim / OpenStreetMap.
  - km de carretera: OSRM (perfil driving, xarxa OSM).
"""

import csv
import json
import sqlite3
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

SP = Path(sys.argv[1])
UA = "FCBillar-ajuts-desplacaments/1.0 (algoam@gmail.com)"

# --- coordenades corregides/validades a mà sobre el resultat de geocode.py -----
COORD = {
    "C.B.BANYOLES": (42.1182826, 2.7642996, "carrer", "Banyoles"),
    "C.B.MONFORTE": (41.4212690, 2.1876695, "portal", "Barcelona"),
    "S.B.F.MOLINS": (41.4120456, 2.0152787, "carrer", "Molins de Rei"),
    "C.B.SANT ADRIÀ": (41.4300112, 2.2172269, "portal", "Sant Adrià de Besòs"),
    "B.C.GRANOLLERS": (41.6088794, 2.2906210, "carrer", "Granollers"),
    "C.B.LLINARS": (41.6401153, 2.4063496, "carrer", "Llinars del Vallès"),
    "C.B.MATARÓ": (41.5464815, 2.4422399, "carrer", "Mataró"),
    "C.B.SANT BOI": (41.3447240, 2.0404287, "carrer", "Sant Boi de Llobregat"),
    "C.B.LLIÇÀ D'AMUNT": (41.6135644, 2.2389756, "carrer", "Lliçà d'Amunt"),
    "C.B.MOLLET": (41.5359685, 2.2191838, "carrer", "Mollet del Vallès"),
    "C.B.2000 CERDANYOLA": (41.4830183, 2.1427308, "carrer", "Cerdanyola del Vallès"),
    "C.B.BLANES": (41.6743889, 2.7925433, "carrer", "Blanes"),
    "C.B.SANTS": (41.3776450, 2.1418588, "portal", "Barcelona"),
    "C.B.CANET DE MAR": (41.5900933, 2.5777998, "municipi", "Canet de Mar"),
    "C.B.BARCELONA": (41.3883171, 2.1659902, "portal", "Barcelona"),
    "C.B.MONT-ROIG": (41.0873067, 0.9613680, "carrer", "Mont-roig del Camp"),
    "S.B.P.E.CENTELLES": (41.7954808, 2.2191965, "carrer", "Centelles"),
    # clubs que nomes surten a la projeccio 2026-2027
    "C.B.VILANOVA": (41.2283657, 1.7259927, "carrer", "Vilanova i la Geltrú"),
    "C.B.CARDONA": (41.9142758, 1.6813300, "municipi", "Cardona"),
    # clubs de les temporades 2014-15 a 2019-20; alguns ja no son a la federacio
    "C.B.MONTMELÓ": (41.5515189, 2.2480812, "municipi", "Montmeló"),
    "C.B.PUNT D'ATAC": (41.1431164, 1.4007425, "carrer", "Torredembarra"),
    "C.B.MATADEPERA": (41.5999338, 2.0337697, "carrer", "Matadepera"),
    "CASINO OLOTÍ": (42.1827209, 2.4871969, "portal", "Olot"),
    "DANY-ELLS C.B.": (41.6079555, 2.2876008, "municipi", "Granollers"),
    "S.B.LA COLMENA": (41.4519395, 2.2080809, "municipi", "Santa Coloma de Gramenet"),
    "S.E.CASAL CERVERA": (41.6699000, 1.2720000, "municipi", "Cervera"),
    "C.B.ALBA": (41.4521635, 2.2500623, "carrer", "Badalona"),
    "C.B.LLEIDA": (41.6212957, 0.6155697, "carrer", "Lleida"),
    "C.B.TARRAGONA": (41.1193211, 1.2463466, "portal", "Tarragona"),
    "C.B.PRAT": (41.3287533, 2.0965011, "carrer", "El Prat de Llobregat"),
    "C.B.PREMIÀ": (41.4897874, 2.3579717, "carrer", "Premià de Mar"),
    "S.B.CORAL COLÓN": (41.5534208, 2.1044223, "carrer", "Sabadell"),
    "C.B.SANT FELIU": (41.6885036, 2.1646769, "municipi", "Sant Feliu de Codines"),
    "S.B. GEiEG": (41.9569086, 2.8236364, "carrer", "Girona"),
    "C.B.MANRESA": (41.7326416, 1.8303536, "carrer", "Manresa"),
    "C.B.VIC": (41.9319543, 2.2516403, "carrer", "Vic"),
    "C.B.OLESA": (41.5396836, 1.8979692, "carrer", "Olesa de Montserrat"),
    "C.B. BORGES": (41.5188127, 0.8693986, "carrer", "Les Borges Blanques"),
    "B.LA UNIÓ CORAL": (41.3818806, 2.0478331, "carrer", "Sant Feliu de Llobregat"),
    "S.B.LA GRAN PENYA": (41.2237774, 1.7248374, "portal", "Vilanova i la Geltrú"),
}

# Variants del nom d'un mateix club a encontres_lliga/copa_encontres -> nom del directori FCB.
# El nom del directori es el canonic a tot el document, perque es el que porta l'adreca.
# Compte: "S.B.CORAL COLON" (Sabadell) i "B.LA UNIO CORAL" (Sant Feliu de Llobregat) son
# clubs diferents i no s'han de fusionar.
ALIAS = {
    "SB FOMENT MOLINS": "S.B.F.MOLINS", "C.B. CANET": "C.B.CANET DE MAR",
    "CORAL COLÓN": "S.B.CORAL COLÓN", "BC OLESA": "C.B.OLESA",
}

# grup_id -> (divisio oficial, grup, tipus). Als grups regulars el grup es nomes la lletra;
# a les fases finals i de promocio no hi ha lletra i s'hi posa el nom de la fase.
GRUPS = {
    205: ("2a DIVISIÓ", "A", "regular"), 218: ("2a DIVISIÓ", "FINAL", "final"),
    210: ("4a DIVISIÓ", "B", "regular"), 229: ("PROMOCIÓ A 1a", "ÚNIC", "promocio"),
    231: ("1a DIVISIÓ", "B", "regular"), 248: ("1a DIVISIÓ", "FINAL", "final"),
    # G251/G253: el nom del grup al portal ("SEMIFINALS A" / "FINAL 4a DIVISIO") no coincideix
    # amb la jornada que s'hi va jugar; aqui hi posem la jornada, que es la dada exacta.
    239: ("4a DIVISIÓ", "D", "regular"), 251: ("4a DIVISIÓ", "QUARTS DE FINAL", "final"),
    253: ("4a DIVISIÓ", "SEMIFINALS", "final"), 258: ("PROMOCIÓ A 3a", "ÚNIC", "promocio"),
    259: ("1a DIVISIÓ", "A", "regular"), 264: ("3a DIVISIÓ", "B", "regular"),
    279: ("PROMOCIÓ A 1a", "ÚNIC", "promocio"), 286: ("1a DIVISIÓ", "A", "regular"),
    298: ("1a DIVISIÓ", "FINAL", "final"), 288: ("2a DIVISIÓ", "A", "regular"),
    292: ("4a DIVISIÓ", "A", "regular"), 317: ("HONOR", "B", "regular"),
    323: ("2a DIVISIÓ", "B", "regular"), 314: ("4a DIVISIÓ", "A", "regular"),
}

# Copa: (temporada, data, jornada, grup, seu). Dates recuperades creuant copa_partides amb games.
COPA = [
    ("2023-2024", "2024-06-08", "1a Jornada", "C", "B.C.GRANOLLERS"),
    ("2023-2024", "2024-06-15", "2a Jornada", "E", "C.B.BANYOLES"),
    ("2024-2025", "2025-06-07", "1a Jornada", "D", "B.LA UNIÓ CORAL"),
    ("2025-2026", "2026-05-23", "1a Jornada", "B", "C.B.BANYOLES"),
    ("2025-2026", "2026-05-30", "2a Jornada", "E", "S.B.CORAL COLÓN"),
    ("2025-2026", "2026-06-06", "3a Jornada", "C", "C.B.MATARÓ"),
]

# Seus de les fases finals i de promocio, revisades amb el club.
#   estat: "verificat" -> seu = el club local que publica la federacio
#          "casa"      -> jugat a Banyoles: no hi ha desplacament
#          "pendent"   -> seu segons el record del club, sense confirmacio documental
#   seu:   club real quan no coincideix amb el local nominal del portal (None si coincideix)
SEUS_FASES = {
    ("2022-05-07", 'Banyoles "A"'): ("casa", None,
                                     "jugat a Banyoles per ser el millor classificat "
                                     "de la fase de grups"),
    ("2022-07-03", 'Banyoles "A"'): ("verificat", None, ""),
    ("2023-05-13", 'Banyoles "A"'): ("verificat", None, ""),
    ("2023-05-13", 'Banyoles "B"'): ("verificat", "C.B.LLINARS",
                                     "tota la fase final de 4a divisió es va disputar a "
                                     "Llinars segons el record del club"),
    ("2023-05-14", 'Banyoles "B"'): ("verificat", "C.B.LLINARS",
                                     "tota la fase final de 4a divisió es va disputar a "
                                     "Llinars segons el record del club"),
    ("2023-05-28", 'Banyoles "B"'): ("verificat", None, ""),
    ("2024-05-25", 'Banyoles "A"'): ("verificat", None, ""),
}

# Encontres del portal sense registre de partides: incompareixences (no jugats).
INCOMPAR = [
    ("2021-2022", "2021-12-18", "B", "4a DIVISIÓ", "B", "B.LA UNIÓ CORAL",
     "0-8: no s'hi presenta el Banyoles"),
    ("2024-2025", "2024-12-14", "C", "4a DIVISIÓ", "A", "C.B.SANTS",
     "0-8: no s'hi presenta el Banyoles"),
    ("2024-2025", "2025-01-18", "A", "1a DIVISIÓ", "A", "C.B.SANT BOI",
     "8-0 a favor: no s'hi presenta el Sant Boi"),
]

# Adreces del directori oficial de clubs de la FCB, normalitzades a un unic criteri
# tipografic (majuscula inicial, abreviatures desplegades). El municipi va en columna a
# part, aixi que aqui nomes hi ha el carrer. No s'hi ha afegit cap dada.
ADRECES = {
    "C.B.BANYOLES": "Carrer de l'Abeurador, 10",
    "B.C.GRANOLLERS": "Carrer Girona, 222 (pavelló de bàsquet)",
    "B.LA UNIÓ CORAL": "Passeig Bertrand, 13",
    "C.B. BORGES": "Carrer Catalunya, s/n (pavelló esportiu Francesc Macià, 1a planta)",
    "C.B.2000 CERDANYOLA": "Avinguda Guiera, 6",
    "C.B.ALBA": "Carrer Sant Pau, 13",
    "C.B.BARCELONA": "Gran Via de les Corts Catalanes, 595-599 (soterrani)",
    "C.B.BLANES": "Plaça d'Espanya, 5 (baixos del Casino de Blanes)",
    "C.B.CANET DE MAR": "Rial de Can Godany, s/n (camp municipal de futbol)",
    "C.B.LLEIDA": "Avinguda Navarra, s/n (camp d'esports)",
    "C.B.LLINARS": "Carrer Ravalet, 17",
    "C.B.LLIÇÀ D'AMUNT": "Carrer Folch i Torres, 117 (Els Galliners)",
    "C.B.MANRESA": "Passatge Dipòsits Vells, 4, baixos",
    "C.B.MATARÓ": "Passeig Carles Padrós, 12 (pavelló municipal Josep Mora)",
    "C.B.MOLLET": "Ronda Can Fàbregas, 1 (soterrani)",
    "C.B.MONFORTE": "Carrer Sant Antoni Maria Claret, 373",
    "C.B.MONT-ROIG": "Carrer Vinyols, 17, baixos",
    "C.B.OLESA": "Plaça Països Catalans, 2",
    "C.B.PRAT": "Carrer Lo Gaiter del Llobregat, 24",
    "C.B.PREMIÀ": "Carrer Sant Antoni, 60, 2n",
    "C.B.SANT ADRIÀ": "Carrer Doctor Barraquer, 6",
    "C.B.SANT BOI": "Carrer Jaume I, 52",
    "C.B.SANT FELIU": "Centre cívic",
    "C.B.SANTS": "Carrer Rector Triadó, 53, interior baixos",
    "C.B.TARRAGONA": "Plaça Imperial Tarraco, 1 (soterrani de l'estació d'autobusos)",
    "C.B.VIC": "Carrer Arquebisbe Alemany, 24, baixos",
    "S.B. GEiEG": "Carrer Església de Sant Miquel, 18 (GEiEG Palau)",
    "S.B.CORAL COLÓN": "Avinguda Onze de Setembre, 125",
    "S.B.F.MOLINS": "Passeig del Terraplè, 49",
    "S.B.LA GRAN PENYA": "Rambla Principal, 52",
    "S.B.P.E.CENTELLES": "Carrer Sant Joan, 14",
    "C.B.VILANOVA": "Plaça de les Casernes / carrer Olesa, s/n (pavelló)",
    "C.B.CARDONA": "Carrer Generalitat, 1",
    "C.B.MONTMELÓ": "—",
    "C.B.PUNT D'ATAC": "Carrer Capella, 6",
    "C.B.MATADEPERA": "Pompeu Fabra, s/n (Club de Golf Can Vinyers)",
    "CASINO OLOTÍ": "Passeig de l'Escultor Miquel Blay, 6",
    "DANY-ELLS C.B.": "—",
    "S.B.LA COLMENA": "—",
    "S.E.CASAL CERVERA": "Plaça Santa Anna, 2",
}

ORIG = COORD["C.B.BANYOLES"]
_cache_path = SP / "osrm_cache.json"
_cache = json.loads(_cache_path.read_text(encoding="utf-8")) if _cache_path.exists() else {}


def road_km(club: str) -> tuple[float, int]:
    if club in _cache:
        return tuple(_cache[club])
    lat, lon = COORD[club][0], COORD[club][1]
    url = (f"https://router.project-osrm.org/route/v1/driving/"
           f"{ORIG[1]},{ORIG[0]};{lon},{lat}?overview=false&alternatives=false")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            j = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
            r = j["routes"][0]
            val = (round(r["distance"] / 1000, 1), round(r["duration"] / 60))
            _cache[club] = list(val)
            _cache_path.write_text(json.dumps(_cache, ensure_ascii=False, indent=1), encoding="utf-8")
            time.sleep(0.6)
            return val
        except Exception as exc:  # noqa: BLE001
            if attempt == 3:
                raise RuntimeError(f"OSRM ha fallat per {club}: {exc}") from exc
            time.sleep(3)
    raise RuntimeError


conn = sqlite3.connect("data/fcbillar.db")
conn.row_factory = sqlite3.Row

rows = []
for r in conn.execute(
    """SELECT t.nom temp, el.data, ev.lletra eq, el.grup_id G, cl.nom seu
       FROM encontres_lliga el
       JOIN temporades t ON t.id = el.temporada_id
       JOIN equips ev ON ev.id = el.equip_visitant_id AND ev.club_id = 7
       JOIN equips eh ON eh.id = el.equip_local_id
       JOIN clubs cl ON cl.id = eh.club_id
       WHERE t.nom >= '2020-2021' ORDER BY t.nom, el.data, ev.lletra"""
):
    divisio, grup, tipus = GRUPS[r["G"]]
    club = ALIAS.get(r["seu"], r["seu"])
    km, mins = road_km(club)
    rows.append({
        "temporada": r["temp"], "data": r["data"], "equip": f'Banyoles "{r["eq"]}"',
        "competicio": "Lliga Catalana Tres Bandes", "divisio": divisio, "grup": grup,
        "tipus": tipus, "seu_club": club, "municipi": COORD[club][3],
        "precisio": COORD[club][2], "km_anada": km, "km_total": round(km * 2, 1),
        "minuts_anada": mins,
    })

for temp, data, jornada, grup, seu in COPA:
    if seu == "C.B.BANYOLES":
        continue  # jornada disputada a casa
    km, mins = road_km(seu)
    rows.append({
        "temporada": temp, "data": data, "equip": "Banyoles",
        "competicio": "Copa Catalana per equips", "divisio": jornada, "grup": grup,
        "tipus": "copa", "seu_club": seu, "municipi": COORD[seu][3],
        "precisio": COORD[seu][2], "km_anada": km, "km_total": round(km * 2, 1),
        "minuts_anada": mins,
    })

# --- temporades 2014-2015 a 2019-2020 -------------------------------------------------
# La base de dades local no les te completes (equips a 0 i sense dates del 2015-16 al
# 2018-19), aixi que aquestes files venen d'un escaneig directe del portal federatiu.
for h in json.loads((SP / "historic_files.json").read_text(encoding="utf-8")):
    if h["casa"]:
        continue
    club = h["club"]
    if club not in COORD:
        raise RuntimeError(f"sense coordenades per a {club} (historic)")
    k, mn = road_km(club)
    rows.append({
        "temporada": h["temporada"], "data": h["data"], "equip": h["equip"],
        "competicio": h["competicio"], "divisio": h["divisio"], "grup": h["grup"],
        "tipus": h["tipus"], "seu_club": club, "municipi": COORD[club][3],
        "precisio": COORD[club][2], "km_anada": k, "km_total": round(k * 2, 1),
        "minuts_anada": mn, "estat": "verificat", "nota": "", "seu_nominal": "",
    })

# Estat de cada linia. Les fases finals i de promocio prenen l'estat que ha confirmat el club;
# les que es van jugar a Banyoles surten de la llista perque no hi va haver desplacament.
a_casa = []
for r in rows:
    r.setdefault("seu_nominal", "")  # només s'omple si la seu real difereix del portal
    if r["tipus"] in ("final", "promocio"):
        # Les fases finals de les temporades historiques no s'han revisat una a una:
        # s'hi pren el club local que publica la federacio, com a la fase regular.
        estat, seu_real, nota = SEUS_FASES.get((r["data"], r["equip"]),
                                               ("verificat", None, ""))
        r["estat"] = estat
        r["nota"] = nota
        if seu_real and seu_real != r["seu_club"]:
            r["seu_nominal"] = r["seu_club"]
            r["seu_club"] = seu_real
            club = ALIAS.get(seu_real, seu_real)
            k, mn = road_km(club)
            r["municipi"] = COORD[club][3]
            r["precisio"] = COORD[club][2]
            r["km_anada"], r["km_total"], r["minuts_anada"] = k, round(k * 2, 1), mn
    elif "estat" not in r:
        r["estat"] = "verificat"
        r["nota"] = ""
a_casa = [r for r in rows if r["estat"] == "casa"]
rows = [r for r in rows if r["estat"] != "casa"]

# Ordre: temporada, després equip (A, B, C i la Copa al final) i, dins de cada equip, data.

# Encontres no jugats per incompareixenca: entren al llistat en la seva posicio, marcats
# amb asterisc, pero no sumen quilometres ni imports perque el viatge no es va fer.
for temp, data, eq, div, grup, seu, nota in INCOMPAR:
    club = ALIAS.get(seu, seu)
    k, mn = road_km(club)
    rows.append({
        "temporada": temp, "data": data, "equip": f'Banyoles "{eq}"',
        "competicio": "Lliga Catalana Tres Bandes", "divisio": div, "grup": grup,
        "tipus": "regular", "seu_club": club, "municipi": COORD[club][3],
        # Es guarda la distancia real perque consti al llistat, pero la fila no suma:
        # el viatge no es va fer i tots els imports queden a zero.
        "precisio": COORD[club][2], "km_anada": k, "km_total": round(k * 2, 1),
        "minuts_anada": mn, "estat": "incompareixenca", "nota": nota, "seu_nominal": "",
    })

rows.sort(key=lambda x: (x["temporada"], "Z" if x["tipus"] == "copa" else x["equip"], x["data"]))


# --- valoracio del desplacament --------------------------------------------------------
# Criteri principal: barem oficial de quilometratge exempt a l'IRPF + dieta de manutencio
# sense pernoctacio (art. 9 del Reglament de l'IRPF), per als desplacaments de mes de 50 km.
AEAT_CANVI = date.fromisoformat("2023-07-17")  # Orden HFP/792/2023: 0,19 -> 0,26 EUR/km
DIETA_MIGDIA = 25.00          # import que aplica el club; el limit exempt a l'IRPF es 26,67
LLINDAR_DIETA_KM = 50         # distancia d'anada a partir de la qual es merita la dieta
JUGADORS_LLIGA = 4            # jugadors per desplacament de lliga (dada del club)
JUGADORS_COPA = 3             # a la Copa cada equip hi presenta 3 jugadors

# Referencia secundaria: cost de combustible amb el preu real de la setmana de cada partit
# (gasolina 95 amb impostos a Espanya, Weekly Oil Bulletin de la Comissio Europea).
CONSUM_L_100KM = 6.5

_preus = {date.fromisoformat(k): v
          for k, v in json.loads((SP / "preus_gasolina_es.json").read_text(encoding="utf-8")).items()}
_setmanes = sorted(_preus)


def preu_gasolina(iso: str) -> tuple[float, str]:
    """Preu €/l de la setmana del butlleti que conte la data (dilluns anterior o igual)."""
    d = date.fromisoformat(iso)
    anteriors = [w for w in _setmanes if w <= d]
    if not anteriors:
        raise RuntimeError(f"sense preu de gasolina per a {iso}")
    w = anteriors[-1]
    return _preus[w], w.isoformat()


def tarifa_aeat(iso: str) -> float:
    return 0.26 if date.fromisoformat(iso) >= AEAT_CANVI else 0.19


def amb_costos(r: dict) -> dict:
    jugat = r["estat"] != "incompareixenca"
    tarifa = tarifa_aeat(r["data"])
    r["tarifa_eur_km"] = tarifa if jugat else 0.0
    r["import_km_eur"] = round(r["km_total"] * tarifa, 2) if jugat else 0.0
    r["jugadors"] = (JUGADORS_COPA if r["tipus"] == "copa" else JUGADORS_LLIGA) if jugat else 0
    r["te_dieta"] = jugat and r["km_anada"] > LLINDAR_DIETA_KM
    r["import_dietes_eur"] = round(r["jugadors"] * DIETA_MIGDIA, 2) if r["te_dieta"] else 0.0
    r["import_total_eur"] = round(r["import_km_eur"] + r["import_dietes_eur"], 2)
    # referencia secundaria
    p, setmana = preu_gasolina(r["data"])
    r["preu_gasolina_eur_l"] = p
    r["setmana_preu"] = setmana
    r["litres"] = round(r["km_total"] * CONSUM_L_100KM / 100, 2)
    r["cost_combustible_eur"] = round(r["km_total"] * CONSUM_L_100KM / 100 * p, 2)
    return r


rows = [amb_costos(r) for r in rows]
a_casa = [dict(r, preu_gasolina_eur_l=preu_gasolina(r["data"])[0]) for r in a_casa]


def amb_data_dmy(r: dict) -> dict:
    """Afegeix la data en dd/mm/aa just despres de la data ISO (que es manté per ordenar)."""
    y, m, d = r["data"].split("-")
    out = {}
    for k, v in r.items():
        out[k] = v
        if k == "data":
            out["data_dmy"] = f"{d}/{m}/{y[2:]}"
    return out


rows = [amb_data_dmy(r) for r in rows]

with (SP / "desplacaments_detall.csv").open("w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
    w.writeheader()
    w.writerows(rows)

incomp = []
for temp, data, eq, div, grup, seu, nota in INCOMPAR:
    club = ALIAS.get(seu, seu)
    km, _ = road_km(club)
    incomp.append(amb_data_dmy(
        {"temporada": temp, "data": data, "equip": f'Banyoles "{eq}"',
         "divisio": div, "grup": grup, "seu_club": seu,
         "municipi": COORD[club][3], "km_total": round(km * 2, 1), "nota": nota}))
with (SP / "incompareixences.csv").open("w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(incomp[0]), delimiter=";")
    w.writeheader()
    w.writerows(incomp)

# --- projeccio 2026-2027 ---------------------------------------------------------------
# Composicio de grups de scripts/projeccio_lliga_2627.py, derivada de les classificacions
# oficials 2025-26 i dels play-offs de promocio del 4-5 de juliol de 2026.
PROJ_ALIAS = {"B.C.SANT FELIU DE CODINES": "C.B.SANT FELIU", "CASAL DE CERVERA": "S.E.CASAL CERVERA"}
DIV_NOM = {"Honor": "HONOR", "1a": "1a DIVISIÓ", "2a": "2a DIVISIÓ",
           "3a": "3a DIVISIÓ", "4a": "4a DIVISIÓ"}
TARIFA_PROJ = 0.26  # barem vigent

proj = json.loads(Path("web/src/lib/data/lliga2627.json").read_text(encoding="utf-8"))
projeccio = []
for div, dd in proj["divisions"].items():
    seed2eq = {e["seed"]: e for e in dd["equips"]}
    for g in dd["grups"]:
        eqs = [seed2eq[s] for s in g["seeds"] if s in seed2eq]
        nostres = [e for e in eqs if e["club"] == "C.B.BANYOLES"]
        for meu in nostres:
            for e in eqs:
                if e is meu or e["club"] == "C.B.BANYOLES":
                    continue
                club = ALIAS.get(PROJ_ALIAS.get(e["club"], e["club"]),
                                 PROJ_ALIAS.get(e["club"], e["club"]))
                if club not in COORD:
                    raise RuntimeError(f"sense coordenades per a {club} (projeccio)")
                k, mn = road_km(club)
                dieta = round(JUGADORS_LLIGA * DIETA_MIGDIA, 2) if k > LLINDAR_DIETA_KM else 0.0
                projeccio.append({
                    "equip": f'Banyoles "{meu["lletra"]}"', "divisio": DIV_NOM[div],
                    "grup": g["lletra"], "rival_club": club,
                    "rival_equip": e["lletra"] if e["lletra"] != "UNICO" else "",
                    "municipi": COORD[club][3], "precisio": COORD[club][2], "km_anada": k,
                    "km_total": round(k * 2, 1), "minuts_anada": mn,
                    "tarifa_eur_km": TARIFA_PROJ,
                    "import_km_eur": round(k * 2 * TARIFA_PROJ, 2),
                    "te_dieta": k > LLINDAR_DIETA_KM, "jugadors": JUGADORS_LLIGA,
                    "import_dietes_eur": dieta,
                    "import_total_eur": round(k * 2 * TARIFA_PROJ + dieta, 2),
                })
projeccio.sort(key=lambda x: (x["equip"], x["rival_club"]))
with (SP / "projeccio_2627.csv").open("w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(projeccio[0]), delimiter=";")
    w.writeheader()
    w.writerows(projeccio)

(SP / "rows.json").write_text(
    json.dumps({"rows": rows, "incompar": incomp, "a_casa": [amb_data_dmy(r) for r in a_casa],
                "adreces": ADRECES, "projeccio": projeccio,
                "params": {"dieta": DIETA_MIGDIA, "llindar_km": LLINDAR_DIETA_KM,
                           "jugadors_lliga": JUGADORS_LLIGA, "jugadors_copa": JUGADORS_COPA,
                           "consum": CONSUM_L_100KM}},
               ensure_ascii=False, indent=1), encoding="utf-8")

print(f"{len(rows)} desplaçaments · {JUGADORS_LLIGA} jugadors a la lliga i {JUGADORS_COPA} "
      f"a la Copa · dieta {DIETA_MIGDIA} € si l'anada supera {LLINDAR_DIETA_KM} km\n")
print(f"{'TEMPORADA':11s} {'n':>4s} {'km':>10s} {'quilometratge':>14s} {'dietes':>11s} "
      f"{'TOTAL':>11s} | {'pend.':>5s} {'km':>8s}")
tk = tq = td = pk = 0.0
for temp in sorted({r["temporada"] for r in rows}):
    conf = [r for r in rows if r["temporada"] == temp and r["estat"] == "verificat"]
    pend = [r for r in rows if r["temporada"] == temp and r["estat"] == "pendent"]
    km_, q, di = (sum(r[k] for r in conf) for k in
                  ("km_total", "import_km_eur", "import_dietes_eur"))
    kp = sum(r["km_total"] for r in pend)
    tk, tq, td, pk = tk + km_, tq + q, td + di, pk + kp
    print(f"{temp:11s} {len(conf):4d} {km_:10,.1f} {q:13,.2f}€ {di:10,.2f}€ {q + di:10,.2f}€"
          f" | {len(pend):5d} {kp:8,.1f}")
print(f"{'TOTAL':11s} {sum(1 for r in rows if r['estat'] == 'verificat'):4d} {tk:10,.1f} "
      f"{tq:13,.2f}€ {td:10,.2f}€ {tq + td:10,.2f}€ | "
      f"{sum(1 for r in rows if r['estat'] == 'pendent'):5d} {pk:8,.1f}")
sense = [r for r in rows if r["estat"] == "verificat" and not r["te_dieta"]]
print(f"\nsense dieta (anada de {LLINDAR_DIETA_KM} km o menys): {len(sense)} -> "
      + ", ".join(f"{r['data']} {r['seu_club']} ({r['km_anada']} km)" for r in sense))
for r in a_casa:
    print(f"\nJugat a casa (fora del recompte): {r['data']} {r['equip']} — {r['nota']}")
for r in rows:
    if r.get("seu_nominal"):
        print(f"Seu corregida: {r['data']} {r['equip']} — portal deia {r['seu_nominal']}, "
              f"s'aplica {r['seu_club']} ({r['km_total']} km)")
