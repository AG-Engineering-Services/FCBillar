"""Incompareixences (W.O.) a les rondes KO d'un open.

Regla (usuari, 2026-07-25, setzens de l'Open de Mataró): quan una partida NO es
juga perquè un dels dos no es presenta, l'altre passa igualment de ronda i, com
que no hi ha fet mitjana, **entra a la ronda següent amb la posició que ocupava
al rànquing de la ronda anterior** (Uceda, 7è dels setzens → 7è dels vuitens;
Pastor, 16è → 16è). La FCB publica aquestes partides amb els punts del guanyador
(2-0) i tota la resta a zero: ni caramboles ni entrades.

Cobreix també la piràmide dels emparellaments CALCULATS, que es fa sobre el pool
SENCER (1-vs-N) i no sobre els jugadors que queden sense emparellar.
"""

from __future__ import annotations

from fcb_opens.scraper.open_live import (
    AdvancingPlayer,
    MatchResult,
    PhaseDetail,
    PhaseRef,
    _attach_ko_provisional_players,
    _is_walkover,
    _ko_winner,
    _phase_player_stats,
    compute_advancing_players,
)


def _m(a: str, b: str, *, punts=(0, 0), car=(0, 0), ent=None, sm=(0, 0)) -> MatchResult:
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
    )


def _wo(winner: str, loser: str) -> MatchResult:
    """Tal com la publica la FCB: 2-0 i tota la resta a zero."""
    return _m(winner, loser, punts=(2, 0), car=(0, 0), ent=0)


# --------------------------------------------------------------------------- #
# Detecció
# --------------------------------------------------------------------------- #


def test_walkover_is_detected_and_decided():
    m = _wo("UCEDA", "JUÁREZ")
    assert m.is_played is False  # sense entrades no s'ha jugat…
    assert _is_walkover(m) is True  # …però el resultat és ferm
    assert _ko_winner(m) == "UCEDA"


def test_unplayed_match_without_result_is_not_a_walkover():
    assert _is_walkover(_m("A", "B")) is False
    assert _ko_winner(_m("A", "B")) is None
    # 0-0 amb entrades a 0 tampoc: encara no hi ha resultat.
    assert _is_walkover(_m("A", "B", punts=(0, 0), ent=0)) is False


def test_played_match_is_not_a_walkover():
    assert _is_walkover(_m("A", "B", punts=(2, 0), car=(40, 25), ent=30)) is False


def test_round_with_walkovers_is_not_active_anymore():
    """Una ronda amb incompareixences ja està tancada. Amb `is_played` es quedava
    "activa" per sempre i l'open sortia encallat en aquella fase encara que ja
    s'hagués jugat la final (cas Mataró 2026: dos W.O. als setzens)."""
    from fcb_opens.scraper.open_live import OpenLiveState, OpenStructure
    from fcb_opens.snapshot_live import _state_payload

    setzens = PhaseDetail(
        ref=PhaseRef(label="SETZENS", kind="ko", url=""),
        ko_matches=(
            _m("A", "B", punts=(2, 0), car=(40, 25), ent=30),
            _wo("C", "D"),
        ),
    )
    state = OpenLiveState(
        structure=OpenStructure(division_id=1, name="OPEN TEST", phase_id=1, phases=(setzens.ref,)),
        phases=[setzens],
    )
    payload = _state_payload(state, "2026-07-27T00:00:00Z")
    assert payload["phases"][0]["is_active"] is False


# --------------------------------------------------------------------------- #
# La ronda compta els dos jugadors (si no, el perdedor queda "en competició")
# --------------------------------------------------------------------------- #


def test_walkover_puts_both_players_in_the_round_stats():
    """Qui no es presenta ha de constar a la ronda amb estadístiques a zero: és
    així com la classificació el pot donar per ELIMINAT en comptes de deixar-lo
    a «encara en competició» (no avança i no surt a cap ronda posterior)."""
    phase = PhaseDetail(
        ref=PhaseRef(label="SETZENS", kind="ko", url=""),
        ko_matches=(
            _wo("UCEDA", "JUÁREZ"),
            _m("PINEDA", "NAVARRO", punts=(2, 0), car=(40, 27), ent=35, sm=(4, 4)),
        ),
    )
    stats = _phase_player_stats(phase)
    assert set(stats) == {"UCEDA", "JUÁREZ", "PINEDA", "NAVARRO"}
    assert stats["UCEDA"] == (0.0, 0, "")
    assert stats["JUÁREZ"] == (0.0, 0, "")
    assert stats["PINEDA"][0] > 0


def test_pending_pairing_does_not_enter_the_round_stats():
    phase = PhaseDetail(
        ref=PhaseRef(label="SETZENS", kind="ko", url=""),
        ko_matches=(_m("A", "B"),),
    )
    assert _phase_player_stats(phase) == {}


# --------------------------------------------------------------------------- #
# Posició a la ronda següent
# --------------------------------------------------------------------------- #


def _setzens_with_two_walkovers() -> list[PhaseDetail]:
    """Setzens complets de 32: 14 partides jugades i 2 incompareixences, els
    guanyadors de les quals són el 7è i el 16è del rànquing de la ronda."""
    seeds = [f"S{i:02d}" for i in range(1, 33)]
    matches = []
    for i in range(16):
        a, b = seeds[i], seeds[31 - i]  # piràmide 1-32, 2-31, …
        if i in (6, 15):  # 7è i 16è: passen per W.O.
            matches.append(_wo(a, b))
        else:
            # Mitjana decreixent amb el seed, per tenir un ordre inequívoc.
            matches.append(_m(a, b, punts=(2, 0), car=(40, 20), ent=30 + i, sm=(5, 3)))
    group = PhaseDetail(ref=PhaseRef(label="PRÈVIA", kind="group", url=""))
    setzens = PhaseDetail(
        ref=PhaseRef(label="SETZENS", kind="ko", url=""),
        ko_matches=tuple(matches),
        provisional_players=tuple(AdvancingPlayer(name=n) for n in seeds),
    )
    vuitens = PhaseDetail(ref=PhaseRef(label="VUITENS", kind="ko", url=""))
    return [group, setzens, vuitens]


def test_walkover_winner_keeps_its_previous_round_position():
    phases = _setzens_with_two_walkovers()
    out = compute_advancing_players(phases, idx=2, last_group_idx=0)
    assert len(out) == 16
    names = [p.name for p in out]
    # El 7è i el 16è dels setzens hi entren com a 7è i 16è dels vuitens.
    assert names[6] == "S07"
    assert names[15] == "S16"
    assert [p.source for p in out if p.name in ("S07", "S16")] == ["walkover"] * 2
    # La resta, per mitjana de la ronda, omplen els forats sense repetir-se.
    assert len(set(names)) == 16
    assert all(p.source == "previous_winner" for p in out if p.name not in ("S07", "S16"))


def test_walkover_out_of_range_position_falls_to_the_tail():
    """Pool encara parcial: la posició reservada no hi cap i el jugador va al
    final; quan la ronda es completi, el recàlcul ja el col·locarà."""
    seeds = [f"S{i:02d}" for i in range(1, 33)]
    setzens = PhaseDetail(
        ref=PhaseRef(label="SETZENS", kind="ko", url=""),
        ko_matches=(
            _m("S01", "S32", punts=(2, 0), car=(40, 20), ent=30),
            _wo("S07", "S26"),
        ),
        provisional_players=tuple(AdvancingPlayer(name=n) for n in seeds),
    )
    phases = [
        PhaseDetail(ref=PhaseRef(label="PRÈVIA", kind="group", url="")),
        setzens,
        PhaseDetail(ref=PhaseRef(label="VUITENS", kind="ko", url="")),
    ]
    out = compute_advancing_players(phases, idx=2, last_group_idx=0)
    assert [p.name for p in out] == ["S01", "S07"]


# --------------------------------------------------------------------------- #
# Emparellaments calculats: piràmide sobre el pool SENCER
# --------------------------------------------------------------------------- #


def test_provisional_pairings_follow_the_full_pyramid():
    """Amb part dels emparellaments ja publicats, els que falten han de ser els
    de la piràmide 1-N original —inclòs el central— i no una piràmide nova feta
    amb els que queden sense rival (que desplaçaria tots els aparellaments)."""
    phases = _setzens_with_two_walkovers()
    # Vuitens amb DOS emparellaments ja publicats per la FCB: 1-16 i 3-14 de la
    # piràmide dels 16 classificats (S01…: veg. l'ordre que dóna la ronda).
    ranked = compute_advancing_players(phases, idx=2, last_group_idx=0)
    order = [p.name for p in ranked]
    official = (
        _m(order[0], order[15], punts=(2, 0), car=(40, 20), ent=30),
        _m(order[2], order[13], punts=(2, 0), car=(40, 20), ent=30),
    )
    phases[2] = PhaseDetail(ref=PhaseRef(label="VUITENS", kind="ko", url=""), ko_matches=official)
    out = _attach_ko_provisional_players(phases, (), {})
    calc = [(m.player_a, m.player_b) for m in out[2].provisional_matches]
    assert calc == [
        (order[1], order[14]),
        (order[3], order[12]),
        (order[4], order[11]),
        (order[5], order[10]),
        (order[6], order[9]),
        (order[7], order[8]),
    ]
    # El 16è (que hi va entrar per incompareixença) juga contra el 1r, com toca.
    assert (order[0], order[15]) == (official[0].player_a, official[0].player_b)


def test_orphans_left_by_an_off_pyramid_official_pairing_are_repaired():
    """Si la FCB emparella algú fora de la piràmide, les seves parelles
    teòriques queden orfes: s'emparellen entre elles, no es perden."""
    phases = _setzens_with_two_walkovers()
    ranked = compute_advancing_players(phases, idx=2, last_group_idx=0)
    order = [p.name for p in ranked]
    # Emparellament oficial fora de piràmide: el 1r contra el 2n (no 1-16).
    official = (_m(order[0], order[1], punts=(2, 0), car=(40, 20), ent=30),)
    phases[2] = PhaseDetail(ref=PhaseRef(label="VUITENS", kind="ko", url=""), ko_matches=official)
    out = _attach_ko_provisional_players(phases, (), {})
    calc = [(m.player_a, m.player_b) for m in out[2].provisional_matches]
    paired = {n for pair in calc for n in pair} | {order[0], order[1]}
    assert paired == set(order)  # ningú es queda fora
    assert (order[14], order[15]) in calc  # els dos orfes, junts
