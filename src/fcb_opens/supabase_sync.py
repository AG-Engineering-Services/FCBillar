"""Push the local SQLite snapshot to the `fcb_opens` schema in Supabase.

Design choices:
  • The local SQLite stays the source of truth — the scraper writes there
    and we have the full test suite around it. Supabase is a derived
    publish target the PWA reads from.
  • Idempotent: each push deletes the league/Open/ranking row and
    re-inserts the children, so re-running after a re-scrape is safe.
  • Foreign keys cross from local SQLite ids to remote Supabase ids, so
    we maintain a `local_id → remote_id` map per entity during the push.

Auth: requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY env vars. The
service-role key bypasses RLS — keep it OUT of git, ENV files and chat.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable

from supabase import Client, create_client

SCHEMA = "fcb_opens"


# --------------------------------------------------------------------------- #
# Client + helpers
# --------------------------------------------------------------------------- #


def get_client() -> Client:
    """Return a Supabase client authenticated with the service-role key.

    The service-role bypasses RLS so the sync can write to every table.
    Read access from the PWA still respects the RLS policies.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url:
        raise RuntimeError("SUPABASE_URL env var is required")
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY env var is required")
    return create_client(url, key)


def _table(sb: Client, name: str):
    """Helper: addressing a table in the `fcb_opens` schema."""
    return sb.schema(SCHEMA).table(name)


def _chunked(rows: list[dict], n: int = 500) -> Iterable[list[dict]]:
    """Yield successive `n`-sized slices for batch inserts."""
    for i in range(0, len(rows), n):
        yield rows[i : i + n]


def _insert_in_chunks(sb: Client, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    for chunk in _chunked(rows):
        _table(sb, table).insert(chunk).execute()


@dataclass
class SyncCounters:
    players: int = 0
    monthly_rankings: int = 0
    monthly_ranking_entries: int = 0
    opens: int = 0
    open_classifications: int = 0
    leagues: int = 0
    league_divisions: int = 0
    league_groups: int = 0
    league_team_standings: int = 0
    league_jornades: int = 0
    league_encontres: int = 0
    league_partides: int = 0


# --------------------------------------------------------------------------- #
# Players (the central anchor — all other tables FK to players.id)
# --------------------------------------------------------------------------- #


def _sync_players(
    sb: Client, conn: sqlite3.Connection
) -> dict[str, int]:
    """Upsert players into Supabase keyed by `normalized_name`.

    Returns a `{normalized_name: remote_id}` map used by every downstream
    sync to remap local FKs.
    """
    rows = list(
        conn.execute(
            "SELECT normalized_name, display_name, current_club FROM players"
        )
    )
    if not rows:
        return {}

    # supabase-py's upsert needs a list of dicts; on_conflict targets the
    # natural key column. We split into chunks because the underlying
    # PostgREST request has a payload-size cap.
    payload = [
        {
            "normalized_name": r["normalized_name"],
            "display_name": r["display_name"],
            "current_club": r["current_club"],
        }
        for r in rows
    ]
    for chunk in _chunked(payload):
        _table(sb, "players").upsert(
            chunk, on_conflict="normalized_name"
        ).execute()

    # Read back to discover remote ids.
    remote = (
        _table(sb, "players")
        .select("id, normalized_name")
        .limit(100000)
        .execute()
    )
    return {r["normalized_name"]: int(r["id"]) for r in remote.data}


# --------------------------------------------------------------------------- #
# Monthly rankings
# --------------------------------------------------------------------------- #


def _sync_monthly_rankings(
    sb: Client,
    conn: sqlite3.Connection,
    player_id_map: dict[str, int],
) -> tuple[int, int]:
    """Replace every monthly_rankings row + entries with the local copy.

    Returns (n_rankings, n_entries).
    """
    local_rankings = list(
        conn.execute(
            "SELECT id, month_id, fetched_at FROM monthly_rankings ORDER BY month_id"
        )
    )
    if not local_rankings:
        return (0, 0)

    # Wipe — ON DELETE CASCADE cleans up entries.
    _table(sb, "monthly_rankings").delete().neq("id", -1).execute()

    # Build payload and insert; capture remote ids in order.
    inserted = (
        _table(sb, "monthly_rankings")
        .insert(
            [
                {
                    "month_id": r["month_id"],
                    "fetched_at": r["fetched_at"],
                }
                for r in local_rankings
            ]
        )
        .execute()
    )
    remote_id_by_month: dict[int, int] = {
        r["month_id"]: int(r["id"]) for r in inserted.data
    }

    # Entries: join on local ranking id → month_id → remote ranking id;
    # join on local player id → normalized_name → remote player id.
    norm_by_local_pid: dict[int, str] = {
        int(r["id"]): r["normalized_name"]
        for r in conn.execute("SELECT id, normalized_name FROM players")
    }
    entry_rows = list(
        conn.execute(
            """
            SELECT mre.position, mre.player_id, mre.club, mre.average,
                   mre.matches_scored, mre.matches_max, mre.is_definitive,
                   mr.month_id
            FROM monthly_ranking_entries mre
            JOIN monthly_rankings mr ON mr.id = mre.ranking_id
            ORDER BY mr.month_id, mre.position
            """
        )
    )
    payload: list[dict[str, Any]] = []
    for r in entry_rows:
        ranking_id = remote_id_by_month.get(r["month_id"])
        norm = norm_by_local_pid.get(int(r["player_id"]))
        if ranking_id is None or norm is None:
            continue
        player_id = player_id_map.get(norm)
        if player_id is None:
            continue
        payload.append(
            {
                "ranking_id": ranking_id,
                "position": r["position"],
                "player_id": player_id,
                "club": r["club"],
                "average": r["average"],
                "matches_scored": r["matches_scored"],
                "matches_max": r["matches_max"],
                "is_definitive": bool(r["is_definitive"]),
            }
        )
    _insert_in_chunks(sb, "monthly_ranking_entries", payload)
    return (len(local_rankings), len(payload))


# --------------------------------------------------------------------------- #
# Opens
# --------------------------------------------------------------------------- #


def _sync_opens(
    sb: Client,
    conn: sqlite3.Connection,
    player_id_map: dict[str, int],
) -> tuple[int, int]:
    """Replace every Open + classification with the local snapshot."""
    local_opens = list(
        conn.execute(
            """
            SELECT id, fcb_division_id, fcb_classification_id, name, season
            FROM opens
            ORDER BY fcb_division_id
            """
        )
    )
    if not local_opens:
        return (0, 0)

    _table(sb, "opens").delete().neq("id", -1).execute()

    inserted = (
        _table(sb, "opens")
        .insert(
            [
                {
                    "fcb_division_id": o["fcb_division_id"],
                    "fcb_classification_id": o["fcb_classification_id"],
                    "name": o["name"],
                    "season": o["season"],
                }
                for o in local_opens
            ]
        )
        .execute()
    )
    remote_open_id_by_div: dict[int, int] = {
        r["fcb_division_id"]: int(r["id"]) for r in inserted.data
    }

    # Classification entries.
    norm_by_local_pid: dict[int, str] = {
        int(r["id"]): r["normalized_name"]
        for r in conn.execute("SELECT id, normalized_name FROM players")
    }
    rows = list(
        conn.execute(
            """
            SELECT oc.position, oc.player_id, oc.club,
                   oc.matches_played, oc.match_points, oc.caramboles, oc.entries,
                   oc.general_average, oc.particular_average,
                   oc.best_series, oc.open_points,
                   o.fcb_division_id
            FROM open_classifications oc
            JOIN opens o ON o.id = oc.open_id
            ORDER BY o.fcb_division_id, oc.position
            """
        )
    )
    payload: list[dict[str, Any]] = []
    for r in rows:
        open_id = remote_open_id_by_div.get(r["fcb_division_id"])
        norm = norm_by_local_pid.get(int(r["player_id"]))
        if open_id is None or norm is None:
            continue
        player_id = player_id_map.get(norm)
        if player_id is None:
            continue
        payload.append(
            {
                "open_id": open_id,
                "position": r["position"],
                "player_id": player_id,
                "club": r["club"],
                "matches_played": r["matches_played"],
                "match_points": r["match_points"],
                "caramboles": r["caramboles"],
                "entries": r["entries"],
                "general_average": r["general_average"],
                "particular_average": r["particular_average"],
                "best_series": r["best_series"],
                "open_points": r["open_points"],
            }
        )
    _insert_in_chunks(sb, "open_classifications", payload)
    return (len(local_opens), len(payload))


# --------------------------------------------------------------------------- #
# Leagues — full tree
# --------------------------------------------------------------------------- #


def _sync_leagues(
    sb: Client,
    conn: sqlite3.Connection,
    player_id_map: dict[str, int],
    counters: SyncCounters,
    on_progress,
) -> None:
    """Replace every league + division + group + jornada + encontre + partida."""
    local_leagues = list(
        conn.execute(
            """
            SELECT id, fcb_competition_id, name, season, fetched_at
            FROM leagues
            ORDER BY fcb_competition_id
            """
        )
    )
    if not local_leagues:
        return

    # ON DELETE CASCADE handles divisions/groups/jornades/encontres/partides.
    _table(sb, "leagues").delete().neq("id", -1).execute()

    inserted_leagues = (
        _table(sb, "leagues")
        .insert(
            [
                {
                    "fcb_competition_id": lg["fcb_competition_id"],
                    "name": lg["name"],
                    "season": lg["season"],
                    "fetched_at": lg["fetched_at"],
                }
                for lg in local_leagues
            ]
        )
        .execute()
    )
    remote_league_by_comp: dict[int, int] = {
        r["fcb_competition_id"]: int(r["id"]) for r in inserted_leagues.data
    }
    counters.leagues = len(inserted_leagues.data)

    norm_by_local_pid: dict[int, str] = {
        int(r["id"]): r["normalized_name"]
        for r in conn.execute("SELECT id, normalized_name FROM players")
    }

    for lg in local_leagues:
        on_progress("league", lg["name"])
        remote_league_id = remote_league_by_comp[lg["fcb_competition_id"]]
        _sync_one_league(
            sb,
            conn,
            local_league_id=int(lg["id"]),
            remote_league_id=remote_league_id,
            player_id_map=player_id_map,
            norm_by_local_pid=norm_by_local_pid,
            counters=counters,
            on_progress=on_progress,
        )


def _sync_one_league(
    sb: Client,
    conn: sqlite3.Connection,
    *,
    local_league_id: int,
    remote_league_id: int,
    player_id_map: dict[str, int],
    norm_by_local_pid: dict[int, str],
    counters: SyncCounters,
    on_progress,
) -> None:
    # Divisions.
    local_divisions = list(
        conn.execute(
            """
            SELECT id, fcb_division_id, name
            FROM league_divisions
            WHERE league_id = ?
            ORDER BY fcb_division_id
            """,
            (local_league_id,),
        )
    )
    if not local_divisions:
        return
    inserted_div = (
        _table(sb, "league_divisions")
        .insert(
            [
                {
                    "league_id": remote_league_id,
                    "fcb_division_id": d["fcb_division_id"],
                    "name": d["name"],
                }
                for d in local_divisions
            ]
        )
        .execute()
    )
    counters.league_divisions += len(inserted_div.data)
    remote_div_by_local: dict[int, int] = {
        local_divisions[i]["id"]: int(inserted_div.data[i]["id"])
        for i in range(len(local_divisions))
    }

    for d in local_divisions:
        on_progress("division", d["name"])
        _sync_one_division(
            sb,
            conn,
            local_division_id=int(d["id"]),
            remote_division_id=remote_div_by_local[int(d["id"])],
            player_id_map=player_id_map,
            norm_by_local_pid=norm_by_local_pid,
            counters=counters,
            on_progress=on_progress,
        )


def _sync_one_division(
    sb: Client,
    conn: sqlite3.Connection,
    *,
    local_division_id: int,
    remote_division_id: int,
    player_id_map: dict[str, int],
    norm_by_local_pid: dict[int, str],
    counters: SyncCounters,
    on_progress,
) -> None:
    # Groups.
    local_groups = list(
        conn.execute(
            """
            SELECT id, fcb_group_id, name
            FROM league_groups
            WHERE division_id = ?
            ORDER BY fcb_group_id
            """,
            (local_division_id,),
        )
    )
    if not local_groups:
        return
    inserted_grp = (
        _table(sb, "league_groups")
        .insert(
            [
                {
                    "division_id": remote_division_id,
                    "fcb_group_id": g["fcb_group_id"],
                    "name": g["name"],
                }
                for g in local_groups
            ]
        )
        .execute()
    )
    counters.league_groups += len(inserted_grp.data)
    remote_grp_by_local: dict[int, int] = {
        local_groups[i]["id"]: int(inserted_grp.data[i]["id"])
        for i in range(len(local_groups))
    }

    for g in local_groups:
        on_progress("group", g["name"])
        _sync_one_group(
            sb,
            conn,
            local_group_id=int(g["id"]),
            remote_group_id=remote_grp_by_local[int(g["id"])],
            player_id_map=player_id_map,
            norm_by_local_pid=norm_by_local_pid,
            counters=counters,
        )


def _sync_one_group(
    sb: Client,
    conn: sqlite3.Connection,
    *,
    local_group_id: int,
    remote_group_id: int,
    player_id_map: dict[str, int],
    norm_by_local_pid: dict[int, str],
    counters: SyncCounters,
) -> None:
    # Standings.
    standings_rows = [
        {
            "group_id": remote_group_id,
            "position": r["position"],
            "team_name": r["team_name"],
            "match_points": r["match_points"],
            "set_points": r["set_points"],
            "matches_played": r["matches_played"],
        }
        for r in conn.execute(
            """
            SELECT position, team_name, match_points, set_points, matches_played
            FROM league_team_standings
            WHERE group_id = ?
            ORDER BY position
            """,
            (local_group_id,),
        )
    ]
    _insert_in_chunks(sb, "league_team_standings", standings_rows)
    counters.league_team_standings += len(standings_rows)

    # Jornades.
    local_jornades = list(
        conn.execute(
            """
            SELECT id, fcb_jornada_id, number, played_on
            FROM league_jornades
            WHERE group_id = ?
            ORDER BY number
            """,
            (local_group_id,),
        )
    )
    if not local_jornades:
        return
    inserted_j = (
        _table(sb, "league_jornades")
        .insert(
            [
                {
                    "group_id": remote_group_id,
                    "fcb_jornada_id": j["fcb_jornada_id"],
                    "number": j["number"],
                    "played_on": j["played_on"],
                }
                for j in local_jornades
            ]
        )
        .execute()
    )
    counters.league_jornades += len(inserted_j.data)
    remote_j_by_local: dict[int, int] = {
        local_jornades[i]["id"]: int(inserted_j.data[i]["id"])
        for i in range(len(local_jornades))
    }

    # Encontres.
    local_encontres = list(
        conn.execute(
            f"""
            SELECT id, jornada_id, fcb_encontre_id,
                   home_team_name, away_team_name,
                   home_match_points, away_match_points,
                   home_set_points, away_set_points
            FROM league_encontres
            WHERE jornada_id IN ({','.join('?' for _ in local_jornades)})
            """,
            tuple(int(j["id"]) for j in local_jornades),
        )
    )
    if not local_encontres:
        return
    inserted_e = (
        _table(sb, "league_encontres")
        .insert(
            [
                {
                    "jornada_id": remote_j_by_local[int(e["jornada_id"])],
                    "fcb_encontre_id": e["fcb_encontre_id"],
                    "home_team_name": e["home_team_name"],
                    "away_team_name": e["away_team_name"],
                    "home_match_points": e["home_match_points"],
                    "away_match_points": e["away_match_points"],
                    "home_set_points": e["home_set_points"],
                    "away_set_points": e["away_set_points"],
                }
                for e in local_encontres
            ]
        )
        .execute()
    )
    counters.league_encontres += len(inserted_e.data)
    remote_e_by_local: dict[int, int] = {
        local_encontres[i]["id"]: int(inserted_e.data[i]["id"])
        for i in range(len(local_encontres))
    }

    # Partides.
    local_encontre_ids = tuple(int(e["id"]) for e in local_encontres)
    partides = list(
        conn.execute(
            f"""
            SELECT encontre_id, slot,
                   home_player_id, home_caramboles, home_serie_major, home_punts,
                   away_player_id, away_caramboles, away_serie_major, away_punts,
                   entrades, arbitre, attendance, modalitat, is_played
            FROM league_partides
            WHERE encontre_id IN ({','.join('?' for _ in local_encontre_ids)})
            ORDER BY encontre_id, slot
            """,
            local_encontre_ids,
        )
    )

    def _remote_player(local_pid) -> int | None:
        if local_pid is None:
            return None
        norm = norm_by_local_pid.get(int(local_pid))
        if norm is None:
            return None
        return player_id_map.get(norm)

    payload = [
        {
            "encontre_id": remote_e_by_local[int(p["encontre_id"])],
            "slot": p["slot"],
            "home_player_id": _remote_player(p["home_player_id"]),
            "home_caramboles": p["home_caramboles"],
            "home_serie_major": p["home_serie_major"],
            "home_punts": p["home_punts"],
            "away_player_id": _remote_player(p["away_player_id"]),
            "away_caramboles": p["away_caramboles"],
            "away_serie_major": p["away_serie_major"],
            "away_punts": p["away_punts"],
            "entrades": p["entrades"],
            "arbitre": p["arbitre"],
            "attendance": p["attendance"],
            "modalitat": p["modalitat"],
            "is_played": bool(p["is_played"]),
        }
        for p in partides
    ]
    _insert_in_chunks(sb, "league_partides", payload)
    counters.league_partides += len(payload)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #


def sync_all(
    conn: sqlite3.Connection,
    *,
    on_progress=None,
) -> SyncCounters:
    """Push the entire local SQLite to Supabase.

    Idempotent: each call replaces all rows in `fcb_opens.*`. Streams
    progress via `on_progress(level, message)` so the CLI can render a
    log without coupling this module to print().
    """
    if on_progress is None:
        on_progress = lambda *_a, **_kw: None  # noqa: E731

    sb = get_client()
    counters = SyncCounters()

    on_progress("phase", "players")
    player_id_map = _sync_players(sb, conn)
    counters.players = len(player_id_map)

    on_progress("phase", "monthly_rankings")
    n_rk, n_entries = _sync_monthly_rankings(sb, conn, player_id_map)
    counters.monthly_rankings = n_rk
    counters.monthly_ranking_entries = n_entries

    on_progress("phase", "opens")
    n_opens, n_class = _sync_opens(sb, conn, player_id_map)
    counters.opens = n_opens
    counters.open_classifications = n_class

    on_progress("phase", "leagues")
    _sync_leagues(sb, conn, player_id_map, counters, on_progress)

    return counters
