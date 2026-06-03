"""Article XVIII.1-2: compute the Rànquing Català d'Opens from stored Opens.

The ranking sums the points a player earned in the 5 most recently
disputed Opens (globally, not per player). When a 6th Open is played,
the oldest of the 5 is dropped.

A player who did not play one of those 5 Opens simply contributes 0 to
their sum for that Open. A player who never played any of the 5 is
absent from the output entirely.

Tiebreaks specified in the FCB-published Opens ranking PDF are:

  1. Total points (descending).
  2. Highest single-Open points among the ranking's Opens (descending).
  3. Mitjana in the Rànquing Català at the moment the last Open closed
     (descending).

The spec says "la mitjana al ranquing català que hi hagi al moment
d'acabar l'Open". We don't store exact Open dates, only the season, so
tiebreak #3 uses the most recent monthly ranking available in the DB
as an approximation. If a player is missing from that ranking, we fall
back to any earlier ranking where they appear; if they appear nowhere,
their mitjana defaults to 0.0 and they sort last among tied players.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class OpenBreakdown:
    open_id: int
    fcb_division_id: int
    name: str
    season: str
    points: int | None


@dataclass
class OpensRankingEntry:
    """One row of the computed Rànquing Català d'Opens."""

    player_id: int
    display_name: str
    club: str | None
    total_points: int
    max_single_open: int  # used for tiebreak #2
    opens_played: int  # informational: how many of the window the player entered
    breakdown: list[OpenBreakdown]


@dataclass(frozen=True)
class OpenWindowOpen:
    open_id: int
    fcb_division_id: int
    name: str
    season: str


def get_window_opens(
    conn: sqlite3.Connection,
    num_recent_opens: int = 5,
    as_of_division_id: int | None = None,
) -> list[OpenWindowOpen]:
    params: list[object] = []
    where_clause = ""
    if as_of_division_id is not None:
        where_clause = "WHERE fcb_division_id <= ?"
        params.append(as_of_division_id)

    rows = conn.execute(
        f"""
        SELECT id, fcb_division_id, name, season
        FROM opens
        {where_clause}
        ORDER BY fcb_division_id DESC
        LIMIT ?
        """,
        [*params, num_recent_opens],
    ).fetchall()

    return [
        OpenWindowOpen(
            open_id=row["id"],
            fcb_division_id=row["fcb_division_id"],
            name=row["name"],
            season=row["season"],
        )
        for row in reversed(rows)
    ]


def load_player_fcb_averages(conn: sqlite3.Connection) -> dict[int, float]:
    """Return {player_id: mitjana} from the most recent monthly ranking
    available, falling back to older rankings for players missing from it.

    This implements tiebreak #3 for Article XVIII. The FCB-published rule
    asks for the mitjana at the moment the last Open closed; since we
    don't store Open dates, we approximate with the latest monthly ranking
    in the DB. Players missing everywhere get 0.0 and sort last.
    """
    rows = conn.execute(
        """
        SELECT mre.player_id AS player_id, mre.average AS average
        FROM monthly_ranking_entries mre
        JOIN monthly_rankings mr ON mr.id = mre.ranking_id
        ORDER BY mr.month_id DESC
        """
    ).fetchall()

    averages: dict[int, float] = {}
    for row in rows:
        pid = int(row["player_id"])
        if pid in averages:
            continue
        averages[pid] = float(row["average"])
    return averages


def compute_opens_ranking(
    conn: sqlite3.Connection,
    num_recent_opens: int = 5,
    as_of_division_id: int | None = None,
) -> list[OpensRankingEntry]:
    """Return players ranked by accumulated Open points.

    Uses `fcb_division_id` as a chronology proxy — the FCB assigns
    division ids monotonically, so the N largest ids are the N most
    recently disputed Opens. A future refinement could switch to an
    explicit `played_at` column.

    Args:
        conn: active SQLite connection with stored Opens.
        num_recent_opens: window size for the ranking (5 per Article XVIII.1).
        as_of_division_id: if set, only consider Opens with
            fcb_division_id <= this value. Used to reconstruct the
            ranking as it stood at a past moment.

    Returns:
        List of OpensRankingEntry sorted by total_points descending,
        then by max_single_open descending (tiebreak), then by name
        as a stable fallback. Players with 0 total points are excluded.
    """
    window_opens = get_window_opens(
        conn,
        num_recent_opens=num_recent_opens,
        as_of_division_id=as_of_division_id,
    )

    if not window_opens:
        return []

    fcb_averages = load_player_fcb_averages(conn)

    open_ids = [op.open_id for op in window_opens]
    placeholders = ",".join("?" * len(open_ids))

    rows = conn.execute(
        f"""
        SELECT
            p.id              AS player_id,
            p.display_name    AS display_name,
            p.current_club    AS current_club,
            oc.open_id        AS open_id,
            oc.open_points    AS open_points,
            oc.club           AS open_club,
            o.fcb_division_id AS fcb_division_id
        FROM open_classifications oc
        JOIN opens o ON o.id = oc.open_id
        JOIN players p ON p.id = oc.player_id
        WHERE oc.open_id IN ({placeholders})
        ORDER BY p.display_name ASC, o.fcb_division_id ASC
        """,
        open_ids,
    ).fetchall()

    by_player: dict[int, dict[str, object]] = {}
    for row in rows:
        player_id = int(row["player_id"])
        payload = by_player.setdefault(
            player_id,
            {
                "display_name": row["display_name"],
                "current_club": row["current_club"],
                "points": {},
                "open_clubs": {},
            },
        )
        points = payload["points"]
        assert isinstance(points, dict)
        points[int(row["open_id"])] = int(row["open_points"])
        open_clubs = payload["open_clubs"]
        assert isinstance(open_clubs, dict)
        if row["open_club"] is not None:
            open_clubs[int(row["fcb_division_id"])] = str(row["open_club"])

    ranking: list[OpensRankingEntry] = []
    for player_id, payload in by_player.items():
        points = payload["points"]
        assert isinstance(points, dict)
        open_clubs = payload["open_clubs"]
        assert isinstance(open_clubs, dict)

        current_club = payload["current_club"]
        if current_club is not None:
            resolved_club = str(current_club)
        else:
            # Fallback: latest known club from Open participations in the active window.
            latest_div = max(open_clubs.keys()) if open_clubs else None
            resolved_club = open_clubs.get(latest_div) if latest_div is not None else None

        breakdown = [
            OpenBreakdown(
                open_id=op.open_id,
                fcb_division_id=op.fcb_division_id,
                name=op.name,
                season=op.season,
                points=points.get(op.open_id),
            )
            for op in window_opens
        ]
        values = [b.points for b in breakdown if b.points is not None]
        total_points = sum(values)
        if total_points <= 0:
            continue
        ranking.append(
            OpensRankingEntry(
                player_id=player_id,
                display_name=str(payload["display_name"]),
                club=resolved_club,
                total_points=total_points,
                max_single_open=max(values) if values else 0,
                opens_played=len(values),
                breakdown=breakdown,
            )
        )

    ranking.sort(
        key=lambda e: (
            -e.total_points,
            -e.max_single_open,
            -fcb_averages.get(e.player_id, 0.0),
            e.display_name,
        )
    )
    return ranking


def count_opens_in_window(
    conn: sqlite3.Connection,
    num_recent_opens: int = 5,
    as_of_division_id: int | None = None,
) -> int:
    """Return how many Opens would contribute to the ranking given the window.

    Useful for UI: if fewer than 5 Opens are stored, the ranking is
    partial and should be labelled as such.
    """
    return len(
        get_window_opens(
            conn,
            num_recent_opens=num_recent_opens,
            as_of_division_id=as_of_division_id,
        )
    )


def apply_official_penalties(
    entries: list[OpensRankingEntry],
    window_opens: list[OpenWindowOpen],
    pdf_penalties: dict[int, dict[int, int]],
    fcb_averages: dict[int, float] | None = None,
) -> list[OpensRankingEntry]:
    """Return a new ranking with PDF -20 penalties folded into each player's
    breakdown and total.

    The HTML scrape that feeds `compute_opens_ranking` omits no-show rows
    entirely, so penalised participations don't appear in our DB at all.
    The official FCB PDF, however, lists those rows with negative point
    values: `0` is a justified absence (no effect), `-20` is unjustified
    (subtracted from the total).

    Args:
        entries: result of `compute_opens_ranking(conn)` — base ranking
            with positive-only points.
        window_opens: the ordered list of Opens in the same window. Must
            match the order used inside `entries[*].breakdown`.
        pdf_penalties: a mapping `{player_id: {open_id: penalty_points}}`
            where `penalty_points` is negative. Caller is responsible
            for matching PDF entries to player_ids and PDF columns to
            DB Open ids (use `reglament.open_match.map_pdf_columns_to_window`).
        fcb_averages: optional `{player_id: mitjana}` for tiebreak #3
            (Article XVIII). If omitted, ties on (total, max_single)
            fall back to display-name order.

    Returns:
        A new list of `OpensRankingEntry` with penalties applied and the
        canonical sort re-applied.
    """
    if not pdf_penalties:
        return list(entries)

    open_id_to_window_idx = {op.open_id: i for i, op in enumerate(window_opens)}
    fcb_avg = fcb_averages or {}

    new_entries: list[OpensRankingEntry] = []
    for entry in entries:
        player_pen = pdf_penalties.get(entry.player_id)
        if not player_pen:
            new_entries.append(entry)
            continue

        # Apply each penalty to the corresponding breakdown slot.
        # The PDF is the official source — when it says -20, it wins
        # over any HTML-scraped value in our `open_classifications`
        # table (which can disagree with the PDF on whether the player
        # showed up at all). The HTML value is replaced and the delta
        # accounts for the swap so the total stays consistent.
        new_breakdown = list(entry.breakdown)
        delta = 0
        for open_id, penalty in player_pen.items():
            wi = open_id_to_window_idx.get(open_id)
            if wi is None:
                continue  # penalty for an Open outside the window
            if penalty >= 0:
                continue  # 0 = justified absence; positives aren't penalties
            slot = new_breakdown[wi]
            old_points = slot.points
            new_breakdown[wi] = replace(slot, points=penalty)
            delta += penalty - (old_points or 0)

        if delta == 0:
            new_entries.append(entry)
            continue

        valid_points = [b.points for b in new_breakdown if b.points is not None]
        new_total = sum(valid_points)
        new_max = max(valid_points) if valid_points else 0
        new_played = len(valid_points)
        new_entries.append(
            replace(
                entry,
                total_points=new_total,
                max_single_open=new_max,
                opens_played=new_played,
                breakdown=new_breakdown,
            )
        )

    # Re-apply the canonical sort (Article XVIII.1-2 tiebreaks).
    new_entries.sort(
        key=lambda e: (
            -e.total_points,
            -e.max_single_open,
            -fcb_avg.get(e.player_id, 0.0),
            e.display_name,
        )
    )
    return new_entries
