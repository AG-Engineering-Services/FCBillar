"""Tests for the Opens inscrits-PDF parser and bracket projection.

Validated against the real 'IV OPEN COSTA DAURADA' inscrits PDF (76 players).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fcb_opens.projection import build_projection, order_inscrits
from fcb_opens.scraper.inscrits_pdf import InscritEntry, parse_inscrits_pdf

PDF = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "2.-INSCRIPCIONES Y ORGANIZACION RANQUING OPENS.pdf"
)

pytestmark = pytest.mark.skipif(not PDF.exists(), reason="inscrits PDF not present")


def test_parse_inscrits_pdf():
    res = parse_inscrits_pdf(PDF)
    assert res.open_name == "IV OPEN COSTA DAURADA"
    assert res.declared_total == 76
    assert len(res.entries) == 76
    # 62 players carry a Catalan-Opens ranking position; 14 newcomers don't.
    assert sum(1 for e in res.entries if e.seed_position is not None) == 62
    assert sum(1 for e in res.entries if e.seed_position is None) == 14
    # Spot-check a known row.
    armand = next(e for e in res.entries if "MORENO CORT" in e.player_name)
    assert armand.seed_position == 1
    assert armand.club == "C.B. LLEIDA"


def test_order_inscrits_seeds_then_newcomers():
    entries = [
        InscritEntry("CLUB", "RANKED LOW", 50, 0.5, "OPENS"),
        InscritEntry("CLUB", "RANKED TOP", 1, 1.2, "OPENS"),
        InscritEntry("CLUB", "NEW PROV", None, 0.6, "Provisional"),
        InscritEntry("CLUB", "NEW DEF", None, 0.4, "Definitiva"),
    ]
    ordered = order_inscrits(entries)
    names = [e.player_name for e in ordered]
    # Seeded by ranking position first; newcomers last with definitius before
    # provisionals (each by mitjana desc — here only one of each).
    assert names == ["RANKED TOP", "RANKED LOW", "NEW DEF", "NEW PROV"]


def test_build_projection_costa_daurada():
    inscrits = parse_inscrits_pdf(PDF)
    proj = build_projection(inscrits, season="2025-2026")

    assert proj["num_inscriptions"] == 76
    # N=76 -> overflow=6 -> P=16 groups, PP=6 groups, no PPP (generator closed form).
    assert proj["structure"] == {"P": 16, "PP": 6}

    # Seeds 1..16 enter the Fase Final directly.
    direct = [s for s in proj["seeds"] if s["entry_phase"] == "Fase Final"]
    assert len(direct) == 16
    assert proj["seeds"][0]["ranking_position"] == 1  # best opens position is seed 1

    # Every prèvia seat for seeds 17..76 is filled exactly once.
    placed = [
        p["seed_order"]
        for ph in proj["phases"]
        for g in ph["groups"]
        for p in g["players"]
        if p["kind"] == "player"
    ]
    assert sorted(placed) == list(range(17, 77))

    # Fase Final: 16 setzens, seed 16 vs Grup A ... seed 1 vs Grup P.
    setzens = proj["fase_final"]["setzens"]
    assert len(setzens) == 16
    assert setzens[0]["a"]["seed_order"] == 16
    assert setzens[0]["b"]["group"] == "A"
    assert setzens[-1]["a"]["seed_order"] == 1
    assert setzens[-1]["b"]["group"] == "P"


def test_build_projection_enrichment():
    """fcb_id, opens points and warnings are attached when inputs are provided."""
    inscrits = parse_inscrits_pdf(PDF)
    first = inscrits.entries[0].player_name
    proj = build_projection(
        inscrits,
        season="2025-2026",
        resolve_fcb_id=lambda n: f"FID:{n}",
        opens_points_by_name={first: 999},
    )
    # Every player reference resolves to a (fake) profile id.
    assert all(s["fcb_id"] == f"FID:{s['player_name']}" for s in proj["seeds"])
    # Opens points are surfaced where provided.
    assert any(s["opens_points"] == 999 for s in proj["seeds"])
    # Newcomers (no opens position) generate an informational warning.
    assert any("sense posició" in w["message"] for w in proj["warnings"])


def test_generator_rejects_out_of_range():
    """N outside [64,128] or odd is unsupported and must raise (not crash callers)."""
    from fcb_opens.generator import generate_tournament

    for bad in (50, 130, 77):  # too few · too many · odd
        with pytest.raises(NotImplementedError):
            generate_tournament(bad)


def test_generator_phase_scaling_examples():
    """The closed-form phase scaling for representative N (Art. VIII-IX)."""
    from fcb_opens.generator import generate_tournament

    def counts(n: int) -> dict[str, int]:
        t = generate_tournament(n)
        return {k: len(v.groups) for k, v in t.phases.items()}

    assert counts(64) == {"P": 16}
    assert counts(76) == {"P": 16, "PP": 6}
    assert counts(96) == {"P": 16, "PP": 16}
    assert counts(120) == {"P": 16, "PP": 16, "PPP": 12}
