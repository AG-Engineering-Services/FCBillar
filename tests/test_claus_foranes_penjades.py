"""Refer una taula no pot deixar les altres apuntant al no-res.

SQLite no sap treure un NOT NULL ni alterar un CHECK: cal refer la taula. Si es
fa reanomenant primer l'original, SQLite reescriu les claus foranes que hi
apunten des d'ALTRES taules perquè segueixin el nom nou —i tot seguit aquell nom
temporal s'esborra. Aquelles taules queden apuntant a una taula que no existeix.

No es veu fins que algú hi escriu, i llavors peta amb «no such table» lluny
d'on és el problema. Va passar dues vegades: la migració v13 (maig) hi va deixar
`ranking_entries` i `ranking_game_links`, i la v15 `games` i
`lliga_pending_partides`. Mesos sense que ningú se n'adonés.
"""

from __future__ import annotations

import sqlite3

import pytest

from fcbillar.db.migrations import claus_penjades, ensure_schema

#: Una base petita amb el mal ja fet: `filla` apunta a `mare_v1`, que no hi és.
TRENCADA = """
CREATE TABLE mare (id INTEGER PRIMARY KEY, nom TEXT);
CREATE TABLE filla (
    id INTEGER PRIMARY KEY,
    mare_id INTEGER NOT NULL REFERENCES "mare_v1"(id) ON DELETE CASCADE
);
"""


def _base_trencada(path) -> None:
    conn = sqlite3.connect(path, isolation_level=None)
    conn.executescript(TRENCADA)
    conn.execute("INSERT INTO mare (id, nom) VALUES (1, 'x')")
    conn.execute("INSERT INTO filla (id, mare_id) VALUES (1, 1)")
    conn.close()


def test_les_troba(tmp_path) -> None:
    db = tmp_path / "t.db"
    _base_trencada(db)
    conn = sqlite3.connect(db)
    assert claus_penjades(conn) == {"filla": {"mare_v1"}}


def test_una_base_sana_no_en_te_cap(tmp_path) -> None:
    conn = ensure_schema(tmp_path / "sana.db")
    assert claus_penjades(conn) == {}


def test_amb_la_clau_penjada_no_s_hi_pot_inserir(tmp_path) -> None:
    """El dany real, i el motiu de no deixar-ho passar."""
    db = tmp_path / "t.db"
    _base_trencada(db)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        conn.execute("INSERT INTO filla (id, mare_id) VALUES (2, 1)")


def test_refer_una_taula_de_l_esquema_no_en_deixa_cap(tmp_path) -> None:
    """El cas de debò: una base vella que passa per totes les migracions.

    `encontres_lliga` i `rankings` es refan pel camí, i `games`,
    `lliga_pending_partides`, `ranking_entries` i `ranking_game_links` hi
    apunten. Si l'ordre de refer-les fos el dolent, aquí es veuria.
    """
    db = tmp_path / "vella.db"
    conn = ensure_schema(db)
    conn.execute("PRAGMA user_version = 1")  # com si vingués de la primera versió
    conn.close()

    conn = ensure_schema(db)
    assert claus_penjades(conn) == {}
    # I s'hi pot escriure, que és el que importa.
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("INSERT INTO clubs (fcb_id, nom) VALUES ('C.B.X', 'C.B.X')")
    conn.execute("INSERT INTO equips (club_id, lletra) VALUES (1, 'A')")
    conn.execute(
        "INSERT INTO encontres_lliga (lliga_id, divisio_id, grup_id, jornada_id, "
        "encontre_id_extern, equip_local_id, equip_visitant_id) VALUES (1,1,1,1,1,1,1)"
    )
    conn.execute(
        "INSERT INTO lliga_pending_partides (encontre_lliga_id, modalitat_codi, "
        "competicio, player1_nom, caramboles1, player2_nom, caramboles2, entrades) "
        "VALUES (1, 1, 'X', 'A', 1, 'B', 1, 10)"
    )
