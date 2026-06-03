"""SQLite persistence layer.

Kept deliberately small: a schema bootstrap function, a connection
helper, and per-entity save functions. No ORM — the schema is simple
enough that hand-written SQL is clearer and fully typed at the call sites.

All save functions are idempotent: calling them twice with the same
input produces the same end state (INSERT OR REPLACE / deletes then
reinserts children where appropriate).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .models import (
    MonthlyRanking,
    Open,
    OpenClassificationEntry,
    normalize_club,
    normalize_name,
)
from .reglament.puntuacio import points_for_position

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS players (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    normalized_name   TEXT NOT NULL UNIQUE,
    display_name      TEXT NOT NULL,
    current_club      TEXT,
    manual_club       TEXT
);

CREATE TABLE IF NOT EXISTS monthly_rankings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    month_id          INTEGER NOT NULL UNIQUE,
    fetched_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS monthly_ranking_entries (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ranking_id        INTEGER NOT NULL REFERENCES monthly_rankings(id) ON DELETE CASCADE,
    position          INTEGER NOT NULL,
    player_id         INTEGER NOT NULL REFERENCES players(id),
    club              TEXT,
    average           REAL NOT NULL,
    matches_scored    INTEGER NOT NULL,
    matches_max       INTEGER NOT NULL,
    is_definitive     INTEGER NOT NULL,
    UNIQUE (ranking_id, position)
);

CREATE INDEX IF NOT EXISTS idx_mre_ranking ON monthly_ranking_entries(ranking_id);
CREATE INDEX IF NOT EXISTS idx_mre_player  ON monthly_ranking_entries(player_id);

CREATE TABLE IF NOT EXISTS opens (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    fcb_division_id          INTEGER NOT NULL UNIQUE,
    fcb_classification_id    INTEGER,
    name                     TEXT NOT NULL,
    season                   TEXT NOT NULL,
    played_at                TEXT
);

CREATE TABLE IF NOT EXISTS open_classifications (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    open_id              INTEGER NOT NULL REFERENCES opens(id) ON DELETE CASCADE,
    position             INTEGER NOT NULL,
    player_id            INTEGER NOT NULL REFERENCES players(id),
    club                 TEXT,
    matches_played       INTEGER NOT NULL,
    match_points         INTEGER NOT NULL,
    caramboles           INTEGER NOT NULL,
    entries              INTEGER NOT NULL,
    general_average      REAL NOT NULL,
    particular_average   REAL NOT NULL,
    best_series          INTEGER NOT NULL,
    open_points          INTEGER NOT NULL,
    UNIQUE (open_id, position)
);

CREATE INDEX IF NOT EXISTS idx_oc_player ON open_classifications(player_id);
CREATE INDEX IF NOT EXISTS idx_oc_open   ON open_classifications(open_id);

CREATE TABLE IF NOT EXISTS open_live_snapshots (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    fcb_division_id   INTEGER NOT NULL,
    captured_at       TEXT NOT NULL,
    payload_json      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ols_div_time
    ON open_live_snapshots(fcb_division_id, captured_at);

-- --------------------------------------------------------------------- --
-- Open projections: the *provisional* bracket computed from the official
-- inscrits-per-clubs PDF (seeding via Art. XVIII + the group generator,
-- Art. VIII-IX), built before the federation publishes the real groups.
-- Stored as a JSON payload (like live snapshots) since it's a read-mostly
-- computed artefact. `fcb_division_id` links it to the live Open once the
-- federation publishes it, so the UI can switch from projection to live.
-- --------------------------------------------------------------------- --
CREATE TABLE IF NOT EXISTS open_projections (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    season            TEXT,
    num_inscriptions  INTEGER NOT NULL,
    source_pdf        TEXT,
    fcb_division_id   INTEGER,
    created_at        TEXT NOT NULL,
    payload_json      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_open_proj_div ON open_projections(fcb_division_id);

-- --------------------------------------------------------------------- --
-- Lliga (league) tables. The Lliga Catalana Tres Bandes is competition
-- id 36 on fcbillar.cat. Within a competition, there are divisions
-- (HONOR, 1a, 2a, 3a, 4a) split into groups (e.g. GRUP A / B). Each
-- group runs a round-robin of jornades; each jornada has a handful of
-- team encounters (encontres) and each encounter contains 4 individual
-- partides (one per board).
-- --------------------------------------------------------------------- --

CREATE TABLE IF NOT EXISTS leagues (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    fcb_competition_id    INTEGER NOT NULL UNIQUE,
    name                  TEXT NOT NULL,
    season                TEXT NOT NULL DEFAULT '',
    fetched_at            TEXT
);

CREATE TABLE IF NOT EXISTS league_divisions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id         INTEGER NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
    fcb_division_id   INTEGER NOT NULL,
    name              TEXT NOT NULL,
    UNIQUE (league_id, fcb_division_id)
);

CREATE TABLE IF NOT EXISTS league_groups (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    division_id       INTEGER NOT NULL REFERENCES league_divisions(id) ON DELETE CASCADE,
    fcb_group_id      INTEGER NOT NULL,
    name              TEXT NOT NULL,
    UNIQUE (division_id, fcb_group_id)
);

CREATE TABLE IF NOT EXISTS league_team_standings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id          INTEGER NOT NULL REFERENCES league_groups(id) ON DELETE CASCADE,
    position          INTEGER NOT NULL,
    team_name         TEXT NOT NULL,
    match_points      INTEGER NOT NULL,
    set_points        INTEGER NOT NULL,
    matches_played    INTEGER NOT NULL,
    UNIQUE (group_id, position)
);

CREATE TABLE IF NOT EXISTS league_jornades (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id          INTEGER NOT NULL REFERENCES league_groups(id) ON DELETE CASCADE,
    fcb_jornada_id    INTEGER NOT NULL,
    number            INTEGER NOT NULL,
    played_on         TEXT,
    UNIQUE (group_id, fcb_jornada_id)
);

CREATE INDEX IF NOT EXISTS idx_lj_group ON league_jornades(group_id);

CREATE TABLE IF NOT EXISTS league_encontres (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    jornada_id          INTEGER NOT NULL REFERENCES league_jornades(id) ON DELETE CASCADE,
    fcb_encontre_id     INTEGER NOT NULL,
    home_team_name      TEXT NOT NULL,
    away_team_name      TEXT NOT NULL,
    home_match_points   INTEGER NOT NULL,
    away_match_points   INTEGER NOT NULL,
    home_set_points     INTEGER NOT NULL,
    away_set_points     INTEGER NOT NULL,
    UNIQUE (jornada_id, fcb_encontre_id)
);

CREATE INDEX IF NOT EXISTS idx_le_jornada ON league_encontres(jornada_id);

CREATE TABLE IF NOT EXISTS league_partides (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    encontre_id         INTEGER NOT NULL REFERENCES league_encontres(id) ON DELETE CASCADE,
    slot                INTEGER NOT NULL,
    home_player_id      INTEGER REFERENCES players(id),
    home_caramboles     INTEGER NOT NULL DEFAULT 0,
    home_serie_major    INTEGER NOT NULL DEFAULT 0,
    home_punts          INTEGER NOT NULL DEFAULT 0,
    away_player_id      INTEGER REFERENCES players(id),
    away_caramboles     INTEGER NOT NULL DEFAULT 0,
    away_serie_major    INTEGER NOT NULL DEFAULT 0,
    away_punts          INTEGER NOT NULL DEFAULT 0,
    entrades            INTEGER NOT NULL DEFAULT 0,
    arbitre             TEXT,
    attendance          TEXT,
    modalitat           TEXT,
    is_played           INTEGER NOT NULL DEFAULT 0,
    UNIQUE (encontre_id, slot)
);

CREATE INDEX IF NOT EXISTS idx_lp_encontre ON league_partides(encontre_id);
CREATE INDEX IF NOT EXISTS idx_lp_home ON league_partides(home_player_id);
CREATE INDEX IF NOT EXISTS idx_lp_away ON league_partides(away_player_id);

-- Per-discrepancy human decisions for the Opens-ranking diff against the
-- official FCB PDF. Lets the user mark a row as "trust calc", "trust PDF",
-- or "dismiss" so /diff focuses on unresolved cases on subsequent visits.
-- Keyed by player_name (normalized, upper) since player_id may be NULL for
-- players present only in the official PDF and not yet in our DB.
CREATE TABLE IF NOT EXISTS diff_overrides (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_name     TEXT NOT NULL,
    discrepancy_kind TEXT NOT NULL,
    decision        TEXT NOT NULL CHECK (decision IN ('keep_computed', 'use_official', 'dismissed')),
    note            TEXT,
    official_total  INTEGER,
    computed_total  INTEGER,
    updated_at      TEXT NOT NULL,
    UNIQUE (player_name, discrepancy_kind)
);
CREATE INDEX IF NOT EXISTS idx_diff_overrides_player ON diff_overrides(player_name);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys and row factory ready.

    `check_same_thread=False` is set because the FastAPI app uses
    dependency-injected connections that may cross thread boundaries
    under uvicorn --reload (the file watcher and some middleware run
    in auxiliary threads). SQLite itself supports this; the Python
    binding's default assertion is overly strict for our use case.
    For a single-user local tool this is safe — we don't have
    concurrent writers that could race.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> None:
    """Create tables if they don't exist. Safe to call repeatedly."""
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        _ensure_monthly_ranking_entries_club_column(conn)
        _ensure_players_manual_club_column(conn)
        migrate_normalize_clubs(conn)
        migrate_backfill_current_clubs_from_opens(conn)
        conn.commit()
    finally:
        conn.close()


def _ensure_monthly_ranking_entries_club_column(conn: sqlite3.Connection) -> None:
    """Backfill schema evolution on existing DBs that predate the club column."""
    cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(monthly_ranking_entries)").fetchall()
    }
    if "club" not in cols:
        conn.execute("ALTER TABLE monthly_ranking_entries ADD COLUMN club TEXT")


def _ensure_players_manual_club_column(conn: sqlite3.Connection) -> None:
    """Add `manual_club` column to existing DBs that predate manual overrides.

    `manual_club` is the user-supplied club applied as the lowest-priority
    fallback in `club_resolution.resolve_player_club` — only surfaced when
    neither Opens nor Lliga history has a club for the player.
    """
    cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(players)").fetchall()
    }
    if "manual_club" not in cols:
        conn.execute("ALTER TABLE players ADD COLUMN manual_club TEXT")


def migrate_normalize_clubs(conn: sqlite3.Connection) -> None:
    """One-shot data cleanup: normalize empty club sentinels to NULL."""
    conn.execute(
        """
        UPDATE players
        SET current_club = NULL
        WHERE TRIM(COALESCE(current_club, '')) = ''
           OR LOWER(TRIM(current_club)) = 'cap'
        """
    )
    conn.execute(
        """
        UPDATE monthly_ranking_entries
        SET club = NULL
        WHERE TRIM(COALESCE(club, '')) = ''
           OR LOWER(TRIM(club)) = 'cap'
        """
    )


def migrate_backfill_current_clubs_from_opens(conn: sqlite3.Connection) -> None:
        """Fill missing players.current_club from the most recent Open club.

        For players where current_club is empty/NULL, look up their latest
        participation across stored Opens (highest fcb_division_id first)
        and copy that Open club if present.
        """
        conn.execute(
                """
                UPDATE players
                SET current_club = (
                        SELECT oc.club
                        FROM open_classifications oc
                        JOIN opens o ON o.id = oc.open_id
                        WHERE oc.player_id = players.id
                            AND oc.club IS NOT NULL
                            AND TRIM(oc.club) <> ''
                            AND LOWER(TRIM(oc.club)) <> 'cap'
                        ORDER BY o.fcb_division_id DESC
                        LIMIT 1
                )
                WHERE (players.current_club IS NULL
                             OR TRIM(players.current_club) = ''
                             OR LOWER(TRIM(players.current_club)) = 'cap')
                    AND EXISTS (
                        SELECT 1
                        FROM open_classifications oc
                        JOIN opens o ON o.id = oc.open_id
                        WHERE oc.player_id = players.id
                            AND oc.club IS NOT NULL
                            AND TRIM(oc.club) <> ''
                            AND LOWER(TRIM(oc.club)) <> 'cap'
                    )
                """
        )


# --------------------------------------------------------------------------- #
# Player upsert
# --------------------------------------------------------------------------- #


def upsert_player(
    conn: sqlite3.Connection,
    display_name: str,
    club: str | None = None,
) -> int:
    """Get or create a player row, returning its id.

    If the player exists and `club` is provided, current_club is updated.
    """
    norm = normalize_name(display_name)
    normalized_club = normalize_club(club)
    row = conn.execute(
        "SELECT id FROM players WHERE normalized_name = ?", (norm,)
    ).fetchone()
    if row is not None:
        # Keep this field sticky: never overwrite an existing value with None.
        if normalized_club is not None:
            conn.execute(
                "UPDATE players SET current_club = ? WHERE id = ?",
                (normalized_club, row["id"]),
            )
        return row["id"]

    cursor = conn.execute(
        """
        INSERT INTO players (normalized_name, display_name, current_club)
        VALUES (?, ?, ?)
        """,
        (norm, display_name, normalized_club),
    )
    return int(cursor.lastrowid)


# --------------------------------------------------------------------------- #
# Monthly ranking persistence
# --------------------------------------------------------------------------- #


def save_monthly_ranking(
    conn: sqlite3.Connection,
    ranking: MonthlyRanking,
) -> int:
    """Persist a monthly ranking. Replaces any existing data for the same month_id.

    Returns the ranking row id.
    """
    conn.execute(
        "DELETE FROM monthly_rankings WHERE month_id = ?", (ranking.month_id,)
    )
    cursor = conn.execute(
        """
        INSERT INTO monthly_rankings (month_id, fetched_at)
        VALUES (?, ?)
        """,
        (ranking.month_id, ranking.fetched_at.isoformat()),
    )
    ranking_id = int(cursor.lastrowid)

    for entry in ranking.entries:
        player_id = upsert_player(conn, entry.player_name, entry.club)
        conn.execute(
            """
            INSERT INTO monthly_ranking_entries
                (ranking_id, position, player_id, club, average,
                 matches_scored, matches_max, is_definitive)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ranking_id,
                entry.position,
                player_id,
                normalize_club(entry.club),
                entry.average,
                entry.matches_scored,
                entry.matches_max,
                1 if entry.is_definitive else 0,
            ),
        )
    return ranking_id


# --------------------------------------------------------------------------- #
# Open classification persistence
# --------------------------------------------------------------------------- #


def save_open(conn: sqlite3.Connection, open_data: Open) -> int:
    """Persist an Open and its classification. Replaces existing data for the
    same fcb_division_id."""
    existing = conn.execute(
        "SELECT id FROM opens WHERE fcb_division_id = ?", (open_data.fcb_division_id,)
    ).fetchone()
    if existing is not None:
        conn.execute("DELETE FROM opens WHERE id = ?", (existing["id"],))

    cursor = conn.execute(
        """
        INSERT INTO opens (fcb_division_id, fcb_classification_id, name, season)
        VALUES (?, ?, ?, ?)
        """,
        (
            open_data.fcb_division_id,
            open_data.fcb_classification_id,
            open_data.name,
            open_data.season,
        ),
    )
    open_id = int(cursor.lastrowid)

    for entry in open_data.classification:
        _insert_classification_entry(conn, open_id, entry)
    return open_id


def _insert_classification_entry(
    conn: sqlite3.Connection,
    open_id: int,
    entry: OpenClassificationEntry,
) -> None:
    player_id = upsert_player(conn, entry.player_name, entry.club)
    conn.execute(
        """
        INSERT INTO open_classifications
            (open_id, position, player_id, club,
             matches_played, match_points, caramboles, entries,
             general_average, particular_average, best_series, open_points)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            open_id,
            entry.position,
            player_id,
            entry.club,
            entry.matches_played,
            entry.match_points,
            entry.caramboles,
            entry.entries,
            entry.general_average,
            entry.particular_average,
            entry.best_series,
            points_for_position(entry.position),
        ),
    )


# --------------------------------------------------------------------------- #
# Convenience readers
# --------------------------------------------------------------------------- #


def count_opens(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM opens").fetchone()
    return int(row["n"])


def count_monthly_rankings(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM monthly_rankings").fetchone()
    return int(row["n"])


def all_players(conn: sqlite3.Connection) -> Iterable[sqlite3.Row]:
    return conn.execute(
        "SELECT id, display_name, current_club FROM players ORDER BY display_name"
    )


# --------------------------------------------------------------------------- #
# Live open snapshots
# --------------------------------------------------------------------------- #


def save_live_snapshot(
    conn: sqlite3.Connection,
    fcb_division_id: int,
    payload_json: str,
    captured_at: str,
) -> int:
    """Append a live-state snapshot to the history table.

    Snapshots are never updated or deduplicated — each refresh is its own
    row. The caller decides cadence (see api/app.py).
    """
    cursor = conn.execute(
        """
        INSERT INTO open_live_snapshots (fcb_division_id, captured_at, payload_json)
        VALUES (?, ?, ?)
        """,
        (fcb_division_id, captured_at, payload_json),
    )
    return int(cursor.lastrowid)


def list_live_snapshots(
    conn: sqlite3.Connection,
    fcb_division_id: int,
    limit: int = 100,
) -> Iterable[sqlite3.Row]:
    """Return snapshots for a given Open, newest first."""
    return conn.execute(
        """
        SELECT id, captured_at FROM open_live_snapshots
        WHERE fcb_division_id = ?
        ORDER BY captured_at DESC
        LIMIT ?
        """,
        (fcb_division_id, limit),
    )


def get_live_snapshot(
    conn: sqlite3.Connection,
    snapshot_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, fcb_division_id, captured_at, payload_json
        FROM open_live_snapshots WHERE id = ?
        """,
        (snapshot_id,),
    ).fetchone()


# --------------------------------------------------------------------------- #
# Open projections (provisional bracket from the inscrits PDF)
# --------------------------------------------------------------------------- #


def save_projection(
    conn: sqlite3.Connection,
    *,
    name: str,
    season: str | None,
    num_inscriptions: int,
    source_pdf: str | None,
    payload_json: str,
    created_at: str,
    fcb_division_id: int | None = None,
    replace_id: int | None = None,
) -> int:
    """Insert (or replace, if ``replace_id`` given) an open projection.

    Re-importing the same Open should overwrite its projection rather than
    pile up duplicates, so the CLI passes ``replace_id`` when a projection
    with the same name already exists.
    """
    if replace_id is not None:
        conn.execute(
            """
            UPDATE open_projections
               SET name = ?, season = ?, num_inscriptions = ?, source_pdf = ?,
                   fcb_division_id = ?, created_at = ?, payload_json = ?
             WHERE id = ?
            """,
            (
                name, season, num_inscriptions, source_pdf,
                fcb_division_id, created_at, payload_json, replace_id,
            ),
        )
        conn.commit()
        return replace_id
    cursor = conn.execute(
        """
        INSERT INTO open_projections
            (name, season, num_inscriptions, source_pdf, fcb_division_id,
             created_at, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (name, season, num_inscriptions, source_pdf, fcb_division_id,
         created_at, payload_json),
    )
    conn.commit()
    return int(cursor.lastrowid)


def find_projection_by_name(
    conn: sqlite3.Connection, name: str
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id FROM open_projections WHERE name = ? ORDER BY id DESC LIMIT 1",
        (name,),
    ).fetchone()


def list_projections(conn: sqlite3.Connection) -> Iterable[sqlite3.Row]:
    """Return all projections, newest first (summary columns only)."""
    return conn.execute(
        """
        SELECT id, name, season, num_inscriptions, source_pdf,
               fcb_division_id, created_at
        FROM open_projections
        ORDER BY created_at DESC, id DESC
        """
    )


def get_projection(conn: sqlite3.Connection, projection_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, name, season, num_inscriptions, source_pdf,
               fcb_division_id, created_at, payload_json
        FROM open_projections WHERE id = ?
        """,
        (projection_id,),
    ).fetchone()


def delete_projection(conn: sqlite3.Connection, projection_id: int) -> None:
    conn.execute("DELETE FROM open_projections WHERE id = ?", (projection_id,))
    conn.commit()
