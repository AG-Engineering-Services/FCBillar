"""Tests for the live-Open KO phase: robust winner detection and the
per-round re-seeding rule.

Re-seeding rule (per the user): the qualifiers of a KO round are re-ordered
for the next round by the mitjana they made IN THAT ROUND ONLY (not the
cumulative one across the whole Open), then paired 1-vs-N, 2-vs-(N-1), …

Winner rule: FCB isn't consistent with the PUNTS column in KO rounds, so the
winner is decided by punts → else caramboles → else the Observacions tie-break.
"""

from __future__ import annotations

from fcb_opens.scraper.open_live import (
    Group,
    GroupStanding,
    MatchResult,
    PhaseDetail,
    PhaseRef,
    _dedupe_ko_matches,
    _ko_winner,
    compute_advancing_players,
    compute_next_ko_round,
)


def _m(
    a: str,
    b: str,
    *,
    punts: tuple[int, int] = (0, 0),
    car: tuple[int, int] = (0, 0),
    ent: int | None = None,
    sm: tuple[int, int] = (0, 0),
    obs: str | None = None,
) -> MatchResult:
    return MatchResult(
        player_a=a,
        player_b=b,
        punts_a=punts[0],
        punts_b=punts[1],
        caramboles_a=car[0],
        caramboles_b=car[1],
        serie_major_a=sm[0],
        serie_major_b=sm[1],
        entrades=ent,
        arbitre=None,
        observations=obs,
    )


def _group_phase(match: MatchResult) -> PhaseDetail:
    g = Group(label="Grup A", url="", standings=(), matches=(match,))
    return PhaseDetail(ref=PhaseRef(label="PRÈVIA", kind="group", url=""), groups=(g,))


def _ko_phase(label: str, matches: tuple[MatchResult, ...]) -> PhaseDetail:
    return PhaseDetail(ref=PhaseRef(label=label, kind="ko", url=""), ko_matches=matches)


# --------------------------------------------------------------------------- #
# _ko_winner
# --------------------------------------------------------------------------- #


def test_winner_by_punts():
    m = _m("A", "B", punts=(1, 0), car=(40, 38), ent=20)
    assert _ko_winner(m) == "A"
    m = _m("A", "B", punts=(0, 2), car=(30, 40), ent=20)
    assert _ko_winner(m) == "B"


def test_winner_by_caramboles_when_punts_tied():
    # FCB left PUNTS at 0-0 but the caramboles make the winner obvious.
    m = _m("A", "B", punts=(0, 0), car=(40, 31), ent=20)
    assert _ko_winner(m) == "A"


def test_winner_by_observations_on_total_tie():
    m = _m(
        "PEREZ ZORRILLA, RAFAEL",
        "MAS CANADELL, JOSEP",
        punts=(1, 1),
        car=(40, 40),
        ent=20,
        obs="GANA PEREZ PER 1-0 AL DESEMPAT",
    )
    assert _ko_winner(m) == "PEREZ ZORRILLA, RAFAEL"


def test_no_winner_when_unplayed_or_unresolvable():
    assert _ko_winner(_m("A", "B", car=(0, 0), ent=None)) is None  # not played
    assert _ko_winner(_m("A", "B", punts=(1, 1), car=(40, 40), ent=20)) is None


# --------------------------------------------------------------------------- #
# Duplicate KO matches (FCB enters some twice, mirrored)
# --------------------------------------------------------------------------- #


def test_dedupe_drops_mirrored_duplicate():
    # Real-world case: same match entered twice with swapped A/B (different
    # arbitre). Keep one; in a KO round each player plays at most once.
    a = _m("MAS CANADELL, JOSEP Mª", "NAVARRO CARMONA, JOAN ANT.", punts=(2, 0), car=(40, 29), ent=27)
    b = _m("NAVARRO CARMONA, JOAN ANT.", "MAS CANADELL, JOSEP Mª", punts=(0, 2), car=(29, 40), ent=27)
    other = _m("GASCÓN REYES, RAFAEL", "PRATS PERI, IVÁN", punts=(2, 2), car=(39, 31), ent=50)
    out = _dedupe_ko_matches((a, b, other))
    assert len(out) == 2
    assert out[0] is a  # first occurrence kept, original order preserved
    assert out[1] is other


def test_dedupe_prefers_played_copy():
    pending = _m("A", "B", car=(0, 0), ent=None)
    played = _m("B", "A", punts=(0, 2), car=(30, 40), ent=20)
    out = _dedupe_ko_matches((pending, played))
    assert len(out) == 1
    assert out[0] is played


# --------------------------------------------------------------------------- #
# Per-round re-seeding
# --------------------------------------------------------------------------- #


def _phases_with_skewed_previa() -> list[PhaseDetail]:
    """PRÈVIA where W1 was dominant (3.0) and W2 weak (0.5); SETZENS where the
    order flips: W2 made 2.0 and W1 only 1.0. Cumulative would seed W1 first;
    per-round (the rule we want) seeds W2 first."""
    previa = _group_phase(_m("W1", "W2", punts=(2, 0), car=(60, 10), ent=20))
    setzens = _ko_phase(
        "SETZENS",
        (
            _m("W1", "L1", punts=(1, 0), car=(20, 10), ent=20),  # W1 round mitjana 1.0
            _m("W2", "L2", punts=(1, 0), car=(40, 12), ent=20),  # W2 round mitjana 2.0
        ),
    )
    vuitens = _ko_phase("VUITENS", ())
    return [previa, setzens, vuitens]


def test_advancing_players_seeded_by_previous_round_mitjana_only():
    phases = _phases_with_skewed_previa()
    out = compute_advancing_players(phases, idx=2, last_group_idx=0)
    assert [p.name for p in out] == ["W2", "W1"]  # per-round, NOT cumulative
    # The surfaced mitjana is the previous round's, not the accumulated one.
    assert out[0].mitjana == 2.0
    assert out[1].mitjana == 1.0


def test_next_ko_round_pairs_by_previous_round_mitjana():
    phases = _phases_with_skewed_previa()
    pairs = compute_next_ko_round(phases, idx=2)
    assert len(pairs) == 1
    # Pyramid 1-vs-N over the per-round seeding → top seed (W2) is player_a.
    assert pairs[0].player_a == "W2"
    assert pairs[0].player_b == "W1"


def test_next_ko_round_empty_when_previous_round_incomplete():
    previa = _group_phase(_m("W1", "W2", punts=(2, 0), car=(60, 10), ent=20))
    setzens = _ko_phase(
        "SETZENS",
        (
            _m("W1", "L1", punts=(1, 0), car=(20, 10), ent=20),
            _m("W2", "L2", car=(0, 0), ent=None),  # unplayed → can't resolve round
        ),
    )
    phases = [previa, setzens, _ko_phase("VUITENS", ())]
    assert compute_next_ko_round(phases, idx=2) == ()
