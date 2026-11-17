"""Campionats d'Espanya de la RFEB: la classificació final de cada campionat.

La RFEB no publica les partides d'un campionat d'Espanya. Publica un PDF de
classificació final (`res_ce_<modalitat>[_<categoria>].pdf`, i `res_gpe_…` per als
Grans Premis) amb els totals de cada jugador. Segons la modalitat i l'any, hi ha
partides jugades, guanyades, empatades i perdudes, caramboles, entrades,
mitjana i sèrie major:

    1 FF Carlos Anguita Díaz MUR 5 4 1 0 200 139 1,439 180
    1 Rubén Legazpi Martín Mad 5 5 0 0 200 114 1,754 11 180
    1 Raúl Cuenca Monrabal Val 1050 35 30,00 100

Fins al 2025 els PDF eren a `rfeb.org/noticiasAAAA/` i ara se'n recuperen les
còpies de Wayback Machine. La carpeta és la de la temporada en què es va
publicar la notícia, no la del campionat: l'any bo és el de la línia de lloc i
dates («CARTAGENA, DEL 18 AL 26 DE ENERO DE 2025»).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from fcbillar.externes.model import (
    AMBIT_ESPANYA,
    MODALITATS,
    Esdeveniment,
    Resultat,
    TotalJugador,
    modalitat_de,
    sense_accents,
)

_MESOS = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "SETIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}

#: Categoria segons el sufix del fitxer.
_CATEGORIES = {
    "fem": "femení",
    "s15": "sub-15",
    "s17": "sub-17",
    "s21": "sub-21",
    "s23": "sub-23",
    "s25": "sub-25",
    "inf": "infantil",
}

_MODALITAT_DEL_FITXER = {
    "3b": "3B",
    "banda": "BANDA",
    "47-2": "47/2",
    "c47-2": "47/2",
    "71-2": "71/2",
    "c71-2": "71/2",
    "libre": "LLIURE",
    "lib": "LLIURE",
}

_RE_RONDA = re.compile(r"^(FF|FP|F|Q|P+Q)(-\d+º?)?$")
_RE_DECIMAL = re.compile(r"^\d+,\d+$")
_RE_ENTER = re.compile(r"^\d+$")
_RE_LLOC = re.compile(
    r"^(?P<lloc>.+?),?\s+DEL?\s+(?P<dia>\d{1,2})\b.*?\bDE\s+(?P<mes>[A-ZÁÉÍÓÚ]+)\s+DE\s+(?P<any>\d{4})",
    re.IGNORECASE,
)


class SenseClassificacio(ValueError):
    """El PDF no té cap classificació final que es pugui llegir."""


def es_classificacio_final(nom_fitxer: str) -> bool:
    """`res_ce_3b.pdf` sí; `res_ce_3b_ff.pdf` (eliminatòries) i `_fp` (prèvia), no."""
    stem = Path(nom_fitxer).stem.lower()
    if not re.match(r"^res_(ce|gpe)_", stem):
        return False
    return not re.search(r"_(ff|fp|fc|q|r\d+\w*|\d+|2y1|prov|rep)$", stem)


def descriu_fitxer(nom_fitxer: str) -> tuple[str | None, str, str]:
    """(modalitat, categoria, tipus) que diu el nom del fitxer."""
    stem = Path(nom_fitxer).stem.lower()
    tipus = "gp_espanya" if stem.startswith("res_gpe") else "campionat_espanya"
    trossos = stem.split("_")[2:]
    modalitat = None
    categoria = ""
    for t in trossos:
        if modalitat is None and t in _MODALITAT_DEL_FITXER:
            modalitat = _MODALITAT_DEL_FITXER[t]
        elif t in _CATEGORIES:
            categoria = _CATEGORIES[t]
    if tipus == "gp_espanya" and modalitat is None and "3b" in stem:
        modalitat = "3B"
    return modalitat, categoria, tipus


def _lloc_i_data(linies: list[str]) -> tuple[str, date | None]:
    for linia in linies[:12]:
        m = _RE_LLOC.match(linia.strip())
        if m:
            mes = _MESOS.get(sense_accents(m.group("mes")).upper())
            if mes:
                try:
                    dia = date(int(m.group("any")), mes, int(m.group("dia")))
                except ValueError:
                    dia = date(int(m.group("any")), mes, 1)
                return m.group("lloc").strip().title(), dia
    return "", None


def _decimal(text: str) -> float:
    return float(text.replace(",", "."))


def llegeix_totals(text: str) -> list[TotalJugador]:
    """Els jugadors de la classificació final, amb els totals que porti el PDF."""
    totals: list[TotalJugador] = []
    amb_serie = False
    #: Les files només compten després de la capçalera de la classificació:
    #: els PDF de grups (juvenils) tenen línies que s'hi assemblen i no ho són.
    capcalera = False
    for linia in text.splitlines():
        linia = linia.strip()
        if re.search(r"\bNOMBRE\b", linia) and re.search(r"\bCAR", linia):
            amb_serie = bool(re.search(r"S\.?M\.?\b|\bSM\b", linia))
            capcalera = True
            continue
        if not capcalera:
            continue
        tokens = linia.split()
        if len(tokens) < 5 or not _RE_ENTER.match(tokens[0]):
            continue
        posicio = int(tokens[0])
        resta = tokens[1:]
        # «4 3 FF Marcos Morales…»: una posició compartida porta un segon número.
        if resta and _RE_ENTER.match(resta[0]):
            resta = resta[1:]
        if resta and _RE_RONDA.match(resta[0]):
            resta = resta[1:]
        i = 0
        while i < len(resta) and not (_RE_ENTER.match(resta[i]) or _RE_DECIMAL.match(resta[i])):
            i += 1
        if i < 2 or i == len(resta):
            continue
        noms, nums = resta[: i - 1], resta[i:]
        federacio = resta[i - 1]
        if not re.fullmatch(r"[A-Za-z]{2,5}", federacio):
            continue
        pos_prom = next((k for k, t in enumerate(nums) if _RE_DECIMAL.match(t)), None)
        if pos_prom is None or pos_prom < 2:
            continue
        abans = [int(t) for t in nums[:pos_prom]]
        caramboles, entrades = abans[-2], abans[-1]
        prom = _decimal(nums[pos_prom])
        if entrades <= 0 or abs(caramboles / entrades - prom) > 0.011 * max(1.0, prom):
            continue
        jugades = guanyades = empatades = perdudes = None
        if len(abans) >= 6:
            jugades, guanyades, empatades, perdudes = abans[-6:-2]
        serie = None
        if amb_serie and pos_prom + 1 < len(nums) and _RE_ENTER.match(nums[pos_prom + 1]):
            serie = int(nums[pos_prom + 1])
        totals.append(
            TotalJugador(
                posicio=posicio,
                jugador=" ".join(noms),
                federacio=federacio.upper(),
                jugades=jugades,
                guanyades=guanyades,
                empatades=empatades,
                perdudes=perdudes,
                caramboles=caramboles,
                entrades=entrades,
                serie=serie,
            )
        )
    return totals


def llegeix_classificacio(
    text: str, id_: str, nom_fitxer: str, url: str = "", temporada: str = ""
) -> Resultat:
    """El campionat i els totals de cada jugador d'un PDF `res_ce_*` o `res_gpe_*`.

    `temporada` és la de la carpeta on es va publicar: només mana si el PDF no
    porta la línia de lloc i dates.
    """
    modalitat, categoria, tipus = descriu_fitxer(nom_fitxer)
    linies = [linia for linia in text.splitlines() if linia.strip()]
    if modalitat is None:
        modalitat = modalitat_de(" ".join(linies[:4]))
    if modalitat is None:
        raise SenseClassificacio(f"{nom_fitxer}: no sé de quina modalitat és")
    totals = llegeix_totals(text)
    if not totals:
        raise SenseClassificacio(f"{nom_fitxer}: no hi ha cap jugador amb totals")
    lloc, dia = _lloc_i_data(linies)
    if tipus == "gp_espanya":
        nom = f"Gran Premi d'Espanya de {MODALITATS[modalitat].lower()}"
    else:
        nom = f"Campionat d'Espanya de {MODALITATS[modalitat].lower()}"
    if categoria:
        nom += f" {categoria}"
    if lloc:
        nom += f" · {lloc}"
    return Resultat(
        esdeveniment=Esdeveniment(
            font="rfeb",
            id=id_,
            nom=nom,
            modalitat=modalitat,
            ambit=AMBIT_ESPANYA,
            tipus=tipus,
            data_inici=dia,
            data_fi=dia,
            lloc=lloc,
            url=url,
            temporada="" if dia else temporada,
        ),
        totals=totals,
    )
