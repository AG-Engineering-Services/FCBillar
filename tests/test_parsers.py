"""Tests dels parsers contra pàgines reals del web nou de la FCB.

Les fixtures de `fixtures/nou/` són captures del 2026-08-30, una per cada mena
de pàgina que sabem llegir (`scripts/captura_fixtures_web_nou.py`). Les del
directori de sobre són del web antic, que ja no existeix.

Els valors que s'hi comproven són dades reals de la temporada 2025-26: si la
federació torna a canviar el marcatge, aquests tests cauen abans que no ho faci
una ingesta a mitja nit.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from fcbillar.scraper.parsers import (
    parse_clubs_listing,
    parse_home_current_rankings,
    parse_individuals_divisions,
    parse_individuals_fases,
    parse_individuals_grups_membership,
    parse_individuals_partides,
    parse_individuals_torneigs_list,
    parse_lliga_classificacio,
    parse_lliga_divisions,
    parse_lliga_encontres,
    parse_lliga_grups,
    parse_lliga_inscripcions,
    parse_lliga_jornades,
    parse_lliga_partides,
    parse_partides_jugador,
    parse_ranking,
    parse_ranking_historial,
    parse_rankings_index,
)

NOU = Path(__file__).parent / "fixtures" / "nou"


def fixture(nom: str) -> str:
    return (NOU / f"{nom}.html").read_text(encoding="utf-8")


# ---------------- rànquings ----------------


@pytest.fixture
def ranking_vigent() -> str:
    return fixture("rankings_dades_vigent_124_1")


@pytest.fixture
def ranking_historic() -> str:
    return fixture("rankings_dades_historic_123_6")


@pytest.fixture
def index_rankings() -> str:
    return fixture("rankings_llistat")


def test_parse_ranking_llegeix_tota_la_taula(ranking_vigent: str) -> None:
    res = parse_ranking(ranking_vigent, 124, 1)
    assert len(res.entries) == 715
    assert len(res.players) == 715  # un jugador no pot sortir dues vegades
    assert res.num_seq == 124
    assert res.modalitat_codi_fcb == 1


def test_parse_ranking_primera_fila(ranking_vigent: str) -> None:
    res = parse_ranking(ranking_vigent, 124, 1)
    top = res.entries[0]
    assert top.posicio == 1
    assert top.player_fcb_id == "843"
    assert res.players[0].nom == "MAS CANADELL, JOSEP Mª"
    assert top.mitjana_general == pytest.approx(1.63665)
    assert top.extras == {
        "mitjana_contraris": pytest.approx(0.71222),
        "rang": pytest.approx(1000.0),
        "caramboles": 527,
        "entrades": 322,
        "punts": 28,
        "punts_totals": 30,
        "definitiva": True,
    }


def test_parse_ranking_vigent_te_mes_decimals(ranking_vigent: str, ranking_historic: str) -> None:
    """El rànquing vigent publica cinc decimals i l'històric només tres."""
    vigent = parse_ranking(ranking_vigent, 124, 1).entries[0].mitjana_general
    historic = parse_ranking(ranking_historic, 123, 6).entries[0].mitjana_general
    assert vigent == pytest.approx(1.63665)
    assert historic == pytest.approx(8.562)


def test_parse_ranking_tots_els_jugadors_tenen_id(ranking_vigent: str) -> None:
    res = parse_ranking(ranking_vigent, 124, 1)
    assert all(e.player_fcb_id.isdigit() for e in res.entries)


def test_parse_ranking_sense_taula_es_queixa() -> None:
    with pytest.raises(ValueError):
        parse_ranking("<html><body>res</body></html>", 124, 1)


def test_index_separa_vigent_i_historial(index_rankings: str) -> None:
    idx = parse_rankings_index(index_rankings)
    assert idx.data_vigent == date(2026, 7, 27)
    assert [(c.modalitat_codi_fcb, c.num_seq) for c in idx.vigents] == [
        (1, 124),
        (2, 124),
        (3, 124),
        (4, 124),
        (6, 124),
    ]
    assert all(c.format_url == "llistat" for c in idx.vigents)
    assert len(idx.historial) == 15


def test_historial_va_del_mes_nou_al_mes_antic(index_rankings: str) -> None:
    historial = parse_ranking_historial(index_rankings)
    assert historial[0].data == date(2026, 7, 1)
    assert historial[0].rankings[1] == ("historial", 123)
    dates = [h.data for h in historial]
    assert dates == sorted(dates, reverse=True)


def test_home_current_rankings_es_la_mateixa_pagina(index_rankings: str) -> None:
    """La portada del jugador i l'índex de rànquings ara són la mateixa cosa."""
    home = parse_home_current_rankings(index_rankings)
    assert home.data_ranking == date(2026, 7, 27)
    assert len(home.rankings) == 5


# ---------------- partides d'un jugador ----------------


@pytest.fixture
def partides_843() -> str:
    return fixture("rankings_partides_vigent_124_1_843")


def test_partides_reparteix_per_competicio(partides_843: str) -> None:
    res = parse_partides_jugador(partides_843)
    per_competicio = {
        c: sum(1 for r in res.rows if r.competicio == c) for c in {r.competicio for r in res.rows}
    }
    assert per_competicio == {"LLIGA": 1, "INDIVIDUAL": 14}
    assert len(res.rows) == 15


def test_partides_primera_fila_de_lliga(partides_843: str) -> None:
    res = parse_partides_jugador(partides_843)
    lliga = next(r for r in res.rows if r.competicio == "LLIGA")
    assert lliga.data_partida == date(2026, 3, 15)
    assert lliga.local_nom == "MAS CANADELL, JOSEP Mª"
    assert (lliga.local_punts, lliga.local_caramboles) == (2, 35)
    assert lliga.visitant_nom == "PASTOR BALAGUÉ, JORDI"
    assert (lliga.visitant_punts, lliga.visitant_caramboles) == (0, 12)
    assert lliga.entrades == 16


def test_partides_recull_els_noms(partides_843: str) -> None:
    res = parse_partides_jugador(partides_843)
    assert "MAS CANADELL, JOSEP Mª" in res.noms
    assert len(res.noms) == 15


# ---------------- lliga ----------------


def test_lliga_divisions() -> None:
    divisions = parse_lliga_divisions(fixture("lligues_divisions_36"))
    assert len(divisions) == 5
    assert all(d.lliga_id == 36 for d in divisions)
    assert {d.divisio_id for d in divisions} == {148, 149, 150, 151, 152}
    honor = next(d for d in divisions if d.divisio_id == 148)
    assert honor.nom == "HONOR"


def test_lliga_grups_amb_club_organitzador() -> None:
    grups = parse_lliga_grups(fixture("lligues_grups_36_148"))
    assert len(grups) == 4
    grup_a = next(g for g in grups if g.nom == "GRUP A")
    assert (grup_a.lliga_id, grup_a.divisio_id, grup_a.grup_id) == (36, 148, 316)
    final = next(g for g in grups if g.nom == "FINAL HONOR")
    assert final.club_responsable == "C.B.MATARÓ"


def test_lliga_jornades_amb_data() -> None:
    jornades = parse_lliga_jornades(fixture("lligues_jornades_36_148_316"))
    assert len(jornades) == 14
    primera = jornades[0]
    assert primera.nom == "Jornada 01"
    assert primera.jornada_id == 2593
    assert primera.data == date(2025, 9, 27)
    assert (primera.lliga_id, primera.divisio_id, primera.grup_id) == (36, 148, 316)


def test_lliga_encontres_parteix_els_equips() -> None:
    encontres = parse_lliga_encontres(fixture("lligues_encontres_36_148_316_2593"))
    assert len(encontres) == 4
    primer = encontres[0]
    assert primer.encontre_id == 10939
    assert primer.equip_local == 'C.B. SANTS "A"'
    assert primer.equip_visitant == 'SB FOMENT MOLINS "A"'
    assert (primer.p_parcials_local, primer.p_parcials_visitant) == (5, 3)
    assert (primer.p_match_local, primer.p_match_visitant) == (3, 0)


def test_lliga_classificacio() -> None:
    files = parse_lliga_classificacio(fixture("lligues_classificacio_36_148_316"))
    assert len(files) == 8
    primer = files[0]
    assert (primer.posicio, primer.equip) == (1, 'C.B. MATARÓ "A"')
    assert (primer.pm, primer.pp, primer.j) == (36, 89, 14)
    assert [f.posicio for f in files] == list(range(1, 9))


def test_lliga_inscripcions_dona_el_club_de_cada_equip() -> None:
    equips = parse_lliga_inscripcions(fixture("lligues_inscripcions_39"))
    assert len(equips) == 29
    granollers = equips[0]
    assert granollers.club == "B.C.GRANOLLERS"
    assert granollers.equip == "B.C. GRANOLLERS"


def test_lliga_partides_llegeix_la_taula_de_partides() -> None:
    """El detall d'encontre de lliga retorna HTTP 500 des del canvi de web.

    Com que la taula de partides és la mateixa a tot el portal, el parser es
    prova contra la d'un grup d'individuals, que sí que funciona. El dia que la
    federació arregli el 500 caldrà confirmar-ho amb una pàgina de debò.
    """
    partides = parse_lliga_partides(fixture("individuals_partides_grup_211_447_799_5100"))
    # Sis files: cinc partides i el buit que deixa un grup incomplet. A la lliga
    # no hi ha buits —els dos equips presenten jugadors—, o sigui que aquest
    # parser no els filtra; el d'individuals sí.
    assert len(partides) == 6
    primera = partides[1]
    assert primera.local_nom == "MAS CANADELL, JOSEP Mª"
    assert primera.local_caramboles == 30
    assert primera.local_serie_major == 6
    assert primera.entrades == 22
    assert primera.arbitre == "MIGUEL"


# ---------------- individuals ----------------


def test_individuals_llistat_de_torneigs() -> None:
    torneigs = parse_individuals_torneigs_list(fixture("individuals_llistat"))
    assert {t.torneig_id_extern for t in torneigs} == {216, 217}
    assert torneigs[0].nom == "OPEN LLIURE PUNT D'ATAC"


def test_individuals_divisions() -> None:
    divisions = parse_individuals_divisions(fixture("individuals_divisions_211"))
    assert len(divisions) == 1
    assert (divisions[0].torneig_id, divisions[0].divisio_id_extern) == (211, 447)
    assert divisions[0].nom == "ÚNICA"
    # La classificació final va desaparèixer: ja no hi ha cap enllaç que hi porti.
    assert divisions[0].classif_href is None


def test_individuals_fases_separa_grups_i_eliminatories() -> None:
    fases = parse_individuals_fases(fixture("individuals_fases_211_447"))
    grups = [f for f in fases if f.tipus == "grups"]
    ko = [f for f in fases if f.tipus == "ko"]
    assert [f.nom for f in grups] == ["PRE-PRE-PREVIA", "PRE-PREVIA", "PREVIA"]
    assert [f.nom for f in ko] == ["SETZENS", "VUITENS", "QUARTS", "SEMIFINALS", "FINAL"]
    assert all(f.torneig_id == 211 for f in fases)


def test_individuals_membres_de_grup() -> None:
    membres = parse_individuals_grups_membership(fixture("individuals_grups_211_447_799"))
    assert len(membres) == 3
    assert membres[0].jugador_nom == "CALLS SARROCA, JOSEP"
    assert all(m.grup_nom == "Grup A" for m in membres)


def test_individuals_partides_de_grup_descarta_els_buits() -> None:
    """Una fila amb el mateix jugador als dos costats i tot a zero no és partida."""
    partides = parse_individuals_partides(fixture("individuals_partides_grup_211_447_799_5100"))
    assert len(partides) == 3  # de sis files, una és un buit i dues no s'han jugat
    assert all(p.local_nom != p.visitant_nom for p in partides)


def test_individuals_partides_deliminatoria() -> None:
    partides = parse_individuals_partides(
        fixture("individuals_partides_eliminatories_211_447_1185")
    )
    assert len(partides) == 1
    final = partides[0]
    assert final.local_nom == "HERNÁNDEZ PARRA, ANTONI"
    assert final.visitant_nom == "GARRIGA COMAS, JORDI"
    assert (final.visitant_serie_major, final.visitant_caramboles) == (9, 40)
    assert final.entrades == 25
    assert final.estat == "Finalitzada"


# ---------------- clubs ----------------


def test_clubs_amb_dades_de_contacte() -> None:
    """El llistat va passar al WordPress i hi va guanyar telèfon, correu i adreça."""
    clubs = parse_clubs_listing(fixture("wp_clubs"))
    assert len(clubs) == 38
    granollers = clubs[0]
    assert granollers.nom == "B.C.GRANOLLERS"
    assert granollers.telefon == "636022079"
    assert granollers.email == "billargranollers@hotmail.com"
    assert "Granollers" in granollers.direccio


def test_clubs_sense_taula_es_queixa() -> None:
    with pytest.raises(ValueError):
        parse_clubs_listing("<html><body>res</body></html>")
