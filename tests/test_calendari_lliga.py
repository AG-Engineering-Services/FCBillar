"""Lectura dels calendaris oficials de grup de la lliga.

Els PDF de referència són els que la federació va publicar per a la 2026-27:

- 1a divisió grup B — vuit equips i les catorze dates bones.
- 4a divisió grup D — set equips, o sigui que cada jornada un descansa. És el
  cas que destapa qualsevol aparellament de columnes fet per ordre d'aparició:
  la fila de l'equip que descansa té una columna sola.
- 2a divisió grup A — el que la federació va publicar amb les dates mal posades:
  `26/09/2026` a totes les jornades menys la 1a i la 8a.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from fcbillar.calendari_lliga import (
    dates_de_referencia,
    esmena_dates,
    llegeix,
)

FIXTURES = Path(__file__).parent / "fixtures"
PRIMERA_B = FIXTURES / "calendari_lliga_2627_1a_grupB.pdf"
SEGONA_A = FIXTURES / "calendari_lliga_2627_2a_grupA.pdf"
QUARTA_D = FIXTURES / "calendari_lliga_2627_4a_grupD.pdf"

#: Les catorze jornades de la 2026-27, totes en dissabte.
DATES = {
    1: date(2026, 9, 26), 2: date(2026, 10, 10), 3: date(2026, 10, 17),
    4: date(2026, 11, 7), 5: date(2026, 11, 21), 6: date(2026, 12, 19),
    7: date(2027, 1, 2), 8: date(2027, 1, 9), 9: date(2027, 1, 30),
    10: date(2027, 2, 20), 11: date(2027, 2, 27), 12: date(2027, 3, 13),
    13: date(2027, 3, 20), 14: date(2027, 4, 3),
}


@pytest.fixture(scope="module")
def primera_b():
    return llegeix(PRIMERA_B)


@pytest.fixture(scope="module")
def quarta_d():
    return llegeix(QUARTA_D)


@pytest.fixture(scope="module")
def segona_a():
    return llegeix(SEGONA_A)


def test_capcalera(primera_b) -> None:
    assert primera_b.temporada == "2026/27"
    assert primera_b.divisio == "1a"
    assert primera_b.grup == "B"


def test_vuit_equips_catorze_jornades_i_quatre_encontres(primera_b) -> None:
    assert len(primera_b.equips) == 8
    assert len(primera_b.encontres) == 14 * 4
    per_jornada = {j: 0 for j in range(1, 15)}
    for e in primera_b.encontres:
        per_jornada[e.jornada] += 1
    assert set(per_jornada.values()) == {4}


def test_les_dates_son_les_de_la_temporada(primera_b) -> None:
    assert primera_b.dates == DATES
    assert all(e.data.weekday() == 5 for e in primera_b.encontres), "totes en dissabte"


def test_la_primera_jornada_del_banyoles(primera_b) -> None:
    """El cas que es va demanar: 26/9, Manresa "A" contra Banyoles "A"."""
    primera = primera_b.de('C.B. BANYOLES "A"')[0]
    assert primera.jornada == 1
    assert primera.data == date(2026, 9, 26)
    assert primera.local == 'C.B. MANRESA "A"'
    assert primera.visitant == 'C.B. BANYOLES "A"'


def test_cada_equip_juga_una_vegada_per_jornada(primera_b) -> None:
    for jornada in range(1, 15):
        equips = [
            equip
            for e in primera_b.encontres
            if e.jornada == jornada
            for equip in (e.local, e.visitant)
        ]
        assert len(equips) == len(set(equips)), f"jornada {jornada} repeteix equips"


def test_cap_equip_juga_contra_si_mateix(primera_b, quarta_d, segona_a) -> None:
    for cal in (primera_b, quarta_d, segona_a):
        assert not [e for e in cal.encontres if e.local == e.visitant]


def test_grup_senar_un_equip_descansa_cada_jornada(quarta_d) -> None:
    """Amb set equips hi ha tres encontres per jornada, no quatre."""
    assert len(quarta_d.equips) == 7
    assert len(quarta_d.encontres) == 14 * 3
    banyoles = quarta_d.de('C.B. BANYOLES "C"')
    assert len(banyoles) == 12, "descansa dues jornades de catorze"


def test_la_segona_divisio_porta_les_dates_malament(segona_a) -> None:
    """Tal com la federació el va publicar, per no arreglar-ho en silenci."""
    dates = segona_a.dates
    assert dates[1] == date(2026, 9, 26)
    assert dates[8] == date(2027, 1, 9)
    repetides = [j for j, d in dates.items() if d == date(2026, 9, 26)]
    assert len(repetides) == 13, "totes menys la 8a duien la data de la 1a"


def test_les_dates_de_referencia_ignoren_el_grup_espatllat(
    primera_b, quarta_d, segona_a
) -> None:
    assert dates_de_referencia([primera_b, quarta_d, segona_a]) == DATES


def test_esmenar_nomes_toca_les_dates(segona_a) -> None:
    esmenat = esmena_dates(segona_a, DATES)
    assert esmenat.dates == DATES
    # Els emparellaments del PDF eren bons: el que fallava era el dia.
    assert [(e.local, e.visitant) for e in esmenat.encontres] == [
        (e.local, e.visitant) for e in segona_a.encontres
    ]


def test_un_grup_espatllat_tot_sol_no_dona_referencia(segona_a) -> None:
    """Sense cap grup bo amb què comparar, val més no dir res que dir mentides."""
    assert dates_de_referencia([segona_a]) == {}


def test_el_banyoles_b_queda_amb_les_catorze_dates(segona_a) -> None:
    partides = esmena_dates(segona_a, DATES).de('C.B. BANYOLES "B"')
    assert len(partides) == 14
    assert [p.data for p in partides] == [DATES[j] for j in range(1, 15)]
