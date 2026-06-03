"""Models de domini (dataclasses)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class Club:
    fcb_id: str
    nom: str


@dataclass(frozen=True, slots=True)
class Player:
    fcb_id: str  # id intern del portal (numèric, p.ex. "566"), únic per jugador
    nom: str
    club_fcb_id: str | None = None
    seguiment: bool = False


@dataclass(frozen=True, slots=True)
class Modalitat:
    codi_fcb: int  # id que apareix a la URL del rànquing
    nom: str


@dataclass(frozen=True, slots=True)
class Competicio:
    nom: str
    temporada: str | None = None
    modalitat_codi_fcb: int | None = None


@dataclass(frozen=True, slots=True)
class Ranking:
    num_seq: int
    modalitat_codi_fcb: int
    url: str
    format_url: str  # "data" | "datahome"
    any_pub: int | None = None
    mes_pub: int | None = None
    scraped_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RankingEntry:
    ranking_num_seq: int
    ranking_modalitat: int
    player_fcb_id: str
    posicio: int | None = None
    mitjana_general: float | None = None
    mitjana_particular: float | None = None
    partides: int | None = None
    extras: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Game:
    """Partida individual entre dos jugadors.

    L'`id_natural` permet deduplicació automàtica: la mateixa partida apareix
    a tots dos jugadors i pot aparèixer en més d'un rànquing mensual consecutiu.
    """

    data_partida: date
    competicio_nom: str
    modalitat_codi_fcb: int
    player1_fcb_id: str
    player2_fcb_id: str
    caramboles1: int | None = None
    caramboles2: int | None = None
    entrades: int | None = None
    mitjana1: float | None = None
    mitjana2: float | None = None
    serie_max1: int | None = None
    serie_max2: int | None = None
    guanyador_fcb_id: str | None = None
    # Camps que provenen de pàgines de lliga (no apareixen a partideshome).
    arbitre: str | None = None
    assistencia: str | None = None
    # IDs interns ja resolts pel pipeline (NULL si vénen de partideshome).
    equip1_id: int | None = None
    equip2_id: int | None = None
    encontre_lliga_id: int | None = None
    temporada_id: int | None = None
    extras: dict = field(default_factory=dict)

    @property
    def id_natural(self) -> str:
        # Ordenem els ids dels jugadors perquè la mateixa partida vista des dels
        # dos jugadors produeixi el mateix hash. Incloem el resultat (caramboles
        # alineades als jugadors ordenats + entrades) perquè dos enfrontaments
        # el mateix dia/competició entre els mateixos jugadors (p.ex. anada i
        # tornada quan en un grup de tres un no es presenta) NO es fusionin.
        # El resultat és simètric respecte de qui mira la partida: a partideshome
        # la fila és sempre el fixture real (local/visitant fixos), així que la
        # deduplicació entre jugadors i entre rànquings consecutius es manté.
        a, b = sorted([self.player1_fcb_id, self.player2_fcb_id])
        if a == self.player1_fcb_id:
            car_a, car_b = self.caramboles1, self.caramboles2
        else:
            car_a, car_b = self.caramboles2, self.caramboles1
        key = "|".join(
            [
                self.data_partida.isoformat(),
                self.competicio_nom.strip().lower(),
                str(self.modalitat_codi_fcb),
                a,
                b,
                "" if car_a is None else str(car_a),
                "" if car_b is None else str(car_b),
                "" if self.entrades is None else str(self.entrades),
            ]
        )
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True, slots=True)
class RankingGameLink:
    """Traçabilitat: en quin rànquing va aparèixer una partida, vista des de quin jugador."""

    ranking_num_seq: int
    ranking_modalitat: int
    game_id: str
    player_fcb_id_origen: str


# ---------- entitats de lliga catalana (schema v2) ----------


@dataclass(frozen=True, slots=True)
class Temporada:
    nom: str  # p.ex. "2025-2026"


@dataclass(frozen=True, slots=True)
class Equip:
    """Un equip d'un club a una competició; identificat per (club, lletra)."""

    club_fcb_id: str
    lletra: str  # "A", "B", "C", "UNICO", ...


@dataclass(frozen=True, slots=True)
class TorneigIndividualRecord:
    """Un torneig individual a la BD (id extern + divisió + temporada)."""

    torneig_id_extern: int
    divisio_id_extern: int
    nom: str
    modalitat_codi_fcb: int | None = None
    temporada_nom: str | None = None


@dataclass(frozen=True, slots=True)
class TorneigParticipantRecord:
    """Una entrada de participant a la classificació d'un torneig."""

    torneig_id_extern: int
    divisio_id_extern: int
    player_fcb_id: str
    posicio: int | None = None
    partides_jugades: int | None = None
    punts: int | None = None
    caramboles: int | None = None
    entrades: int | None = None
    mitjana_general: float | None = None
    mitjana_particular: float | None = None
    serie_max: int | None = None
    club_text: str | None = None


@dataclass(frozen=True, slots=True)
class EncontreLliga:
    """Un encontre equip-vs-equip d'una jornada de lliga."""

    lliga_id: int
    divisio_id: int
    grup_id: int
    jornada_id: int
    encontre_id_extern: int
    equip_local: Equip
    equip_visitant: Equip
    data: date | None = None
    temporada_nom: str | None = None
    p_parcials_local: int | None = None
    p_match_local: int | None = None
    p_parcials_visitant: int | None = None
    p_match_visitant: int | None = None
