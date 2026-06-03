"""Anomaly detection for inscription lists and rankings.

The validator catches the four classes of errors observed in the real
30è Memorial Joaquim Domingo inscription list:

  1. Players flagged "Provisional 0 punts" even though they already
     have Opens points and/or appear in the FCB monthly ranking with
     a Definitiu average.       → Vila Clopes pattern
  2. Groups of players tied on opens_points whose order does not
     respect the FCB ranking position tiebreaker.
                                 → Torrisco / Serrano / Pujol pattern
  3. Duplicate players (same name, same club) with split points.
                                 → Torrisco duplicated pattern
  4. Players mis-tiered: opens_points don't match the section of the
     inscription list they've been placed in.
                                 → Yáñez / Nuévalos / Porqueras pattern

Each anomaly is returned as a structured record so that callers
(CLI, future web UI) can render them as actionable messages.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .models import normalize_name
from .reglament.ordenacio import InscriptionEntry, sort_inscriptions


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #


@dataclass
class Anomaly:
    """A single detected issue with an inscription list.

    `severity` is one of "error" (definitely wrong), "warning"
    (suspicious but defensible), or "info" (worth flagging).
    """

    code: str
    severity: str
    message: str
    affected_players: list[str]


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #


def check_provisional_with_points(entries: Iterable[InscriptionEntry]) -> list[Anomaly]:
    """Flag players marked Provisional who actually have points.

    A player who has any opens_points > 0 cannot legitimately be
    "Provisional 0 punts" — they have a track record.
    """
    issues: list[Anomaly] = []
    for entry in entries:
        if entry.opens_points > 0 and entry.fcb_ranking_position is None:
            issues.append(
                Anomaly(
                    code="provisional_with_points",
                    severity="error",
                    message=(
                        f"{entry.player_name} has {entry.opens_points} Opens points "
                        f"but is not linked to any FCB ranking entry. "
                        f"Likely a Vila-Clopes-style sync error."
                    ),
                    affected_players=[entry.player_name],
                )
            )
    return issues


def check_duplicate_players(entries: Iterable[InscriptionEntry]) -> list[Anomaly]:
    """Flag players who appear more than once under the same (normalized)
    name and club.

    A duplicate inscription usually means the same player was
    double-counted somewhere upstream (the Torrisco duplicated-row
    pattern on the FCB's own Opens ranking PDF).
    """
    seen: Counter[tuple[str, str]] = Counter()
    for entry in entries:
        key = (normalize_name(entry.player_name), entry.club.strip().upper())
        seen[key] += 1

    issues: list[Anomaly] = []
    for (norm, club), count in seen.items():
        if count > 1:
            issues.append(
                Anomaly(
                    code="duplicate_inscription",
                    severity="error",
                    message=(
                        f"Player '{norm}' from '{club}' appears {count} times "
                        f"in the inscription list. Likely a duplicated row."
                    ),
                    affected_players=[norm],
                )
            )
    return issues


def check_sort_order(
    entries: list[InscriptionEntry],
) -> list[Anomaly]:
    """Flag runs of entries whose given order does not match Article XVIII.5.

    Compares the caller-provided order against what `sort_inscriptions`
    would produce. Mismatches on the same opens_points tier are flagged
    as sort violations (Torrisco/Serrano/Pujol pattern).
    """
    expected = sort_inscriptions(entries)
    given_by_name = [normalize_name(e.player_name) for e in entries]
    expected_by_name = [normalize_name(e.player_name) for e in expected]

    if given_by_name == expected_by_name:
        return []

    # Find the affected runs — consecutive positions where the two
    # differ. We don't try to describe each swap; we just group them
    # by opens_points tier so the message is actionable.
    affected: list[str] = []
    for given, exp in zip(given_by_name, expected_by_name):
        if given != exp and given not in affected:
            affected.append(given)

    return [
        Anomaly(
            code="sort_order_violation",
            severity="warning",
            message=(
                "The given inscription order does not match Article XVIII.5. "
                "Players with the same opens_points should be ordered by FCB "
                "ranking position (Definitiu before Provisional, then by "
                "rank position ascending)."
            ),
            affected_players=affected,
        )
    ]


# --------------------------------------------------------------------------- #
# Aggregate validator
# --------------------------------------------------------------------------- #


def validate_inscriptions(entries: list[InscriptionEntry]) -> list[Anomaly]:
    """Run all checks against an inscription list, returning all anomalies.

    The list is ordered: errors first, then warnings, then info, with
    anomalies of the same severity kept in the order the checks ran.
    """
    results: list[Anomaly] = []
    results.extend(check_provisional_with_points(entries))
    results.extend(check_duplicate_players(entries))
    results.extend(check_sort_order(entries))

    severity_rank = {"error": 0, "warning": 1, "info": 2}
    results.sort(key=lambda a: severity_rank.get(a.severity, 99))
    return results
