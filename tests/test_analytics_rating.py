"""Tests del rendiment per nivell d'oponent (fcbillar.analytics).

Franges centrades en el nivell del jugador (±0,3 en passos de 0,1, cues
agrupades) + indicadors (índex ponderat, creuament 50%)."""

from __future__ import annotations

import sqlite3

from fcbillar.analytics import (
    _centered_buckets,
    _crossover,
    _weighted_index,
    rating_breakdown,
)
from fcbillar.db.migrations import ensure_schema


def test_centered_buckets_window_and_tails() -> None:
    # Jugador de nivell 0,6 → cues < 0,3 i > 0,9, mig de 0,1 en 0,1.
    games = [(1, 0.2), (1, 0.35), (-1, 0.6), (1, 0.89), (-1, 0.95)]
    b = _centered_buckets(games, 0.6)
    assert [x["label"] for x in b] == [
        "< 0,3", "0,3-0,4", "0,4-0,5", "0,5-0,6", "0,6-0,7", "0,7-0,8", "0,8-0,9", "> 0,9"
    ]
    assert b[0]["wins"] == 1  # 0,2 → cua inferior
    assert b[1]["wins"] == 1  # 0,35 → 0,3-0,4
    assert b[4]["losses"] == 1  # 0,6 → 0,6-0,7
    assert b[6]["wins"] == 1  # 0,89 → 0,8-0,9
    assert b[-1]["losses"] == 1  # 0,95 → cua superior


def test_centered_buckets_drops_low_tail_for_weak_player() -> None:
    # Nivell baix: la cua inferior cauria sota 0,0, així que no s'hi posa.
    b = _centered_buckets([(1, 0.2)], 0.2)
    assert not any(x["label"].startswith("<") for x in b)
    assert b[-1]["label"] == "> 0,5"


def test_weighted_index_rewards_beating_strong() -> None:
    assert _weighted_index([(1, 1.0), (-1, 0.5)]) == 66.7
    assert _weighted_index([(0, 0.5)]) is None


def test_crossover_interpolates_50pct() -> None:
    games = [(1, 0.4), (1, 0.4), (1, 0.7), (-1, 0.7), (-1, 1.0), (-1, 1.0)]
    # Centre 0,7: franges decisives creuen el 50% cap a 0,7.
    cx = _crossover(_centered_buckets(games, 0.7))
    assert cx is not None and 0.6 <= cx <= 0.8


def _setup(tmp_path) -> sqlite3.Connection:
    """P (nivell 0,6 al rànquing) contra 4 rivals de nivell conegut."""
    conn = ensure_schema(tmp_path / "t.db")
    conn.row_factory = sqlite3.Row
    tb = conn.execute("SELECT id FROM modalitats WHERE codi_fcb = 1").fetchone()["id"]
    for pid, nom in [(1, "P"), (2, "A"), (3, "B"), (4, "C"), (5, "D")]:
        conn.execute("INSERT INTO players (id, fcb_id, nom) VALUES (?,?,?)", (pid, f"f{pid}", nom))
    conn.execute(
        "INSERT INTO rankings (id, num_seq, modalitat_id, url, format_url) VALUES (1,1,?,?,?)",
        (tb, "u", "data"),
    )
    for player_id, mitjana in [(1, 0.6), (2, 0.4), (3, 0.6), (4, 0.9), (5, 1.2)]:
        conn.execute(
            "INSERT INTO ranking_entries (ranking_id, player_id, mitjana_general) VALUES (1,?,?)",
            (player_id, mitjana),
        )

    def game(gid: str, p2: int, winner: int) -> None:
        conn.execute(
            "INSERT INTO games (id, data_partida, modalitat_id, player1_id, player2_id, "
            "caramboles1, caramboles2, entrades, guanyador_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (gid, "2025-01-01", tb, 1, p2, 40, 30, 30, winner),
        )

    game("gA", 2, 1)  # P guanya A (0,4)
    game("gB", 3, 1)  # P guanya B (0,6)
    game("gC", 4, 4)  # P perd amb C (0,9)
    game("gD", 5, 5)  # P perd amb D (1,2)
    for gid, opp in [("gA", 2), ("gB", 3), ("gC", 4), ("gD", 5)]:
        conn.execute(
            "INSERT INTO ranking_game_links (ranking_id, game_id, player_id_origen) VALUES (1,?,?)",
            (gid, opp),
        )
    return conn


def test_rating_breakdown_end_to_end(tmp_path) -> None:
    prof = rating_breakdown(_setup(tmp_path), 1, [1])[1]
    assert prof["center"] == 0.6  # nivell de P al rànquing
    assert prof["total"] == 4
    assert len(prof["buckets"]) == 8  # cua + 6 franges + cua
    assert sum(b["wins"] for b in prof["buckets"]) == 2
    assert sum(b["losses"] for b in prof["buckets"]) == 2
    # Índex ponderat = 100·(0,4+0,6)/(0,4+0,6+0,9+1,2) = 32,3.
    assert prof["weighted_index"] == 32.3


def test_rating_breakdown_non_tres_bandes_is_empty(tmp_path) -> None:
    assert rating_breakdown(_setup(tmp_path), 2, [1]) == {}
