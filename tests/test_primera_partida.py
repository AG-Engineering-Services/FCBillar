"""Quan s'ha disputat la primera partida de la temporada.

El senyal no és una data del calendari: la federació endarrereix jornades i els
seus PDF ja han portat dates equivocades. Tampoc no és que existeixin encontres,
perquè els dona d'alta abans que es juguin —de la 26/27 ja en tenim sense jugar.
El senyal és que hi hagi un resultat.
"""

from __future__ import annotations

import sqlite3

import pytest

import scripts.primera_partida as pp
from fcbillar.db.migrations import ensure_schema

TEMPORADA = "2026/2027"


@pytest.fixture
def conn(tmp_path):
    c = ensure_schema(tmp_path / "t.db")
    c.execute("INSERT INTO temporades (nom) VALUES ('2026-2027')")
    # Dos jugadors: `games` en vol dos de reals i aquí no interessa qui són.
    c.execute("INSERT INTO clubs (fcb_id, nom) VALUES ('C.B.BANYOLES', 'C.B.BANYOLES')")
    for i, nom in ((1, "UN, JUGADOR"), (2, "ALTRE, U")):
        c.execute(
            "INSERT INTO players (id, fcb_id, nom, club_id) VALUES (?, ?, ?, 1)", (i, nom, nom)
        )
    c.execute(
        "INSERT INTO lliga_calendari "
        "(temporada, divisio, grup, jornada, data, local, visitant) "
        "VALUES (?, '1a', 'B', 1, '2026-09-26', 'A', 'B')",
        (TEMPORADA,),
    )
    return c


def _temporada_id(conn) -> int:
    return conn.execute("SELECT id FROM temporades WHERE nom = '2026-2027'").fetchone()[0]


def _encontre(conn) -> int:
    """Un encontre nou. El número extern ha de ser diferent a cada crida."""
    seguent = conn.execute("SELECT COUNT(*) + 1 FROM encontres_lliga").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO encontres_lliga "
        "(lliga_id, divisio_id, grup_id, jornada_id, encontre_id_extern, temporada_id) "
        "VALUES (36, 1, 1, 1, ?, ?)",
        (seguent, _temporada_id(conn)),
    )
    return cur.lastrowid


def _partida(conn, encontre_id: int, entrades: int | None) -> None:
    conn.execute(
        "INSERT INTO games "
        "(data_partida, modalitat_id, player1_id, player2_id, entrades, "
        " encontre_lliga_id, temporada_id) "
        "VALUES ('2026-09-26', (SELECT id FROM modalitats WHERE nom = 'Tres bandes'), "
        "1, 2, ?, ?, ?)",
        (entrades, encontre_id, _temporada_id(conn)),
    )


def test_la_temporada_surt_del_calendari_carregat(conn) -> None:
    assert pp.temporada_en_curs(conn) == TEMPORADA


def test_sense_calendari_no_hi_ha_temporada(tmp_path) -> None:
    buida = ensure_schema(tmp_path / "buida.db")
    assert pp.temporada_en_curs(buida) is None


def test_tenir_encontres_no_es_haver_jugat(conn) -> None:
    """La federació els dona d'alta abans: de la 26/27 ja en teníem sense jugar."""
    _encontre(conn)
    assert pp.primera_de_lliga(conn, TEMPORADA) is None


def test_una_partida_sense_entrades_tampoc(conn) -> None:
    """Una fila creada i encara no disputada no diu que la lliga hagi començat."""
    _partida(conn, _encontre(conn), None)
    _partida(conn, _encontre(conn), 0)
    assert pp.primera_de_lliga(conn, TEMPORADA) is None


def test_amb_resultat_si(conn) -> None:
    _partida(conn, _encontre(conn), 42)
    resultat = pp.primera_de_lliga(conn, TEMPORADA)
    assert resultat is not None
    assert resultat[0] == "2026-09-26"


def test_l_individual_es_mira_a_part(conn) -> None:
    """Pot començar abans que la lliga: les prèvies són al setembre."""
    conn.execute(
        "INSERT INTO torneigs_individuals "
        "(id, torneig_id_extern, divisio_id_extern, nom, modalitat_id, temporada_id) "
        "VALUES (1, 1, 1, 'PRE-PRÈVIA 2a', "
        "(SELECT id FROM modalitats WHERE nom = 'Tres bandes'), ?)",
        (_temporada_id(conn),),
    )
    conn.execute(
        "INSERT INTO games "
        "(data_partida, modalitat_id, player1_id, player2_id, entrades, "
        " torneig_id, temporada_id) "
        "VALUES ('2026-09-19', (SELECT id FROM modalitats WHERE nom = 'Tres bandes'), "
        "1, 2, 50, 1, ?)",
        (_temporada_id(conn),),
    )
    assert pp.primera_de_lliga(conn, TEMPORADA) is None
    individual = pp.primera_individual(conn, TEMPORADA)
    assert individual is not None
    assert individual == ("2026-09-19", "PRE-PRÈVIA 2a")


def test_les_partides_d_altres_temporades_no_compten(conn) -> None:
    conn.execute("INSERT INTO temporades (nom) VALUES ('2025-2026')")
    anterior = conn.execute("SELECT id FROM temporades WHERE nom = '2025-2026'").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO encontres_lliga "
        "(lliga_id, divisio_id, grup_id, jornada_id, encontre_id_extern, temporada_id) "
        "VALUES (36, 1, 1, 1, 999, ?)",
        (anterior,),
    )
    conn.execute(
        "INSERT INTO games "
        "(data_partida, modalitat_id, player1_id, player2_id, entrades, "
        " encontre_lliga_id, temporada_id) "
        "VALUES ('2026-01-10', (SELECT id FROM modalitats WHERE nom = 'Tres bandes'), "
        "1, 2, 40, ?, ?)",
        (cur.lastrowid, anterior),
    )
    assert pp.primera_de_lliga(conn, TEMPORADA) is None


def test_no_peta_amb_una_base_buida(tmp_path, capsys) -> None:
    """El guió corre a cada reingesta; si peta, s'emporta el resum del job."""
    ensure_schema(tmp_path / "b.db")
    conn = sqlite3.connect(tmp_path / "b.db")
    assert pp.primera_de_lliga(conn, TEMPORADA) is None
    assert pp.primera_individual(conn, TEMPORADA) is None
