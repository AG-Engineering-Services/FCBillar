"""Tests del rendiment per nivell d'oponent (fcbillar.analytics).

Franges per quantils (cada eix ~ el mateix nombre de partides) + indicadors
(índex ponderat, creuament 50%)."""

from __future__ import annotations

import sqlite3

from fcbillar.analytics import (
    _crossover,
    _quantile_buckets,
    _weighted_index,
    rating_breakdown,
)
from fcbillar.db.migrations import ensure_schema


def test_quantile_equal_counts() -> None:
    # 16 partides amb mitjanes distintes → 8 franges de 2 partides cada una.
    games = [(1 if i % 2 else -1, round(0.10 + i * 0.10, 2)) for i in range(16)]
    buckets = _quantile_buckets(games, 8)
    assert len(buckets) == 8
    assert all(b["wins"] + b["losses"] + b["draws"] == 2 for b in buckets)
    assert buckets[0]["rating_min"] <= buckets[-1]["rating_max"]


def test_quantile_keeps_equal_ratings_together() -> None:
    # Sis rivals de 0,50 no es poden partir entre franges.
    games = [(1, 0.5)] * 6 + [(-1, 0.9), (-1, 1.0)]
    buckets = _quantile_buckets(games, 2)
    assert buckets[0]["wins"] + buckets[0]["losses"] == 6  # tots els 0,50 junts
    assert buckets[0]["label"] == "0,50"


def test_weighted_index_rewards_beating_strong() -> None:
    assert _weighted_index([(1, 1.0), (-1, 0.5)]) == 66.7
    assert _weighted_index([(0, 0.5)]) is None


def test_crossover_interpolates_50pct() -> None:
    games = [(1, 0.4)] * 4 + [(1, 0.7), (-1, 0.7)] * 2 + [(-1, 1.0)] * 4
    cx = _crossover(_quantile_buckets(games, 3))
    assert cx is not None and 0.5 <= cx <= 0.9


def _setup(tmp_path) -> sqlite3.Connection:
    """P contra 4 rivals de nivell conegut (via link): guanya els fluixos."""
    conn = ensure_schema(tmp_path / "t.db")
    conn.row_factory = sqlite3.Row
    tb = conn.execute("SELECT id FROM modalitats WHERE codi_fcb = 1").fetchone()["id"]
    for pid, nom in [(1, "P"), (2, "A"), (3, "B"), (4, "C"), (5, "D")]:
        conn.execute("INSERT INTO players (id, fcb_id, nom) VALUES (?,?,?)", (pid, f"f{pid}", nom))
    conn.execute(
        "INSERT INTO rankings (id, num_seq, modalitat_id, url, format_url) VALUES (1,1,?,?,?)",
        (tb, "u", "data"),
    )
    for player_id, mitjana in [(2, 0.4), (3, 0.6), (4, 0.9), (5, 1.2)]:
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
    assert prof["total"] == 4
    assert sum(b["wins"] for b in prof["buckets"]) == 2
    assert sum(b["losses"] for b in prof["buckets"]) == 2
    # Índex ponderat = 100·(0,4+0,6)/(0,4+0,6+0,9+1,2) = 32,3.
    assert prof["weighted_index"] == 32.3
    assert prof["crossover"] is not None


def test_rating_breakdown_modality_without_games_is_empty(tmp_path) -> None:
    # El setup només té partides de Tres bandes; una modalitat sense partides → {}.
    assert rating_breakdown(_setup(tmp_path), 4, [1]) == {}
