"""Dataclasses for the Lliga (league) feature.

All structures are plain dataclasses to mirror the package style. The
hierarchy follows the FCB site:

    competition (e.g. 36 = Lliga Catalana Tres Bandes)
      └── division (e.g. 149 = 1a Divisió)
            └── group (e.g. 318 = Grup A)
                  ├── team_standings (computed by FCB)
                  └── jornada (matchday)
                        └── encontre (team vs team)
                              └── partida (player vs player)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Division:
    """A division within a league competition (e.g. "1a DIVISIÓ")."""

    fcb_division_id: int  # 148-152 for Tres Bandes
    name: str  # "1a DIVISIÓ"


@dataclass(frozen=True)
class Group:
    """A group within a division (e.g. "GRUP A")."""

    fcb_group_id: int  # 318, 319 …
    fcb_division_id: int
    name: str  # "GRUP A"


@dataclass
class TeamStanding:
    """One row of the FCB team-standings table for a group.

    Columns visible on the FCB classificacio page:
        Posició, Equip, PM (punts de match), PP (punts parcials), J (jornades)
    """

    position: int
    team_name: str
    match_points: int  # PM
    set_points: int    # PP
    matches_played: int  # J


@dataclass
class Jornada:
    """A matchday within a group."""

    fcb_jornada_id: int  # e.g. 2621
    fcb_group_id: int
    number: int          # 1..14
    played_on: str       # ISO YYYY-MM-DD; FCB usually publishes a date


@dataclass
class Partida:
    """An individual player-vs-player match within an encontre.

    All counters are 0 if the match has not been played yet.
    """

    slot: int  # ordinal within the encontre (1..n)
    home_player_name: str
    home_caramboles: int
    home_serie_major: int
    home_punts: int
    away_player_name: str
    away_caramboles: int
    away_serie_major: int
    away_punts: int
    entrades: int
    arbitre: str | None
    attendance: str | None  # "Partit disputat", "Pendent", …
    modalitat: str | None
    is_played: bool


@dataclass
class Encontre:
    """A team-vs-team encounter (one cell of a jornada)."""

    fcb_encontre_id: int
    fcb_jornada_id: int
    home_team_name: str
    away_team_name: str
    home_match_points: int  # P.Match (0..3 typically)
    away_match_points: int
    home_set_points: int    # P.Parcials
    away_set_points: int
    partides: list[Partida] = field(default_factory=list)


@dataclass
class LeagueSnapshot:
    """Result of a full scrape of a competition (e.g. 36).

    `divisions[i].groups[j].standings` and `.jornades[k].encontres[l]
    .partides[m]` form the full tree.
    """

    competition_id: int
    season: str
    name: str  # "LLIGA CATALANA TRES BANDES"
    divisions: list[DivisionSnapshot] = field(default_factory=list)


@dataclass
class GroupSnapshot:
    group: Group
    standings: list[TeamStanding] = field(default_factory=list)
    jornades: list[JornadaSnapshot] = field(default_factory=list)


@dataclass
class JornadaSnapshot:
    jornada: Jornada
    encontres: list[Encontre] = field(default_factory=list)


@dataclass
class DivisionSnapshot:
    division: Division
    groups: list[GroupSnapshot] = field(default_factory=list)
