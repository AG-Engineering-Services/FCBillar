"""Quins jugadors de la Lliga Nacional són a la fitxa del cens català.

La RFEB escriu «José Mª Mas Canadell» i la FCB «MAS CANADELL, JOSEP Mª», i no
hi ha cap identificador comú. Aquí només es proposen candidats: un lligam no
val fins que algú el marca com a validat a `fonts/nacional/fitxes.csv`.

Un candidat ha de tenir els DOS cognoms iguals i el mateix nom de pila, o el
seu equivalent català o castellà (Josep i José, Jordi i Jorge). Amb un sol
cognom no es proposa res.

El lligam només serveix perquè la fitxa del jugador ensenyi el seu apartat de
Lliga Nacional. No fa comptar cap partida de la Nacional per a cap rànquing ni
cap mitjana catalana.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

#: Cada grup és un mateix nom de pila en català i en castellà, i els
#: hipocorístics que la RFEB fa servir com a nom («Toni Ortiz Torrent»).
_EQUIVALENTS = [
    {"JOSEP", "JOSE", "PEP"},
    {"JORDI", "JORGE"},
    {"JOAN", "JUAN"},
    {"XAVIER", "JAVIER", "XAVI"},
    {"FRANCESC", "FRANCISCO", "PACO", "XESC"},
    {"PERE", "PEDRO"},
    {"ANTONI", "ANTONIO", "TONI"},
    {"MIQUEL", "MIGUEL"},
    {"LLUIS", "LUIS"},
    {"ENRIC", "ENRIQUE"},
    {"ALBERT", "ALBERTO"},
    {"CARLES", "CARLOS"},
    {"JAUME", "JAIME"},
    {"JOAQUIM", "JOAQUIN", "QUIM"},
    {"MANEL", "MANUEL", "MANOLO"},
    {"IGNASI", "IGNACIO"},
    {"NARCIS", "NARCISO"},
    {"MARTI", "MARTIN"},
    {"ANDREU", "ANDRES"},
    {"ESTEVE", "ESTEBAN"},
    {"VICENC", "VICENTE"},
    {"AGUSTI", "AGUSTIN"},
    {"SEBASTIA", "SEBASTIAN"},
    {"CRISTOFOL", "CRISTOBAL"},
    {"BARTOMEU", "BARTOLOME"},
    {"RAFEL", "RAFAEL"},
    {"MARC", "MARCOS"},
    {"PAU", "PABLO"},
    {"ISIDRE", "ISIDRO"},
    {"DOMENEC", "DOMINGO"},
    {"GERARD", "GERARDO"},
    {"FERRAN", "FERNANDO"},
    {"EDUARD", "EDUARDO"},
    {"RICARD", "RICARDO"},
    {"ALFONS", "ALFONSO"},
    {"LLORENC", "LORENZO"},
    {"BENET", "BENITO"},
    {"CLIMENT", "CLEMENTE"},
    {"VALENTI", "VALENTIN"},
    {"SERGI", "SERGIO"},
    {"JULIA", "JULIAN"},
    {"FELIP", "FELIPE"},
    {"GUILLEM", "GUILLERMO"},
    {"NICOLAU", "NICOLAS"},
    {"ADRIA", "ADRIAN"},
    {"ALEIX", "ALEJO"},
    {"ALEXANDRE", "ALEJANDRO"},
    {"EMILI", "EMILIO"},
    {"RAIMON", "RAIMUNDO"},
    {"ANNA", "ANA"},
    {"MONTSERRAT", "MONTSE"},
    {"MERCE", "MERCEDES"},
    {"DOLORS", "DOLORES"},
    {"ROSER", "ROSARIO"},
    {"CARME", "CARMEN"},
    {"ELISABET", "ISABEL"},
    {"ASSUMPCIO", "ASUNCION"},
    {"CONCEPCIO", "CONCEPCION"},
]
_GRUP = {nom: i for i, grup in enumerate(_EQUIVALENTS) for nom in grup}

#: «Mª», «M.ª», «Mª.» i «Ma.» volen dir Maria.
_RE_MARIA = re.compile(r"^M\.?[ªA]\.?$")


@dataclass(frozen=True)
class JugadorRfeb:
    nom: str
    equip: str
    divisio: str


@dataclass(frozen=True)
class JugadorCens:
    fcb_id: str
    nom: str  # «COGNOM1 COGNOM2, NOM»
    club: str


@dataclass(frozen=True)
class Candidat:
    rfeb: JugadorRfeb
    cens: JugadorCens
    #: Per què es proposa: «exacte», «abreujat», «falta» o «un cognom».
    motiu: str = "exacte"


#: Com abreuja la RFEB els cognoms més corrents («Jorge J. Sánchez Fdez.»).
_ABREUJATS = {
    "FDEZ": "FERNANDEZ",
    "FERNDEZ": "FERNANDEZ",
    "FDZ": "FERNANDEZ",
    "RGUEZ": "RODRIGUEZ",
    "RODGUEZ": "RODRIGUEZ",
    "RDGUEZ": "RODRIGUEZ",
    "RODZ": "RODRIGUEZ",
    "GLEZ": "GONZALEZ",
    "GZLEZ": "GONZALEZ",
    "GONZ": "GONZALEZ",
    "MTEZ": "MARTINEZ",
    "MTNEZ": "MARTINEZ",
    "MNEZ": "MARTINEZ",
    "HDEZ": "HERNANDEZ",
    "HDZ": "HERNANDEZ",
    "HERNDEZ": "HERNANDEZ",
    "DGUEZ": "DOMINGUEZ",
    "DOMGUEZ": "DOMINGUEZ",
    "JMNEZ": "JIMENEZ",
    "GA": "GARCIA",  # «Gª»
}


def _mots(text: str) -> list[str]:
    mots = []
    for mot in text.replace("-", " ").split():
        if _RE_MARIA.match(mot.upper()):
            mots.append("MARIA")
            continue
        net = unicodedata.normalize("NFKD", mot).encode("ascii", "ignore").decode().upper()
        inicial = net.endswith(".") and len(net.rstrip(".")) == 1
        net = re.sub(r"[^A-Z]", "", net)
        if net:
            mots.append(net + "." if inicial else net)
    return mots


def _mateix_nom(a: str, b: str) -> bool:
    if a.endswith(".") or b.endswith("."):
        return a[0] == b[0]
    return a == b or (a in _GRUP and _GRUP.get(b) == _GRUP[a])


def _noms_compatibles(rfeb: list[str], cens: list[str]) -> bool:
    if not rfeb or not cens or rfeb[0].endswith(".") or cens[0].endswith("."):
        return False
    # El primer nom ha de coincidir; els següents, només si tots dos en tenen.
    return all(_mateix_nom(a, b) for a, b in zip(rfeb, cens, strict=False))


def _una_lletra(a: str, b: str) -> bool:
    """Si `a` i `b` es diferencien en una lletra canviada, de més o de menys."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) <= 1
    curt, llarg = sorted((a, b), key=len)
    return any(llarg[:i] + llarg[i + 1 :] == curt for i in range(len(llarg)))


def _cognoms_casen(rfeb: tuple[str, ...], cens: tuple[str, ...]) -> str | None:
    """«exacte», «abreujat», «falta» o `None` si els cognoms no són els mateixos."""
    if rfeb == cens:
        return "exacte"
    if len(rfeb) != len(cens):
        return None
    desplegats = tuple(_ABREUJATS.get(m, m) for m in rfeb)
    if desplegats == cens:
        return "abreujat"
    # Una sola lletra en un sol cognom, i només en cognoms prou llargs perquè
    # una lletra no en faci un altre de corrent («Gil» i «Gilí»).
    diferents = [(a, b) for a, b in zip(desplegats, cens, strict=True) if a != b]
    if len(diferents) == 1 and min(map(len, diferents[0])) >= 5 and _una_lletra(*diferents[0]):
        return "falta"
    return None


def candidats(rfeb: list[JugadorRfeb], cens: list[JugadorCens]) -> list[Candidat]:
    """Parelles (RFEB, cens) que poden ser el mateix jugador, amb el motiu.

    La base és el nom de pila (en català o castellà) i els dos cognoms. La RFEB,
    però, escriu el mateix jugador de moltes maneres, i també es proposen:
    cognoms abreujats («Fdez.»), una lletra de diferència en un cognom, i un sol
    cognom quan al cens no hi ha cap altre jugador amb aquell nom i aquell
    primer cognom. Tot passa per la validació a mà.
    """
    fitxes: list[tuple[tuple[str, ...], list[str], JugadorCens]] = []
    for c in cens:
        cognoms, _, noms = c.nom.partition(",")
        mots_cognoms = tuple(_mots(cognoms))
        if len(mots_cognoms) >= 2 and noms.strip():
            fitxes.append((mots_cognoms, _mots(noms), c))

    out = []
    for r in rfeb:
        mots = _mots(r.nom)
        trobats = []
        for cognoms, noms, c in fitxes:
            n = len(cognoms)
            if len(mots) <= n or not _noms_compatibles(mots[:-n], noms):
                continue
            if motiu := _cognoms_casen(tuple(mots[-n:]), cognoms):
                trobats.append(Candidat(rfeb=r, cens=c, motiu=motiu))
        if not trobats and len(mots) >= 2:
            # «Sergio Martínez»: un sol cognom. Només si és inequívoc al cens.
            cognom = _ABREUJATS.get(mots[-1], mots[-1])
            possibles = [
                c
                for cognoms, noms, c in fitxes
                if cognoms[0] == cognom
                # Si no, «Juan Pérez López» seria «Juan Pérez» de nom i «López».
                and len(mots) - 1 <= len(noms)
                and _noms_compatibles(mots[:-1], noms)
            ]
            if len(possibles) == 1:
                trobats.append(Candidat(rfeb=r, cens=possibles[0], motiu="un cognom"))
        out.extend(trobats)
    return out


# --------------------------- el fitxer de validació ---------------------------

CAMPS = [
    "validat",
    "jugador_rfeb",
    "equip_rfeb",
    "divisio",
    "fcb_id",
    "nom_cens",
    "club_cens",
    "motiu",
]


def escriu_candidats(trobats: list[Candidat], cami: str | Path) -> tuple[int, int]:
    """Afegeix al CSV els candidats nous i hi deixa intactes els que ja hi són.

    `validat` queda buit fins que algú hi posa «si» o «no». Retorna quants n'hi
    havia i quants s'hi han afegit.
    """
    cami = Path(cami)
    files = []
    if cami.exists():
        with cami.open(encoding="utf-8", newline="") as f:
            files = list(csv.DictReader(f))
    vistos = {(f["jugador_rfeb"], f["fcb_id"]) for f in files}
    nous = 0
    for c in trobats:
        if (c.rfeb.nom, c.cens.fcb_id) in vistos:
            continue
        vistos.add((c.rfeb.nom, c.cens.fcb_id))
        files.append(
            {
                "validat": "",
                "jugador_rfeb": c.rfeb.nom,
                "equip_rfeb": c.rfeb.equip,
                "divisio": c.rfeb.divisio,
                "fcb_id": c.cens.fcb_id,
                "nom_cens": c.cens.nom,
                "club_cens": c.cens.club,
                "motiu": c.motiu,
            }
        )
        nous += 1
    files.sort(key=lambda f: (f["validat"] != "", f["jugador_rfeb"]))
    cami.parent.mkdir(parents=True, exist_ok=True)
    with cami.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPS, restval="")
        w.writeheader()
        w.writerows(files)
    return len(files) - nous, nous


def lligams_validats(cami: str | Path, divisio: str | None = None) -> dict[str, str]:
    """`{nom a la font: fcb_id}` dels lligams marcats amb «si».

    Amb `divisio`, només els validats per a aquella divisió (p. ex. «palmares-fcb»).
    """
    cami = Path(cami)
    if not cami.exists():
        return {}
    with cami.open(encoding="utf-8", newline="") as f:
        return {
            r["jugador_rfeb"]: r["fcb_id"]
            for r in csv.DictReader(f)
            if r["validat"].strip().lower() == "si" and (divisio is None or r["divisio"] == divisio)
        }
