"""Projecció de la Lliga Catalana de Tres Bandes 2026-2027.

Composició de divisions derivada de les classificacions oficials 2025-26 i dels
play-offs de promoció del 4-5 de juliol de 2026, i llista d'inscripció projectada
de cada club: el pool de jugadors ordenat per la mitjana del rànquing oficial
vigent i repartit en les bandes reglamentàries de la federació (1-3 equip A,
4-8 equip B i reserves de l'A, 9-12 equip C, 13-16 equip D, la resta equip E).

Alimenta la pestanya "Lliga 26/27" de la web:
    python scripts/projeccio_lliga_2627.py --json web/src/lib/data/lliga2627.json
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import sqlite3
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DB = "data/fcbillar.db"
RANK_ID = 832  # rànquing tres bandes num_seq 124 (2026-07-27)
DIVORD = {"Honor": 0, "1a": 1, "2a": 2, "3a": 3, "4a": 4}
DIST = {"Honor": 40, "1a": 35, "2a": 30, "3a": 25, "4a": 25}
DIV2526 = {148: "Honor", 149: "1a", 150: "2a", 151: "3a", 152: "4a"}

# Composició projectada 2026-27: (nom de club a la BD, lletra d'equip)
COMP: dict[str, list[tuple[str, str]]] = {
    "Honor": [
        ("C.B.MATARÓ", "A"), ("C.B.SANT ADRIÀ", "A"), ("C.B.LLINARS", "A"), ("C.B.SANT BOI", "A"),
        ("C.B.LLEIDA", "A"), ("C.B.SANT ADRIÀ", "B"), ("SB FOMENT MOLINS", "A"),
        ("B.C.GRANOLLERS", "A"), ("C.B.MOLLET", "A"), ("C.B.MONFORTE", "A"),
        ("C.B.BARCELONA", "A"), ("B.C.GRANOLLERS", "B"), ("C.B.MONT-ROIG", "A"),
        ("C.B.MONFORTE", "B"), ("BC OLESA", "UNICO"), ("CASAL DE CERVERA", "UNICO"),
    ],
    "1a": [
        ("C.B.2000 CERDANYOLA", "A"), ("S.B.LA GRAN PENYA", "A"), ("C.B. CANET", "A"),
        ("B.LA UNIÓ CORAL", "A"), ("C.B.MANRESA", "A"), ("C.B.SANTS", "B"), ("C.B.MONFORTE", "C"),
        ("C.B.MOLLET", "B"), ("C.B.PRAT", "A"), ("C.B.SANTS", "A"), ("C.B.BANYOLES", "A"),
        ("S.B.P.E.CENTELLES", "A"), ("C.B.MATARÓ", "B"), ("C.B.ALBA", "UNICO"),
        ("C.B.MONT-ROIG", "B"), ("C.B.SANT ADRIÀ", "C"),
    ],
    "2a": [
        ("S.B.CORAL COLÓN", "A"), ("C.B.TARRAGONA", "B"), ("C.B.BLANES", "A"), ("C.B.VIC", "UNICO"),
        ("C.B.SANT BOI", "B"), ("C.B.PREMIÀ", "UNICO"), ("SB FOMENT MOLINS", "C"),
        ("C.B.BANYOLES", "B"), ("C.B.LLINARS", "B"), ("SB FOMENT MOLINS", "B"),
        ("C.B.TARRAGONA", "A"), ("C.B.LLEIDA", "B"), ("C.B.CARDONA", "UNICO"),
        ("C.B.BARCELONA", "B"), ("C.B.2000 CERDANYOLA", "B"), ("C.B.SANTS", "D"),
    ],
    "3a": [
        ("C.B.MONFORTE", "D"), ("S.B.P.E.CENTELLES", "B"), ("C.B.PRAT", "B"),
        ("B. EL MASNOU", "UNICO"), ("C.B.LLINARS", "C"), ("B.C.GRANOLLERS", "C"),
        ("B.C.GRANOLLERS", "D"), ("C.B.SANTS", "C"), ("S.B.ESPLUGUES L'AVENÇ", "A"),
        ("C.B.LLIÇÀ D'AMUNT", "B"), ("C.B.LLIÇÀ D'AMUNT", "A"), ("S.B. GEiEG", "UNICO"),
        ("C.B.SANT ADRIÀ", "D"), ("C.B. CANET", "B"), ("S.B.LA GRAN PENYA", "B"),
        ("C.B.MATARÓ", "C"),
    ],
    "4a": [
        ("C.B. CANET", "C"), ("C.B.MONT-ROIG", "C"), ("C.B.LLINARS", "D"), ("B.LA UNIÓ CORAL", "B"),
        ("C.B.MONFORTE", "E"), ("C.B.2000 CERDANYOLA", "C"), ("C.B.BANYOLES", "C"),
        ("C.B.MATARÓ", "D"), ("C.B.LLINARS", "E"), ("C.B. BORGES", "UNICO"), ("C.B.BLANES", "B"),
        ("S.B.CORAL COLÓN", "B"), ("B.C.SANT FELIU DE CODINES", "UNICO"),
        ("S.B.ESPLUGUES L'AVENÇ", "B"), ("C.B.MANRESA", "B"), ("C.B.SANTS", "E"),
        ("C.B.BARCELONA", "C"), ("C.B.SANT BOI", "C"), ("C.B.VILANOVA", "UNICO"),
    ],
}

# Noms de club per a la interfície (a la BD hi són en majúscules i sense espais)
NOMS = {
    "B. EL MASNOU": "B. El Masnou", "B.C.GRANOLLERS": "B.C. Granollers",
    "B.C.SANT FELIU DE CODINES": "B.C. Sant Feliu de Codines",
    "B.LA UNIÓ CORAL": "B. La Unió Coral", "BC OLESA": "B.C. Olesa",
    "C.B. BORGES": "C.B. Borges", "C.B. CANET": "C.B. Canet",
    "C.B.2000 CERDANYOLA": "C.B. 2000 Cerdanyola", "C.B.ALBA": "C.B. Alba",
    "C.B.BANYOLES": "C.B. Banyoles", "C.B.BARCELONA": "C.B. Barcelona",
    "C.B.BLANES": "C.B. Blanes", "C.B.CARDONA": "C.B. Cardona", "C.B.LLEIDA": "C.B. Lleida",
    "C.B.LLINARS": "C.B. Llinars", "C.B.LLIÇÀ D'AMUNT": "C.B. Lliçà d'Amunt",
    "C.B.MANRESA": "C.B. Manresa", "C.B.MATARÓ": "C.B. Mataró", "C.B.MOLLET": "C.B. Mollet",
    "C.B.MONFORTE": "C.B. Monforte", "C.B.MONT-ROIG": "C.B. Mont-roig", "C.B.PRAT": "C.B. Prat",
    "C.B.PREMIÀ": "C.B. Premià", "C.B.SANT ADRIÀ": "C.B. Sant Adrià",
    "C.B.SANT BOI": "C.B. Sant Boi", "C.B.SANTS": "C.B. Sants",
    "C.B.TARRAGONA": "C.B. Tarragona", "C.B.VIC": "C.B. Vic", "C.B.VILANOVA": "C.B. Vilanova",
    "CASAL DE CERVERA": "Casal de Cervera", "S.B. GEiEG": "S.B. GEiEG",
    "S.B.CORAL COLÓN": "S.B. Coral Colón", "S.B.ESPLUGUES L'AVENÇ": "S.B. Esplugues l'Avenç",
    "S.B.LA GRAN PENYA": "S.B. La Gran Penya", "S.B.P.E.CENTELLES": "S.B.P.E. Centelles",
    "SB FOMENT MOLINS": "S.B. Foment Molins",
}


def nom_club(clau: str) -> str:
    return NOMS.get(clau, clau)


# Motiu del canvi de divisió respecte del 2025-26
MOTIU = {
    ("CASAL DE CERVERA", "UNICO"): "puja · play-off guanyat a Centelles A",
    ("C.B.MONFORTE", "B"): "puja · campió 1a A",
    ("BC OLESA", "UNICO"): "puja · campió 1a B",
    ("C.B.SANTS", "A"): "baixa · 8è Honor A",
    ("C.B.BANYOLES", "A"): "baixa · 8è Honor B",
    ("S.B.P.E.CENTELLES", "A"): "baixa · play-off perdut amb Casal Cervera",
    ("C.B.MATARÓ", "B"): "puja · campió 2a A",
    ("C.B.ALBA", "UNICO"): "puja · campió 2a B",
    ("C.B.MONT-ROIG", "B"): "puja · play-off guanyat a Llinars B",
    ("C.B.SANT ADRIÀ", "C"): "puja · play-off amb Lleida B, desempat per caramboles (201-186)",
    ("SB FOMENT MOLINS", "B"): "baixa · 8è 1a A",
    ("C.B.TARRAGONA", "A"): "baixa · 8è 1a B",
    ("C.B.LLINARS", "B"): "baixa · play-off perdut amb Mont-roig B",
    ("C.B.LLEIDA", "B"): "baixa · play-off amb Sant Adrià C, desempat per caramboles (186-201)",
    ("C.B.CARDONA", "UNICO"): "puja · campió 3a A",
    ("C.B.BARCELONA", "B"): "puja · campió 3a B",
    ("C.B.2000 CERDANYOLA", "B"): "puja · play-off guanyat a Lliçà d'Amunt A",
    ("C.B.SANTS", "D"): "puja · play-off amb Canet B, desempat per caramboles (178-177)",
    ("S.B. GEiEG", "UNICO"): "baixa · 8è 2a A",
    ("C.B.SANT ADRIÀ", "D"): "baixa · 8è 2a B",
    ("C.B.LLIÇÀ D'AMUNT", "A"): "baixa · play-off perdut amb Cerdanyola B",
    ("C.B. CANET", "B"): "baixa · play-off amb Sants D, desempat per caramboles (177-178)",
    ("S.B.LA GRAN PENYA", "B"): "puja · campió 4a A",
    ("C.B.MATARÓ", "C"): "puja · campió 4a B",
    ("C.B.SANT BOI", "C"): "baixa · 8è 3a A",
    ("C.B.VILANOVA", "UNICO"): "baixa · 8è 3a B",
}


# Canvis de club coneguts per a la 2026-27 (nom exacte a `players` → club destí a la BD).
TRASPASSOS = [
    ("CORPAS NATOLI, FERNANDO", "C.B.LLINARS"),
    ("RODRÍGUEZ NAVARRA, FERRÁN", "S.B. GEiEG"),
    ("CHUECOS ENRIQUEZ, LUIS", "C.B.MONFORTE"),
    ("CARDONA GALLEGO, JULIÁN ALBERTO", "C.B.MONFORTE"),
    ("MAS CANADELL, JOSEP Mª", "B.C.GRANOLLERS"),
    ("GUERRERO GONZÁLEZ, MIQUEL A.", "C.B.SANT ADRIÀ"),
    ("GIL PÉREZ, ALBERT", "C.B.SANT ADRIÀ"),
    ("PORQUERAS SABATÉ, VÍCTOR", "C.B.SANT ADRIÀ"),
    ("GARCÍA GARCÍA, JORDI", "B.LA UNIÓ CORAL"),
    ("GARRIGA COMAS, JORDI", "C.B.MATARÓ"),
    ("SÁNCHEZ GALLEGO, JOEL", "C.B.MATARÓ"),
    ("MULA CALLEJÓN, FRANCISCO", "C.B.SANTS"),
    ("SÁNCHEZ MARTÍNEZ, PASCUAL", "C.B.SANTS"),
]


def aplica_traspassos(conn, pool: dict, rk: dict) -> None:
    """Mou jugadors d'un pool de club a un altre. Els que no van jugar la lliga
    2025-26 s'incorporen des del rànquing amb 0 partides."""
    for nom, desti in TRASPASSOS:
        row = conn.execute(
            "select p.id, c.nom from players p left join clubs c on c.id=p.club_id where p.nom=?",
            (nom,),
        ).fetchone()
        if row is None:
            print(f"AVÍS: jugador no trobat -> {nom}", file=sys.stderr)
            continue
        pid, club_llicencia = row
        origen = next((cl for cl, ps in pool.items() if pid in ps), None)
        if origen == desti:
            continue  # ja hi és
        if origen is not None:
            agg = pool[origen].pop(pid)
            agg["de_club"] = origen
        elif pid in rk:
            agg = dict(nom=nom, pj=0, car=0, ent=0, equips=collections.Counter(),
                       de_club=club_llicencia or "sense club")
        else:
            print(f"AVÍS: sense mitjana de referència -> {nom}", file=sys.stderr)
            continue
        agg["equips"] = collections.Counter()
        pool[desti][pid] = agg


def banda(num: int) -> str:
    """Bandes d'inscripció de la FCB: els clubs presenten UNA sola llista i la
    federació l'ordena per rànquing. 1-3 només equip A; 4-8 titulars del B i
    reserves de l'A; 9-12 titulars del C; 13-16 titulars del D; la resta, equip E
    i/o reserves."""
    if num <= 3:
        return "A"
    if num <= 8:
        return "B"
    if num <= 12:
        return "C"
    if num <= 16:
        return "D"
    return "E"


def referents(llista: list[dict], lletra: str) -> list[dict]:
    """Els quatre jugadors que, en jornada regular, formen l'alineació d'un equip.

    L'equip A només té tres jugadors propis (1-3): el quart surt de la banda del B,
    normalment el nº 4. Per això el B, en jornada regular, tira dels nº 5-8."""
    if lletra == "A":
        return [p for p in llista if p["num"] <= 4]
    if lletra == "B":
        return [p for p in llista if 5 <= p["num"] <= 8]
    return [p for p in llista if p["banda"] == lletra][:4]


def build(db: str = DB) -> dict:
    conn = sqlite3.connect(db)
    rk = {
        r[0]: (r[1], r[2])
        for r in conn.execute(
            "select player_id, mitjana_general, posicio from ranking_entries where ranking_id=?",
            (RANK_ID,),
        )
    }
    q = """
    with p as (
     select e.divisio_id d, g.equip1_id eq, g.player1_id pl, g.caramboles1 car, g.entrades ent
       from games g join encontres_lliga e on e.id=g.encontre_lliga_id
      where e.temporada_id=1 and e.lliga_id=36
     union all
     select e.divisio_id, g.equip2_id, g.player2_id, g.caramboles2, g.entrades
       from games g join encontres_lliga e on e.id=g.encontre_lliga_id
      where e.temporada_id=1 and e.lliga_id=36)
    select cl.nom, coalesce(q.lletra,'UNICO'), p.d, p.pl, pl.nom, count(*), sum(p.car), sum(p.ent)
    from p join equips q on q.id=p.eq join clubs cl on cl.id=q.club_id join players pl on pl.id=p.pl
    group by q.id, p.pl"""
    pool: dict[str, dict[int, dict]] = collections.defaultdict(dict)
    prev_div: dict[tuple[str, str], str] = {}
    for club, lletra, d, pid, nom, n, car, ent in conn.execute(q):
        prev_div[(club, lletra)] = DIV2526[d]
        a = pool[club].setdefault(
            pid, dict(nom=nom, pj=0, car=0, ent=0, equips=collections.Counter())
        )
        a["pj"] += n
        a["car"] += car
        a["ent"] += ent
        a["equips"][lletra] += n

    aplica_traspassos(conn, pool, rk)

    # Les lletres es tornen a repartir cada temporada per categoria: l'A és sempre
    # l'equip de més divisió, després B, C, D i E. Les de COMP són les heretades del
    # 2025-26 (les que van guanyar la plaça) i serveixen només per lligar-hi el motiu
    # de l'ascens o descens.
    club_teams = collections.defaultdict(list)
    for div, teams in COMP.items():
        for club, lletra in teams:
            club_teams[club].append((DIVORD[div], lletra, div))
    for club, v in club_teams.items():
        v.sort()
        club_teams[club] = [
            (ord_div, chr(ord("A") + i), div, lletra)
            for i, (ord_div, lletra, div) in enumerate(v)
        ]

    def nivell(pid: int, a: dict) -> tuple[float, int | None]:
        if pid in rk:
            return rk[pid][0], rk[pid][1]
        return (a["car"] / a["ent"] if a["ent"] else 0.0), None

    out: dict = {"rank_id": RANK_ID, "clubs": [], "divisions": {}}
    for club in sorted(club_teams):
        teams = club_teams[club]
        ranked = []
        for pid, a in pool.get(club, {}).items():
            m, pos = nivell(pid, a)
            ranked.append(
                dict(
                    pid=pid, nom=a["nom"], mitjana=m, pos=pos, pj=a["pj"],
                    equip_2526=a["equips"].most_common(1)[0][0] if a["equips"] else None,
                    de_club=a.get("de_club"),
                )
            )
        ranked.sort(key=lambda x: -x["mitjana"])
        lletres = [t[1] for t in teams]
        div_de = {t[1]: t[2] for t in teams}
        multi = len(teams) > 1
        llista = []
        for i, p in enumerate(ranked, 1):
            b = banda(i)
            titular = b in div_de
            llista.append(dict(
                num=i, banda=b, titular=titular,
                reserva_de=[x for x in lletres if x < b] if titular else lletres[:],
                swing=(i == 4 and multi),
                nom=p["nom"], mitjana=round(p["mitjana"], 4), pos=p["pos"],
                de_club=nom_club(p["de_club"]) if p["de_club"] else None,
            ))
        equips = [dict(lletra=lt, unic=(not multi), divisio=dv, distancia=DIST[dv],
                       lletra_2526=("" if antiga == "UNICO" else antiga),
                       div_2526=prev_div.get((club, antiga)), motiu=MOTIU.get((club, antiga)))
                  for _, lt, dv, antiga in teams]
        out["clubs"].append(dict(
            club=club, nom=nom_club(club), equips=equips, llista=llista, multi=multi,
        ))

    # La vista per divisió només guarda la referència a l'equip: la banda i els
    # quatre titulars es deriven de la llista del club (mateixa funció `referents`).
    per_club = {c["club"]: c for c in out["clubs"]}
    for div in ["Honor", "1a", "2a", "3a", "4a"]:
        equips = []
        for club, lletra in COMP[div]:
            c = per_club[club]
            e = next(x for x in c["equips"] if x["lletra_2526"] == ("" if lletra == "UNICO" else lletra))
            tit = referents(c["llista"], e["lletra"])
            equips.append(dict(
                club=club, nom=nom_club(club), lletra=e["lletra"], unic=e["unic"],
                lletra_2526=e["lletra_2526"], div_2526=e["div_2526"], motiu=e["motiu"],
                mitjana_equip=(sum(t["mitjana"] for t in tit) / len(tit) if tit else 0.0),
            ))
        equips.sort(key=lambda e: -e["mitjana_equip"])
        out["divisions"][div] = dict(distancia=DIST[div], equips=equips)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="desa el resultat en JSON")
    args = ap.parse_args()
    data = build()
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        print(f"OK -> {args.json}")
    else:
        for c in data["clubs"]:
            eq = " · ".join(f"{e['lletra']} a {e['divisio']}" for e in c["equips"])
            print(f"\n{'=' * 72}\n{c['club']}   [{eq}]")
            vist = None
            for p in c["llista"]:
                if p["banda"] != vist:
                    vist = p["banda"]
                    rol = (f"titulars equip {vist}" if p["titular"]
                           else "reserves de " + ", ".join(p["reserva_de"]))
                    print(f"  -- banda {vist}: {rol} --")
                mk = f"  <- {p['de_club']}" if p["de_club"] else ""
                sw = "  (nº4: limitat amb el B)" if p["swing"] else ""
                print(f"    {p['num']:3d}. {p['nom']:34s} {p['mitjana']:.4f}{sw}{mk}")
