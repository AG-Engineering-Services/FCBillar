"""El lector dels PDF de la Lliga Nacional de la RFEB (Primera Divisió).

Les proves van contra PDF de debò, perquè el que es pot trencar aquí és la
disposició de la pàgina i no cap regla: dos encontres de costat, noms i números
que no cauen a la mateixa alçada, equips amb el nom en dues línies, i una fila de
totals que uns anys hi és i d'altres no.

    liga_nal_1_j1_2627.pdf    jornada 1 de la 2026-27, amb totals
    liga_nal_1_j1_1819.pdf    jornada 1 de la 2018-19, sense totals
    liga_nal_1_cjug_2627.pdf  classificació de jugadors després de la jornada 2
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from fcbillar.lliga_nacional import (
    FormatDesconegut,
    Jornada,
    llegeix_classificacio_de_jugadors,
    llegeix_jornada,
)

NACIONAL = Path(__file__).parent / "fixtures" / "nacional"


@pytest.fixture(scope="module")
def j1_2627() -> Jornada:
    return llegeix_jornada(NACIONAL / "liga_nal_1_j1_2627.pdf")


@pytest.fixture(scope="module")
def j1_1819() -> Jornada:
    return llegeix_jornada(NACIONAL / "liga_nal_1_j1_1819.pdf")


def _encontre(jornada: Jornada, tros: str):
    return next(
        e for g in jornada.grups for e in g.encontres if tros in e.local or tros in e.visitant
    )


def test_la_capcalera_diu_la_jornada_i_el_dia(j1_2627: Jornada) -> None:
    assert j1_2627.numero == 1
    assert j1_2627.data == date(2026, 9, 12)


def test_hi_ha_dos_grups_amb_vuit_equips_i_quatre_encontres(j1_2627: Jornada) -> None:
    assert [(g.grup, len(g.classificacio), len(g.encontres)) for g in j1_2627.grups] == [
        ("A", 8, 4),
        ("B", 8, 4),
    ]


def test_la_classificacio_del_grup(j1_2627: Jornada) -> None:
    primer = j1_2627.grups[0].classificacio[0]
    assert (primer.posicio, primer.equip, primer.punts) == (1, "C.B. SOLLER", 3)
    assert (primer.caramboles, primer.entrades, primer.mitjana) == (146, 180, 0.811)
    assert primer.parcials == 8
    # El rètol «GRUPO» s'escriu a l'alçada de la tercera fila i no és part del nom.
    assert j1_2627.grups[0].classificacio[2].equip == "C.B. AYAMONTE"


def test_un_encontre_amb_les_seves_partides(j1_2627: Jornada) -> None:
    e = _encontre(j1_2627, "SANT ADRI")
    # El nom del local és massa llarg i salta a la línia de sota del resultat.
    assert e.local == "INVIKTCUES GRANOLLERS 'B'"
    assert (e.punts_local, e.punts_visitant) == (3, 5)
    assert (e.mitjana_local, e.mitjana_visitant) == (0.759, 0.918)
    assert [
        (p.jugador_local, p.caramboles_local, p.caramboles_visitant, p.jugador_visitant)
        for p in e.partides
    ] == [
        ("Joan Espinasa Sánchez", 34, 40, "Juan Carlos Jiménez Vasco"),
        ("César Mas Canadell", 40, 40, "Jesús Luque Martínez"),
        ("Juan A. Navarro Carmona", 38, 36, "Miguel Ángel Guerrero González"),
        ("Josep Martín Vilchez", 17, 40, "Jonatan Hernández López"),
    ]
    assert [p.entrades for p in e.partides] == [33, 43, 50, 44]


def test_l_encontre_del_costat_no_s_hi_barreja(j1_2627: Jornada) -> None:
    """Van de dos en dos: llegint línia a línia, els jugadors de l'un cauen a l'altre."""
    esquerra = _encontre(j1_2627, "TOMELLOSO")
    dreta = _encontre(j1_2627, "ELDENSE")
    assert (esquerra.local, esquerra.visitant) == ("C.B. C. TOMELLOSO", "C.B. MURCIA")
    assert (dreta.local, dreta.visitant) == ("C.B.C. EXC. ELDENSE", "C.B. SEVILLA")
    assert esquerra.partides[0].jugador_visitant == "Fernando Alonso López"
    assert dreta.partides[0].jugador_local == "Ramón López Martínez"


@pytest.mark.parametrize("quina", ["j1_2627", "j1_1819"])
def test_els_totals_i_el_resultat_surten_de_les_partides(quina: str, request) -> None:
    """El que fa de prova del nou: tot el que es pot sumar ha de quadrar."""
    jornada: Jornada = request.getfixturevalue(quina)
    for g in jornada.grups:
        for e in g.encontres:
            assert sum(p.caramboles_local for p in e.partides) == e.caramboles_local
            assert sum(p.caramboles_visitant for p in e.partides) == e.caramboles_visitant
            assert sum(p.entrades for p in e.partides) == e.entrades
            guanyades = sum(1 for p in e.partides if p.caramboles_local > p.caramboles_visitant)
            empatades = sum(1 for p in e.partides if p.caramboles_local == p.caramboles_visitant)
            assert 2 * guanyades + empatades == e.punts_local


def test_un_pdf_sense_fila_de_totals_tambe_es_llegeix(j1_1819: Jornada) -> None:
    assert j1_1819.data == date(2018, 10, 6)
    e = _encontre(j1_1819, "AYAMONTE")
    assert (e.local, e.visitant) == ("C.B. C. AYAMONTE", "ALICANTE B.C.")
    assert (e.punts_local, e.punts_visitant) == (3, 5)
    assert len(e.partides) == 4
    assert e.entrades == 29 + 47 + 50 + 50


def test_les_millors_series(j1_2627: Jornada) -> None:
    primera = j1_2627.millors_series[0]
    assert (primera.jugador, primera.equip, primera.serie) == (
        "Alain Lagúe Roldan",
        "C.B. Soller",
        12,
    )
    assert len(j1_2627.millors_series) == 10


def test_la_classificacio_de_jugadors() -> None:
    jugadors = llegeix_classificacio_de_jugadors(NACIONAL / "liga_nal_1_cjug_2627.pdf")
    assert len(jugadors) == 79
    primer = jugadors[0]
    # L'equip comença més a l'esquerra que la seva capçalera: «C.B.» no és del jugador.
    assert (primer.jugador, primer.equip) == ("Juan Carlos Jiménez Vasco", "C.B. Sant Adriá")
    assert (primer.jugades, primer.guanyades, primer.caramboles, primer.entrades) == (2, 2, 80, 67)
    assert primer.mitjana == 1.194
    assert [j.posicio for j in jugadors] == list(range(1, 80))


def test_un_pdf_que_no_es_una_jornada_ho_diu() -> None:
    with pytest.raises(FormatDesconegut):
        llegeix_jornada(NACIONAL / "liga_nal_1_cjug_2627.pdf")
