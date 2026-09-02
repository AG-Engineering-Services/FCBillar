"""Un encontre pot no saber quins equips el van jugar, i ho ha de poder dir.

`encontres_lliga.equip_local_id` i `equip_visitant_id` eren NOT NULL, o sigui
que la ingesta que no resolia l'equip hi posava un 0. I 0 no és cap equip: no
existeix a `equips`, trenca la clau forana i fa que l'encontre sembli un partit
d'un equip contra ell mateix. N'hi havia 2.035 així, del backfill històric de
2015-2019, i eren prou convincents per enganyar a qui els mirés.

No es podien esborrar: hi pengen 5.631 partides que sí que tenen dades. El que
es podia fer és que el camp digués la veritat.
"""

from __future__ import annotations

import sqlite3

from fcbillar.db.migrations import SCHEMA_VERSION, ensure_schema

#: L'esquema tal com era abans de la v15, amb els dos camps obligatoris.
ESQUEMA_V14 = """
CREATE TABLE clubs (id INTEGER PRIMARY KEY AUTOINCREMENT, fcb_id TEXT NOT NULL UNIQUE,
                    nom TEXT NOT NULL);
CREATE TABLE temporades (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL UNIQUE);
CREATE TABLE equips (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
                     lletra TEXT NOT NULL, UNIQUE(club_id, lletra));
CREATE TABLE encontres_lliga (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lliga_id INTEGER NOT NULL, divisio_id INTEGER NOT NULL, grup_id INTEGER NOT NULL,
    jornada_id INTEGER NOT NULL, encontre_id_extern INTEGER NOT NULL,
    data TEXT, temporada_id INTEGER REFERENCES temporades(id),
    equip_local_id INTEGER NOT NULL REFERENCES equips(id),
    equip_visitant_id INTEGER NOT NULL REFERENCES equips(id),
    p_parcials_local INTEGER, p_match_local INTEGER,
    p_parcials_visitant INTEGER, p_match_visitant INTEGER,
    UNIQUE(lliga_id, divisio_id, grup_id, jornada_id, encontre_id_extern)
);
"""


def _base_v14(path) -> None:
    conn = sqlite3.connect(path, isolation_level=None)
    conn.executescript(ESQUEMA_V14)
    conn.execute("INSERT INTO clubs (id, fcb_id, nom) VALUES (1, 'C.B.X', 'C.B.X')")
    conn.execute("INSERT INTO equips (id, club_id, lletra) VALUES (7, 1, 'A')")
    # Un encontre de debò i dos dels que no sabien l'equip.
    conn.executemany(
        "INSERT INTO encontres_lliga (lliga_id, divisio_id, grup_id, jornada_id, "
        "encontre_id_extern, equip_local_id, equip_visitant_id) VALUES (?,?,?,?,?,?,?)",
        [(5, 25, 49, 408, 1, 7, 7), (5, 25, 49, 408, 2, 0, 0), (5, 25, 49, 409, 3, 7, 0)],
    )
    conn.execute("PRAGMA user_version = 14")
    conn.commit()
    conn.close()


def test_els_zeros_passen_a_desconegut(tmp_path) -> None:
    db = tmp_path / "v14.db"
    _base_v14(db)
    conn = ensure_schema(db)

    zeros = conn.execute(
        "SELECT COUNT(*) FROM encontres_lliga WHERE equip_local_id = 0 OR equip_visitant_id = 0"
    ).fetchone()[0]
    assert zeros == 0
    desconeguts = conn.execute(
        "SELECT COUNT(*) FROM encontres_lliga "
        "WHERE equip_local_id IS NULL OR equip_visitant_id IS NULL"
    ).fetchone()[0]
    assert desconeguts == 2


def test_no_es_perd_cap_encontre_ni_el_seu_id(tmp_path) -> None:
    """Refer la taula no pot moure els id: les partides hi apunten."""
    db = tmp_path / "v14.db"
    _base_v14(db)
    conn = ensure_schema(db)

    files = conn.execute(
        "SELECT id, encontre_id_extern FROM encontres_lliga ORDER BY id"
    ).fetchall()
    assert [(r[0], r[1]) for r in files] == [(1, 1), (2, 2), (3, 3)]


def test_l_encontre_que_si_que_tenia_equips_es_queda_igual(tmp_path) -> None:
    db = tmp_path / "v14.db"
    _base_v14(db)
    conn = ensure_schema(db)

    r = conn.execute(
        "SELECT equip_local_id, equip_visitant_id FROM encontres_lliga WHERE encontre_id_extern = 1"
    ).fetchone()
    assert (r[0], r[1]) == (7, 7)


def test_els_partits_contra_un_mateix_deixen_de_ser_mentida(tmp_path) -> None:
    """Era el dany real: 2.035 encontres semblaven un equip contra ell mateix."""
    db = tmp_path / "v14.db"
    _base_v14(db)
    conn = ensure_schema(db)

    # NULL = NULL no és cert a SQL, o sigui que els desconeguts ja no hi compten.
    iguals = conn.execute(
        "SELECT COUNT(*) FROM encontres_lliga WHERE equip_local_id = equip_visitant_id"
    ).fetchone()[0]
    assert iguals == 1, "només el que de debò porta el mateix equip a totes dues bandes"


def test_una_base_nova_ja_els_admet_opcionals(tmp_path) -> None:
    conn = ensure_schema(tmp_path / "nova.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    obligatoris = {
        r[1]
        for r in conn.execute("PRAGMA table_info(encontres_lliga)")
        if r[3] and r[1] in ("equip_local_id", "equip_visitant_id")
    }
    assert obligatoris == set()
