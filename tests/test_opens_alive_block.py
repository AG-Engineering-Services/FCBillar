"""Tests for the still-alive block of `compute_open_classification`.

Jugadors que han entrat al quadre KO i encara no han estat eliminats ocupen,
PROVISIONALMENT, els llocs de dalt (1..K). Per petició de l'usuari:
  • els 16 primers llocs s'ordenen pel RÀNQUING INICIAL (seeding del Rànquing
    Català d'Opens);
  • del 17 en avall, per l'ordre de classificació a la següent fase.
Tot marcat provisional fins que la federació publiqui la classificació final.
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


def _state(groups: list[Group]) -> OpenLiveState:
    """A PRÈVIA group phase (group winners qualify) + an undrawn QUARTS KO,
    so ko_size=8 and the PRÈVIA losers land at 9+."""
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
    return OpenLiveState(structure=struct, phases=[previa, quarts])


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


def test_top16_ordered_by_seeding():
    state = _state(_groups())
    # Seeding (Rànquing d'Opens): D millor, després B, A, C.
    state.seeding = {"WIN_D": 1, "WIN_B": 5, "WIN_A": 9, "WIN_C": 20}
    rows = compute_open_classification(state)
    order = [r.player_name for r in sorted(rows, key=lambda r: r.position)
             if r.round_label == "EN JOC"]
    assert order == ["WIN_D", "WIN_B", "WIN_A", "WIN_C"]


def test_without_seeding_falls_back_to_qualification_order():
    # Sense seeding, el bloc viu s'ordena per classificació (punts iguals →
    # mitjana DESC): D(1.00) > B(0.90) > A(0.80) > C(0.70).
    rows = compute_open_classification(_state(_groups()))
    order = [r.player_name for r in sorted(rows, key=lambda r: r.position)
             if r.round_label == "EN JOC"]
    assert order == ["WIN_D", "WIN_B", "WIN_A", "WIN_C"]
