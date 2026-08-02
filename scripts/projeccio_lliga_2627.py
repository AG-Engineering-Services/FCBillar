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
import math
import sqlite3
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DB = "data/fcbillar.db"
RANK_ID = 832  # rànquing tres bandes num_seq 124 (2026-07-27)
DIVORD = {"Honor": 0, "1a": 1, "2a": 2, "3a": 3, "4a": 4}
DIST = {"Honor": 40, "1a": 35, "2a": 30, "3a": 25, "4a": 25}
DIV2526 = {148: "Honor", 149: "1a", 150: "2a", 151: "3a", 152: "4a"}

# Composició i ORDRE de sembra, presos de la "CLASSIFICACIO FINAL LLIGUES TRES
# BANDES" de la FCB: primer els que baixen de la divisió de sobre, després els que
# s'hi mantenen intercalats per posició de grup, i al final els que hi pugen.
#
# CORRECCIÓ sobre el document: el play-off Sants D - Canet B el va guanyar el
# SANTS D, no el Canet B. El desempat de les eliminatòries igualades és, doncs,
# el TOTAL de caramboles (178-177), que és també el que decideix l'altra
# (Sant Adrià C 201-186 Lleida B). Sants D puja a 2a i Canet B baixa a 3a, i
# cadascun va al bloc que li toca —els que pugen, al final; els que baixen, al
# principi—; la posició exacta dins del bloc és inferència nostra.
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
        # baixen de 1a
        ("C.B.LLEIDA", "B"), ("C.B.LLINARS", "B"), ("C.B.TARRAGONA", "A"),
        ("SB FOMENT MOLINS", "B"),
        # s'hi mantenen
        ("S.B.CORAL COLÓN", "A"), ("C.B.SANT BOI", "B"), ("C.B.TARRAGONA", "B"),
        ("C.B.PREMIÀ", "UNICO"), ("C.B.BLANES", "A"), ("SB FOMENT MOLINS", "C"),
        ("C.B.BANYOLES", "B"), ("C.B.VIC", "UNICO"),
        # hi pugen: primer els de play-off, després els campions
        ("C.B.2000 CERDANYOLA", "B"), ("C.B.SANTS", "D"), ("C.B.CARDONA", "UNICO"),
        ("C.B.BARCELONA", "B"),
    ],
    "3a": [
        # baixen de 2a: primer els de play-off, després els vuitens
        ("C.B.LLIÇÀ D'AMUNT", "A"), ("C.B. CANET", "B"), ("S.B. GEiEG", "UNICO"),
        ("C.B.SANT ADRIÀ", "D"),
        # s'hi mantenen
        ("B.C.GRANOLLERS", "C"), ("C.B.MONFORTE", "D"), ("B.C.GRANOLLERS", "D"),
        ("S.B.P.E.CENTELLES", "B"), ("C.B.SANTS", "C"), ("C.B.PRAT", "B"),
        ("S.B.ESPLUGUES L'AVENÇ", "A"), ("B. EL MASNOU", "UNICO"),
        ("C.B.LLIÇÀ D'AMUNT", "B"), ("C.B.LLINARS", "C"),
        # hi pugen
        ("C.B.MATARÓ", "C"), ("S.B.LA GRAN PENYA", "B"),
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
    ("C.B.SANT ADRIÀ", "C"): "puja · play-off amb Lleida B, desempat per caramboles (201-186)",
    ("C.B.SANTS", "D"): "puja · play-off amb Canet B, desempat per caramboles (178-177)",
    ("SB FOMENT MOLINS", "B"): "baixa · 8è 1a A",
    ("C.B.TARRAGONA", "A"): "baixa · 8è 1a B",
    ("C.B.LLINARS", "B"): "baixa · play-off perdut amb Mont-roig B",
    ("C.B.LLEIDA", "B"): "baixa · play-off amb Sant Adrià C, desempat per caramboles (186-201)",
    ("C.B. CANET", "B"): "baixa · play-off amb Sants D, desempat per caramboles (177-178)",
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
#   opt  → 4-4-4-4-4: cada equip amb els seus quatre i cap de compartit. És la
#          millor combinació que un club pot presentar en una jornada, perquè
#          tothom juga a l'equip que li toca per rànquing sense cedir ningú.
#   alt  → 4-6-6-6: cada equip té els seus quatre titulars propis i el B, el C i
#          el D porten dos suplents més a la seva banda.
ESQUEMES = {
    "fcb": {"talls": [3, 8, 12, 16], "inici": {"A": 1, "B": 5, "C": 9, "D": 13, "E": 17}},
    "opt": {"talls": [4, 8, 12, 16], "inici": {"A": 1, "B": 5, "C": 9, "D": 13, "E": 17}},
    "alt": {"talls": [4, 10, 16, 22], "inici": {"A": 1, "B": 5, "C": 11, "D": 17, "E": 23}},
}
LLETRES = ["A", "B", "C", "D", "E"]


# ---------------------------------------------------------------------------
# Pronòstic de grup
#
# Model de partida individual calibrat amb les 2.433 partides de la lliga
# 2025-26 (rànquing vigent en cada jornada, no el final):
#
#     P(guanya el local) = (1 - P_TAULES) · sigmoide(K · Δmitjana + LOCAL)
#
# K i LOCAL surten d'una màxima versemblança conjunta. L'avantatge de camp és
# real i mesurable: els locals s'enduen el 55,1% dels parcials, i amb mitjanes
# iguals el local guanya el 54,5% de les partides. Validat per trams, el model
# encerta la freqüència real dins d'un o dos punts.
K_MITJANA = 8.00
AVANTATGE_LOCAL = 0.18
P_TAULES = 0.05
N_SIMS = 10000


def alineacio_probable(club: dict, lletra: str) -> list[int]:
    """Els quatre números de la llista que amb més probabilitat formen l'alineació
    d'aquest equip, repartits de dalt a baix.

    Un jugador no pot jugar la mateixa jornada amb dos equips del club: si és dels
    quatre més probables de l'A, ja no compta per al B. Per això es reparteix per
    ordre de categoria i cada equip tria d'entre els que queden lliures."""
    memo = club.setdefault("_alineacions", {})
    if memo:
        return memo.get(lletra, [])
    agafats: set[int] = set()
    for e in club["equips"]:
        lt = e["lletra"]
        ultim = club["equips"][-1]["lletra"] == lt
        banda = [x for x in club["llista"] if banda_de(x["num"], "fcb") == lt]
        tit = referents(club["llista"], lt, "fcb")
        nums = {x["num"] for x in banda} | {x["num"] for x in tit}
        if ultim and nums:
            nums |= {x["num"] for x in club["llista"] if x["num"] >= min(nums)}
        lliures = [x for x in club["llista"] if x["num"] in nums and x["num"] not in agafats]
        tria = sorted(lliures, key=lambda x: (-x["taxa"], -x["mitjana"]))[:4]
        agafats |= {x["num"] for x in tria}
        memo[lt] = [x["num"] for x in tria]
    return memo.get(lletra, [])


def alineacio_efectiva(pool: list[tuple[float, float]], llavor: int, n: int = 4000) -> list[float]:
    """Mitjana esperada a cada taula (1..4) d'un equip, mostrejant qui hi juga.

    `pool` són els candidats de l'equip amb el seu pes de presència. Els equips
    que roden molt hi perden: si els millors només fan la meitat de les jornades,
    la taula 1 no té sempre la seva millor mitjana. Sense això el model dona per
    fet que els quatre titulars juguen sempre, cosa que només passa a 34 dels 83
    equips."""
    import numpy as np

    m = np.array([x[0] for x in pool], dtype=float)
    if len(pool) <= 4:
        v = sorted(m, reverse=True)
        return [v[i] if i < len(v) else (v[-1] if v else 0.0) for i in range(4)]
    w = np.clip(np.array([x[1] for x in pool], dtype=float), 0.02, None)
    prob = w / w.sum()
    rng = np.random.default_rng(llavor)
    acc = np.zeros(4)
    for _ in range(n):
        idx = rng.choice(len(pool), size=4, replace=False, p=prob)
        acc += np.sort(m[idx])[::-1]
    return list(acc / n)


def _dist_encontre(mit_local: list[float], mit_visitant: list[float]):
    """Distribució dels parcials del local (0..8) en un encontre de quatre taules.

    Les taules s'aparellen per ordre: el nº 1 d'un equip contra el nº 1 de l'altre."""
    import numpy as np

    dist = np.zeros(9)
    dist[0] = 1.0
    for t in range(4):
        dm = (mit_local[t] if t < len(mit_local) else 0.0) - (
            mit_visitant[t] if t < len(mit_visitant) else 0.0
        )
        p = 1.0 / (1.0 + math.exp(-(K_MITJANA * dm + AVANTATGE_LOCAL)))
        pw, pd, pl = (1 - P_TAULES) * p, P_TAULES, (1 - P_TAULES) * (1 - p)
        nova = np.zeros(9)
        for v in range(9):
            if dist[v] == 0.0:
                continue
            if v + 2 <= 8:
                nova[v + 2] += dist[v] * pw
            if v + 1 <= 8:
                nova[v + 1] += dist[v] * pd
            nova[v] += dist[v] * pl
        dist = nova
    return dist


def pronostic_grup(mitjanes: list[list[float]], llavor: int) -> list[dict]:
    """Simula la lliga doble d'un grup i retorna, per equip, la probabilitat de
    quedar 1r, 2n, penúltim i últim, i la posició mitjana.

    Cada encontre es resol mostrejant els parcials del local; els punts de match
    són 3/1/0 i el desempat, els parcials, com fa la federació."""
    import numpy as np

    n = len(mitjanes)
    parelles = [(i, j) for i in range(n) for j in range(n) if i != j]
    cdfs = np.array([np.cumsum(_dist_encontre(mitjanes[i], mitjanes[j])) for i, j in parelles])
    rng = np.random.default_rng(llavor)
    u = rng.random((N_SIMS, len(parelles)))
    parcials_local = (u[:, :, None] > cdfs[None, :, :]).sum(axis=2)

    pm = np.zeros((N_SIMS, n), dtype=np.int32)
    pp = np.zeros((N_SIMS, n), dtype=np.int32)
    for idx, (i, j) in enumerate(parelles):
        h = parcials_local[:, idx]
        a = 8 - h
        pp[:, i] += h
        pp[:, j] += a
        pm[:, i] += np.where(h > 4, 3, np.where(h == 4, 1, 0))
        pm[:, j] += np.where(a > 4, 3, np.where(a == 4, 1, 0))

    score = pm * 1000 + pp
    ordre = np.argsort(-score, axis=1, kind="stable")
    pos = np.empty_like(ordre)
    np.put_along_axis(pos, ordre, np.arange(n)[None, :].repeat(N_SIMS, 0), axis=1)
    return [
        dict(
            p_1r=round(float((pos[:, i] == 0).mean()), 4),
            p_2n=round(float((pos[:, i] == 1).mean()), 4),
            p_penultim=round(float((pos[:, i] == n - 2).mean()), 4),
            p_ultim=round(float((pos[:, i] == n - 1).mean()), 4),
            pos_mitjana=round(float(pos[:, i].mean()) + 1, 2),
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Pronòstic: TOTA la lliga, jornada a jornada
#
# Simular cada grup per separat no podia respectar la regla que de debò lliga els
# equips d'un club: un jugador no juga la mateixa jornada amb dos equips. Ara se
# simula el calendari sencer —les cinc divisions i els deu grups alhora— i, a
# cada jornada:
#
#   1. per a cada jugador es sorteja si està disponible, amb la seva presència;
#   2. cada club reparteix els disponibles entre els seus equips per ordre de
#      categoria: l'A tria primer, i cadascú agafa els de la seva banda i, si no
#      n'hi ha prou, puja els millors de les de sota, que és el que diu el
#      reglament —es pot fer de suplent dels equips que es tenen per sobre;
#   3. es resolen els encontres amb les alineacions que han quedat.
#
# Si un equip no arriba a quatre jugadors, les taules que li falten es donen per
# perdudes, com una incompareixença parcial.
LLETRA_ORD = {lt: i for i, lt in enumerate(LLETRES)}


def calendari(n: int) -> list[list[tuple[int, int]]]:
    """Calendari de lliga a doble volta per a n equips (mètode del cercle).

    Retorna, per jornada, les parelles (local, visitant) amb índexs 0..n-1. Amb un
    nombre senar d'equips cada jornada un equip descansa."""
    idx = list(range(n)) + ([-1] if n % 2 else [])
    m = len(idx)
    anada: list[list[tuple[int, int]]] = []
    for r in range(m - 1):
        parelles = []
        for i in range(m // 2):
            a, b = idx[i], idx[m - 1 - i]
            if a != -1 and b != -1:
                parelles.append((a, b) if (r + i) % 2 == 0 else (b, a))
        anada.append(parelles)
        idx = [idx[0], idx[-1], *idx[1:-1]]
    return anada + [[(b, a) for a, b in jor] for jor in anada]


def simula_lliga(per_club: dict, divisions: dict, n_sims: int, llavor: int = 20260802) -> dict:
    """Simula n_sims temporades senceres i retorna, per (divisió, cap de sèrie), la
    probabilitat de cada equip de quedar 1r, 2n, penúltim i últim del seu grup."""
    import random

    rnd = random.Random(llavor)
    aleatori = rnd.random

    # --- equips de tota la lliga ------------------------------------------
    equips: list[dict] = []
    per_grup: dict[tuple[str, str], list[int]] = {}
    for div, dades in divisions.items():
        per_seed = {e["seed"]: e for e in dades["equips"]}
        for g in dades["grups"]:
            ids = []
            for seed in g["seeds"]:
                e = per_seed[seed]
                ids.append(len(equips))
                equips.append(dict(div=div, seed=seed, club=e["club"], lletra=e["lletra"],
                                   grup=(div, g["lletra"])))
            per_grup[(div, g["lletra"])] = ids

    # --- calendaris i en quines jornades juga cada equip -------------------
    cal = {k: calendari(len(ids)) for k, ids in per_grup.items()}
    n_jor = max(len(v) for v in cal.values())
    juga: list[set[int]] = [set() for _ in equips]
    for k, ids in per_grup.items():
        for j, jornada in enumerate(cal[k]):
            for il, iv in jornada:
                juga[ids[il]].add(j)
                juga[ids[iv]].add(j)

    # --- clubs: equips per ordre de categoria i jugadors amb la seva banda --
    clubs: dict[str, dict] = {}
    for i, e in enumerate(equips):
        clubs.setdefault(e["club"], {"equips": [], "jug": None, "nom": e["club"]})["equips"].append(
            (i, e["lletra"]))
    for nom, c in clubs.items():
        c["equips"].sort(key=lambda t: LLETRA_ORD[t[1]])
        c["equips"] = [(i, LLETRA_ORD[lt]) for i, lt in c["equips"]]
        # La presència es va mesurar amb l'estructura d'equips de l'any passat i
        # el club en té una altra: cal reescalar-la perquè, en conjunt, cobreixi
        # les places que ara ha d'omplir cada jornada, amb un marge del 15% que
        # és el que permet que hi hagi rotació de debò. L'ordre relatiu no es
        # toca: qui jugava la meitat de les jornades en segueix jugant menys que
        # qui no en fallava cap.
        taxes = [p["taxa"] for p in per_club[nom]["llista"]]
        objectiu = min(4 * len(c["equips"]) * 1.15, len(taxes))
        lo, hi = 0.5, 50.0
        for _ in range(40):
            f = (lo + hi) / 2
            if sum(min(1.0, t * f) for t in taxes) < objectiu:
                lo = f
            else:
                hi = f
        f = (lo + hi) / 2
        c["jug"] = [(p["num"], p["mitjana"], min(1.0, p["taxa"] * f),
                     LLETRA_ORD[banda_de(p["num"], "fcb")])
                    for p in per_club[nom]["llista"]]
    llista_clubs = list(clubs.values())

    n_eq = len(equips)
    comptes = [[0, 0, 0, 0] for _ in range(n_eq)]
    suma_pos = [0.0] * n_eq
    sense_quatre = 0
    # Comptem dues coses per equip: quantes jornades juga cada jugador i quantes
    # vegades surt cada combinació de quatre. L'alineació més probable és la
    # combinació que més es repeteix, no els quatre jugadors més freqüents per
    # separat —que podrien no haver coincidit mai a la mateixa taula.
    cops: list[dict[int, int]] = [{} for _ in range(n_eq)]
    combos: list[dict[tuple, int]] = [{} for _ in range(n_eq)]
    # El mode de cada equip per separat pot no quadrar dins del club: dos equips
    # podrien tenir el mateix jugador a la seva alineació més freqüent, tot i que
    # cap jornada no hi coincideixen. Per això es compta també el repartiment
    # SENCER del club, i el que més es repeteix és el que es publica.
    combos_club: dict[str, dict[tuple, int]] = {nom: {} for nom in clubs}
    # i qui ocupa cada taula: la taula 1 és el de més mitjana dels quatre que
    # juguen, o sigui que un jugador pot rondar entre la 2 i la 3 segons qui
    # l'acompanyi aquell dia
    per_taula: list[list[dict[int, int]]] = [[{} for _ in range(4)] for _ in range(n_eq)]

    for _ in range(n_sims):
        pm = [0] * n_eq
        pp = [0] * n_eq
        for j in range(n_jor):
            alin: dict[int, list[float]] = {}
            for c in llista_clubs:
                juguen = [(i, o) for i, o in c["equips"] if j in juga[i]]
                if not juguen:
                    continue
                # Repartiment de la jornada, en dos passos.
                #
                # 1) Qui és a disposició del club: cada jugador, amb la seva
                #    presència. És el que fa que un equip no tregui sempre els
                #    seus millors promitjos —al Granollers, els tres primers del
                #    rànquing català juguen la meitat de les jornades.
                # 2) Els equips trien per ordre de categoria i, dins de cadascun,
                #    els MILLORS disponibles: primer els de la seva banda i, si no
                #    n'hi ha prou, pujant-ne de les de sota. Un equip només pot
                #    pujar-ne si en queden prou per als de sota; sense aquest
                #    límit, l'A i el B buiden la banda de l'últim equip.
                disp = {pj[0] for pj in c["jug"] if aleatori() < pj[2]}
                usats: set[int] = set()
                repartiment: list[tuple[int, tuple]] = []
                for n_fets, (idx_eq, ordre_eq) in enumerate(juguen):
                    resten = len(juguen) - n_fets - 1
                    propis, sota = [], []
                    for pj in c["jug"]:
                        if pj[0] in usats or pj[0] not in disp:
                            continue
                        if pj[3] == ordre_eq:
                            propis.append(pj)
                        elif pj[3] > ordre_eq:
                            sota.append(pj)
                    propis.sort(key=lambda pj: -pj[1])
                    tria = propis[:4]
                    if len(tria) < 4:
                        sota.sort(key=lambda pj: -pj[1])
                        marge = len(sota) - 4 * resten
                        max_sota = max(4 - len(propis), min(4, marge)) if resten else 4
                        tria = tria + sota[: min(4 - len(tria), max(0, max_sota))]
                    if len(tria) < 4:
                        # el club acaba trobant qui completi l'equip
                        reserva = [pj for pj in c["jug"]
                                   if pj[3] >= ordre_eq and pj[0] not in usats and pj[0] not in disp]
                        reserva.sort(key=lambda pj: -pj[1])
                        tria = tria + reserva[: 4 - len(tria)]
                        sense_quatre += 1
                    for pj in tria:
                        usats.add(pj[0])
                    tria.sort(key=lambda pj: -pj[1])
                    alin[idx_eq] = [pj[1] for pj in tria]
                    c_eq = cops[idx_eq]
                    for pj in tria:
                        c_eq[pj[0]] = c_eq.get(pj[0], 0) + 1
                    pt = per_taula[idx_eq]
                    for t, pj in enumerate(tria):
                        pt[t][pj[0]] = pt[t].get(pj[0], 0) + 1
                    clau = tuple(sorted(pj[0] for pj in tria))
                    cmb = combos[idx_eq]
                    cmb[clau] = cmb.get(clau, 0) + 1
                    repartiment.append((idx_eq, clau))
                if len(juguen) == len(c["equips"]):
                    cc = combos_club[c["nom"]]
                    k_club = tuple(repartiment)
                    cc[k_club] = cc.get(k_club, 0) + 1

            for k, ids in per_grup.items():
                if j >= len(cal[k]):
                    continue
                for il, iv in cal[k][j]:
                    loc, vis = ids[il], ids[iv]
                    ml = alin.get(loc) or []
                    mv = alin.get(vis) or []
                    a = b = 0
                    for t in range(4):
                        hi_l, hi_v = t < len(ml), t < len(mv)
                        if not hi_l and not hi_v:
                            continue
                        if not hi_l:
                            b += 2
                            continue
                        if not hi_v:
                            a += 2
                            continue
                        u = aleatori()
                        if u < P_TAULES:
                            a += 1
                            b += 1
                        else:
                            p = 1.0 / (1.0 + math.exp(
                                -(K_MITJANA * (ml[t] - mv[t]) + AVANTATGE_LOCAL)))
                            if u < P_TAULES + (1 - P_TAULES) * p:
                                a += 2
                            else:
                                b += 2
                    pp[loc] += a
                    pp[vis] += b
                    if a > b:
                        pm[loc] += 3
                    elif b > a:
                        pm[vis] += 3
                    else:
                        pm[loc] += 1
                        pm[vis] += 1

        for ids in per_grup.values():
            n = len(ids)
            for lloc, i in enumerate(sorted(ids, key=lambda i: (-pm[i], -pp[i]))):
                suma_pos[i] += lloc + 1
                if lloc == 0:
                    comptes[i][0] += 1
                elif lloc == 1:
                    comptes[i][1] += 1
                if lloc == n - 2:
                    comptes[i][2] += 1
                elif lloc == n - 1:
                    comptes[i][3] += 1

    if sense_quatre:
        print(f"nota: en un {sense_quatre / (n_sims * n_eq * 14) * 100:.1f}% dels encontres el club "
              f"ha hagut de completar l'equip amb algú de fora dels disponibles", file=sys.stderr)
    jugades = [len(juga[i]) or 1 for i in range(n_eq)]

    # el repartiment de club més freqüent mana; si un club no té mai tots els
    # equips jugant el mateix dia, cada equip es queda amb el seu mode
    del_club: dict[int, list[int]] = {}
    for cc in combos_club.values():
        if not cc:
            continue
        k_club, _ = max(cc.items(), key=lambda t: t[1])
        for idx_eq, clau in k_club:
            del_club[idx_eq] = list(clau)

    def _millor(i: int) -> tuple[list[int], float]:
        if not combos[i]:
            return [], 0.0
        nums = del_club.get(i)
        if nums is None:
            nums = list(max(combos[i].items(), key=lambda t: t[1])[0])
        n = combos[i].get(tuple(sorted(nums)), 0)
        return nums, round(n / (n_sims * jugades[i]), 3)

    def _taules(i: int, nums: list[int]) -> list[dict]:
        """Per a cada taula, el jugador de l'alineació modal i la probabilitat que
        hi jugui ell. Va ordenat per mitjana, que és com es formen les taules."""
        mit = {p["num"]: p["mitjana"] for p in per_club[equips[i]["club"]]["llista"]}
        ordenats = sorted(nums, key=lambda n: -mit.get(n, 0))
        total = n_sims * jugades[i]
        return [dict(num=n, taula=t + 1, p=round(per_taula[i][t].get(n, 0) / total, 3))
                for t, n in enumerate(ordenats)]

    return {
        (e["div"], e["seed"]): dict(
            alineacio=_millor(i)[0],
            p_alineacio=_millor(i)[1],
            taules=_taules(i, _millor(i)[0]),
            presencia=[
                dict(num=k, p=round(v / (n_sims * jugades[i]), 3))
                for k, v in sorted(cops[i].items(), key=lambda t: -t[1])
            ],
            p_1r=round(comptes[i][0] / n_sims, 4),
            p_2n=round(comptes[i][1] / n_sims, 4),
            p_penultim=round(comptes[i][2] / n_sims, 4),
            p_ultim=round(comptes[i][3] / n_sims, 4),
            pos_mitjana=round(suma_pos[i] / n_sims, 2),
        )
        for i, e in enumerate(equips)
    }


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


def banda_de(num: int, esquema: str = "fcb") -> str:
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
    # Presència: quina part de les jornades va jugar cadascú, mesurada sobre les
    # DUES últimes temporades. El denominador és sempre el de l'equip on va jugar
    # més aquella temporada —no el del club—, perquè els grups de 4a divisió tenen
    # més jornades que la resta. La temporada en curs pesa el doble que l'anterior:
    # qui acaba d'agafar la titularitat no ha d'arrossegar l'any que no jugava.
    TEMPORADES = ((1, 36, 2.0), (405, 34, 1.0))  # (temporada_id, lliga_id, pes)
    presencia: dict[int, list[tuple[float, float]]] = collections.defaultdict(list)
    for temp_id, lliga_id, pes in TEMPORADES:
        jorn: dict[int, int] = collections.Counter()
        for camp in ("equip_local_id", "equip_visitant_id"):
            for (eq,) in conn.execute(
                f"select {camp} from encontres_lliga where temporada_id=? and lliga_id=?",
                (temp_id, lliga_id),
            ):
                jorn[eq] += 1
        qp = """
        with p as (
         select g.equip1_id eq, g.player1_id pl from games g
           join encontres_lliga e on e.id=g.encontre_lliga_id
          where e.temporada_id=? and e.lliga_id=?
         union all
         select g.equip2_id, g.player2_id from games g
           join encontres_lliga e on e.id=g.encontre_lliga_id
          where e.temporada_id=? and e.lliga_id=?)
        select pl, eq, count(*) from p group by pl, eq"""
        per_jug: dict[int, list[tuple[int, int]]] = collections.defaultdict(list)
        for pid, eq, n in conn.execute(qp, (temp_id, lliga_id, temp_id, lliga_id)):
            per_jug[pid].append((eq, n))
        for pid, files in per_jug.items():
            total = sum(n for _, n in files)
            principal = max(files, key=lambda x: x[1])[0]
            ref = jorn.get(principal) or 14
            presencia[pid].append((min(1.0, total / ref), pes))

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
        # Presència: quina part de les jornades del club va jugar cadascú el 2025-26.
        # És l'ingredient que falta a les mitjanes — hi ha jugadors forts que amb
        # prou feines juguen— i serveix tant per marcar l'alineació habitual com
        # per no sobreestimar els equips que roden molt.
        def taxa_de(p: dict) -> float | None:
            files = presencia.get(p["pid"])
            if not files:
                return None
            return round(sum(r * w for r, w in files) / sum(w for _, w in files), 3)

        conegudes = [t for t in (taxa_de(p) for p in ranked) if t is not None]
        per_defecte = sorted(conegudes)[len(conegudes) // 2] if conegudes else 0.5
        llista = [dict(
            num=i, nom=p["nom"], mitjana=round(p["mitjana"], 4), pos=p["pos"],
            de_club=nom_club(p["de_club"]) if p["de_club"] else None, retorn=p["retorn"],
            pj=p["pj"], temporades=len(presencia.get(p["pid"], [])),
            taxa=(taxa_de(p) if taxa_de(p) is not None else per_defecte),
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

    # El pronòstic es fa amb TOTA la lliga alhora, no grup per grup: cal, perquè
    # un jugador no pot jugar la mateixa jornada amb dos equips del seu club.
    pron = simula_lliga(per_club, out["divisions"], N_SIMS)
    for div, dades in out["divisions"].items():
        for e in dades["equips"]:
            e.update(pron[(div, e["seed"])])
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
                b = banda_de(p["num"], esq)
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
