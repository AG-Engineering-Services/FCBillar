"""Per-player stats derived from stored league partides.

Queries are kept here (rather than in api/app.py) so the rule for
what counts as a "win" / "loss" / "average" lives in one place and
can be exercised in isolation if needed.

A partida result is decided by `home_punts` vs `away_punts`:
    home > away  → home wins,  away loses
    home < away  → home loses, away wins
    home == away (typically 1-1) → draw
Unplayed partides (`is_played = 0`) are ignored.

Mitjana = total caramboles / total entrades, computed across all played
partides where the player was either home or away.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class PlayerLeagueStats:
    """Aggregated KPIs for one player within a single group's matches.

    Used for the per-group player ranking (rànquing per categoria).
    """

    player_id: int
    display_name: str
    team_name: str           # the team they played for in this group
    matches_played: int
    wins: int
    draws: int
    losses: int
    caramboles: int
    entrades: int
    best_serie: int
    match_points: int        # 2 per win, 1 per draw, 0 per loss
    # Slot distribution: how many times the player played as slot 1, 2,
    # 3 or 4 within an encontre. The "tablero" they typically take.
    s1: int = 0
    s2: int = 0
    s3: int = 0
    s4: int = 0

    @property
    def average(self) -> float:
        return (self.caramboles / self.entrades) if self.entrades else 0.0


@dataclass
class PartidaSummary:
    """One partida flattened from the perspective of a single player.

    The player can have been the home or away side; we expose both a
    `was_home` flag and an `opponent_name` so the UI can render
    consistently.
    """

    partida_id: int
    encontre_id: int
    fcb_encontre_id: int
    jornada_number: int
    played_on: str | None
    division_name: str
    group_name: str
    own_team_name: str
    opponent_name: str | None
    opponent_team_name: str
    was_home: bool
    own_caramboles: int
    own_serie_major: int
    own_punts: int
    opp_caramboles: int
    opp_serie_major: int
    opp_punts: int
    entrades: int
    is_played: bool

    @property
    def result(self) -> str:
        """One of "V" (victòria), "D" (derrota), "E" (empat), "—" (no jugat)."""
        if not self.is_played:
            return "—"
        if self.own_punts > self.opp_punts:
            return "V"
        if self.own_punts < self.opp_punts:
            return "D"
        return "E"


# --------------------------------------------------------------------------- #
# Per-group ranking
# --------------------------------------------------------------------------- #


_PLAYER_AGG_SQL = """
WITH played AS (
    SELECT
        lp.encontre_id,
        lp.is_played,
        lp.entrades,
        lp.slot AS slot,
        le.home_team_name,
        le.away_team_name,
        lj.group_id,
        -- emit two rows per partida: one per side
        CASE
            WHEN side = 'home' THEN lp.home_player_id
            ELSE lp.away_player_id
        END AS player_id,
        CASE
            WHEN side = 'home' THEN lp.home_caramboles
            ELSE lp.away_caramboles
        END AS caramboles,
        CASE
            WHEN side = 'home' THEN lp.home_serie_major
            ELSE lp.away_serie_major
        END AS serie_major,
        CASE
            WHEN side = 'home' THEN lp.home_punts
            ELSE lp.away_punts
        END AS own_punts,
        CASE
            WHEN side = 'home' THEN lp.away_punts
            ELSE lp.home_punts
        END AS opp_punts,
        CASE
            WHEN side = 'home' THEN le.home_team_name
            ELSE le.away_team_name
        END AS team_name
    FROM league_partides lp
    JOIN league_encontres le ON le.id = lp.encontre_id
    JOIN league_jornades lj ON lj.id = le.jornada_id
    JOIN (SELECT 'home' AS side UNION ALL SELECT 'away') sides
    WHERE lj.group_id = :group_id
      AND lp.is_played = 1
      AND (
           (side = 'home' AND lp.home_player_id IS NOT NULL)
        OR (side = 'away' AND lp.away_player_id IS NOT NULL)
      )
)
SELECT
    p.id AS player_id,
    p.display_name,
    -- pick the team they appeared in most often (handles transfers across
    -- jornades; in practice players don't move mid-season, so this is
    -- typically the only team they played for).
    (
        SELECT pp.team_name
        FROM played pp
        WHERE pp.player_id = p.id
        GROUP BY pp.team_name
        ORDER BY COUNT(*) DESC, pp.team_name
        LIMIT 1
    ) AS team_name,
    COUNT(*) AS matches_played,
    SUM(CASE WHEN played.own_punts > played.opp_punts THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN played.own_punts = played.opp_punts THEN 1 ELSE 0 END) AS draws,
    SUM(CASE WHEN played.own_punts < played.opp_punts THEN 1 ELSE 0 END) AS losses,
    SUM(played.caramboles) AS caramboles,
    SUM(played.entrades) AS entrades,
    MAX(played.serie_major) AS best_serie,
    SUM(CASE WHEN played.own_punts > played.opp_punts THEN 2
             WHEN played.own_punts = played.opp_punts THEN 1
             ELSE 0 END) AS match_points,
    SUM(CASE WHEN played.slot = 1 THEN 1 ELSE 0 END) AS s1,
    SUM(CASE WHEN played.slot = 2 THEN 1 ELSE 0 END) AS s2,
    SUM(CASE WHEN played.slot = 3 THEN 1 ELSE 0 END) AS s3,
    SUM(CASE WHEN played.slot = 4 THEN 1 ELSE 0 END) AS s4
FROM played
JOIN players p ON p.id = played.player_id
GROUP BY p.id, p.display_name
ORDER BY match_points DESC,
         (CAST(SUM(played.caramboles) AS REAL) / NULLIF(SUM(played.entrades), 0)) DESC,
         best_serie DESC,
         p.display_name
"""


def player_ranking_for_group(
    conn: sqlite3.Connection, group_id: int
) -> list[PlayerLeagueStats]:
    """Compute the player ranking within a group.

    Sort key (highest first):
        match_points → mitjana general → millor sèrie → name
    """
    rows = conn.execute(_PLAYER_AGG_SQL, {"group_id": group_id}).fetchall()
    return [_row_to_stats(r) for r in rows]


# --------------------------------------------------------------------------- #
# Per-category (division) ranking
# --------------------------------------------------------------------------- #


_PLAYER_AGG_DIVISION_SQL = """
WITH played AS (
    SELECT
        CASE
            WHEN side = 'home' THEN lp.home_player_id
            ELSE lp.away_player_id
        END AS player_id,
        CASE
            WHEN side = 'home' THEN lp.home_caramboles
            ELSE lp.away_caramboles
        END AS caramboles,
        CASE
            WHEN side = 'home' THEN lp.home_serie_major
            ELSE lp.away_serie_major
        END AS serie_major,
        CASE
            WHEN side = 'home' THEN lp.home_punts
            ELSE lp.away_punts
        END AS own_punts,
        CASE
            WHEN side = 'home' THEN lp.away_punts
            ELSE lp.home_punts
        END AS opp_punts,
        CASE
            WHEN side = 'home' THEN le.home_team_name
            ELSE le.away_team_name
        END AS team_name,
        lp.entrades,
        lp.slot AS slot
    FROM league_partides lp
    JOIN league_encontres le ON le.id = lp.encontre_id
    JOIN league_jornades lj ON lj.id = le.jornada_id
    JOIN league_groups lg ON lg.id = lj.group_id
    JOIN (SELECT 'home' AS side UNION ALL SELECT 'away') sides
    WHERE lg.division_id = :division_id
      AND lp.is_played = 1
      AND (
           (side = 'home' AND lp.home_player_id IS NOT NULL)
        OR (side = 'away' AND lp.away_player_id IS NOT NULL)
      )
)
SELECT
    p.id AS player_id,
    p.display_name,
    (
        SELECT pp.team_name
        FROM played pp
        WHERE pp.player_id = p.id
        GROUP BY pp.team_name
        ORDER BY COUNT(*) DESC, pp.team_name
        LIMIT 1
    ) AS team_name,
    COUNT(*) AS matches_played,
    SUM(CASE WHEN played.own_punts > played.opp_punts THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN played.own_punts = played.opp_punts THEN 1 ELSE 0 END) AS draws,
    SUM(CASE WHEN played.own_punts < played.opp_punts THEN 1 ELSE 0 END) AS losses,
    SUM(played.caramboles) AS caramboles,
    SUM(played.entrades) AS entrades,
    MAX(played.serie_major) AS best_serie,
    SUM(CASE WHEN played.own_punts > played.opp_punts THEN 2
             WHEN played.own_punts = played.opp_punts THEN 1
             ELSE 0 END) AS match_points,
    SUM(CASE WHEN played.slot = 1 THEN 1 ELSE 0 END) AS s1,
    SUM(CASE WHEN played.slot = 2 THEN 1 ELSE 0 END) AS s2,
    SUM(CASE WHEN played.slot = 3 THEN 1 ELSE 0 END) AS s3,
    SUM(CASE WHEN played.slot = 4 THEN 1 ELSE 0 END) AS s4
FROM played
JOIN players p ON p.id = played.player_id
GROUP BY p.id, p.display_name
ORDER BY match_points DESC,
         (CAST(SUM(played.caramboles) AS REAL) / NULLIF(SUM(played.entrades), 0)) DESC,
         best_serie DESC,
         p.display_name
"""


def player_ranking_for_division(
    conn: sqlite3.Connection, division_id: int
) -> list[PlayerLeagueStats]:
    """Aggregate the player ranking across every group of a division.

    Same shape as `player_ranking_for_group`, but rows that span multiple
    groups (rare — would mean a player switched groups mid-season) are
    summed into a single entry. The sort key matches the group ranking:
        match_points → mitjana → best sèrie → name.
    """
    rows = conn.execute(
        _PLAYER_AGG_DIVISION_SQL, {"division_id": division_id}
    ).fetchall()
    return [_row_to_stats(r) for r in rows]


def _row_to_stats(row) -> PlayerLeagueStats:
    return PlayerLeagueStats(
        player_id=row["player_id"],
        display_name=row["display_name"],
        team_name=row["team_name"] or "",
        matches_played=int(row["matches_played"]),
        wins=int(row["wins"]),
        draws=int(row["draws"]),
        losses=int(row["losses"]),
        caramboles=int(row["caramboles"] or 0),
        entrades=int(row["entrades"] or 0),
        best_serie=int(row["best_serie"] or 0),
        match_points=int(row["match_points"] or 0),
        s1=int(row["s1"] or 0),
        s2=int(row["s2"] or 0),
        s3=int(row["s3"] or 0),
        s4=int(row["s4"] or 0),
    )


# --------------------------------------------------------------------------- #
# Team aggregates (mitjana per equip = ΣCAR_team / ΣENT_team)
# --------------------------------------------------------------------------- #


@dataclass
class TeamAggregate:
    """Caramboles / entrades / mitjana totals for a team within a group.

    Sums across every played partida where the team appeared on either side.
    `entrades` are the SAME for both sides of a partida (4-cushion / 3-bandes
    rule), so summing each side's partidas gives the team's total entrades.
    """

    team_name: str
    caramboles: int
    entrades: int

    @property
    def average(self) -> float:
        return (self.caramboles / self.entrades) if self.entrades else 0.0


_TEAM_AGG_GROUP_SQL = """
SELECT
    team_name,
    SUM(caramboles) AS caramboles,
    SUM(entrades) AS entrades
FROM (
    SELECT le.home_team_name AS team_name,
           lp.home_caramboles AS caramboles,
           lp.entrades
    FROM league_partides lp
    JOIN league_encontres le ON le.id = lp.encontre_id
    JOIN league_jornades lj ON lj.id = le.jornada_id
    WHERE lj.group_id = :group_id AND lp.is_played = 1
    UNION ALL
    SELECT le.away_team_name AS team_name,
           lp.away_caramboles AS caramboles,
           lp.entrades
    FROM league_partides lp
    JOIN league_encontres le ON le.id = lp.encontre_id
    JOIN league_jornades lj ON lj.id = le.jornada_id
    WHERE lj.group_id = :group_id AND lp.is_played = 1
)
GROUP BY team_name
"""


def team_aggregates_for_group(
    conn: sqlite3.Connection, group_id: int
) -> dict[str, TeamAggregate]:
    """Return `{team_name: TeamAggregate}` for every team that has played
    at least one partida in the group. Teams with no played partides are
    absent — the caller should treat the missing entry as 0/0/0.0.
    """
    rows = conn.execute(_TEAM_AGG_GROUP_SQL, {"group_id": group_id}).fetchall()
    return {
        r["team_name"]: TeamAggregate(
            team_name=r["team_name"],
            caramboles=int(r["caramboles"] or 0),
            entrades=int(r["entrades"] or 0),
        )
        for r in rows
    }


# --------------------------------------------------------------------------- #
# Group / division mitjana general (overall)
# --------------------------------------------------------------------------- #


@dataclass
class ScopeAggregate:
    """Caramboles / entrades totals for a group or a division.

    The mitjana is computed as `Σ caramboles per side / Σ entrades per side`
    across every played partida in scope. Because each partida contributes
    one (home, entrades) row AND one (away, entrades) row to the sums,
    the entrades total equals `2 × Σ entrades_per_partida`, which is the
    correct weighting for a "per player turn" overall average.
    """

    caramboles: int
    entrades: int

    @property
    def average(self) -> float:
        return (self.caramboles / self.entrades) if self.entrades else 0.0


def _aggregate_sql(scope_column: str) -> str:
    return f"""
        SELECT
            COALESCE(SUM(caramboles), 0) AS caramboles,
            COALESCE(SUM(entrades), 0) AS entrades
        FROM (
            SELECT lp.home_caramboles AS caramboles, lp.entrades
            FROM league_partides lp
            JOIN league_encontres le ON le.id = lp.encontre_id
            JOIN league_jornades lj ON lj.id = le.jornada_id
            JOIN league_groups lg ON lg.id = lj.group_id
            WHERE lp.is_played = 1 AND {scope_column} = :scope_id
            UNION ALL
            SELECT lp.away_caramboles AS caramboles, lp.entrades
            FROM league_partides lp
            JOIN league_encontres le ON le.id = lp.encontre_id
            JOIN league_jornades lj ON lj.id = le.jornada_id
            JOIN league_groups lg ON lg.id = lj.group_id
            WHERE lp.is_played = 1 AND {scope_column} = :scope_id
        )
    """


def group_aggregate(conn: sqlite3.Connection, group_id: int) -> ScopeAggregate:
    """Mitjana general of an entire group (every played partida combined)."""
    row = conn.execute(
        _aggregate_sql("lg.id"), {"scope_id": group_id}
    ).fetchone()
    return ScopeAggregate(
        caramboles=int(row["caramboles"] or 0),
        entrades=int(row["entrades"] or 0),
    )


def division_aggregate(
    conn: sqlite3.Connection, division_id: int
) -> ScopeAggregate:
    """Mitjana general across every group of a division (category)."""
    row = conn.execute(
        _aggregate_sql("lg.division_id"), {"scope_id": division_id}
    ).fetchone()
    return ScopeAggregate(
        caramboles=int(row["caramboles"] or 0),
        entrades=int(row["entrades"] or 0),
    )


# --------------------------------------------------------------------------- #
# Slot reliability — per-slot performance for one player
# --------------------------------------------------------------------------- #


@dataclass
class SlotPerformance:
    """A player's record at one slot (1..4) of an encontre.

    "Fiabilitat" = the player's track record when assigned to that
    tablero. Captains use this to decide who to put at each board.
    """

    slot: int  # 1..4
    matches_played: int
    wins: int
    draws: int
    losses: int
    match_points: int
    caramboles: int
    entrades: int
    best_serie: int

    @property
    def win_rate(self) -> float:
        return (self.wins / self.matches_played) if self.matches_played else 0.0

    @property
    def average(self) -> float:
        return (self.caramboles / self.entrades) if self.entrades else 0.0


_SLOT_PERFORMANCE_SQL = """
WITH played AS (
    SELECT
        lp.slot AS slot,
        lp.entrades,
        CASE WHEN side = 'home' THEN lp.home_caramboles
             ELSE lp.away_caramboles END AS caramboles,
        CASE WHEN side = 'home' THEN lp.home_serie_major
             ELSE lp.away_serie_major END AS serie_major,
        CASE WHEN side = 'home' THEN lp.home_punts
             ELSE lp.away_punts END AS own_punts,
        CASE WHEN side = 'home' THEN lp.away_punts
             ELSE lp.home_punts END AS opp_punts
    FROM league_partides lp
    JOIN (SELECT 'home' AS side UNION ALL SELECT 'away') sides
    WHERE lp.is_played = 1
      AND (
           (side = 'home' AND lp.home_player_id = :player_id)
        OR (side = 'away' AND lp.away_player_id = :player_id)
      )
)
SELECT
    slot,
    COUNT(*) AS matches_played,
    SUM(CASE WHEN own_punts > opp_punts THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN own_punts = opp_punts THEN 1 ELSE 0 END) AS draws,
    SUM(CASE WHEN own_punts < opp_punts THEN 1 ELSE 0 END) AS losses,
    SUM(CASE WHEN own_punts > opp_punts THEN 2
             WHEN own_punts = opp_punts THEN 1
             ELSE 0 END) AS match_points,
    SUM(caramboles) AS caramboles,
    SUM(entrades) AS entrades,
    MAX(serie_major) AS best_serie
FROM played
GROUP BY slot
ORDER BY slot
"""


def slot_performance_for_player(
    conn: sqlite3.Connection, player_id: int
) -> list[SlotPerformance]:
    """Per-slot record across every league partida the player has played.

    Returned list contains only slots where the player has at least one
    played partida. The caller fills in absent slots as zero rows if it
    needs all four columns rendered.
    """
    rows = conn.execute(
        _SLOT_PERFORMANCE_SQL, {"player_id": player_id}
    ).fetchall()
    return [
        SlotPerformance(
            slot=int(r["slot"]),
            matches_played=int(r["matches_played"]),
            wins=int(r["wins"]),
            draws=int(r["draws"]),
            losses=int(r["losses"]),
            match_points=int(r["match_points"] or 0),
            caramboles=int(r["caramboles"] or 0),
            entrades=int(r["entrades"] or 0),
            best_serie=int(r["best_serie"] or 0),
        )
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# Per-player history (across all groups they played in)
# --------------------------------------------------------------------------- #


_PLAYER_PARTIDES_SQL = """
SELECT
    lp.id AS partida_id,
    le.id AS encontre_id,
    le.fcb_encontre_id,
    lj.number AS jornada_number,
    lj.played_on,
    ld.name AS division_name,
    lg.name AS group_name,
    lg.id AS group_db_id,
    lp.is_played,
    lp.entrades,
    le.home_team_name,
    le.away_team_name,
    lp.home_player_id,
    lp.away_player_id,
    lp.home_caramboles,
    lp.home_serie_major,
    lp.home_punts,
    lp.away_caramboles,
    lp.away_serie_major,
    lp.away_punts,
    home_p.display_name AS home_player_name,
    away_p.display_name AS away_player_name
FROM league_partides lp
JOIN league_encontres le ON le.id = lp.encontre_id
JOIN league_jornades lj ON lj.id = le.jornada_id
JOIN league_groups lg ON lg.id = lj.group_id
JOIN league_divisions ld ON ld.id = lg.division_id
LEFT JOIN players home_p ON home_p.id = lp.home_player_id
LEFT JOIN players away_p ON away_p.id = lp.away_player_id
WHERE lp.home_player_id = :pid OR lp.away_player_id = :pid
ORDER BY ld.name, lg.name, lj.number, lp.slot
"""


def partides_for_player(
    conn: sqlite3.Connection, player_id: int
) -> list[PartidaSummary]:
    rows = conn.execute(_PLAYER_PARTIDES_SQL, {"pid": player_id}).fetchall()
    out: list[PartidaSummary] = []
    for row in rows:
        was_home = row["home_player_id"] == player_id
        if was_home:
            own_team = row["home_team_name"]
            opp_team = row["away_team_name"]
            opp_name = row["away_player_name"]
            own_car = row["home_caramboles"]
            own_serie = row["home_serie_major"]
            own_pts = row["home_punts"]
            opp_car = row["away_caramboles"]
            opp_serie = row["away_serie_major"]
            opp_pts = row["away_punts"]
        else:
            own_team = row["away_team_name"]
            opp_team = row["home_team_name"]
            opp_name = row["home_player_name"]
            own_car = row["away_caramboles"]
            own_serie = row["away_serie_major"]
            own_pts = row["away_punts"]
            opp_car = row["home_caramboles"]
            opp_serie = row["home_serie_major"]
            opp_pts = row["home_punts"]
        out.append(
            PartidaSummary(
                partida_id=row["partida_id"],
                encontre_id=row["encontre_id"],
                fcb_encontre_id=row["fcb_encontre_id"],
                jornada_number=row["jornada_number"],
                played_on=row["played_on"],
                division_name=row["division_name"],
                group_name=row["group_name"],
                own_team_name=own_team,
                opponent_name=opp_name,
                opponent_team_name=opp_team,
                was_home=was_home,
                own_caramboles=own_car,
                own_serie_major=own_serie,
                own_punts=own_pts,
                opp_caramboles=opp_car,
                opp_serie_major=opp_serie,
                opp_punts=opp_pts,
                entrades=row["entrades"],
                is_played=bool(row["is_played"]),
            )
        )
    return out


def player_league_summary(
    conn: sqlite3.Connection, player_id: int
) -> dict[str, PlayerLeagueStats]:
    """Aggregate KPIs for a player across each group they appear in.

    Returns a mapping `"DIVISION • GROUP" -> PlayerLeagueStats`.
    """
    # First find the groups the player appears in.
    rows = conn.execute(
        """
        SELECT DISTINCT lg.id, ld.name AS division_name, lg.name AS group_name
        FROM league_partides lp
        JOIN league_encontres le ON le.id = lp.encontre_id
        JOIN league_jornades lj ON lj.id = le.jornada_id
        JOIN league_groups lg ON lg.id = lj.group_id
        JOIN league_divisions ld ON ld.id = lg.division_id
        WHERE lp.home_player_id = ? OR lp.away_player_id = ?
        ORDER BY ld.name, lg.name
        """,
        (player_id, player_id),
    ).fetchall()
    out: dict[str, PlayerLeagueStats] = {}
    for r in rows:
        ranking = player_ranking_for_group(conn, r["id"])
        for entry in ranking:
            if entry.player_id == player_id:
                key = f"{r['division_name']} • {r['group_name']}"
                out[key] = entry
                break
    return out
