"""La Divisió d'Honor i la Segona de la Lliga Nacional, llegides dels seus PDF.

Les dues van en pàgina vertical, amb un encontre a sota de l'altre, però cada
una posa el resultat en un lloc: Honor a la línia dels equips, Segona als
marges d'una de les partides. Les proves van contra PDF de debò de la 2025-26:

    liga_nal_h_j1_2526.pdf      Honor, jornada 1
    liga_nal_h_j12_2526.pdf     Honor, jornada 12, amb tres encontres suspesos
    liga_nal_2_j1_2526.pdf      Segona, jornada 1, grups B, C i D
    liga_nal_2a_j1_2526.pdf     Segona, jornada 1, grup A
    liga_nal_2_cjug_2526.pdf    Segona, classificació de jugadors, sense punts
    calendari_honor_2526.pdf    Honor, amb files de la primera pàgina repetides
    calendari_2_2526.pdf        Segona, els quatre grups
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from fcbillar import lliga_nacional as LN
from fcbillar.db.migrations import ensure_schema

NACIONAL = Path(__file__).parent / "fixtures" / "nacional"
AVUI = date(2025, 10, 8)


@pytest.fixture(scope="module")
def honor() -> LN.Jornada:
    return LN.llegeix_jornada(NACIONAL / "liga_nal_h_j1_2526.pdf")


@pytest.fixture(scope="module")
def segona() -> LN.Jornada:
    return LN.llegeix_jornada(NACIONAL / "liga_nal_2_j1_2526.pdf")


@pytest.fixture(scope="module")
def segona_a() -> LN.Jornada:
    return LN.llegeix_jornada(NACIONAL / "liga_nal_2a_j1_2526.pdf")


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    return ensure_schema(tmp_path / "t.db")


def _encontre(jornada: LN.Jornada, tros: str) -> LN.EncontreNacional:
    return next(
        e for g in jornada.grups for e in g.encontres if tros in e.local or tros in e.visitant
    )


# --------------------------- Honor ---------------------------


def test_honor_la_data_va_amb_xifres(honor):
    assert (honor.numero, honor.data) == (1, date(2025, 9, 13))


def test_honor_un_sol_grup_amb_la_classificacio_a_la_pagina_de_despres(honor):
    assert [(g.grup, len(g.classificacio), len(g.encontres)) for g in honor.grups] == [
        (None, 10, 5)
    ]
    primer = honor.grups[0].classificacio[0]
    assert (primer.posicio, primer.equip, primer.punts, primer.parcials) == (
        1,
        "MADRID E. NACIONAL",
        3,
        8,
    )


def test_honor_el_resultat_va_a_la_linia_dels_equips(honor):
    e = _encontre(honor, "AYAMONTE")
    assert (e.local, e.visitant, e.punts_local, e.punts_visitant) == (
        "C.B. AYAMONTE",
        "C.B. CASTALLA",
        2,
        6,
    )
    assert (e.caramboles_local, e.caramboles_visitant, e.entrades) == (128, 152, 130)
    assert (e.mitjana_local, e.mitjana_visitant) == (0.985, 1.169)
    assert [
        (p.jugador_local, p.caramboles_local, p.caramboles_visitant, p.entrades) for p in e.partides
    ] == [
        ("Javier Díaz Rodríguez", 38, 40, 35),
        ("Jaime Sánchez Faraco", 24, 40, 28),
        ("Germán Núñez Pérez", 26, 40, 29),
        ("Manuel González Castrillo", 40, 32, 38),
    ]


def test_honor_les_millors_series_no_s_emporten_la_jornada_que_ve(honor):
    assert len(honor.millors_series) == 12
    primera = honor.millors_series[0]
    assert (primera.jugador, primera.equip, primera.serie) == (
        "Carlos Anguita Díaz",
        "DS Predator Cartagena",
        11,
    )


def test_honor_un_encontre_suspes_hi_es_sense_resultat():
    j12 = LN.llegeix_jornada(NACIONAL / "liga_nal_h_j12_2526.pdf")
    (grup,) = j12.grups
    assert grup.classificacio == []
    suspesos = [e for e in grup.encontres if e.suspes]
    assert [(e.local, e.visitant) for e in suspesos] == [
        ("C.B. PAIPORTA", "C.B. AYAMONTE"),
        ("ALICANTE B.C.", "CHEF AMADEO GANDIA"),
        ("ASOC. B. PALMA", "C.B. CASTALLA"),
    ]
    assert all(e.punts_local is None and e.partides == [] for e in suspesos)
    jugat = _encontre(j12, "MÓSTOLES")
    assert (jugat.punts_local, jugat.punts_visitant, len(jugat.partides)) == (7, 1, 4)


# --------------------------- Segona ---------------------------


def test_segona_dos_pdf_per_jornada_un_per_al_grup_a(segona, segona_a):
    assert [(g.grup, len(g.classificacio), len(g.encontres)) for g in segona.grups] == [
        ("B", 6, 3),
        ("C", 6, 3),
        ("D", 5, 2),
    ]
    assert [(g.grup, len(g.classificacio), len(g.encontres)) for g in segona_a.grups] == [
        ("A", 7, 3)
    ]
    assert segona.data == segona_a.data == date(2025, 9, 13)


def test_segona_el_resultat_va_als_marges(segona):
    e = _encontre(segona, "SOLLER")
    assert (e.local, e.visitant, e.punts_local, e.punts_visitant) == (
        "C.B SOLLER",
        "EST. MIR. EL OLIVAR",
        2,
        6,
    )
    assert (e.caramboles_local, e.entrades, e.caramboles_visitant) == (136, 162, 147)
    assert [(p.caramboles_local, p.entrades, p.caramboles_visitant) for p in e.partides] == [
        (39, 33, 40),
        (40, 32, 27),
        (32, 47, 40),
        (25, 50, 40),
    ]
    assert e.partides[0].jugador_visitant == "Raúl Castán Burillo"


def test_segona_l_equip_que_descansa_no_es_cap_encontre(segona):
    d = next(g for g in segona.grups if g.grup == "D")
    equips = {nom for e in d.encontres for nom in (e.local, e.visitant)}
    assert "ABACO C.B." not in equips
    # A la classificació sí que hi és, amb tot a zero.
    assert d.classificacio[-1].equip == "ABACO C.B."
    assert d.classificacio[-1].jugats == 0


@pytest.mark.parametrize("quina", ["honor", "segona", "segona_a"])
def test_el_resultat_surt_de_les_partides(quina, request):
    jornada: LN.Jornada = request.getfixturevalue(quina)
    for g in jornada.grups:
        for e in g.encontres:
            guanyades = sum(1 for p in e.partides if p.caramboles_local > p.caramboles_visitant)
            empatades = sum(1 for p in e.partides if p.caramboles_local == p.caramboles_visitant)
            assert 2 * guanyades + empatades == e.punts_local
            assert e.punts_local + e.punts_visitant == 2 * len(e.partides)


def test_segona_la_classificacio_de_jugadors_no_porta_punts():
    jugadors = LN.llegeix_classificacio_de_jugadors(NACIONAL / "liga_nal_2_cjug_2526.pdf")
    assert len(jugadors) == 164
    assert [j.posicio for j in jugadors] == list(range(1, 165))
    assert all(j.punts is None for j in jugadors)
    assert (jugadors[0].jugador, jugadors[0].equip, jugadors[0].mitjana) == (
        "Raúl Castán Burillo",
        "EST. MIR. EL OLIVAR",
        1.059,
    )


@pytest.mark.parametrize(
    "fitxer", ["liga_nal_2_cjug_2526.pdf", "calendari_honor_2526.pdf", "calendari_2_2526.pdf"]
)
def test_el_que_no_es_una_jornada_no_es_llegeix_com_a_jornada(fitxer):
    with pytest.raises(LN.FormatDesconegut):
        LN.llegeix_jornada(NACIONAL / fitxer)


# --------------------------- calendaris ---------------------------


def test_calendari_honor_divuit_jornades_de_cinc():
    calendari = LN.llegeix_calendari(NACIONAL / "calendari_honor_2526.pdf")
    per_jornada = Counter(e.jornada for e in calendari)
    assert sorted(per_jornada) == list(range(1, 19))
    assert set(per_jornada.values()) == {5}
    assert {e.grup for e in calendari} == {""}


def test_calendari_honor_les_files_repetides_no_trepitgen_la_jornada_10():
    """A la segona pàgina, la jornada 1 es torna a escriure a sobre de la 10."""
    calendari = LN.llegeix_calendari(NACIONAL / "calendari_honor_2526.pdf")
    j10 = [(e.local, e.visitant) for e in calendari if e.jornada == 10]
    assert j10[:2] == [
        ("C.B. Castalla", "C.B. Ayamonte"),
        ("Alicante B.C.", "Madrid E. Nacional"),
    ]
    assert {e.data for e in calendari if e.jornada == 10} == {date(2026, 1, 24)}


def test_calendari_segona_quatre_grups_i_el_que_descansa_fora():
    calendari = LN.llegeix_calendari(NACIONAL / "calendari_2_2526.pdf")
    jornades = Counter(g for g, _ in Counter((e.grup, e.jornada) for e in calendari))
    assert jornades == {"A": 14, "B": 10, "C": 10, "D": 10}
    a1 = [(e.local, e.visitant) for e in calendari if e.grup == "A" and e.jornada == 1]
    assert a1[1:] == [('C.B Murcia "B"', "C.B.C Campello"), ("C.B. Caravaca", "C.E. Eldense")]
    d1 = [(e.local, e.visitant) for e in calendari if e.grup == "D" and e.jornada == 1]
    assert d1 == [("C.B. Barcelona", 'A.B Palma "C"'), ("C.B Soller", "Est. Mir. El Olivar")]


# --------------------------- desar i pujar ---------------------------


def _per_grup(conn, taula: str) -> dict[str, int]:
    return dict(conn.execute(f"SELECT grup, COUNT(*) FROM {taula} WHERE jornada = 1 GROUP BY grup"))


def test_els_dos_pdf_de_segona_no_s_esborren_l_un_a_l_altre(conn, segona, segona_a):
    for _ in range(2):
        LN.desa_jornada(conn, segona, "2")
        LN.desa_jornada(conn, segona_a, "2")
    assert _per_grup(conn, "nacional_encontres") == {"A": 3, "B": 3, "C": 3, "D": 2}
    assert _per_grup(conn, "nacional_classificacio") == {"A": 7, "B": 6, "C": 6, "D": 5}
    series = conn.execute("SELECT COUNT(*) FROM nacional_millors_series").fetchone()[0]
    assert series == len(segona.millors_series) + len(segona_a.millors_series)


def test_el_calendari_de_segona_respecta_cada_grup_jugat(conn, segona_a):
    LN.desa_jornada(conn, segona_a, "2")
    calendari = LN.llegeix_calendari(NACIONAL / "calendari_2_2526.pdf")
    LN.desa_calendari(conn, calendari, "2", "2025-2026")
    jugats = dict(
        conn.execute(
            "SELECT grup, COUNT(*) FROM nacional_encontres "
            "WHERE jornada = 1 AND punts_local IS NOT NULL GROUP BY grup"
        )
    )
    assert jugats == {"A": 3}
    assert _per_grup(conn, "nacional_encontres") == {"A": 3, "B": 3, "C": 3, "D": 2}


def test_un_encontre_suspes_es_desa_com_per_jugar(conn):
    LN.desa_jornada(conn, LN.llegeix_jornada(NACIONAL / "liga_nal_h_j12_2526.pdf"), "honor")
    per_jugar = conn.execute(
        "SELECT COUNT(*) FROM nacional_encontres WHERE jornada = 12 AND punts_local IS NULL"
    ).fetchone()[0]
    assert per_jugar == 3


def test_la_classificacio_de_jugadors_de_segona_es_desa_sense_punts(conn):
    jugadors = LN.llegeix_classificacio_de_jugadors(NACIONAL / "liga_nal_2_cjug_2526.pdf")
    assert LN.desa_classificacio_de_jugadors(conn, jugadors, "2", "2025-2026") == 164
    assert (
        conn.execute("SELECT COUNT(*) FROM nacional_jugadors WHERE punts IS NULL").fetchone()[0]
        == 164
    )


def test_pujar_els_dos_pdf_de_segona_fa_dos_fitxers(tmp_path):
    a = LN.reconeix_i_desa(NACIONAL / "liga_nal_2a_j1_2526.pdf", "2", tmp_path, AVUI)
    resta = LN.reconeix_i_desa(NACIONAL / "liga_nal_2_j1_2526.pdf", "2", tmp_path, AVUI)
    assert (a.fitxer, resta.fitxer) == (
        "2025-2026/2/liga_nal_2_j1_A.pdf",
        "2025-2026/2/liga_nal_2_j1_BCD.pdf",
    )


@pytest.mark.parametrize(
    ("fitxer", "divisio", "tipus", "nom"),
    [
        ("liga_nal_h_j1_2526.pdf", "honor", "jornada", "liga_nal_honor_j1.pdf"),
        ("calendari_honor_2526.pdf", "honor", "calendari", "calendari.pdf"),
        ("calendari_2_2526.pdf", "2", "calendari", "calendari.pdf"),
        ("liga_nal_2_cjug_2526.pdf", "2", "jugadors", "liga_nal_2_cjug.pdf"),
    ],
)
def test_honor_i_segona_es_reconeixen_sols(tmp_path, fitxer, divisio, tipus, nom):
    r = LN.reconeix_i_desa(NACIONAL / fitxer, divisio, tmp_path, AVUI)
    assert (r.tipus, r.fitxer) == (tipus, f"2025-2026/{divisio}/{nom}")
