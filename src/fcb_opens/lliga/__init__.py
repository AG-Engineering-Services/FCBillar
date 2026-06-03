"""League (Lliga) feature: scraping, persistence and KPIs for the
FCB Catalan Three-Cushion League.

Hierarchy mirrored from fcbillar.cat:

    Lliga (competition_id, e.g. 36)
      └── Division (e.g. 149 = 1a Divisió)
            └── Group (e.g. 318 = Grup A)
                  ├── TeamStanding (PM/PP/J)
                  └── Jornada (matchday)
                        └── Encontre (team vs team)
                              └── Partida (player vs player)
"""

from .models import (
    Division,
    Encontre,
    Group,
    Jornada,
    LeagueSnapshot,
    Partida,
    TeamStanding,
)

__all__ = [
    "Division",
    "Encontre",
    "Group",
    "Jornada",
    "LeagueSnapshot",
    "Partida",
    "TeamStanding",
]
