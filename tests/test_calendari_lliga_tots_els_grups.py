"""Els grups que el lector es deixava, i com se sap que se'ls deixa.

El 6 de setembre de 2026 la federació va publicar de cop els dotze calendaris
de la lliga de tres bandes 26/27. Passats pel lector d'aleshores, quatre en
sortien escapçats i ningú no ho hauria sabut:

    honor grup A    54 de 56        3a grup A   49 de 56
    1a grup A       36 de 56        3a grup B   52 de 56

La causa era que les columnes s'agrupaven pel punt on comencen. El text dels
encontres va **centrat**, o sigui que el principi es mou amb la llargada del nom
de l'equip —fins a 25,9 punts a la 1a grup A— i el llindar de columna és de 20:
la columna es partia en dues i les files del mig no cabien enlloc. Agrupant pel
centre, la dispersió d'aquella mateixa columna és de 0,1 punts.

I no en sortia cap error: el resultat continuava sent un calendari, només que
amb forats. Per això hi ha `problemes()`, i per això les proves d'aquí no miren
només que el número surti bé, sinó que la comprovació hauria cridat.

Els dos PDF de referència són els dos casos:

- **Honor grup A** — la capçalera diu `DIVISIÓ HONOR`, sense número, i el lector
  només sabia llegir `1ª DIVISIÓ`: la divisió quedava buida.
- **1a grup A** — el pitjor escapçat dels dotze.
"""

from __future__ import annotations

import collections
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from fcbillar.calendari_lliga import llegeix, problemes

FIXTURES = Path(__file__).parent / "fixtures"
HONOR_A = FIXTURES / "calendari_lliga_2627_honor_grupA.pdf"
PRIMERA_A = FIXTURES / "calendari_lliga_2627_1a_grupA.pdf"


@pytest.fixture(scope="module")
def honor_a():
    return llegeix(HONOR_A)


@pytest.fixture(scope="module")
def primera_a():
    return llegeix(PRIMERA_A)


# --------------------------- la divisió d'Honor ---------------------------


def test_honor_te_divisio(honor_a) -> None:
    """'Honor' és com l'anomena `categories.norm_divisio`, que mana."""
    assert honor_a.divisio == "Honor"
    assert honor_a.grup == "A"


def test_honor_no_es_desa_sense_divisio(honor_a) -> None:
    """Amb la divisió buida els dos grups d'Honor s'ajuntarien en un de sol."""
    assert "sense divisio" not in problemes(honor_a)


# --------------------------- els encontres que faltaven ---------------------------


@pytest.mark.parametrize(
    "nom, equips",
    [("honor_a", 8), ("primera_a", 8)],
)
def test_hi_son_tots_els_encontres(request, nom, equips) -> None:
    cal = request.getfixturevalue(nom)
    assert len(cal.equips) == equips
    assert len(cal.encontres) == equips // 2 * 14


def test_cada_jornada_te_els_mateixos_encontres(primera_a) -> None:
    """El que es perdia: jornades de 2 i de 3 en un grup de vuit equips."""
    per_jornada = collections.Counter(e.jornada for e in primera_a.encontres)
    assert sorted(per_jornada) == list(range(1, 15))
    assert set(per_jornada.values()) == {4}


def test_tothom_juga_cada_jornada(primera_a) -> None:
    for jornada in range(1, 15):
        enc = [e for e in primera_a.encontres if e.jornada == jornada]
        juguen = sorted(x for e in enc for x in (e.local, e.visitant))
        assert juguen == sorted(primera_a.equips), f"jornada {jornada}"


def test_l_anada_i_la_tornada_es_corresponen(primera_a) -> None:
    """La jornada 8 és la 1a amb els camps girats, la 9 la 2a, i així fins a la 14."""
    for jornada in range(1, 8):
        anada = {(e.local, e.visitant) for e in primera_a.encontres if e.jornada == jornada}
        tornada = {(e.local, e.visitant) for e in primera_a.encontres if e.jornada == jornada + 7}
        assert {(v, l) for l, v in anada} == tornada, f"jornada {jornada}"


# --------------------------- la comprovació ---------------------------


def test_els_dos_grups_quadren(honor_a, primera_a) -> None:
    assert problemes(honor_a) == []
    assert problemes(primera_a) == []


def test_una_jornada_escapcada_es_veu(primera_a) -> None:
    """Exactament el que passava: una fila de menys a una jornada."""
    una_menys = [e for e in primera_a.encontres if e != primera_a.encontres[0]]
    escapcat = replace(primera_a, encontres=tuple(una_menys))

    assert any("menys aquestes" in p for p in problemes(escapcat))


def test_una_jornada_sencera_que_falta_es_veu(primera_a) -> None:
    sense_la_setena = replace(
        primera_a, encontres=tuple(e for e in primera_a.encontres if e.jornada != 7)
    )

    assert any("falten" in p for p in problemes(sense_la_setena))


def test_un_equip_dos_cops_el_mateix_dia_es_veu(primera_a) -> None:
    """Si dues columnes s'aparellen malament, l'error surt com un equip repetit."""
    dolent = replace(
        primera_a,
        encontres=tuple(
            replace(e, local=primera_a.equips[0]) if e.jornada == 1 else e
            for e in primera_a.encontres
        ),
    )

    assert any("més d'un cop" in p for p in problemes(dolent))


def test_un_equip_contra_ell_mateix_es_veu(primera_a) -> None:
    primer = primera_a.encontres[0]
    dolent = replace(
        primera_a,
        encontres=(replace(primer, visitant=primer.local),) + primera_a.encontres[1:],
    )

    assert any("contra ell mateix" in p for p in problemes(dolent))


def test_un_calendari_buit_es_veu(primera_a) -> None:
    assert problemes(replace(primera_a, equips=(), encontres=())) == ["cap encontre"]


# --------------------------- les dates ---------------------------


def test_les_dates_son_les_de_la_lliga(honor_a) -> None:
    """Les jornades són comunes a tota la lliga; aquestes són les de la 26/27."""
    assert honor_a.dates[1] == date(2026, 9, 26)
    assert honor_a.dates[8] == date(2027, 1, 9)
    assert honor_a.dates[14] == date(2027, 4, 3)


# --------------------------- llegir de la memòria ---------------------------


def test_llegeix_els_bytes_igual_que_el_fitxer(honor_a) -> None:
    """La ingesta del web no escriu els PDF enlloc: els passa tal com arriben."""
    assert llegeix(HONOR_A.read_bytes()) == honor_a
