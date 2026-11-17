"""El que llegeixen les tres fonts, en una sola forma."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

AMBIT_ESPANYA = "espanya"
AMBIT_INTERNACIONAL = "internacional"

#: Les modalitats que es desen, amb el nom que fa servir la FCB. El 47/1 no es
#: juga a Catalunya però sí als Europeus. La resta de disciplines de la CEB i la
#: UMB (artístic, cinc quilles, pool, snooker) no són carambola o no es
#: comptabilitzen per caramboles i entrades.
MODALITATS = {
    "3B": "Tres bandes",
    "LLIURE": "Lliure",
    "47/2": "Quadre 47/2",
    "BANDA": "Banda",
    "71/2": "Quadre 71/2",
    "47/1": "Quadre 47/1",
}


def sense_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def modalitat_de(text: str) -> str | None:
    """«3-Cushion», «Cadre 47/2», «Tres Bandas», «Cuadro 71/2»… → clau de `MODALITATS`."""
    t = sense_accents(text).lower()
    if re.search(r"3[- ]?cushion|three[- ]cushion|tres bandas|3 ?bandas|\b3c\b|\b3b\b", t):
        return "3B"
    if re.search(r"1[- ]?cushion|one[- ]cushion|a la banda|\bbanda\b", t):
        return "BANDA"
    if re.search(r"free ?game|libre|lliure|straight rail", t):
        return "LLIURE"
    if re.search(r"47\s*/\s*2", t):
        return "47/2"
    if re.search(r"47\s*/\s*1", t):
        return "47/1"
    if re.search(r"71\s*/\s*2", t):
        return "71/2"
    return None


def tipus_de(nom: str) -> str | None:
    """Mundial, Europeu o Copa del Món, pel nom de l'esdeveniment. La resta, None.

    Els Grans Premis, les Copes d'Europa de clubs i els tornejos per invitació no
    hi entren: l'abast que es va demanar són campionats d'Espanya, Mundials,
    Europeus i Copes del Món.
    """
    t = sense_accents(nom).lower()
    if "world cup" in t or "coupe du monde" in t:
        return "copa_mon"
    if "world championship" in t or "championnat du monde" in t or "world games" in t:
        return "mundial"
    if "european championship" in t or "championnat d'europe" in t:
        return "europeu"
    return None


@dataclass
class Esdeveniment:
    font: str  # ceb | umb | rfeb
    id: str
    nom: str
    modalitat: str
    ambit: str
    tipus: str
    data_inici: date | None = None
    data_fi: date | None = None
    lloc: str = ""
    url: str = ""
    #: «2024-2025». Si no es diu, surt de `data_inici` (la temporada canvia l'1
    #: d'agost). Alguns PDF de la RFEB no porten dates i només la sabem per la
    #: carpeta on es van publicar.
    temporada: str = ""

    def __post_init__(self) -> None:
        if not self.temporada and self.data_inici is not None:
            d = self.data_inici
            any_ = d.year if d.month >= 8 else d.year - 1
            self.temporada = f"{any_}-{any_ + 1}"


@dataclass
class Partida:
    """Una partida, tal com la dona la font: els dos jugadors amb les seves xifres."""

    ordre: int
    jugador1: str
    jugador2: str
    caramboles1: int | None
    caramboles2: int | None
    entrades1: int | None
    entrades2: int | None
    serie1: int | None = None
    serie2: int | None = None
    punts1: int | None = None
    punts2: int | None = None
    data: date | None = None
    fase: str = ""
    grup: str = ""
    nacio1: str = ""
    nacio2: str = ""


@dataclass
class TotalJugador:
    """Els totals d'un jugador en un campionat, quan la font no en dona les partides."""

    posicio: int | None
    jugador: str
    federacio: str
    jugades: int | None
    guanyades: int | None
    empatades: int | None
    perdudes: int | None
    caramboles: int | None
    entrades: int | None
    serie: int | None = None


@dataclass
class Resultat:
    esdeveniment: Esdeveniment
    partides: list[Partida] = field(default_factory=list)
    totals: list[TotalJugador] = field(default_factory=list)
