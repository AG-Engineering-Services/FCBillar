"""Lector dels resultats de Kozoom (còpies del Wayback Machine)."""

from datetime import date
from pathlib import Path

from fcbillar.kozoom import (
    de_les_pagines_de_jugador,
    llegeix_classificacio,
    llegeix_partides,
    llegeix_titol,
    nom_umb,
    proves_del_jugador,
)

FIX = Path(__file__).parent / "fixtures" / "kozoom"


def _html(nom: str) -> str:
    return (FIX / nom).read_text(encoding="utf-8")


def test_noms_a_l_ordre_de_la_umb():
    assert nom_umb("Esteve MATA") == "MATA Esteve"
    assert nom_umb("Michel VAN SILFHOUT") == "VAN SILFHOUT Michel"
    assert nom_umb("Ricardo GARCIA ALARCON") == "GARCIA ALARCON Ricardo"


def test_titol():
    t = llegeix_titol("3-Cushion - World Cup - Hurghada (EGY) - 9/4/06 to 9/9/06")
    assert (t.disciplina, t.nom, t.inici, t.fi) == ("3-Cushion", "World Cup", date(2006, 9, 4), date(2006, 9, 9))


def test_classificacio_del_quadre_71_2_de_l_europeu_2023():
    titol, files, _ = llegeix_classificacio(_html("classificacio_ec_712_2023.html"))
    assert (titol.disciplina, titol.nom) == ("Balk-Line 71/2", "European Championship")
    mata = next(f for f in files if f.jugador == "MATA Esteve")
    assert (mata.posicio, mata.caramboles, mata.entrades, mata.serie1, mata.nacionalitat) == (8, 317, 12, 100, "ES")


def test_partides_d_una_prova_amb_el_guanyador_marcat():
    titol, partides, jugadors = llegeix_partides(_html("partides_bundesliga.html"))
    assert titol.nom == "German 1st Bundesliga round 14"
    p = partides[0]
    assert (p.a.jugador, p.a.caramboles, p.a.entrades, p.a.serie, p.a.punts) == ("KERLS Uwe", 40, 55, 6, 2)
    assert (p.b.jugador, p.b.caramboles, p.b.punts) == ("ZITLAU Jörg", 35, 0)
    assert "DE" in {j.nacionalitat for j in jugadors}


def test_partides_a_sets_des_de_la_pagina_d_un_jugador():
    html = _html("jugador_sets_hurghada_2006.html")
    _t, partides, _ = llegeix_partides(html)
    p = partides[0]
    assert p.a.sets == [(10, 13), (12, 14)] and p.b.sets == [(15, 13), (15, 15)]
    assert (p.a.punts, p.b.punts, p.a.caramboles, p.a.entrades) == (0, 2, 22, 27)
    assert proves_del_jugador(html)[0] == (550, "3-Cushion - World Cup - Séville (ESP) - 5/3/04 to 5/9/04")


def test_una_partida_vista_des_dels_dos_jugadors_surt_un_cop():
    html = _html("jugador_sets_hurghada_2006.html")
    ll = de_les_pagines_de_jugador([html, html])
    assert len(ll.partides) == len(llegeix_partides(html)[1])
