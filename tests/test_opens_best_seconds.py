"""El millor 2n entra al llistat de classificats provisionals abans que la
federació publiqui el sorteig de la ronda següent (Sant Adrià, pre-pre-prèvia)."""

from __future__ import annotations

from fcb_opens.scraper.open_live import (
    Group,
    GroupStanding,
    MatchResult,
    OpenLiveState,
    OpenStructure,
    PhaseDetail,
    PhaseRef,
    compute_provisional_qualifiers,
)
from fcbillar.cloud_sync import _add_best_seconds_to_qualifiers


def _match(a: str, b: str, *, played: bool = True) -> MatchResult:
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


def _group(label: str, rows: list[tuple[str, int, float]], *, closed: bool = True) -> Group:
    names = [r[0] for r in rows]
    matches = (
        _match(names[0], names[1]),
        _match(names[0], names[2]),
        _match(names[1], names[2], played=closed),
    )
    return Group(
        label=label,
        url="",
        standings=tuple(
            GroupStanding(player_name=n, club="", punts=p, mitjana=m) for n, p, m in rows
        ),
        matches=matches,
    )


def _state(*groups: Group) -> OpenLiveState:
    ph = PhaseDetail(ref=PhaseRef(label="PRE-PRE-PRÈVIA", kind="group", url=""), groups=groups)
    ph = PhaseDetail(
        ref=ph.ref, groups=groups, provisional_qualifiers=compute_provisional_qualifiers(ph)
    )
    return OpenLiveState(
        structure=OpenStructure(division_id=223, name="OPEN", phase_id=1, phases=()),
        phases=[ph],
    )


def _quals(state: OpenLiveState) -> list[tuple[str, int]]:
    return [(q.player_name, q.position_in_group) for q in state.phases[0].provisional_qualifiers]


def test_best_second_joins_the_qualifiers_when_every_group_is_closed():
    state = _state(
        _group("Grup AG", [("A1", 4, 0.9), ("A2", 2, 0.7), ("A3", 0, 0.5)]),
        _group("Grup AH", [("B1", 4, 0.9), ("B2", 2, 0.8), ("B3", 0, 0.5)]),
    )
    assert _add_best_seconds_to_qualifiers(state, {"PPP": 1})
    assert _quals(state) == [("A1", 1), ("B1", 1), ("B2", 2)]
    # Una segona passada no el torna a afegir.
    assert not _add_best_seconds_to_qualifiers(state, {"PPP": 1})


def test_provisional_best_second_while_groups_are_still_playing():
    # Sant Adrià: AL acabat, AK a mig jugar, AG sense començar.
    state = _state(
        _group(
            "Grup AL", [("LOZANO", 2, 0.8676), ("MAGDALENO", 2, 0.6508), ("AMETLLER", 2, 0.6024)]
        ),
        _group(
            "Grup AK",
            [("MUÑOZ", 2, 0.5), ("MARTÍNEZ", 2, 0.45), ("SISTANÉ", 0, 0.14)],
            closed=False,
        ),
        Group(label="Grup AG", url="", standings=(), matches=()),
    )
    assert _add_best_seconds_to_qualifiers(state, {"PPP": 1})
    assert _quals(state) == [("LOZANO", 1), ("MUÑOZ", 1), ("MAGDALENO", 2)]


def test_no_best_second_when_the_phase_has_none():
    state = _state(_group("Grup AG", [("A1", 4, 0.9), ("A2", 2, 0.7), ("A3", 0, 0.5)]))
    assert not _add_best_seconds_to_qualifiers(state, {"PP": 1})
    assert _quals(state) == [("A1", 1)]


def test_tie_on_points_and_average_goes_to_the_best_serie():
    def grp(label: str, second: str, sm: int) -> Group:
        g = _group(label, [(f"{label}1", 4, 0.9), (second, 2, 0.7), (f"{label}3", 0, 0.5)])
        m = g.matches[2]
        played = MatchResult(**{**m.__dict__, "serie_major_a": sm})
        return Group(label=g.label, url="", standings=g.standings, matches=(*g.matches[:2], played))

    state = _state(grp("Grup AG", "SM3", 3), grp("Grup AH", "SM5", 5))
    assert _add_best_seconds_to_qualifiers(state, {"PPP": 1})
    assert _quals(state)[-1] == ("SM5", 2)


def test_tie_on_best_serie_goes_to_the_second_best_serie():
    # Mateixos punts, mitjana i sèrie major (5): passa qui té la 2a sèrie més alta.
    def grp(label: str, second: str, sm2: int) -> Group:
        g = _group(label, [(f"{label}1", 4, 0.9), (second, 2, 0.7), (f"{label}3", 0, 0.5)])
        m0, m1, m2 = g.matches
        m0 = MatchResult(**{**m0.__dict__, "serie_major_b": 5})
        m2 = MatchResult(**{**m2.__dict__, "serie_major_a": sm2})
        return Group(label=g.label, url="", standings=g.standings, matches=(m0, m1, m2))

    state = _state(grp("Grup AG", "S2A", 2), grp("Grup AH", "S2B", 4))
    assert _add_best_seconds_to_qualifiers(state, {"PPP": 1})
    q = state.phases[0].provisional_qualifiers[-1]
    assert (q.player_name, q.series) == ("S2B", (5, 4))
