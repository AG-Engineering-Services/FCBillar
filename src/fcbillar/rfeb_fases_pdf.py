"""Partides dels PDF de fases de la web vella de la RFEB (`_fp`, `_ff`, `_q`).

Fins al 2018 la RFEB penjava, a més de la classificació final de cada
campionat, un PDF per fase (prèvia, final…) amb totes les partides. Del 2019 al
2024 encara hi ha el del Campionat d'Espanya per equips de jocs de sèrie
(`res_ce_jds_ff`).

El text d'aquests PDF surt barrejat: hi ha lletres girades al marge (l'hora i
el dia escrits en vertical) i, segons l'any, les entrades d'una partida van en
una línia a part. Per això no es llegeix cap columna: es busquen les línies de
jugador (`[taula] núm. NOM FED caramboles [entrades] mitjana [sèrie]`) i
s'aparellen de dues en dues dins de cada bloc. Les entrades, quan no hi són, es
treuen de les caramboles i la mitjana, i les dues línies de la partida n'han de
donar les mateixes. Un bloc amb un nombre senar de línies llegides es descarta
sencer: vol dir que n'hi ha una que no s'ha entès i aparellar la resta podria
casar jugadors de partides diferents.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from fcbillar.rfeb_fulls import PartidaFull

_FED = r"[A-Z][A-Za-z]{1,4}(?:[.\-][A-Za-z]{1,4})?"
_RE_JUGADOR = re.compile(
    r"^(?P<davant>(?:.*?\s)?)\d{1,3}\s+(?P<nom>[^\d,]+?)\s+(?P<fed>" + _FED + r")\s+(?:[PGE]\s+)?"
    r"(?:(?P<n1>\d{1,3})(?:\s+ENT)?(?:\s+(?P<n2>\d{1,3}))?\s+)?(?P<prom>\d{1,2},\d{3})"
    r"(?:\s+(?P<sm>\d{1,3}))?\s*$"
)
_RE_SOL = re.compile(r"^(?:\d{1,3}\s+)*\d{1,3}$")
_RE_CAPCALERA = re.compile(r"\bCAR\b.*\bPROM\b")
_RE_SERIE = re.compile(
    r"^(?P<mod>BANDA|LIBRE|CUADRO 47/2|CUADRO 71/2|CUADRO 47/1|TRES BANDAS)\s+"
    r"(?P<a>.+?)\s+(?P<ca>\d{1,3})\s+(?P<cb>\d{1,3})\s+(?P<b>.+?)\s+en\s+(?P<ent>\d{1,3})$"
)
_MODALITATS = {
    "BANDA": "banda",
    "LIBRE": "lliure",
    "CUADRO 47/2": "47_2",
    "CUADRO 71/2": "71_2",
    "CUADRO 47/1": "47_1",
    "TRES BANDAS": "3b",
}

#: Sufix del fitxer → fase.
FASES = {"_ff": "Fase final", "_fp": "Fase prèvia", "_q": "Classificació", "_pq": "Prèvia"}
_RE_SUFIX = re.compile(r"(_ff|_fp|_q|_pq)(?:_[a-z]+)?$")


def prova_i_fase(cami: Path) -> tuple[str, str] | None:
    """(`carpeta/fitxer` de la prova sense la fase, fase), o None si no és d'una fase."""
    m = _RE_SUFIX.search(cami.stem)
    if not m:
        return None
    return f"{cami.parent.name}/{cami.stem[: m.start()]}", FASES[m.group(1)]


@dataclass
class _Linia:
    nom: str
    fed: str
    numeros: tuple[int | None, int | None]
    mitjana: float
    serie: int | None
    solts: tuple[int, ...] = ()  # els números sols del bloc: caramboles o entrades


def _opcions(lin: _Linia) -> set[tuple[int, int]]:
    """Les (caramboles, entrades) que fan aquella mitjana."""
    n1, n2 = lin.numeros
    p = lin.mitjana
    out = set()

    def bo(car: int, ent: int) -> bool:
        return ent > 0 and car <= 400 and abs(round(car / ent, 3) - p) < 0.0011

    if n1 is not None and n2 is not None and bo(n1, n2):
        out.add((n1, n2))
    if p == 0:
        out.add((0, -1))  # sense carambola: les entrades les diu l'altre
        return out
    if n1 is None:
        # Els números van en línies a part: qualsevol que faci la mitjana.
        for x in lin.solts:
            if (ent := round(x / p)) and bo(x, ent):
                out.add((x, ent))
            if bo(car := round(x * p), x):
                out.add((car, x))
        return out
    if n2 is None:
        if (ent := round(n1 / p)) and bo(n1, ent):
            out.add((n1, ent))
        if bo(car := round(n1 * p), n1):
            out.add((car, n1))
    return out


def _aparella(a: _Linia, b: _Linia) -> tuple[int, int, int] | None:
    """(caramboles A, caramboles B, entrades) si les dues línies quadren."""
    trobats = set()
    for ca, ea in _opcions(a):
        for cb, eb in _opcions(b):
            if ea == eb or -1 in (ea, eb):
                ent = max(ea, eb)
                if ent > 0:
                    trobats.add((ca, cb, ent))
    return trobats.pop() if len(trobats) == 1 else None


def _linies_del_pdf(cami: Path) -> list[str]:
    import pdfplumber

    with pdfplumber.open(str(cami)) as pdf:
        return [
            li.strip()
            for p in pdf.pages
            for li in (p.extract_text() or "").split("\n")
            if li.strip()
        ]


def _parelles(linies: list[str], fase: str) -> tuple[list[PartidaFull], int]:
    """Partides i nombre de blocs descartats."""
    blocs: list[list[_Linia]] = [[]]
    solts: list[list[int]] = [[]]
    for text in linies:
        if _RE_CAPCALERA.search(text):
            blocs.append([])
            solts.append([])
            continue
        if _RE_SOL.match(text):
            solts[-1].extend(int(x) for x in text.split())
            continue
        if m := _RE_JUGADOR.match(text):
            solts[-1].extend(int(x) for x in re.findall(r"\d{1,3}", m.group("davant")))
            blocs[-1].append(
                _Linia(
                    nom=" ".join(m.group("nom").split()),
                    fed=m.group("fed").upper(),
                    numeros=(
                        int(m.group("n1")) if m.group("n1") else None,
                        int(m.group("n2")) if m.group("n2") else None,
                    ),
                    mitjana=float(m.group("prom").replace(",", ".")),
                    serie=int(m.group("sm")) if m.group("sm") else None,
                )
            )
    for bloc, sols in zip(blocs, solts, strict=True):
        for lin in bloc:
            lin.solts = tuple(sorted(set(sols)))
    partides, descartats = [], 0
    for bloc in blocs:
        if not bloc:
            continue
        if len(bloc) % 2:
            descartats += 1
            continue
        parells = [
            (bloc[k], bloc[k + 1], _aparella(bloc[k], bloc[k + 1])) for k in range(0, len(bloc), 2)
        ]
        if any(r is None for _, _, r in parells):
            descartats += 1
            continue
        for a, b, (ca, cb, ent) in parells:
            pa, pb = (2, 0) if ca > cb else (0, 2) if cb > ca else (1, 1)
            partides.append(
                PartidaFull(
                    fase=fase,
                    grup="",
                    ordre=len(partides) + 1,
                    jugador_a=a.nom,
                    caramboles_a=ca,
                    serie_a=a.serie if a.serie is None or a.serie <= ca else None,
                    jugador_b=b.nom,
                    caramboles_b=cb,
                    serie_b=b.serie if b.serie is None or b.serie <= cb else None,
                    entrades=ent,
                    punts_a=pa,
                    punts_b=pb,
                    # A les proves individuals, l'«equip» és la federació.
                    equip_a=a.fed,
                    equip_b=b.fed,
                )
            )
    return partides, descartats


def _jocs_de_serie(linies: list[str], fase: str) -> list[PartidaFull]:
    partides = []
    for text in linies:
        if not (m := _RE_SERIE.match(text)):
            continue
        ca, cb, ent = int(m.group("ca")), int(m.group("cb")), int(m.group("ent"))
        if ent < 1:
            continue
        pa, pb = (2, 0) if ca > cb else (0, 2) if cb > ca else (1, 1)
        partides.append(
            PartidaFull(
                fase=fase,
                grup="",
                ordre=len(partides) + 1,
                jugador_a=m.group("a"),
                caramboles_a=ca,
                serie_a=None,
                jugador_b=m.group("b"),
                caramboles_b=cb,
                serie_b=None,
                entrades=ent,
                punts_a=pa,
                punts_b=pb,
                modalitat=_MODALITATS[m.group("mod")],
            )
        )
    return partides


# ------------------------------------------- partides costat per costat (2012-2014)
#
# Els PDF de fases de banda i quadre del 2012 al 2014 posen dues partides una al
# costat de l'altra, sense federació:
#
#     CAR ENT PROM SM CAR ENT PROM SM
#     Esteve Mata 100 12,50 33 Carmelo Garcés 100 3,13 17
#     8 32
#     Salvador Lacarcel 39 4,88 16 José Luis Peláez 60 1,88 13
#
# La línia del mig són les entrades de cada partida. Al davant d'un nom hi pot
# haver text de la columna del costat («GRUPO 1», «CLASIFICACIÓN», la capçalera
# de la classificació): es treu.

_RE_TROS = re.compile(
    r"(?P<nom>[^\W\d_][^\W\d_.'\- ]*(?:[ .'\-]+[^\W\d_][^\W\d_.'\-]*)*)\s+"
    r"(?P<car>\d{1,3})\s+(?P<prom>\d{1,3},\d{1,3})(?:\s+(?P<sm>\d{1,3}))?(?=\s|$)"
)
_RE_ENTRADES = re.compile(r"^\d{1,3}(?:\s+\d{1,3})?$")
_SOROLL = {
    "grupo", "clasificacion", "nombre", "fed", "car", "ent", "prom", "ptos", "sm",
    "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo", "h", "fase",
}  # fmt: skip


def _sense_accent(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def _trossos(text: str) -> list[tuple[str, int, float, int | None]]:
    """Els (nom, caramboles, mitjana, sèrie) d'una línia de jugadors."""
    if re.search(r"\d+\s*º", text):
        return []  # una fila de classificació («1º Esteve Mata Cat 300 46 6,52 6»)
    out = []
    for m in _RE_TROS.finditer(text):
        paraules = m.group("nom").split()
        while paraules and (
            _sense_accent(paraules[0]).strip(".") in _SOROLL or len(paraules[0]) == 1
        ):
            paraules.pop(0)
        if not paraules:
            continue
        sm = int(m.group("sm")) if m.group("sm") else None
        out.append(
            (" ".join(paraules), int(m.group("car")), float(m.group("prom").replace(",", ".")), sm)
        )
    return out


def _quadra(car: int, ent: int, prom: float) -> bool:
    if ent <= 0:
        return False
    if car == 0:
        return prom == 0
    decimals = len(f"{prom}".split(".")[1]) if "." in f"{prom}" else 0
    return abs(car / ent - prom) <= 0.6 * 10 ** -max(decimals, 2) + 1e-9


def _costat_per_costat(linies: list[str], fase: str) -> tuple[list[PartidaFull], int]:
    partides: list[PartidaFull] = []
    descartats = 0
    i = 0
    while i + 2 < len(linies):
        dalt = _trossos(linies[i])
        mig = linies[i + 1].strip()
        if not dalt or not _RE_ENTRADES.match(mig):
            i += 1
            continue
        baix = _trossos(linies[i + 2])
        entrades = [int(x) for x in mig.split()]
        if not (len(dalt) == len(baix) == len(entrades)):
            descartats += 1
            i += 1
            continue
        for (na, ca, pa, sa), (nb, cb, pb, sb), ent in zip(dalt, baix, entrades, strict=True):
            if not (_quadra(ca, ent, pa) and _quadra(cb, ent, pb)):
                descartats += 1
                continue
            punts = (2, 0) if ca > cb else (0, 2) if cb > ca else (1, 1)
            partides.append(
                PartidaFull(
                    fase=fase,
                    grup="",
                    ordre=len(partides) + 1,
                    jugador_a=na,
                    caramboles_a=ca,
                    serie_a=sa if sa is None or sa <= ca else None,
                    jugador_b=nb,
                    caramboles_b=cb,
                    serie_b=sb if sb is None or sb <= cb else None,
                    entrades=ent,
                    punts_a=punts[0],
                    punts_b=punts[1],
                )
            )
        i += 3
    return partides, descartats


# ------------------------------------------------ una fila per jugador (2012-2019)
#
# Altres PDF posen cada jugador en una fila amb les caramboles, les entrades, la
# mitjana, la sèrie i els punts, i les dues files d'una partida una sota l'altra
# (a vegades amb l'hora, el billar i l'àrbitre entremig):
#
#     ESTEVE MATA 250 4 62,500 199 2 1
#     9:00 1 PERE LLUMÀ
#     MIQUEL PLANDOLIT 8 4 2,000 3 0 1
#
# o dues partides per línia, amb la federació:
#
#     Esteve Mata Cat 250 7 35,714 125 2 J. Albert Tornero Val 250 14 17,857 105 2
#     Jordi Garriga Cat 14 7 2 10 0 Joan Espinasa Cat 238 14 17 57 0
#
# Una fila només compta si les caramboles entre les entrades fan la mitjana, i
# una partida si les dues files tenen les mateixes entrades.

_RE_FILA = re.compile(
    r"(?P<nom>[^\W\d_][^\W\d_.'\- ]*(?:[ .'\-]+[^\W\d_][^\W\d_.'\-]*)*)\s+"
    r"(?:\d{2}/\d{2}/\d{2}\s+)?(?P<car>\d{1,3})\s+(?P<ent>\d{1,3})\s+(?P<prom>\d{1,3}(?:,\d{1,3})?)"
    r"(?:\s+(?P<sm>\d{1,3}))?\s+(?P<pts>[012])(?:\s+\d)?(?=\s|$)"
)


@dataclass
class _Fila:
    nom: str
    fed: str | None
    car: int
    ent: int
    sm: int | None


def _nom_i_fed(nom: str) -> tuple[str, str | None]:
    from fcbillar.rfeb_individuals import normalitza_fed

    paraules = nom.split()
    while paraules and _sense_accent(paraules[0]).strip(".") in _SOROLL:
        paraules.pop(0)
    fed = None
    if len(paraules) > 2 and len(paraules[-1]) <= 5 and (f := normalitza_fed(paraules[-1])):
        fed = f
        paraules.pop()
    nom = " ".join(paraules)
    if nom.isupper():
        nom = nom.title()
    return nom, fed


#: La mateixa fila amb la federació i els punts davant de les caramboles
#: (sub-17, sub-21 i sub-25 del 2014-15): `2 DAVID FIOL CAT 2 18 50 0,360 3`.
_RE_FILA_PUNTS_DAVANT = re.compile(
    r"(?P<nom>[^\W\d_][^\W\d_.'\- ]*(?:[ .'\-]+[^\W\d_][^\W\d_.'\-]*)*)\s+"
    r"(?P<pts>[012])\s+(?P<car>\d{1,3})\s+(?P<ent>\d{1,3})\s+(?P<prom>\d{1,3},\d{1,3})"
    r"(?:\s+(?P<sm>\d{1,3}))?(?=\s|$)"
)


def _files(text: str) -> list[_Fila]:
    if re.search(r"clasif", text, re.I):
        return []
    # Una fila de classificació al davant («… 0,670 5 1º»): només compta el que ve després.
    text = re.split(r"\d+\s*º", text)[-1]
    out = []
    trobades = list(_RE_FILA.finditer(text)) or list(_RE_FILA_PUNTS_DAVANT.finditer(text))
    for m in trobades:
        car, ent = int(m.group("car")), int(m.group("ent"))
        if not _quadra(car, ent, float(m.group("prom").replace(",", "."))):
            continue
        nom, fed = _nom_i_fed(m.group("nom"))
        if len(nom) < 4:
            continue
        sm = int(m.group("sm")) if m.group("sm") else None
        out.append(_Fila(nom, fed, car, ent, sm if sm is None or sm <= car else None))
    return out


def _fila_per_jugador(linies: list[str], fase: str) -> tuple[list[PartidaFull], int]:
    amb = [f for f in (_files(t) for t in linies) if f]
    partides: list[PartidaFull] = []
    descartats = 0
    i = 0
    while i + 1 < len(amb):
        dalt, baix = amb[i], amb[i + 1]
        if len(dalt) == len(baix) and all(a.ent == b.ent for a, b in zip(dalt, baix, strict=True)):
            for a, b in zip(dalt, baix, strict=True):
                punts = (2, 0) if a.car > b.car else (0, 2) if b.car > a.car else (1, 1)
                partides.append(
                    PartidaFull(
                        fase=fase,
                        grup="",
                        ordre=len(partides) + 1,
                        jugador_a=a.nom,
                        caramboles_a=a.car,
                        serie_a=a.sm,
                        jugador_b=b.nom,
                        caramboles_b=b.car,
                        serie_b=b.sm,
                        entrades=a.ent,
                        punts_a=punts[0],
                        punts_b=punts[1],
                        equip_a=a.fed,
                        equip_b=b.fed,
                    )
                )
            i += 2
        else:
            descartats += 1
            i += 1
    return partides, descartats


def llegeix_fase(cami: str | Path) -> tuple[list[PartidaFull], int]:
    """Les partides d'un PDF de fase i quants blocs no s'han pogut llegir."""
    cami = Path(cami)
    pf = prova_i_fase(cami)
    fase = pf[1] if pf else "Fase"
    linies = _linies_del_pdf(cami)
    if any("(cid:" in li for li in linies[:20]):
        return [], -1  # lletra codificada: no hi ha text per llegir
    if serie := _jocs_de_serie(linies, fase):
        return serie, 0
    amb_fed = _parelles(linies, fase)
    # Cada format només llegeix el seu: el que en treu més partides és el del PDF.
    lectures = [amb_fed, _costat_per_costat(linies, fase), _fila_per_jugador(linies, fase)]
    return max(lectures, key=lambda r: len(r[0]))


def desa_partides(conn: sqlite3.Connection, prova_id: str, partides: list[PartidaFull]) -> None:
    """Reemplaça les partides d'una prova que ja és a `rfeb_proves`."""
    comptes: dict[tuple[str, str], int] = {}
    for p in partides:
        clau = (p.fase, p.grup)
        comptes[clau] = comptes.get(clau, 0) + 1
        p.ordre = comptes[clau]
    conn.execute("DELETE FROM rfeb_partides WHERE prova_id = ?", (prova_id,))
    conn.executemany(
        "INSERT INTO rfeb_partides (prova_id, fase, grup, ordre, data, modalitat, jugador_a, "
        "equip_a, caramboles_a, serie_a, punts_a, jugador_b, equip_b, caramboles_b, serie_b, "
        "punts_b, entrades) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                prova_id,
                p.fase,
                p.grup,
                p.ordre,
                p.data.isoformat() if p.data else None,
                p.modalitat,
                p.jugador_a,
                p.equip_a,
                p.caramboles_a,
                p.serie_a,
                p.punts_a,
                p.jugador_b,
                p.equip_b,
                p.caramboles_b,
                p.serie_b,
                p.punts_b,
                p.entrades,
            )
            for p in partides
        ],
    )


@dataclass
class Resultat:
    fitxer: str
    prova_id: str | None
    partides: int
    descartats: int
    motiu: str = ""


def _mots(nom: str) -> tuple[str, ...]:
    pla = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode().upper()
    return tuple(w for w in re.split(r"[^A-Z]+", pla) if len(w) > 1)


def _cobertura(jugadors: set[tuple[str, ...]], classificats: set[tuple[str, ...]]) -> float:
    """Quina part dels jugadors d'una fase surt a una classificació.

    Els noms de les fases van sovint escurçats («ANTONIO MONTES»): un jugador hi
    és si les seves paraules són les primeres d'algun nom de la classificació.
    """
    if not jugadors:
        return 0.0
    hi_son = sum(any(c[: len(j)] == j for c in classificats) for j in jugadors)
    return hi_son / len(jugadors)


_MOTS_GENERICS = {"res", "resultados", "3b", "ff", "fp", "q", "pq", "gpe", "ce"}


def _prova_per_jugadors(
    cami: Path, partides: list[PartidaFull], classificats: dict[str, set[tuple[str, ...]]]
) -> str | None:
    """La classificació de la mateixa carpeta d'on és una fase amb un altre nom.

    Els mateixos jugadors d'elit ho juguen tot, i la cobertura sola separa poc
    dues proves de la mateixa temporada. Per això primer es miren les que
    comparteixen el lloc amb el nom del fitxer (`res_3b_madrid_ff` i
    `res_gpe_3b_madrid`), on n'hi ha prou amb el 60 % dels jugadors; si cap no
    el comparteix, cal el 75 % i deu punts per sobre de la segona.
    """
    jugadors = {_mots(p.jugador_a) for p in partides} | {_mots(p.jugador_b) for p in partides}
    carpeta = cami.parent.name + "/"
    mots_fitxer = set(cami.stem.lower().split("_"))
    llocs = mots_fitxer - _MOTS_GENERICS
    # Si el nom diu de quin tipus és («gpe», «ce»), només una prova del mateix
    # tipus. Sense això, la fase final del GPE de Múrcia 2012 anava a parar al
    # Campionat d'Espanya d'aquell any, que tenia gairebé els mateixos jugadors.
    tipus = mots_fitxer & {"gpe", "ce"}

    def del_tipus(pid: str) -> bool:
        return not tipus or bool(tipus & set(pid.split("/")[-1].lower().split("_")))

    cob = sorted(
        (
            (_cobertura(jugadors, cls), pid)
            for pid, cls in classificats.items()
            if pid.startswith(carpeta) and del_tipus(pid)
        ),
        reverse=True,
    )
    amb_lloc = [(c, pid) for c, pid in cob if llocs & set(pid.split("/")[-1].lower().split("_"))]
    if len(amb_lloc) == 1 and amb_lloc[0][0] >= 0.6:
        return amb_lloc[0][1]
    if (
        not amb_lloc
        and cob
        and cob[0][0] >= 0.75
        and (len(cob) == 1 or cob[1][0] <= cob[0][0] - 0.1)
    ):
        return cob[0][1]
    return None


#: El Campionat d'Espanya per equips de jocs de sèrie no té classificació
#: individual: la prova es crea amb el que diu la carpeta.
_JOCS_DE_SERIE = "res_ce_jds"


def carrega(conn: sqlite3.Connection, arrel: str | Path) -> list[Resultat]:
    """Llegeix els PDF de fase de `arrel` i en desa les partides a la seva prova.

    La prova és la classificació final de `rfeb_proves` amb el mateix nom de
    fitxer sense la fase. Quan no n'hi ha cap amb aquell nom (`res_3b_madrid_ff`
    és de `res_gpe_3b_madrid`), és la de la mateixa carpeta on surten almenys
    tres quarts dels jugadors de la fase, si n'hi ha una i només una. Les fases
    d'una mateixa prova s'ajunten i la reemplacen sencera.
    """
    from fcbillar.rfeb_individuals import temporada_de_carpeta

    proves = {r[0] for r in conn.execute("SELECT id FROM rfeb_proves")}
    classificats: dict[str, set[tuple[str, ...]]] = {}
    for prova, jugador in conn.execute("SELECT prova_id, jugador FROM rfeb_classificacions"):
        classificats.setdefault(prova, set()).add(_mots(jugador))
    resultats: list[Resultat] = []
    per_prova: dict[str, list[PartidaFull]] = {}
    for cami in sorted(Path(arrel).rglob("*.pdf")):
        pf = prova_i_fase(cami)
        if pf is None:
            continue
        nom = f"{cami.parent.name}/{cami.name}"
        try:
            partides, descartats = llegeix_fase(cami)
        except Exception as exc:
            resultats.append(Resultat(nom, None, 0, 0, f"illegible: {exc}"))
            continue
        prova = pf[0] if pf[0] in proves else None
        if prova is None and pf[0].endswith("/" + _JOCS_DE_SERIE) and partides:
            prova = pf[0]
            if prova not in proves:
                temporada = temporada_de_carpeta(cami.parent.name)
                conn.execute(
                    "INSERT OR REPLACE INTO rfeb_proves (id, temporada, modalitat, categoria, "
                    "tipus, titol, font) VALUES (?, ?, 'serie', 'absolut', 'equips', ?, ?)",
                    (
                        prova,
                        temporada,
                        f"Campeonato de España por Equipos de Juegos de Serie {temporada}",
                        f"https://rfeb.org/{cami.parent.name}/{cami.name}",
                    ),
                )
                proves.add(prova)
        if prova is None and partides:
            prova = _prova_per_jugadors(cami, partides, classificats)
        if prova is None:
            motiu = "sense partides" if not partides else "sense la prova a rfeb_proves"
            resultats.append(Resultat(nom, None, 0, max(descartats, 0), motiu))
            continue
        motiu = "lletra codificada" if descartats < 0 else "" if partides else "format desconegut"
        resultats.append(Resultat(nom, prova, len(partides), max(descartats, 0), motiu))
        per_prova.setdefault(prova, []).extend(partides)
    for prova, partides in per_prova.items():
        if partides:
            desa_partides(conn, prova, partides)
    return resultats
