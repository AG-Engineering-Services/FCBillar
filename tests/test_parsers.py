"""Tests del parser contra fixtures HTML reals capturades de fcbillar.cat."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from fcbillar.scraper.parsers import (
    HistorialEntry,
    parse_home_current_rankings,
    parse_partides_jugador,
    parse_ranking,
    parse_ranking_historial,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def ranking_lliure_121_html() -> str:
    return (FIXTURES / "ranking_lliure_121.html").read_text(encoding="utf-8")


@pytest.fixture
def ranking_tres_bandes_121_html() -> str:
    return (FIXTURES / "ranking_tres_bandes_121.html").read_text(encoding="utf-8")


@pytest.fixture
def historial_html() -> str:
    return (FIXTURES / "ranking_historial.html").read_text(encoding="utf-8")


# ---------------- parse_ranking ----------------


def test_parse_ranking_lliure_121_basic_shape(ranking_lliure_121_html: str) -> None:
    result = parse_ranking(ranking_lliure_121_html, num_seq=121, modalitat_codi_fcb=2)
    assert result.num_seq == 121
    assert result.modalitat_codi_fcb == 2
    # A la fixture hi ha 166 jugadors (vist a inspecció manual).
    assert len(result.entries) == 166
    # Tots els jugadors són únics en aquesta llista.
    assert len(result.players) == 166


def test_parse_ranking_first_row_is_vilalta(ranking_lliure_121_html: str) -> None:
    result = parse_ranking(ranking_lliure_121_html, num_seq=121, modalitat_codi_fcb=2)
    first = result.entries[0]
    assert first.posicio == 1
    assert first.player_fcb_id == "566"
    assert first.mitjana_general == pytest.approx(21.91071)
    assert first.partides is None  # no es publica al rànquing
    assert first.extras["mitjana_contraris"] == pytest.approx(11.38221)
    assert first.extras["caramboles"] == 2454
    assert first.extras["entrades"] == 112
    assert first.extras["punts"] == 16
    assert first.extras["punts_totals"] == 20
    assert first.extras["definitiva"] is True

    first_player = next(p for p in result.players if p.fcb_id == "566")
    assert first_player.nom == "VILALTA PARÉ, VALENTÍ"


def test_parse_ranking_non_definitiva_row(ranking_lliure_121_html: str) -> None:
    """Posició 64 ja és la primera amb Def=No."""
    result = parse_ranking(ranking_lliure_121_html, num_seq=121, modalitat_codi_fcb=2)
    row_64 = result.entries[63]
    assert row_64.posicio == 64
    assert row_64.extras["definitiva"] is False


def test_parse_ranking_player_ids_all_extracted(ranking_lliure_121_html: str) -> None:
    """Tots els entries han de tenir un player_fcb_id (no None)."""
    result = parse_ranking(ranking_lliure_121_html, num_seq=121, modalitat_codi_fcb=2)
    for entry in result.entries:
        assert entry.player_fcb_id
        assert entry.player_fcb_id.isdigit()


def test_parse_ranking_tres_bandes_121_has_more_players(
    ranking_tres_bandes_121_html: str,
) -> None:
    """Tres bandes (155KB) té molts més jugadors que lliure (53KB)."""
    result = parse_ranking(ranking_tres_bandes_121_html, num_seq=121, modalitat_codi_fcb=1)
    assert len(result.entries) > 200


# ---------------- parse_ranking_historial ----------------


def test_parse_historial_count(historial_html: str) -> None:
    entries = parse_ranking_historial(historial_html)
    # A la fixture vam veure 15 entrades (del 98 al 112).
    assert len(entries) == 15


def test_parse_historial_first_entry_is_112(historial_html: str) -> None:
    entries = parse_ranking_historial(historial_html)
    e = entries[0]
    assert isinstance(e, HistorialEntry)
    assert e.data == date(2025, 7, 1)
    # Totes 5 modalitats han d'aparèixer.
    assert set(e.rankings.keys()) == {1, 2, 3, 4, 6}
    # Format: aquests rànquings antics usen "data".
    fmt, num_seq = e.rankings[1]
    assert fmt == "data"
    assert num_seq == 112


def test_parse_historial_last_entry_is_98(historial_html: str) -> None:
    entries = parse_ranking_historial(historial_html)
    e = entries[-1]
    assert e.data == date(2024, 4, 2)
    fmt, num_seq = e.rankings[1]
    assert num_seq == 98


# ---------------- parse_partides_jugador ----------------


@pytest.fixture
def partides_lliure_p566_html() -> str:
    return (FIXTURES / "partideshome_lliure_121_p566.html").read_text(encoding="utf-8")


@pytest.fixture
def partides_tresbandes_p769_html() -> str:
    return (FIXTURES / "partideshome_tresbandes_121_p769.html").read_text(encoding="utf-8")


def test_parse_partides_lliure_p566_categories(partides_lliure_p566_html: str) -> None:
    """Vilalta (lliure 121) té una partida de LLIGA i 9 d'INDIVIDUAL."""
    result = parse_partides_jugador(partides_lliure_p566_html)
    by_comp: dict[str, int] = {}
    for r in result.rows:
        by_comp[r.competicio] = by_comp.get(r.competicio, 0) + 1
    assert by_comp.get("LLIGA") == 1
    assert by_comp.get("INDIVIDUAL") == 9


def test_parse_partides_lliga_first_row(partides_lliure_p566_html: str) -> None:
    result = parse_partides_jugador(partides_lliure_p566_html)
    lliga = [r for r in result.rows if r.competicio == "LLIGA"]
    assert len(lliga) == 1
    row = lliga[0]
    assert row.data_partida == date(2026, 2, 1)
    assert row.local_nom == "PALLISA GONZÁLEZ, JOSEP"
    assert row.local_punts == 0
    assert row.local_caramboles == 53
    assert row.visitant_nom == "VILALTA PARÉ, VALENTÍ"
    assert row.visitant_punts == 2
    assert row.visitant_caramboles == 200
    assert row.entrades == 9


def test_parse_partides_noms_unics(partides_lliure_p566_html: str) -> None:
    """Tots els noms han de quedar al set de noms únics."""
    result = parse_partides_jugador(partides_lliure_p566_html)
    assert "VILALTA PARÉ, VALENTÍ" in result.noms
    assert "PALLISA GONZÁLEZ, JOSEP" in result.noms


def test_parse_partides_tres_bandes_p769_lliga(
    partides_tresbandes_p769_html: str,
) -> None:
    """Jiménez Galera té només partides de LLIGA en aquest rànquing."""
    result = parse_partides_jugador(partides_tresbandes_p769_html)
    assert all(r.competicio == "LLIGA" for r in result.rows)
    assert len(result.rows) == 15


# ---------------- parse_home_current_rankings ----------------


@pytest.fixture
def home_authed_html() -> str:
    return (FIXTURES / "jugador_home_authed.html").read_text(encoding="utf-8")


def test_parse_home_current_rankings(home_authed_html: str) -> None:
    result = parse_home_current_rankings(home_authed_html)
    assert result.data_ranking == date(2026, 5, 4)
    # Han de sortir les 5 modalitats actives.
    modalitats = {r.modalitat_codi_fcb for r in result.rankings}
    assert modalitats == {1, 2, 3, 4, 6}
    # Totes apunten al num_seq 121 amb format datahome.
    assert all(r.num_seq == 121 for r in result.rankings)
    assert all(r.format_url == "datahome" for r in result.rankings)
