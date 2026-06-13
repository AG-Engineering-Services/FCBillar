"""Tests for the live-Open group seeding (`_seed_unplayed_groups`).

Rule (per the user): while a group hasn't started, order its players by the
Rànquing Català d'Opens, EXCEPT players who advanced from a previous phase,
who are always the last seed of their group (the 3rd in a group of 3).
Started groups (any match played) keep their result-driven order.
"""

from __future__ import annotations

from fcb_opens.scraper.open_live import (
    Group,
    GroupStanding,
    MatchResult,
    _seed_unplayed_groups,
)


def _st(name: str) -> GroupStanding:
    return GroupStanding(player_name=name, club="", punts=0, mitjana=0.0)


def _match(a: str, b: str, *, played: bool) -> MatchResult:
    return MatchResult(
        player_a=a,
        player_b=b,
        punts_a=0,
        punts_b=0,
        caramboles_a=0,
        caramboles_b=0,
        serie_major_a=0,
        serie_major_b=0,
        entrades=10 if played else None,
        arbitre=None,
    )


def _group(names: list[str], *, started: bool = False) -> Group:
    matches = (_match(names[0], names[-1], played=started),) if len(names) >= 2 else ()
    return Group(label="Grup A", url="", standings=tuple(_st(n) for n in names), matches=matches)


def _order(g: Group) -> list[str]:
    return [s.player_name for s in g.standings]


def test_orders_unplayed_group_by_opens_ranking():
    g = _group(["B", "A", "C"])
    rank = {"A": 1, "B": 3, "C": 2}
    out = _seed_unplayed_groups((g,), frozenset(), rank)
    assert _order(out[0]) == ["A", "C", "B"]


def test_advancer_is_always_last_regardless_of_ranking():
    # Z has the 2nd-best ranking but advanced from a previous phase → goes 3rd.
    g = _group(["X", "Y", "Z"])
    rank = {"X": 1, "Y": 5, "Z": 2}
    out = _seed_unplayed_groups((g,), frozenset({"Z"}), rank)
    assert _order(out[0]) == ["X", "Y", "Z"]


def test_unranked_players_keep_federation_order_after_ranked():
    g = _group(["P", "Q", "R", "S"])
    rank = {"Q": 2, "S": 1}  # P and R are not in the ranking
    out = _seed_unplayed_groups((g,), frozenset(), rank)
    assert _order(out[0]) == ["S", "Q", "P", "R"]


def test_started_group_is_left_untouched():
    g = _group(["B", "A"], started=True)
    rank = {"A": 1, "B": 2}
    out = _seed_unplayed_groups((g,), frozenset(), rank)
    assert _order(out[0]) == ["B", "A"]


def test_without_ranking_advancers_still_go_last():
    # Backward-compatible fallback: no ranking → keep federation order but push
    # the advancer to the end.
    g = _group(["A", "ADV", "B"])
    out = _seed_unplayed_groups((g,), frozenset({"ADV"}), None)
    assert _order(out[0]) == ["A", "B", "ADV"]


def test_no_ranking_no_advancers_is_a_noop():
    g = _group(["C", "A", "B"])
    out = _seed_unplayed_groups((g,), frozenset(), None)
    assert out[0] is g  # same object, untouched


def test_name_matching_is_case_and_whitespace_insensitive():
    g = _group(["garcía  alarcón, ricardo", "MORENO CORTÉS, ARMAND"])
    rank = {"MORENO CORTÉS, ARMAND": 1, "GARCÍA ALARCÓN, RICARDO": 5}
    out = _seed_unplayed_groups((g,), frozenset(), rank)
    assert _order(out[0]) == ["MORENO CORTÉS, ARMAND", "garcía  alarcón, ricardo"]
