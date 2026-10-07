"""El calendari de la Lliga Nacional: les jornades que encara no s'han jugat."""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from fcbillar import lliga_nacional as LN
from fcbillar.db.migrations import ensure_schema

NACIONAL = Path(__file__).parent / "fixtures" / "nacional"


@pytest.fixture(scope="module")
def calendari() -> list[LN.EncontreDeCalendari]:
    return LN.llegeix_calendari(NACIONAL / "calendari_1_2627.pdf")


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    return ensure_schema(tmp_path / "t.db")


def _encontres(conn, on: str = "1 = 1", *args) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM nacional_encontres WHERE {on}", args).fetchone()[0]


def test_catorze_jornades_de_quatre_encontres_per_grup(calendari):
    per_bloc = Counter((e.jornada, e.grup) for e in calendari)
    assert sorted({j for j, _ in per_bloc}) == list(range(1, 15))
    assert set(per_bloc.values()) == {4}
    assert {g for _, g in per_bloc} == {"A", "B"}


def test_cada_equip_juga_set_cops_a_casa_i_set_a_fora(calendari):
    assert set(Counter(e.local for e in calendari).values()) == {7}
    assert set(Counter(e.visitant for e in calendari).values()) == {7}


def test_dos_noms_llargs_enganxats_no_es_barregen(calendari):
    # A la jornada 3 el PDF escriu «…Chef Amadeo Gandia 'B'Inviktcues Granollers 'B'…».
    j3 = [(e.local, e.visitant) for e in calendari if e.jornada == 3 and e.grup == "B"]
    assert ("C.B. Sant Adriá", "Chef Amadeo Gandia 'B'") in j3
    assert ("Inviktcues Granollers 'B'", "C.B. Paiporta") in j3


def test_cada_jornada_porta_el_seu_dia(calendari):
    dies = {e.jornada: e.data for e in calendari}
    assert dies[1] == date(2026, 9, 12)
    assert dies[8] == date(2027, 2, 13)
    assert dies[14] == date(2027, 5, 22)


def test_una_jornada_no_es_un_calendari():
    with pytest.raises(LN.FormatDesconegut):
        LN.llegeix_calendari(NACIONAL / "liga_nal_1_j1_2627.pdf")


def test_el_calendari_no_trepitja_una_jornada_ja_jugada(conn, calendari):
    jornada = LN.llegeix_jornada(NACIONAL / "liga_nal_1_j1_2627.pdf")
    temporada = LN.desa_jornada(conn, jornada, "1")
    jugats = _encontres(conn, "jornada = ?", jornada.numero)

    desats = LN.desa_calendari(conn, calendari, "1", temporada)

    assert desats == len(calendari) - 8
    assert _encontres(conn, "jornada = ? AND punts_local IS NULL", jornada.numero) == 0
    assert _encontres(conn, "jornada = ?", jornada.numero) == jugats


def test_el_resultat_reemplaca_el_calendari_i_tornar_a_desar_no_duplica(conn, calendari):
    LN.desa_calendari(conn, calendari, "1", "2026-2027")
    LN.desa_calendari(conn, calendari, "1", "2026-2027")
    assert _encontres(conn) == len(calendari)

    jornada = LN.llegeix_jornada(NACIONAL / "liga_nal_1_j1_2627.pdf")
    LN.desa_jornada(conn, jornada, "1")
    assert _encontres(conn, "jornada = ? AND punts_local IS NULL", jornada.numero) == 0
