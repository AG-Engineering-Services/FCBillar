"""Fusió de fases REALS (web FCB) i PROJECTADES en el payload d'`open_live`.

Regressió del 2026-07-25 (Open de Mataró, fase final en joc): `_phase_code`
col·lapsa TOTES les rondes KO a "FINAL" a posta —perquè la "Fase Final (K.O.)"
projectada, que és una sola fase, casi amb el quadre real es digui SETZENS o
FINAL—, però la fusió només en conservava UNA. Amb el quadre ja penjat
(SETZENS…FINAL) se'n publicava una i se'n perdien quatre, i amb elles els
`provisional_players` de cada ronda: els classificats per a la ronda següent.
"""

from __future__ import annotations

from fcbillar.cloud_sync import _merge_projected_phases, _phase_code


def _ko(label: str, **extra) -> dict:
    return {"label": label, "kind": "ko", **extra}


def _grp(label: str, **extra) -> dict:
    return {"label": label, "kind": "group", **extra}


PROJECTED = [
    _grp("Pre-pre-prèvies"),
    _grp("Pre-prèvies"),
    _grp("Prèvies"),
    _ko("Fase Final (K.O.)"),
]


def test_phase_code_collapses_every_ko_round():
    codes = {_phase_code(lbl, "ko") for lbl in
             ("SETZENS", "VUITENS", "QUARTS", "SEMIFINALS", "FINAL")}
    assert codes == {"FINAL"}
    assert _phase_code("PRE-PRE-PREVIA", "group") == "PPP"
    assert _phase_code("Pre-prèvies", "group") == "PP"
    assert _phase_code("PREVIA", "group") == "P"


def test_merge_keeps_every_real_ko_round():
    """El template porta UNA fase KO; la federació en publica CINC. Han de
    sortir totes cinc, en ordre, i cap marcada com a projectada."""
    real = [
        _grp("PRE-PRE-PREVIA"),
        _grp("PRE-PREVIA"),
        _grp("PREVIA"),
        _ko("SETZENS", ko_matches=[{}] * 16),
        _ko("VUITENS", provisional_players=[{"name": "A"}, {"name": "B"}]),
        _ko("QUARTS"),
        _ko("SEMIFINALS"),
        _ko("FINAL"),
    ]
    merged = _merge_projected_phases(real, PROJECTED)
    assert [p["label"] for p in merged] == [
        "PRE-PRE-PREVIA", "PRE-PREVIA", "PREVIA",
        "SETZENS", "VUITENS", "QUARTS", "SEMIFINALS", "FINAL",
    ]
    assert not any(p.get("projected") for p in merged)
    # Els classificats per a la ronda següent sobreviuen a la fusió.
    vuitens = next(p for p in merged if p["label"] == "VUITENS")
    assert [s["name"] for s in vuitens["provisional_players"]] == ["A", "B"]


def test_merge_keeps_projected_phase_when_no_real_ko_yet():
    """Sense cap ronda KO real, la fase KO projectada es manté i es marca."""
    real = [_grp("PRE-PREVIA"), _grp("PREVIA")]
    merged = _merge_projected_phases(real, PROJECTED)
    assert [p["label"] for p in merged] == [
        "Pre-pre-prèvies", "PRE-PREVIA", "PREVIA", "Fase Final (K.O.)",
    ]
    assert merged[0]["projected"] is True    # prèvia que la FCB encara no ha penjat
    assert merged[-1]["projected"] is True   # quadre final encara no publicat
    assert "projected" not in merged[1]


def test_merge_appends_real_phases_absent_from_template():
    """Fases reals amb un codi que el template no porta van al final, totes."""
    real = [_grp("PREVIA"), _ko("SEMIFINALS"), _ko("FINAL")]
    merged = _merge_projected_phases(real, [_grp("Prèvies")])
    assert [p["label"] for p in merged] == ["PREVIA", "SEMIFINALS", "FINAL"]


def test_merge_without_template_is_identity():
    real = [_grp("PREVIA"), _ko("SETZENS")]
    assert _merge_projected_phases(real, None) is real
    assert _merge_projected_phases(real, []) is real
