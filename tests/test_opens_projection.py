"""Tests for the Opens inscrits-PDF parser and bracket projection.

Validated against the real 'IV OPEN COSTA DAURADA' inscrits PDF (76 players).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fcb_opens.projection import (
    build_projection,
    build_projection_from_seeded,
    order_inscrits,
)
from fcb_opens.scraper.inscrits_pdf import InscritEntry, parse_inscrits_pdf
from fcb_opens.scraper.ranking_inicial_pdf import (
    RankingInicialEntry,
    RankingInicialList,
    parse_ranking_inicial_pdf,
)

PDF = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "2.-INSCRIPCIONES Y ORGANIZACION RANQUING OPENS.pdf"
)

# The RÀNQUING INICIAL PDF the user provided (repo root, not committed).
RANKING_PDF = (
    Path(__file__).resolve().parents[1] / "RANKING INICIAL XIV OPEN LES SANTES DE MATARO.pdf"
)

needs_inscrits = pytest.mark.skipif(not PDF.exists(), reason="inscrits PDF not present")
needs_ranking = pytest.mark.skipif(
    not RANKING_PDF.exists(), reason="RÀNQUING INICIAL PDF not present"
)


def _synthetic_ranking(n: int) -> RankingInicialList:
    """A minimal seeded ranking list of N players (posició = seed order)."""
    return RankingInicialList(
        open_name="TEST OPEN",
        entries=tuple(
            RankingInicialEntry(
                posicio=i,
                player_name=f"PLAYER {i:03d}",
                club="TEST CLUB",
                ranking_position=i if i <= n - 5 else None,
                ranquing_estat="OPENS" if i <= n - 5 else "Definitiva",
                punts=max(0, 900 - i),
                mitjana=1.0,
            )
            for i in range(1, n + 1)
        ),
    )


@needs_inscrits
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


@needs_inscrits
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

    # Fase Final: 16 setzens, seed 16 vs 1-P ... seed 1 vs 16-P.
    setzens = proj["fase_final"]["setzens"]
    assert len(setzens) == 16
    assert setzens[0]["a"]["seed_order"] == 16
    assert setzens[0]["b"]["placeholder"] == "1-P"
    assert setzens[-1]["a"]["seed_order"] == 1
    assert setzens[-1]["b"]["placeholder"] == "16-P"


@needs_inscrits
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
    """N outside [64,128] is unsupported and must raise (not crash callers)."""
    from fcb_opens.generator import generate_tournament

    for bad in (50, 63, 129):
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


@pytest.mark.parametrize(
    ("n", "plan"),
    [
        (64, {"P": (16, 16)}),
        (76, {"P": (16, 16), "PP": (6, 6)}),
        # Senar: la fase més baixa fa un grup més i també passa el millor segon.
        (77, {"P": (16, 16), "PP": (7, 8)}),
        (95, {"P": (16, 16), "PP": (16, 17)}),
        (96, {"P": (16, 16), "PP": (16, 16)}),
        (97, {"P": (16, 16), "PP": (16, 16), "PPP": (1, 2)}),
        (98, {"P": (16, 16), "PP": (16, 16), "PPP": (1, 1)}),
        (107, {"P": (16, 16), "PP": (16, 16), "PPP": (6, 7)}),
        (127, {"P": (16, 16), "PP": (16, 16), "PPP": (16, 17)}),
        (128, {"P": (16, 16), "PP": (16, 16), "PPP": (16, 16)}),
    ],
)
def test_generator_groups_and_qualifiers(n, plan):
    """(grups, classificats) per fase, per a qualsevol N de 64 a 128."""
    from fcb_opens.generator import generate_tournament

    t = generate_tournament(n)
    assert {k: (len(v.groups), v.qualifiers) for k, v in t.phases.items()} == plan


@pytest.mark.parametrize("n", range(64, 129))
def test_generator_every_seed_once_and_seats_match_qualifiers(n):
    """Cada seed 17..N surt un sol cop, i cada fase té tantes places de
    classificat com classificats dona la fase de sota."""
    from fcb_opens.generator import generate_tournament

    t = generate_tournament(n)
    direct = sorted(
        s.inscription_position
        for ph in t.phases.values()
        for g in ph.groups
        for s in g.slots
        if s.inscription_position is not None
    )
    assert direct == list(range(17, n + 1))
    for ph in t.phases.values():
        assert all(len(g.slots) == 3 for g in ph.groups)
        for src in {s.placeholder_phase for g in ph.groups for s in g.slots} - {None}:
            ranks = sorted(
                s.placeholder_rank
                for g in ph.groups
                for s in g.slots
                if s.placeholder_phase == src
            )
            assert ranks == list(range(1, t.phases[src].qualifiers + 1))


# Sorteig oficial del X Open Sant Adrià (2026, 107 inscrits), tal com el va
# enviar la federació als PDF GRUPS PREVIA / PRE-PREVIA / PRE-PRE-PREVIA.
SANT_ADRIA_2026 = {
    "P": {
        "A": ["17", "48", "16-PP"], "B": ["18", "47", "15-PP"], "C": ["19", "46", "14-PP"],
        "D": ["20", "45", "13-PP"], "E": ["21", "44", "12-PP"], "F": ["22", "43", "11-PP"],
        "G": ["23", "42", "10-PP"], "H": ["24", "41", "9-PP"], "I": ["25", "40", "8-PP"],
        "J": ["26", "39", "7-PP"], "K": ["27", "38", "6-PP"], "L": ["28", "37", "5-PP"],
        "M": ["29", "36", "4-PP"], "N": ["30", "35", "3-PP"], "O": ["31", "34", "2-PP"],
        "P": ["32", "33", "1-PP"],
    },
    "PP": {
        "Q": ["49", "80", "7-PPP"], "R": ["50", "79", "6-PPP"], "S": ["51", "78", "5-PPP"],
        "T": ["52", "77", "4-PPP"], "U": ["53", "76", "3-PPP"], "V": ["54", "75", "2-PPP"],
        "W": ["55", "74", "1-PPP"], "X": ["56", "73", "89"], "Y": ["57", "72", "88"],
        "Z": ["58", "71", "87"], "AA": ["59", "70", "86"], "AB": ["60", "69", "85"],
        "AC": ["61", "68", "84"], "AD": ["62", "67", "83"], "AE": ["63", "66", "82"],
        "AF": ["64", "65", "81"],
    },
    "PPP": {
        "AG": ["90", "101", "107"], "AH": ["91", "100", "106"], "AI": ["92", "99", "105"],
        "AJ": ["93", "98", "104"], "AK": ["94", "97", "103"], "AL": ["95", "96", "102"],
    },
}


def test_generator_matches_sant_adria_2026_draw():
    """107 inscrits: 6 grups de PPP i 7 classificats, idèntic al sorteig oficial."""
    from fcb_opens.generator import generate_tournament

    t = generate_tournament(107)
    got = {
        name: {g.label: [s.label for s in g.slots] for g in ph.groups}
        for name, ph in t.phases.items()
    }
    assert got == SANT_ADRIA_2026


REAL_DRAWS = sorted((Path(__file__).parent / "fixtures" / "sorteig_opens").glob("*.json"))


@pytest.mark.parametrize("draw", REAL_DRAWS, ids=lambda p: p.stem)
def test_generator_matches_every_published_draw(draw):
    """Sorteigs oficials de la federació (GRUPS PREVIA / PRE-PREVIA /
    PRE-PRE-PREVIA de cada open): el generador els ha de reproduir grup per grup."""
    import json

    from fcb_opens.generator import generate_tournament

    real = json.loads(draw.read_text(encoding="utf-8"))
    t = generate_tournament(real["n_inscrits"])
    got = {
        name: {g.label: [s.label for s in g.slots] for g in ph.groups}
        for name, ph in t.phases.items()
    }
    assert got == real["phases"]


def test_projection_labels_the_best_second_slot():
    proj = build_projection_from_seeded(_synthetic_ranking(107))
    assert proj["qualifiers"] == {"P": 16, "PP": 16, "PPP": 7}
    pp = next(p for p in proj["phases"] if p["name"] == "PP")
    q = next(g for g in pp["groups"] if g["label"] == "Q")
    assert q["players"][2]["placeholder"] == "7-PPP"
    assert q["players"][2]["label"] == "Millor segon de Pre-pre-prèvies"
    w = next(g for g in pp["groups"] if g["label"] == "W")
    assert w["players"][2]["label"] == "Guanyador 1r de Pre-pre-prèvies"


# --------------------------------------------------------------------------- #
# RÀNQUING INICIAL path (seed order taken verbatim from the federation's PDF)
# --------------------------------------------------------------------------- #


@needs_ranking
def test_parse_ranking_inicial_mataro():
    res = parse_ranking_inicial_pdf(RANKING_PDF)
    assert res.open_name == 'XIV OPEN LES SANTES DE MATARO "MEMORIAL JOAQUIM ANDRES"'
    assert res.num_players == 98
    # Posició is contiguous 1..N (authoritative seed order).
    assert [e.posicio for e in res.entries] == list(range(1, 99))
    # 85 players carry an opens ranking position; the last 13 (Definitiva/
    # Provisional) don't.
    assert sum(1 for e in res.entries if e.ranking_position is None) == 13
    top = res.entries[0]
    assert top.player_name.startswith("MORENO CORT")
    assert top.club == "C.B. LLEIDA"
    assert top.ranking_position == 1
    assert top.punts == 801
    # Negative points parse (seed 85 has -2 in the real PDF).
    assert any(e.punts < 0 for e in res.entries)


@needs_ranking
def test_build_projection_from_seeded_mataro():
    """The projected bracket must match the official GRUPS PPP draw exactly."""
    ranking = parse_ranking_inicial_pdf(RANKING_PDF)
    proj = build_projection_from_seeded(ranking, season="2025-2026")

    assert proj["num_inscriptions"] == 98
    # N=98 -> overflow=17 -> P=16, PP=16, PPP=1 (generator closed form).
    assert proj["structure"] == {"P": 16, "PP": 16, "PPP": 1}

    # The single PPP group (label AG) holds the three deepest seeds 96/97/98 —
    # verbatim what the federation published in GRUPS PRE-PRE-PRÈVIA.
    ppp = next(p for p in proj["phases"] if p["name"] == "PPP")
    assert ppp["n_groups"] == 1
    ag = ppp["groups"][0]
    assert ag["label"] == "AG"
    seeds_in_ag = [p["seed_order"] for p in ag["players"] if p["kind"] == "player"]
    assert seeds_in_ag == [96, 97, 98]

    # Setzens, com al full SETZENS DE FINAL: el 16 contra el 1-P ... l'1 contra el 16-P.
    setzens = proj["fase_final"]["setzens"]
    assert setzens[0]["a"]["seed_order"] == 16 and setzens[0]["b"]["placeholder"] == "1-P"
    assert setzens[-1]["a"]["seed_order"] == 1 and setzens[-1]["b"]["placeholder"] == "16-P"
    assert setzens[-1]["b"]["label"] == "Guanyador 16è de Prèvies"


def test_build_projection_from_seeded_uses_posicio_verbatim():
    """Seed order comes straight from Posició — no re-seeding (CI-safe, no PDF)."""
    proj = build_projection_from_seeded(_synthetic_ranking(98))
    assert proj["structure"] == {"P": 16, "PP": 16, "PPP": 1}
    # Seeds 1..16 enter the Fase Final directly, in Posició order.
    direct = [s for s in proj["seeds"] if s["entry_phase"] == "Fase Final"]
    assert [s["seed_order"] for s in direct] == list(range(1, 17))
    assert direct[0]["player_name"] == "PLAYER 001"
    # Every prèvia seat for seeds 17..98 is filled exactly once.
    placed = sorted(
        p["seed_order"]
        for ph in proj["phases"]
        for g in ph["groups"]
        for p in g["players"]
        if p["kind"] == "player"
    )
    assert placed == list(range(17, 99))
    # The deepest group (PPP) still gets the last three seeds.
    ppp = next(p for p in proj["phases"] if p["name"] == "PPP")
    assert [p["seed_order"] for p in ppp["groups"][0]["players"] if p["kind"] == "player"] == [
        96,
        97,
        98,
    ]
