"""Les caramboles i entrades de cada encontre, per a la classificació de lliga."""

import sqlite3

from fcbillar.cloud_sync import _caramboles_per_encontre


def _bd() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE players (id INTEGER PRIMARY KEY, nom TEXT);
        CREATE TABLE encontres_lliga (
            id INTEGER PRIMARY KEY, lliga_id INTEGER, temporada_id INTEGER,
            equip_local_id INTEGER, equip_visitant_id INTEGER);
        CREATE TABLE games (
            encontre_lliga_id INTEGER, player1_id INTEGER, player2_id INTEGER,
            caramboles1 INTEGER, caramboles2 INTEGER, entrades INTEGER, equip1_id INTEGER);
        CREATE TABLE lliga_pending_partides (
            encontre_lliga_id INTEGER, player1_nom TEXT, caramboles1 INTEGER,
            player2_nom TEXT, caramboles2 INTEGER, entrades INTEGER);
        INSERT INTO players VALUES (1, 'GÓMEZ AMETLLER, ALBERT'), (2, 'SÁNCHEZ NARVÁEZ, JACINTO'),
                                   (3, 'RODRÍGUEZ MAIA, MARIO FELIPE'), (4, 'HERNÁNDEZ, FRANCESC');
        -- Local: equip 10. Visitant: equip 20.
        INSERT INTO encontres_lliga VALUES (100, 38, 1, 10, 20);
        """
    )
    return conn


def test_el_jugador_1_es_el_local_si_no_es_diu_el_contrari():
    conn = _bd()
    conn.execute("INSERT INTO games VALUES (100, 1, 2, 28, 23, 50, 10)")
    conn.execute("INSERT INTO games VALUES (100, 3, 4, 35, 28, 40, NULL)")
    assert _caramboles_per_encontre(conn, 38, 1)[100] == [(28, 23, 50), (35, 28, 40)]


def test_si_el_jugador_1_es_del_visitant_la_partida_es_gira():
    conn = _bd()
    conn.execute("INSERT INTO games VALUES (100, 2, 1, 23, 28, 50, 20)")
    assert _caramboles_per_encontre(conn, 38, 1)[100] == [(28, 23, 50)]


def test_la_partida_de_l_acta_no_es_compta_dos_cops():
    conn = _bd()
    conn.execute("INSERT INTO games VALUES (100, 1, 2, 28, 23, 50, 10)")
    # La mateixa partida a l'acta, amb els noms escrits una mica diferent.
    conn.execute(
        "INSERT INTO lliga_pending_partides VALUES "
        "(100, 'Gomez Ametller, Albert', 28, 'SANCHEZ NARVAEZ, JACINTO', 23, 50)"
    )
    # I una que el rànquing encara no ha publicat.
    conn.execute(
        "INSERT INTO lliga_pending_partides VALUES "
        "(100, 'RODRÍGUEZ MAIA, MARIO FELIPE', 35, 'HERNÁNDEZ, FRANCESC', 28, 40)"
    )
    assert _caramboles_per_encontre(conn, 38, 1)[100] == [(28, 23, 50), (35, 28, 40)]
