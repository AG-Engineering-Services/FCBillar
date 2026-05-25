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
    extras: dict = field(default_factory=dict)

    @property
    def id_natural(self) -> str:
        # Ordenem els ids dels jugadors perquè la mateixa partida vista des dels
        # dos jugadors produeixi el mateix hash.
        a, b = sorted([self.player1_fcb_id, self.player2_fcb_id])
        key = "|".join(
            [
                self.data_partida.isoformat(),
                self.competicio_nom.strip().lower(),
                str(self.modalitat_codi_fcb),
                a,
                b,
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
