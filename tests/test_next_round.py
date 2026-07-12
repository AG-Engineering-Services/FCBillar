"""Tests del muntatge de la ronda següent des dels classificats segurs."""

from __future__ import annotations

from fcb_opens.next_round import (
    RoundWinner,
    group_is_closed,
    rank_winners,
    resolve_next_round,
    secured_winners,
)
from fcb_opens.scraper.open_live import (
    Group,
    GroupStanding,
    MatchResult,
    PhaseDetail,
    PhaseRef,
)


def _match(a, b, ca, cb, sma=0, smb=0, ent=50):
    return MatchResult(
        player_a=a, player_b=b, punts_a=0, punts_b=0,
        caramboles_a=ca, caramboles_b=cb, serie_major_a=sma, serie_major_b=smb,
        entrades=ent, arbitre=None,
    )


def _group(label, standings, matches):
    return Group(
        label=label, url="", venue=None,
        standings=tuple(GroupStanding(*s) for s in standings),
        matches=tuple(matches),
    )


# --------------------------------------------------------------------------- #
# rank_winners: punts DESC, mitjana DESC, sèrie major DESC, nom
# --------------------------------------------------------------------------- #


def test_rank_winners_serie_major_tiebreak():
    """Empat a punts i mitjana → mana la sèrie major (cas Aguilera vs Miguel)."""
    aguilera = RoundWinner("AGUILERA", "", "Grup AA", 4, 0.741, 5)
    miguel = RoundWinner("SANCHEZ BARRERA, MIGUEL", "", "Grup Q", 4, 0.741, 6)
    ranked = rank_winners([aguilera, miguel])
    assert [w.player_name for w in ranked] == ["SANCHEZ BARRERA, MIGUEL", "AGUILERA"]


def test_rank_winners_full_order():
    ws = [
        RoundWinner("A", "", "g1", 4, 0.5, 3),
        RoundWinner("B", "", "g2", 4, 0.9, 2),   # més mitjana → primer
        RoundWinner("C", "", "g3", 2, 1.5, 9),   # menys punts → últim tot i mitjana alta
    ]
    assert [w.player_name for w in rank_winners(ws)] == ["B", "A", "C"]


def test_rank_winners_name_is_last_tiebreak():
    ws = [
        RoundWinner("ZZZ", "", "g1", 4, 0.7, 5),
        RoundWinner("AAA", "", "g2", 4, 0.7, 5),
    ]
    assert [w.player_name for w in rank_winners(ws)] == ["AAA", "ZZZ"]


# --------------------------------------------------------------------------- #
# group_is_closed
# --------------------------------------------------------------------------- #


def test_group_closed_all_played():
    g = _group("Grup A", [("X", "", 4, 1.0)], [_match("X", "Y", 25, 10)])
    assert group_is_closed(g) is True


def test_group_open_pending_match():
    g = _group(
        "Grup A", [("X", "", 2, 1.0)],
        [_match("X", "Y", 25, 10), MatchResult("X", "Z", 0, 0, 0, 0, 0, 0, None, None)],
    )
    assert group_is_closed(g) is False


def test_group_closed_no_show():
    # Grup de 3 amb Z no presentat: X i Y juguen dos cops → tancat amb 2 partides.
    g = _group(
        "Grup A", [("X", "", 4, 1.0)],
        [_match("X", "Y", 25, 10), _match("Y", "X", 12, 25)],
    )
    assert group_is_closed(g) is True


# --------------------------------------------------------------------------- #
# secured_winners: 1r de cada grup REGULAR i TANCAT
# --------------------------------------------------------------------------- #


def test_secured_winners_only_closed_regular():
    closed = _group("Grup A", [("WIN_A", "CB", 4, 1.2)], [_match("WIN_A", "L", 25, 8, sma=7)])
    open_g = _group(
        "Grup B", [("LEAD_B", "", 2, 0.9)],
        [_match("LEAD_B", "L2", 25, 5), MatchResult("LEAD_B", "L3", 0, 0, 0, 0, 0, 0, None, None)],
    )
    reservats = _group("Grup ww", [("R", "", 0, 0.0)], [])  # no regular
    phase = PhaseDetail(ref=PhaseRef("PRE-PREVIA", "group", ""), groups=(closed, open_g, reservats))
    winners = secured_winners(phase)
    assert [w.player_name for w in winners] == ["WIN_A"]
    assert winners[0].serie_major == 7  # màx SM de les partides del grup
    assert winners[0].punts == 4


# --------------------------------------------------------------------------- #
# resolve_next_round: omple placeholders <k>-<fase> per rank
# --------------------------------------------------------------------------- #


def _proj_group(label, players):
    return {"label": label, "players": players}


def test_resolve_fills_placeholders_by_rank():
    winners = [
        RoundWinner("BEST", "", "Grup Q", 4, 1.0, 5),
        RoundWinner("SECOND", "", "Grup R", 4, 0.8, 4),
    ]
    ranked = rank_winners(winners)
    groups = [
        _proj_group("A", [
            {"slot": 0, "kind": "player", "player_name": "SEED1"},
            {"slot": 1, "kind": "winner", "placeholder": "2-PP", "label": "Guanyador ..."},
        ]),
        _proj_group("B", [
            {"slot": 0, "kind": "winner", "placeholder": "1-PP", "label": "Guanyador ..."},
            {"slot": 1, "kind": "winner", "placeholder": "3-PP", "label": "Guanyador ..."},
        ]),
    ]
    out, nres, npend = resolve_next_round(groups, ranked, "PP")
    assert (nres, npend) == (2, 1)
    # 1-PP → BEST, 2-PP → SECOND, 3-PP → pendent (només 2 guanyadors segurs)
    assert out[0]["players"][1]["player_name"] == "SECOND"
    assert out[0]["players"][1]["seed_rank"] == 2
    assert out[1]["players"][0]["player_name"] == "BEST"
    assert out[1]["players"][1].get("pending") is True
    # el seed directe no es toca
    assert out[0]["players"][0]["player_name"] == "SEED1"


def test_resolve_ignores_other_phase_placeholders():
    ranked = [RoundWinner("W", "", "g", 4, 1.0, 5)]
    groups = [_proj_group("Q", [
        {"slot": 0, "kind": "winner", "placeholder": "1-PPP", "label": "..."},  # altra fase
    ])]
    out, nres, npend = resolve_next_round(groups, ranked, "PP")
    assert (nres, npend) == (0, 0)
    assert out[0]["players"][0]["kind"] == "winner"  # intacte
