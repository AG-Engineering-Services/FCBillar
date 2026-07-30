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

# Composició i ORDRE OFICIALS, tal com surten a "CLASSIFICACIO FINAL LLIGUES TRES
# BANDES" de la FCB. L'ordre és el de sembra: primer els que baixen de la divisió
# de sobre, després els que s'hi mantenen intercalats per posició de grup, i al
# final els que hi pugen. Verificat: coincideix equip per equip amb la composició
# que derivàvem dels play-offs.
COMP: dict[str, list[tuple[str, str]]] = {
    "Honor": [
        ("C.B.MATARÓ", "A"), ("B.C.GRANOLLERS", "A"), ("C.B.MOLLET", "A"), ("C.B.SANT ADRIÀ", "A"),
        ("C.B.MONFORTE", "A"), ("C.B.LLINARS", "A"), ("C.B.BARCELONA", "A"), ("C.B.LLEIDA", "A"),
        ("C.B.SANT ADRIÀ", "B"), ("B.C.GRANOLLERS", "B"), ("SB FOMENT MOLINS", "A"),
        ("C.B.MONT-ROIG", "A"), ("C.B.SANT BOI", "A"), ("CASAL DE CERVERA", "UNICO"),
        ("BC OLESA", "UNICO"), ("C.B.MONFORTE", "B"),
    ],
    "1a": [
        ("S.B.P.E.CENTELLES", "A"), ("C.B.BANYOLES", "A"), ("C.B.SANTS", "A"),
        ("C.B.2000 CERDANYOLA", "A"), ("S.B.LA GRAN PENYA", "A"), ("C.B.SANTS", "B"),
        ("C.B. CANET", "A"), ("C.B.MONFORTE", "C"), ("B.LA UNIÓ CORAL", "A"), ("C.B.MOLLET", "B"),
        ("C.B.MANRESA", "A"), ("C.B.PRAT", "A"), ("C.B.MONT-ROIG", "B"), ("C.B.SANT ADRIÀ", "C"),
        ("C.B.MATARÓ", "B"), ("C.B.ALBA", "UNICO"),
    ],
    "2a": [
        ("C.B.LLEIDA", "B"), ("C.B.LLINARS", "B"), ("C.B.TARRAGONA", "A"),
        ("SB FOMENT MOLINS", "B"), ("S.B.CORAL COLÓN", "A"), ("C.B.SANT BOI", "B"),
        ("C.B.TARRAGONA", "B"), ("C.B.PREMIÀ", "UNICO"), ("C.B.BLANES", "A"),
        ("SB FOMENT MOLINS", "C"), ("C.B.BANYOLES", "B"), ("C.B.VIC", "UNICO"),
        ("C.B. CANET", "B"), ("C.B.2000 CERDANYOLA", "B"), ("C.B.CARDONA", "UNICO"),
        ("C.B.BARCELONA", "B"),
    ],
    "3a": [
        ("C.B.LLIÇÀ D'AMUNT", "A"), ("S.B. GEiEG", "UNICO"), ("C.B.SANT ADRIÀ", "D"),
        ("C.B.SANTS", "D"), ("B.C.GRANOLLERS", "C"), ("C.B.MONFORTE", "D"),
        ("B.C.GRANOLLERS", "D"), ("S.B.P.E.CENTELLES", "B"), ("C.B.SANTS", "C"),
        ("C.B.PRAT", "B"), ("S.B.ESPLUGUES L'AVENÇ", "A"), ("B. EL MASNOU", "UNICO"),
        ("C.B.LLIÇÀ D'AMUNT", "B"), ("C.B.LLINARS", "C"), ("C.B.MATARÓ", "C"),
        ("S.B.LA GRAN PENYA", "B"),
    ],
    "4a": [
        ("C.B.SANT BOI", "C"), ("C.B.VILANOVA", "UNICO"), ("C.B. BORGES", "UNICO"),
        ("C.B. CANET", "C"), ("C.B.BLANES", "B"), ("C.B.MONT-ROIG", "C"),
        ("S.B.CORAL COLÓN", "B"), ("C.B.LLINARS", "D"), ("B.LA UNIÓ CORAL", "B"),
        ("B.C.SANT FELIU DE CODINES", "UNICO"), ("C.B.MONFORTE", "E"),
        ("S.B.ESPLUGUES L'AVENÇ", "B"), ("C.B.2000 CERDANYOLA", "C"), ("C.B.BANYOLES", "C"),
        ("C.B.MANRESA", "B"), ("C.B.MATARÓ", "D"), ("C.B.SANTS", "E"), ("C.B.LLINARS", "E"),
        ("C.B.BARCELONA", "C"),
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
    ("C.B.SANT ADRIÀ", "C"): "puja · play-off amb Lleida B, desempat per caramboles a fora (102-95)",
    ("SB FOMENT MOLINS", "B"): "baixa · 8è 1a A",
    ("C.B.TARRAGONA", "A"): "baixa · 8è 1a B",
    ("C.B.LLINARS", "B"): "baixa · play-off perdut amb Mont-roig B",
    ("C.B.LLEIDA", "B"): "baixa · play-off amb Sant Adrià C, desempat per caramboles a fora (95-102)",
    ("C.B.CARDONA", "UNICO"): "puja · campió 3a A",
    ("C.B.BARCELONA", "B"): "puja · campió 3a B",
    ("C.B.2000 CERDANYOLA", "B"): "puja · play-off guanyat a Lliçà d'Amunt A",
    ("S.B. GEiEG", "UNICO"): "baixa · 8è 2a A",
    ("C.B.SANT ADRIÀ", "D"): "baixa · 8è 2a B",
    ("C.B.LLIÇÀ D'AMUNT", "A"): "baixa · play-off perdut amb Cerdanyola B",
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
    ("MERCADER BOSCH, JOSEP", "C.B.BANYOLES"),
    ("ROCHA VERA, JEFERSON", "C.B.MONFORTE"),
]


def aplica_traspassos(conn, pool: dict, rk: dict) -> None:
    """Mou jugadors d'un pool de club a un altre.

    Qui no va jugar la lliga 2025-26 s'incorpora des del rànquing amb 0 partides.
    Si ja tenia llicència al club de destí és una reincorporació, no un traspàs:
    es marca com a `retorn` perquè la interfície no digui que ve d'un altre club."""
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
            agg = dict(nom=nom, pj=0, car=0, ent=0, equips=collections.Counter())
            if club_llicencia == desti:
                agg["retorn"] = True
            else:
                agg["de_club"] = club_llicencia or "sense club"
        else:
            print(f"AVÍS: sense mitjana de referència -> {nom}", file=sys.stderr)
            continue
        agg["equips"] = collections.Counter()
        pool[desti][pid] = agg


# Repartiments de la llista única en bandes. Els clubs inscriuen tots els jugadors
# en una sola llista i la federació els ordena per rànquing; la banda diu a quin
# equip pot jugar cadascú, i sempre pot fer de suplent dels equips que té per sobre.
#
#   fcb  → 3-5-4-4: l'equip A només té tres jugadors propis i el quart de cada
#          encontre surt de la banda del B (normalment el nº 4, amb la limitació
#          de l'Assemblea 03/06/23), de manera que el B tira dels nº 5-8.
#   alt  → 4-6-6-6: cada equip té els seus quatre titulars propis i el B, el C i
#          el D porten dos suplents més a la seva banda.
ESQUEMES = {
    "fcb": {"talls": [3, 8, 12, 16], "inici": {"A": 1, "B": 5, "C": 9, "D": 13, "E": 17}},
    "alt": {"talls": [4, 10, 16, 22], "inici": {"A": 1, "B": 5, "C": 11, "D": 17, "E": 23}},
}
LLETRES = ["A", "B", "C", "D", "E"]


def forma_grups(ordre: list[tuple[str, str]]) -> tuple[list[int], list[int], list[dict]]:
    """Reparteix una divisió en dos grups pel serpentí A-B-B-A sobre l'ordre de
    sembra —1-4-5-8-9-12-13-16 al grup A i 2-3-6-7-10-11-14-15 al B, estirat igual
    a 4a amb 19 equips— i hi fa les permutes necessàries perquè dos equips d'un
    mateix club no coincideixin de grup.

    Es mou sempre el SEGON equip del club dins del grup, no el primer, i s'intercanvia
    amb l'equip que ocupa el mateix slot a l'altre grup. Exemple: si el Monforte A és
    el 3r del grup i el Monforte B el 8è, es permuta el Monforte B amb el 8è de l'altre
    grup. Així l'equip millor classificat es queda on el posa la sembra i el moviment
    és el mínim possible: els slots homòlegs són sempre posicions consecutives de
    l'ordre oficial (l'A2 és el 4 i el B2 el 3; l'A3 és el 5 i el B3 el 6…).

    Retorna les posicions (0-based) de cada grup i les permutes fetes."""
    n = len(ordre)
    serp = ["A" if (p - 1) % 4 in (0, 3) else "B" for p in range(1, n + 1)]
    A = [i for i in range(n) if serp[i] == "A"]
    B = [i for i in range(n) if serp[i] == "B"]

    def segon_repetit() -> tuple[str, int, int] | None:
        """El primer cas de dos equips del mateix club en un grup: en retorna el segon."""
        for lst, nom in ((A, "A"), (B, "B")):
            vistos: set[str] = set()
            for slot, i in enumerate(lst):
                club = ordre[i][0]
                if club in vistos:
                    return nom, slot, i
                vistos.add(club)
        return None

    permutes: list[dict] = []
    estats: set[tuple[int, ...]] = set()
    for _ in range(40):
        objectiu = segon_repetit()
        if objectiu is None:
            break
        estat = tuple(A + B)
        if estat in estats:
            break  # ja hi hem passat: no convergeix, ho deixem com està
        estats.add(estat)
        _nom, slot, i = objectiu
        if slot >= len(A) or slot >= len(B):
            break  # a 4a el grup B té un slot més: aquell no té homòleg
        j = B[slot] if A[slot] == i else A[slot]
        A[slot], B[slot] = B[slot], A[slot]
        permutes.append(dict(slot=slot + 1, seed_a=i + 1, seed_b=j + 1))
    return A, B, permutes


def banda(num: int, esquema: str = "fcb") -> str:
    """A quina banda de la llista única cau el jugador nº `num`."""
    for lletra, tall in zip(LLETRES, ESQUEMES[esquema]["talls"], strict=False):
        if num <= tall:
            return lletra
    return "E"


def referents(llista: list[dict], lletra: str, esquema: str = "fcb") -> list[dict]:
    """Els quatre jugadors que, en jornada regular, formen l'alineació d'un equip."""
    inici = ESQUEMES[esquema]["inici"][lletra]
    return [p for p in llista if inici <= p["num"] <= inici + 3]


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
                    de_club=a.get("de_club"), retorn=bool(a.get("retorn")),
                )
            )
        ranked.sort(key=lambda x: -x["mitjana"])
        multi = len(teams) > 1
        # La banda depèn del repartiment triat, i el repartiment es tria a la
        # interfície: aquí només desem la posició a la llista única.
        llista = [dict(
            num=i, nom=p["nom"], mitjana=round(p["mitjana"], 4), pos=p["pos"],
            de_club=nom_club(p["de_club"]) if p["de_club"] else None, retorn=p["retorn"],
        ) for i, p in enumerate(ranked, 1)]
        equips = [dict(lletra=lt, unic=(not multi), divisio=dv, distancia=DIST[dv],
                       lletra_2526=("" if antiga == "UNICO" else antiga),
                       div_2526=prev_div.get((club, antiga)), motiu=MOTIU.get((club, antiga)))
                  for _, lt, dv, antiga in teams]
        out["clubs"].append(dict(
            club=club, nom=nom_club(club), equips=equips, llista=llista, multi=multi,
        ))

    # La vista per divisió només guarda la referència a l'equip; els quatre titulars
    # i la mitjana d'equip es deriven de la llista del club amb el repartiment actiu.
    per_club = {c["club"]: c for c in out["clubs"]}
    for div in ["Honor", "1a", "2a", "3a", "4a"]:
        equips = []
        for seed, (club, lletra) in enumerate(COMP[div], 1):
            c = per_club[club]
            antiga = "" if lletra == "UNICO" else lletra
            e = next(x for x in c["equips"] if x["lletra_2526"] == antiga)
            equips.append(dict(
                seed=seed, club=club, nom=nom_club(club), lletra=e["lletra"], unic=e["unic"],
                lletra_2526=e["lletra_2526"], div_2526=e["div_2526"], motiu=e["motiu"],
            ))
        A, B, permutes = forma_grups(COMP[div])
        moguts = {p["seed_a"] for p in permutes} | {p["seed_b"] for p in permutes}
        grups = [dict(lletra=g, seeds=[i + 1 for i in lst]) for g, lst in (("A", A), ("B", B))]
        out["divisions"][div] = dict(
            distancia=DIST[div], equips=equips, grups=grups, permutes=permutes,
            moguts=sorted(moguts),
        )
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="desa el resultat en JSON")
    ap.add_argument("--esquema", choices=sorted(ESQUEMES), default="fcb",
                    help="repartiment en bandes per a la sortida de text")
    args = ap.parse_args()
    data = build()
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        print(f"OK -> {args.json}")
    else:
        esq = args.esquema
        for c in data["clubs"]:
            eq = " · ".join(f"{e['lletra']} a {e['divisio']}" for e in c["equips"])
            lletres = [e["lletra"] for e in c["equips"]]
            print(f"\n{'=' * 72}\n{c['club']}   [{eq}]")
            vist = None
            for p in c["llista"]:
                b = banda(p["num"], esq)
                if b != vist:
                    vist = b
                    rol = (f"titulars equip {b}" if b in lletres
                           else "reserves de " + ", ".join(lletres))
                    print(f"  -- banda {b}: {rol} --")
                mk = (f"  <- {p['de_club']}" if p["de_club"]
                      else "  (reincorporacio)" if p["retorn"] else "")
                sw = ("  (nº4: limitat amb el B)"
                      if esq == "fcb" and p["num"] == 4 and c["multi"] else "")
                print(f"    {p['num']:3d}. {p['nom']:34s} {p['mitjana']:.4f}{sw}{mk}")
