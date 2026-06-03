"""Article XVIII.5: ordering of inscribed players for an Open.

The reglament specifies two criteria for sorting sign-up lists:

  (a) Punts d'Opens (descending).
  (b) Position in the last FCB Tres Bandes monthly ranking at the time
      of the Open's convocatòria, with Definitiu players before
      Provisional players. The FCB monthly ranking is itself ordered by
      mitjana general, so using its position as the tiebreaker
      automatically handles mitjana ordering.

A player may be on an inscription list without appearing in either the
Opens ranking (if they've never scored Open points) or the monthly FCB
ranking (if they're a brand-new federated player). These cases are
handled by placing such players at the end, ordered among themselves by
whatever information is available.

This module is intentionally free of any FCB-specific I/O: it operates
on plain `InscriptionEntry` records, so it can be unit-tested without
touching the scrapers or the database.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InscriptionEntry:
    """One player on an Open sign-up list, enriched with ranking context.

    Attributes:
        player_name: display name as it should appear on group lists.
        club: club affiliation at the time of inscription.
        opens_points: points in the Rànquing Català d'Opens at the
            moment of convocatòria publication (0 if the player has
            never scored).
        fcb_ranking_position: position in the latest FCB monthly Tres
            Bandes ranking (1-indexed). None if the player is not in
            that ranking yet.
        fcb_ranking_is_definitive: True if Definitiu, False if
            Provisional. Only meaningful when
            `fcb_ranking_position` is not None.
        fcb_ranking_average: the mitjana general from the FCB ranking,
            used only as a last-resort tiebreaker and for informational
            display.
    """

    player_name: str
    club: str
    opens_points: int = 0
    fcb_ranking_position: int | None = None
    fcb_ranking_is_definitive: bool = False
    fcb_ranking_average: float = 0.0


def sort_inscriptions(entries: list[InscriptionEntry]) -> list[InscriptionEntry]:
    """Sort inscription entries following Article XVIII.5.

    Sort key (in order of priority):

      1. opens_points (descending)
      2. ranking tier: Definitiu < Provisional < not ranked
      3. fcb_ranking_position (ascending, lower is better)
      4. fcb_ranking_average (descending) — defensive fallback for
         identical positions, should never trigger in practice

    Returns a new list; the input is not mutated.
    """

    def sort_key(entry: InscriptionEntry) -> tuple[int, int, float, float]:
        if entry.fcb_ranking_position is None:
            tier = 2  # not ranked
            position = float("inf")
        elif entry.fcb_ranking_is_definitive:
            tier = 0  # Definitiu
            position = float(entry.fcb_ranking_position)
        else:
            tier = 1  # Provisional
            position = float(entry.fcb_ranking_position)

        return (
            -entry.opens_points,   # higher points first
            tier,                  # Definitiu first
            position,              # lower rank first
            -entry.fcb_ranking_average,  # higher mitjana first (defensive)
        )

    return sorted(entries, key=sort_key)
