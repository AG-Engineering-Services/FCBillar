"""Player-club resolution with explicit source priority.

The `players.current_club` column is populated opportunistically at
upsert-time from the monthly ranking and Opens, so its value can be
stale or empty for players whose latest authoritative source is the
lliga, or who have no source at all.

This module computes the *resolved* club on demand by inspecting every
known source and applying the priority:

    1. Manual              — `players.manual_club`, set by the user.
                             Definitive once set.
    2. Opens (current season) — Opens are individual events; the club
                             listed there is the player's licensed club.
                             A current-season Open is the strongest
                             "real club" signal.
    3. Lliga (current season) — most recent team_name from
                             `league_partides`. League players can be on
                             loan to a different team than their licensed
                             club, so we prefer Opens when available, but
                             fall back to Lliga if no current-season Open
                             exists.
    4. Opens (older seasons) — last resort: a player's last known club
                             from older Opens. Stale, but better than
                             showing nothing for players who haven't
                             played either an Open or the Lliga this
                             season.
    5. None

The "current season" cutoff is computed from the data: `fcb_division_id`
is monotonic, so the boundary is `max(fcb_division_id) + 1` of the
most-recent labeled season — Opens above that belong to the current
(unlabeled) season.

Each resolved value is returned alongside the per-source values so
callers (UI in particular) can show the user where the club came from
and let them disambiguate.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .models import extract_club_name


@dataclass(frozen=True)
class PlayerClubSources:
    """Per-source club values plus the resolved value for one player.

    `source` is one of: "manual", "opens" (current-season), "lliga",
    "opens_old" (pre-current season), "none".
    """

    opens_club: str | None        # current-season Opens club, if any
    opens_old_club: str | None    # most recent older-season Opens club, if any
    lliga_club: str | None
    manual_club: str | None
    resolved_club: str | None
    source: str


def current_season_div_threshold(conn: sqlite3.Connection) -> int:
    """Return the minimum `fcb_division_id` considered "current season".

    Heuristic: take the highest `fcb_division_id` among Opens that have a
    non-empty, labeled `season` (e.g. "2024-2025"). Anything above that is
    assumed to belong to the current, unlabeled season — matches how
    `scrape-current-opens` ingests fresh Opens without a season string.

    Returns 0 if no labeled season exists (everything counts as current,
    matches the legacy behaviour for tests / fresh DBs).
    """
    row = conn.execute(
        """
        SELECT MAX(fcb_division_id) AS max_id
        FROM opens
        WHERE season IS NOT NULL AND TRIM(season) <> ''
        """
    ).fetchone()
    if row is None or row["max_id"] is None:
        return 0
    return int(row["max_id"]) + 1


def _opens_clubs_for(
    conn: sqlite3.Connection,
    player_id: int,
    *,
    current_season_threshold: int | None = None,
) -> tuple[str | None, str | None]:
    """Return `(current_season_club, older_season_club)` for one player.

    Both values are extracted from `open_classifications` ordered by
    `fcb_division_id DESC`. The current/older split happens at
    `current_season_threshold`. Either may be None if no relevant Open
    has a usable club (e.g. only "Cap" sentinels).
    """
    if current_season_threshold is None:
        current_season_threshold = current_season_div_threshold(conn)
    rows = conn.execute(
        """
        SELECT oc.club, o.fcb_division_id
        FROM open_classifications oc
        JOIN opens o ON o.id = oc.open_id
        WHERE oc.player_id = ?
          AND oc.club IS NOT NULL
          AND TRIM(oc.club) <> ''
        ORDER BY o.fcb_division_id DESC
        """,
        (player_id,),
    ).fetchall()
    current_club: str | None = None
    older_club: str | None = None
    for row in rows:
        normalized = extract_club_name(row["club"])
        if not normalized:
            continue
        if int(row["fcb_division_id"]) >= current_season_threshold:
            if current_club is None:
                current_club = normalized
        else:
            if older_club is None:
                older_club = normalized
        if current_club is not None and older_club is not None:
            break
    return current_club, older_club


def _lliga_club_for(conn: sqlite3.Connection, player_id: int) -> str | None:
    """Most recent team_name this player appeared with, joining
    league_partides → league_encontres → league_jornades and ordering
    by jornada then encontre id descending."""
    rows = conn.execute(
        """
        SELECT
            CASE
                WHEN lp.home_player_id = ? THEN le.home_team_name
                ELSE le.away_team_name
            END AS team_name
        FROM league_partides lp
        JOIN league_encontres le ON le.id = lp.encontre_id
        JOIN league_jornades lj ON lj.id = le.jornada_id
        WHERE lp.home_player_id = ? OR lp.away_player_id = ?
        ORDER BY lj.id DESC, le.id DESC
        """,
        (player_id, player_id, player_id),
    ).fetchall()
    for row in rows:
        normalized = extract_club_name(row["team_name"])
        if normalized:
            return normalized
    return None


def _manual_club_for(conn: sqlite3.Connection, player_id: int) -> str | None:
    row = conn.execute(
        "SELECT manual_club FROM players WHERE id = ?", (player_id,)
    ).fetchone()
    if row is None:
        return None
    val = row["manual_club"]
    if val is None or not str(val).strip():
        return None
    return str(val)


def resolve_player_club(conn: sqlite3.Connection, player_id: int) -> PlayerClubSources:
    """Return the per-source clubs and the resolved value for one player.

    Resolution priority:
      1. Manual
      2. Opens (current season)
      3. Lliga
      4. Opens (older seasons)
      5. None
    """
    opens_current, opens_old = _opens_clubs_for(conn, player_id)
    lliga = _lliga_club_for(conn, player_id)
    manual = _manual_club_for(conn, player_id)

    if manual:
        return PlayerClubSources(opens_current, opens_old, lliga, manual, manual, "manual")
    if opens_current:
        return PlayerClubSources(opens_current, opens_old, lliga, manual, opens_current, "opens")
    if lliga:
        return PlayerClubSources(opens_current, opens_old, lliga, manual, lliga, "lliga")
    if opens_old:
        return PlayerClubSources(opens_current, opens_old, lliga, manual, opens_old, "opens_old")
    return PlayerClubSources(opens_current, opens_old, lliga, manual, None, "none")


def resolve_clubs_bulk(
    conn: sqlite3.Connection,
    player_ids: list[int],
) -> dict[int, PlayerClubSources]:
    """Batched club resolution for a list of players.

    Used by listing endpoints to avoid N round-trips. The query plan
    runs each source once across all requested players and joins the
    results in Python.
    """
    if not player_ids:
        return {}
    placeholders = ",".join("?" * len(player_ids))

    # Current-season threshold computed once per request.
    current_threshold = current_season_div_threshold(conn)

    # Latest Open club per player — collect both current-season AND older
    # in a single scan, ordered DESC so the first hit per side wins.
    opens_rows = conn.execute(
        f"""
        SELECT oc.player_id, oc.club, o.fcb_division_id
        FROM open_classifications oc
        JOIN opens o ON o.id = oc.open_id
        WHERE oc.player_id IN ({placeholders})
          AND oc.club IS NOT NULL
          AND TRIM(oc.club) <> ''
        ORDER BY oc.player_id, o.fcb_division_id DESC
        """,
        player_ids,
    ).fetchall()
    opens_current_by_player: dict[int, str] = {}
    opens_old_by_player: dict[int, str] = {}
    for r in opens_rows:
        pid = int(r["player_id"])
        normalized = extract_club_name(r["club"])
        if not normalized:
            continue
        if int(r["fcb_division_id"]) >= current_threshold:
            opens_current_by_player.setdefault(pid, normalized)
        else:
            opens_old_by_player.setdefault(pid, normalized)

    # Latest Lliga team per player
    lliga_rows = conn.execute(
        f"""
        SELECT
            lp.home_player_id AS home_id,
            lp.away_player_id AS away_id,
            le.home_team_name AS home_team,
            le.away_team_name AS away_team,
            lj.id AS jornada_id,
            le.id AS encontre_id
        FROM league_partides lp
        JOIN league_encontres le ON le.id = lp.encontre_id
        JOIN league_jornades lj ON lj.id = le.jornada_id
        WHERE lp.home_player_id IN ({placeholders})
           OR lp.away_player_id IN ({placeholders})
        ORDER BY lj.id DESC, le.id DESC
        """,
        player_ids + player_ids,
    ).fetchall()
    lliga_by_player: dict[int, str] = {}
    requested = set(player_ids)
    for r in lliga_rows:
        for pid_key, team_key in (("home_id", "home_team"), ("away_id", "away_team")):
            raw = r[pid_key]
            if raw is None:
                continue
            pid = int(raw)
            if pid not in requested or pid in lliga_by_player:
                continue
            normalized = extract_club_name(r[team_key])
            if normalized:
                lliga_by_player[pid] = normalized

    # Manual clubs
    manual_rows = conn.execute(
        f"SELECT id, manual_club FROM players WHERE id IN ({placeholders})",
        player_ids,
    ).fetchall()
    manual_by_player: dict[int, str | None] = {
        int(r["id"]): (r["manual_club"] if r["manual_club"] and str(r["manual_club"]).strip() else None)
        for r in manual_rows
    }

    out: dict[int, PlayerClubSources] = {}
    for pid in player_ids:
        opens_current = opens_current_by_player.get(pid)
        opens_old = opens_old_by_player.get(pid)
        lliga = lliga_by_player.get(pid)
        manual = manual_by_player.get(pid)
        # Priority: Manual > Opens(current) > Lliga > Opens(old) > None.
        if manual:
            out[pid] = PlayerClubSources(opens_current, opens_old, lliga, manual, manual, "manual")
        elif opens_current:
            out[pid] = PlayerClubSources(opens_current, opens_old, lliga, manual, opens_current, "opens")
        elif lliga:
            out[pid] = PlayerClubSources(opens_current, opens_old, lliga, manual, lliga, "lliga")
        elif opens_old:
            out[pid] = PlayerClubSources(opens_current, opens_old, lliga, manual, opens_old, "opens_old")
        else:
            out[pid] = PlayerClubSources(opens_current, opens_old, lliga, manual, None, "none")
    return out


def set_manual_club(
    conn: sqlite3.Connection,
    player_id: int,
    manual_club: str | None,
) -> None:
    """Set or clear the manual override. Empty/whitespace becomes NULL."""
    value: str | None = None
    if manual_club is not None:
        stripped = manual_club.strip()
        if stripped:
            value = stripped
    conn.execute(
        "UPDATE players SET manual_club = ? WHERE id = ?",
        (value, player_id),
    )
