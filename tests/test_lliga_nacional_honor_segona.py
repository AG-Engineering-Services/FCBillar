"""Les jornades de la Divisió d'Honor i de la Segona, que tenen disposició pròpia."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from fcbillar import lliga_nacional as LN
from fcbillar.db.migrations import ensure_schema

NACIONAL = Path(__file__).parent / "fixtures" / "nacional"


@pytest.fixture(scope="module")
def honor() -> LN.Jornada:
    return LN.llegeix_jornada(NACIONAL / "liga_nal_h_j5_2526.pdf")


@pytest.fixture(scope="module")
def segona_a() -> LN.Jornada:
    return LN.llegeix_jornada(NACIONAL / "liga_nal_2a_j5_2526.pdf")


@pytest.fixture(scope="module")
def segona_bd() -> LN.Jornada:
    return LN.llegeix_jornada(NACIONAL / "liga_nal_2bd_j5_2526.pdf")


def test_honor_capcalera_i_encontres(honor):
    assert (honor.numero, honor.data) == (5, date(2025, 11, 22))
    [grup] = honor.grups
    assert grup.grup is None
    assert len(grup.encontres) == 5
    assert len(grup.classificacio) == 10


def test_honor_partida_amb_entrades(honor):
    e = honor.grups[0].encontres[1]
    assert (e.local, e.punts_local, e.punts_visitant, e.visitant) == (
        "INVIKTCUES GRANOLLERS",
        4,
        4,
        "MADRID E. NACIONAL",
    )
    p = e.partides[0]
    assert (p.jugador_local, p.caramboles_local, p.jugador_visitant) == (
        "Sergio Jiménez Galera",
        40,
        "Mikael De Volegaere",
    )
    assert (p.caramboles_visitant, p.entrades) == (28, 17)


def test_honor_series_amb_l_equip_de_la_classificacio(honor):
    s = honor.millors_series[0]
    assert (s.jugador, s.equip, s.serie) == ("Jesús Rico Francés", "C.B. CASTALLA", 13)


def test_segona_un_fitxer_per_grup_a_i_un_per_grups_b_a_d(segona_a, segona_bd):
    assert [g.grup for g in segona_a.grups] == ["A"]
    assert [g.grup for g in segona_bd.grups] == ["B", "C", "D"]
    # Cada fitxer porta la seva numeració: les dues són la «jornada 5».
    assert segona_a.numero == segona_bd.numero == 5
    assert segona_a.data != segona_bd.data


def test_segona_resultat_al_marge_i_entrades_al_mig(segona_a):
    e = segona_a.grups[0].encontres[2]
    assert (e.local, e.punts_local, e.punts_visitant, e.visitant) == (
        "C.B. MARACENA “B”",
        5,
        3,
        "C.E. ELDENSE",
    )
    p = e.partides[1]
    assert (p.jugador_local, p.caramboles_local, p.entrades, p.caramboles_visitant) == (
        "Carlos Samaniego",
        23,
        50,
        23,
    )


def test_segona_del_2018_te_el_mateix_format():
    j = LN.llegeix_jornada(NACIONAL / "liga_nal_2_j3_1819.pdf")
    assert [g.grup for g in j.grups] == ["A", "B", "C"]
    assert j.data == date(2018, 11, 3)


def test_desar_un_fitxer_de_segona_no_esborra_els_grups_de_l_altre(tmp_path, segona_a, segona_bd):
    conn = ensure_schema(tmp_path / "t.db")
    LN.desa_jornada(conn, segona_a, "2", "2025-2026")
    LN.desa_jornada(conn, segona_bd, "2", "2025-2026")
    # Tornar-ne a desar un no ha de duplicar ni esborrar res de l'altre.
    LN.desa_jornada(conn, segona_a, "2", "2025-2026")
    per_grup = dict(
        conn.execute(
            "SELECT grup, COUNT(*) FROM nacional_encontres WHERE jornada = 5 GROUP BY grup"
        ).fetchall()
    )
    assert per_grup == {"A": 3, "B": 3, "C": 3, "D": 2}
    n_partides = conn.execute("SELECT COUNT(*) FROM nacional_partides").fetchone()[0]
    assert n_partides == 4 * 11


def test_un_pdf_amb_unes_quantes_jornades_no_es_llegeix_com_si_fos_una():
    # «j7a9»: les jornades 7, 8 i 9 seguides. Juntes, cada equip jugaria tres
    # vegades la jornada 7.
    with pytest.raises(LN.FormatDesconegut, match="més d'una jornada"):
        LN.llegeix_jornada(NACIONAL / "liga_nal_h_j7a9_2122.pdf")
