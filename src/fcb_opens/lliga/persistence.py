"""Persistence helpers for the Lliga (league) data model.

Each `save_*` function is idempotent for the corresponding scope:
saving a competition snapshot replaces all stored rows for that
competition, divisions, groups, jornades, encontres and partides.

Player rows are reused (via `db.upsert_player`) so that the existing
Opens / monthly-ranking history stays joinable on `player_id`.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ..db import upsert_player
from ..models import normalize_club
from .models import (
    Encontre,
    Jornada,
    JornadaSnapshot,
    LeagueSnapshot,
    Partida,
)


def save_league_snapshot(
    conn: sqlite3.Connection,
    snapshot: LeagueSnapshot,
) -> int:
    """Persist a complete league snapshot. Replaces existing rows.

    The cascade delete on `leagues` removes divisions, groups, standings,
    jornades, encontres and partides via foreign keys.
    """
    conn.execute(
        "DELETE FROM leagues WHERE fcb_competition_id = ?",
        (snapshot.competition_id,),
    )
    cur = conn.execute(
        """
        INSERT INTO leagues (fcb_competition_id, name, season, fetched_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            snapshot.competition_id,
            snapshot.name,
            snapshot.season,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    league_id = int(cur.lastrowid)

    for div_snap in snapshot.divisions:
        cur = conn.execute(
            """
            INSERT INTO league_divisions (league_id, fcb_division_id, name)
            VALUES (?, ?, ?)
            """,
            (league_id, div_snap.division.fcb_division_id, div_snap.division.name),
        )
        division_id = int(cur.lastrowid)

        for grp_snap in div_snap.groups:
            cur = conn.execute(
                """
                INSERT INTO league_groups (division_id, fcb_group_id, name)
                VALUES (?, ?, ?)
                """,
                (
                    division_id,
                    grp_snap.group.fcb_group_id,
                    grp_snap.group.name,
                ),
            )
            group_id = int(cur.lastrowid)

            for st in grp_snap.standings:
                conn.execute(
                    """
                    INSERT INTO league_team_standings
                        (group_id, position, team_name, match_points,
                         set_points, matches_played)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        group_id,
                        st.position,
                        st.team_name,
                        st.match_points,
                        st.set_points,
                        st.matches_played,
                    ),
                )

            for jor_snap in grp_snap.jornades:
                cur = conn.execute(
                    """
                    INSERT INTO league_jornades
                        (group_id, fcb_jornada_id, number, played_on)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        group_id,
                        jor_snap.jornada.fcb_jornada_id,
                        jor_snap.jornada.number,
                        jor_snap.jornada.played_on or None,
                    ),
                )
                jornada_db_id = int(cur.lastrowid)

                for enc in jor_snap.encontres:
                    cur = conn.execute(
                        """
                        INSERT INTO league_encontres
                            (jornada_id, fcb_encontre_id,
                             home_team_name, away_team_name,
                             home_match_points, away_match_points,
                             home_set_points, away_set_points)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            jornada_db_id,
                            enc.fcb_encontre_id,
                            enc.home_team_name,
                            enc.away_team_name,
                            enc.home_match_points,
                            enc.away_match_points,
                            enc.home_set_points,
                            enc.away_set_points,
                        ),
                    )
                    encontre_db_id = int(cur.lastrowid)

                    for partida in enc.partides:
                        # Pass club=None: team names like 'C.B. MONFORTE "B"'
                        # carry a team-letter suffix that doesn't belong in
                        # players.current_club (which mirrors the FCB
                        # monthly ranking's club). The team membership lives
                        # in league_encontres.{home,away}_team_name.
                        home_id = (
                            upsert_player(conn, partida.home_player_name)
                            if partida.home_player_name
                            else None
                        )
                        away_id = (
                            upsert_player(conn, partida.away_player_name)
                            if partida.away_player_name
                            else None
                        )
                        conn.execute(
                            """
                            INSERT INTO league_partides
                                (encontre_id, slot,
                                 home_player_id, home_caramboles,
                                 home_serie_major, home_punts,
                                 away_player_id, away_caramboles,
                                 away_serie_major, away_punts,
                                 entrades, arbitre, attendance,
                                 modalitat, is_played)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                encontre_db_id,
                                partida.slot,
                                home_id,
                                partida.home_caramboles,
                                partida.home_serie_major,
                                partida.home_punts,
                                away_id,
                                partida.away_caramboles,
                                partida.away_serie_major,
                                partida.away_punts,
                                partida.entrades,
                                normalize_club(partida.arbitre)
                                if partida.arbitre
                                else None,
                                partida.attendance,
                                partida.modalitat,
                                1 if partida.is_played else 0,
                            ),
                        )
    return league_id


# --------------------------------------------------------------------------- #
# Incremental-refresh support
# --------------------------------------------------------------------------- #


def get_league_id(conn: sqlite3.Connection, competition_id: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM leagues WHERE fcb_competition_id = ?", (competition_id,)
    ).fetchone()
    return int(row["id"]) if row else None


def update_league_fetched_at(
    conn: sqlite3.Connection,
    competition_id: int,
    iso_timestamp: str | None = None,
) -> None:
    ts = iso_timestamp or datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE leagues SET fetched_at = ? WHERE fcb_competition_id = ?",
        (ts, competition_id),
    )


def is_jornada_complete(
    conn: sqlite3.Connection,
    *,
    fcb_group_id: int,
    fcb_jornada_id: int,
) -> bool:
    """A jornada is "complete" only when every encontre has been scheduled
    by FCB (real id, not a synthetic negative one) AND every saved partida
    is `is_played = 1`.

    The cache hint used by the incremental scraper to decide whether
    re-fetching encontres/partides for that jornada might bring new info.
    Jornades not yet in the DB, or with any pending pairing, are NOT
    complete — otherwise once-pending encontres would never refresh after
    FCB publishes the results.
    """
    pending_row = conn.execute(
        """
        SELECT COUNT(*) AS pending
        FROM league_encontres le
        JOIN league_jornades lj ON lj.id = le.jornada_id
        JOIN league_groups lg ON lg.id = lj.group_id
        WHERE lg.fcb_group_id = ?
          AND lj.fcb_jornada_id = ?
          AND le.fcb_encontre_id < 0
        """,
        (fcb_group_id, fcb_jornada_id),
    ).fetchone()
    if pending_row and int(pending_row["pending"] or 0) > 0:
        return False

    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(lp.is_played), 0) AS played
        FROM league_jornades lj
        JOIN league_groups lg ON lg.id = lj.group_id
        JOIN league_encontres le ON le.jornada_id = lj.id
        JOIN league_partides lp ON lp.encontre_id = le.id
        WHERE lg.fcb_group_id = ? AND lj.fcb_jornada_id = ?
        """,
        (fcb_group_id, fcb_jornada_id),
    ).fetchone()
    if not row or int(row["total"] or 0) == 0:
        return False
    return int(row["played"]) == int(row["total"])


def load_jornada_from_db(
    conn: sqlite3.Connection,
    *,
    fcb_group_id: int,
    fcb_jornada_id: int,
) -> JornadaSnapshot | None:
    """Reconstruct a JornadaSnapshot from saved data.

    Used by `incremental_refresh` to reuse complete jornades without
    re-hitting the network. Returns None if the jornada is not stored.
    """
    j_row = conn.execute(
        """
        SELECT lj.id, lj.fcb_jornada_id, lj.number, lj.played_on
        FROM league_jornades lj
        JOIN league_groups lg ON lg.id = lj.group_id
        WHERE lg.fcb_group_id = ? AND lj.fcb_jornada_id = ?
        """,
        (fcb_group_id, fcb_jornada_id),
    ).fetchone()
    if j_row is None:
        return None
    jornada = Jornada(
        fcb_jornada_id=j_row["fcb_jornada_id"],
        fcb_group_id=fcb_group_id,
        number=j_row["number"],
        played_on=j_row["played_on"] or "",
    )

    enc_rows = conn.execute(
        """
        SELECT le.id, le.fcb_encontre_id,
               le.home_team_name, le.away_team_name,
               le.home_match_points, le.away_match_points,
               le.home_set_points, le.away_set_points
        FROM league_encontres le
        WHERE le.jornada_id = ?
        ORDER BY le.fcb_encontre_id
        """,
        (j_row["id"],),
    ).fetchall()

    encontres: list[Encontre] = []
    for er in enc_rows:
        partida_rows = conn.execute(
            """
            SELECT lp.slot,
                   lp.home_caramboles, lp.home_serie_major, lp.home_punts,
                   lp.away_caramboles, lp.away_serie_major, lp.away_punts,
                   lp.entrades, lp.arbitre, lp.attendance,
                   lp.modalitat, lp.is_played,
                   hp.display_name AS home_name, ap.display_name AS away_name
            FROM league_partides lp
            LEFT JOIN players hp ON hp.id = lp.home_player_id
            LEFT JOIN players ap ON ap.id = lp.away_player_id
            WHERE lp.encontre_id = ?
            ORDER BY lp.slot
            """,
            (er["id"],),
        ).fetchall()
        partides = [
            Partida(
                slot=p["slot"],
                home_player_name=p["home_name"] or "",
                home_caramboles=p["home_caramboles"],
                home_serie_major=p["home_serie_major"],
                home_punts=p["home_punts"],
                away_player_name=p["away_name"] or "",
                away_caramboles=p["away_caramboles"],
                away_serie_major=p["away_serie_major"],
                away_punts=p["away_punts"],
                entrades=p["entrades"],
                arbitre=p["arbitre"],
                attendance=p["attendance"],
                modalitat=p["modalitat"],
                is_played=bool(p["is_played"]),
            )
            for p in partida_rows
        ]
        encontres.append(
            Encontre(
                fcb_encontre_id=er["fcb_encontre_id"],
                fcb_jornada_id=jornada.fcb_jornada_id,
                home_team_name=er["home_team_name"],
                away_team_name=er["away_team_name"],
                home_match_points=er["home_match_points"],
                away_match_points=er["away_match_points"],
                home_set_points=er["home_set_points"],
                away_set_points=er["away_set_points"],
                partides=partides,
            )
        )
    return JornadaSnapshot(jornada=jornada, encontres=encontres)

