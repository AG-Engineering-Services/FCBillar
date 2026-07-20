"""L'inici d'un open: la llista "RESERVATS" del web FCB sovint va per darrere del
quadre (p.ex. 15 dels 16 caps de sèrie), de manera que als setzens en falta un.

Aquests tests cobreixen la reparació:
  - `augment_state_reservats` afegeix caps de sèrie extres i recalcula el pool del
    primer KO in-place;
  - `cloud_sync._complete_first_ko_reservats` casa la projecció (RÀNQUING INICIAL,
    16 reservats) amb el viu (15) per `_reservat_match_key` (robust a l'abreviatura
    del 2n cognom i a l'espai després de la coma) i afegeix NOMÉS el que hi manca.
"""

from __future__ import annotations

from fcb_opens.scraper.open_live import (
    GroupStanding,
    OpenLiveState,
    OpenStructure,
    PhaseDetail,
    PhaseRef,
    ProvisionalQualifier,
    augment_state_reservats,
)
from fcbillar import cloud_sync as cs


def _state(reservats: tuple[GroupStanding, ...]) -> OpenLiveState:
    """PRÈVIA (amb un 1r de grup classificat) + SETZENS buit (pool incomplet)."""
    prev = PhaseDetail(
        ref=PhaseRef(label="PRÈVIA", kind="group", url=""),
        provisional_qualifiers=(
            ProvisionalQualifier(
                group_label="Grup A",
                position_in_group=1,
                player_name="WINNER U, ONE",
                club="C.B.X",
                punts=6,
                mitjana=1.0,
            ),
        ),
    )
    setzens = PhaseDetail(ref=PhaseRef(label="SETZENS", kind="ko", url=""))
    return OpenLiveState(
        structure=OpenStructure(division_id=1, name="OPEN X", phase_id=1, phases=()),
        phases=[prev, setzens],
        seeding={},
        reservats=reservats,
    )


def _setzens_reservats(state: OpenLiveState) -> list[str]:
    setzens = next(p for p in state.phases if p.ref.kind == "ko")
    return [p.name for p in setzens.provisional_players if p.source == "reservat"]


def test_augment_state_reservats_recomputes_first_ko_pool():
    state = _state((GroupStanding("SEED A, A", "C.B.X", 0, 0.0),))
    augment_state_reservats(state, [GroupStanding("SEED B, B", "C.B.Y", 0, 0.0)])
    assert len(state.reservats) == 2
    names = _setzens_reservats(state)
    assert "SEED B, B" in names
    assert "SEED A, A" in names
    assert len(names) == 2


def test_augment_state_reservats_noop_on_empty():
    state = _state((GroupStanding("SEED A, A", "C.B.X", 0, 0.0),))
    before = state.reservats
    augment_state_reservats(state, [])
    assert state.reservats is before


def test_reservat_match_key_is_robust_to_abbreviation_and_comma_spacing():
    # 2n cognom abreujat al PDF vs sencer al viu → mateixa clau.
    assert cs._reservat_match_key(
        "HERNÁNDEZ HDEZ, FRANCESC", "C.B. MANRESA"
    ) == cs._reservat_match_key("HERNÁNDEZ HERNÁNDEZ, FRANCESC", "C.B.MANRESA")
    # Falta d'espai després de la coma i accents → mateixa clau.
    assert cs._reservat_match_key(
        "GARCIA ALARCÓN,RICARDO", "C.B. MONFORTE"
    ) == cs._reservat_match_key("GARCIA ALARCON, RICARDO", "C.B.MONFORTE")
    # Persones diferents (mateix 1r cognom, club diferent) → claus diferents.
    assert cs._reservat_match_key(
        "PÉREZ ZORRILLA, RAFAEL", "C.B.MOLLET"
    ) != cs._reservat_match_key("PÉREZ DONAIRE, JAVIER", "C.B.CARDONA")


def test_complete_first_ko_reservats_adds_only_the_missing_one():
    # Viu: 2 reservats (un amb el 2n cognom abreujat respecte de la projecció).
    live = (
        GroupStanding("HERNÁNDEZ HERNÁNDEZ, FRANCESC", "C.B.MANRESA", 0, 0.0),
        GroupStanding("MORENO CORTÉS, ARMAND", "C.B.LLEIDA", 0, 0.0),
    )
    state = _state(live)
    # Projecció: 3 reservats (el tercer, GARCIA ALARCÓN, encara no és al viu).
    proj_phases = [
        {
            "kind": "ko",
            "label": "Fase Final",
            "provisional_players": [
                {"name": "HERNÁNDEZ HDEZ, FRANCESC", "club": "C.B. MANRESA", "source": "reservat"},
                {"name": "MORENO CORTÉS, ARMAND", "club": "C.B. LLEIDA", "source": "reservat"},
                {"name": "GARCIA ALARCÓN,RICARDO", "club": "C.B. MONFORTE", "source": "reservat"},
            ],
        }
    ]
    added = cs._complete_first_ko_reservats(state, proj_phases)
    assert added == 1
    assert len(state.reservats) == 3
    names = _setzens_reservats(state)
    assert len(names) == 3
    # El que s'afegeix es normalitza amb l'espai després de la coma.
    assert "GARCIA ALARCÓN, RICARDO" in names


def test_seed_first_ko_by_projection_uses_ranking_inicial_order():
    """Els caps de sèrie del primer KO s'ordenen per la Posició del RÀNQUING INICIAL
    (que porta la projecció), no pel rànquing d'Opens VIGENT (`state.seeding`)."""
    live = (
        GroupStanding("ALPHA AA, A", "C.B.A", 0, 0.0),
        GroupStanding("BETA BB, B", "C.B.B", 0, 0.0),
        GroupStanding("GAMMA GG, G", "C.B.G", 0, 0.0),
    )
    state = _state(live)
    # Rànquing d'Opens VIGENT (derivat): donaria l'ordre ALPHA, BETA, GAMMA.
    state.seeding = {"ALPHA AA, A": 1, "BETA BB, B": 2, "GAMMA GG, G": 3}
    # Projecció (RÀNQUING INICIAL, Posició): l'ordre correcte és GAMMA, ALPHA, BETA.
    proj_phases = [
        {
            "kind": "ko",
            "label": "Fase Final",
            "provisional_players": [
                {"name": "GAMMA GG, G", "club": "C.B.G", "source": "reservat"},
                {"name": "ALPHA AA, A", "club": "C.B.A", "source": "reservat"},
                {"name": "BETA BB, B", "club": "C.B.B", "source": "reservat"},
            ],
        }
    ]
    assert cs._seed_first_ko_by_projection(state, proj_phases) is True
    assert _setzens_reservats(state) == ["GAMMA GG, G", "ALPHA AA, A", "BETA BB, B"]


def test_complete_first_ko_reservats_noop_when_live_is_complete():
    live = (
        GroupStanding("HERNÁNDEZ HERNÁNDEZ, FRANCESC", "C.B.MANRESA", 0, 0.0),
        GroupStanding("MORENO CORTÉS, ARMAND", "C.B.LLEIDA", 0, 0.0),
    )
    state = _state(live)
    proj_phases = [
        {
            "kind": "ko",
            "label": "Fase Final",
            "provisional_players": [
                {"name": "HERNÁNDEZ HDEZ, FRANCESC", "club": "C.B. MANRESA", "source": "reservat"},
                {"name": "MORENO CORTÉS, ARMAND", "club": "C.B. LLEIDA", "source": "reservat"},
            ],
        }
    ]
    added = cs._complete_first_ko_reservats(state, proj_phases)
    assert added == 0
    assert len(state.reservats) == 2
