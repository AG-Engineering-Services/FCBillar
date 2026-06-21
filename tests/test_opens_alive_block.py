"""Tests for the still-alive block of `compute_open_classification`.

Un cop superada la prèvia, els llocs de dalt de la classificació (el quadre KO,
encara per jugar) s'omplen PROVISIONALMENT:
  • PRIMER els RESERVATS (caps de sèrie que no juguen la prèvia), ordenats pel
    RÀNQUING INICIAL d'opens (seeding) → llocs 1..16;
  • DESPRÉS els classificats de la prèvia, per l'ORDRE DE CLASSIFICACIÓ a la
    següent fase (1rs abans que 2ns; després punts/mitjana) → llocs 17..32.
Tot marcat provisional fins a la classificació definitiva.
"""

from __future__ import annotations

from fcb_opens.scraper.open_live import (
    Group,
    GroupStanding,
    MatchResult,
    OpenLiveState,
    OpenStructure,
    PhaseDetail,
    PhaseRef,
    ProvisionalQualifier,
    compute_open_classification,
)


def _played(a: str, b: str) -> MatchResult:
    return MatchResult(
        player_a=a, player_b=b, punts_a=2, punts_b=0,
        caramboles_a=30, caramboles_b=20, serie_major_a=3, serie_major_b=2,
        entrades=40, arbitre=None,
    )


def _group(label: str, players: list[tuple[str, int, float]]) -> Group:
    """A fully-played 3-player group; `players` already in standings order
    (winner first), each a (name, punts, mitjana)."""
    st = tuple(GroupStanding(n, "", p, m) for n, p, m in players)
    n = [p[0] for p in players]
    matches = (_played(n[0], n[1]), _played(n[0], n[2]), _played(n[1], n[2]))
    return Group(label=label, url="", standings=st, matches=matches)


def _state(groups: list[Group], reservats: list[tuple[str, str]] | None = None) -> OpenLiveState:
    """A PRÈVIA group phase (group winners qualify) + an undrawn QUARTS KO,
    so ko_size=8 and the PRÈVIA losers land at 9+. `reservats` is a list of
    (name, club) seeded directly into the KO."""
    quals = tuple(
        ProvisionalQualifier(g.label, 1, g.standings[0].player_name, "",
                             g.standings[0].punts, g.standings[0].mitjana, 0)
        for g in groups
    )
    previa = PhaseDetail(
        ref=PhaseRef(label="PRÈVIA", kind="group", url=""),
        groups=tuple(groups),
        provisional_qualifiers=quals,
    )
    quarts = PhaseDetail(ref=PhaseRef(label="QUARTS", kind="ko", url=""))
    struct = OpenStructure(division_id=1, name="OPEN TEST", phase_id=1,
                           phases=(previa.ref, quarts.ref))
    res = tuple(GroupStanding(n, c, 0, 0.0) for n, c in (reservats or []))
    return OpenLiveState(structure=struct, phases=[previa, quarts], reservats=res)


def _groups() -> list[Group]:
    # 4 winners (A..D) with distinct mitjanes; the runner-up/3rd get eliminated.
    return [
        _group("Grup A", [("WIN_A", 4, 0.80), ("A2", 2, 0.5), ("A3", 0, 0.3)]),
        _group("Grup B", [("WIN_B", 4, 0.90), ("B2", 2, 0.5), ("B3", 0, 0.3)]),
        _group("Grup C", [("WIN_C", 4, 0.70), ("C2", 2, 0.5), ("C3", 0, 0.3)]),
        _group("Grup D", [("WIN_D", 4, 1.00), ("D2", 2, 0.5), ("D3", 0, 0.3)]),
    ]


def test_alive_winners_fill_the_top_provisionally():
    rows = compute_open_classification(_state(_groups()))
    alive = [r for r in rows if r.round_label == "EN JOC"]
    assert {r.player_name for r in alive} == {"WIN_A", "WIN_B", "WIN_C", "WIN_D"}
    assert [r.position for r in sorted(alive, key=lambda r: r.position)] == [1, 2, 3, 4]
    assert all(r.is_provisional_position for r in alive)
    # Els eliminats (2ns/3rs) queden sota el quadre (ko_size=8 → 9+).
    elim = [r for r in rows if r.round_label == "PRÈVIA"]
    assert elim and min(r.position for r in elim) >= 9


def test_reservats_first_by_seeding_then_previa_by_qualification():
    state = _state(_groups(), reservats=[("RES_X", "CX"), ("RES_Y", "CY")])
    # Seeding: RES_Y millor que RES_X (i, per provar que NO afecta la prèvia,
    # els winners reben un seeding contrari al seu ordre de classificació).
    state.seeding = {"RES_Y": 2, "RES_X": 5,
                     "WIN_C": 1, "WIN_A": 3, "WIN_B": 7, "WIN_D": 9}
    rows = compute_open_classification(state)
    alive = sorted([r for r in rows if r.round_label == "EN JOC"], key=lambda r: r.position)
    order = [r.player_name for r in alive]
    # 1-2: reservats per seeding; 3-6: winners per classificació (mitjana DESC),
    # IGNORANT el seeding dels winners.
    assert order == ["RES_Y", "RES_X", "WIN_D", "WIN_B", "WIN_A", "WIN_C"]
    # El club dels reservats es manté tot i no jugar cap partida.
    assert next(r.club for r in alive if r.player_name == "RES_Y") == "CY"


def test_without_reservats_previa_is_ordered_by_qualification_not_seeding():
    state = _state(_groups())
    # Seeding contrari a l'ordre de mitjana: ha de guanyar la classificació.
    state.seeding = {"WIN_A": 1, "WIN_B": 2, "WIN_C": 3, "WIN_D": 4}
    order = [r.player_name for r in sorted(compute_open_classification(state),
             key=lambda r: r.position) if r.round_label == "EN JOC"]
    assert order == ["WIN_D", "WIN_B", "WIN_A", "WIN_C"]  # mitjana DESC, no seeding
