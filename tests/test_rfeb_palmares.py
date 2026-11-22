"""El podi de cada campionat carregat, contrastat amb el palmarès de medalles."""

from __future__ import annotations

import pytest

from fcbillar.db.migrations import ensure_schema
from fcbillar.rfeb_palmares import compara, mateix_jugador


@pytest.fixture
def conn(tmp_path):
    c = ensure_schema(tmp_path / "rfeb.db")
    # El palmarès el carrega una altra eina; aquí només cal la taula.
    c.execute(
        "CREATE TABLE IF NOT EXISTS palmares_medalles (font TEXT, competicio TEXT, categoria TEXT, "
        "edicio TEXT, any_edicio INTEGER, lloc TEXT, posicio INTEGER, jugador TEXT, pais TEXT, "
        "mitjana REAL)"
    )
    yield c
    c.close()


def _prova(conn, id_, data_inici=None, temporada="2016-2017", categoria="sub17"):
    conn.execute(
        "INSERT INTO rfeb_proves (id, temporada, modalitat, categoria, tipus, titol, data_inici, "
        "font) VALUES (?, ?, '3b', ?, 'ce', 't', ?, 'f')",
        (id_, temporada, categoria, data_inici),
    )


def _fila(conn, id_, posicio, jugador, empat=None):
    conn.execute(
        "INSERT INTO rfeb_classificacions (prova_id, posicio, jugador, posicio_empat) "
        "VALUES (?, ?, ?, ?)",
        (id_, posicio, jugador, empat),
    )


def _medalla(conn, any_, edicio, posicio, jugador):
    conn.execute(
        "INSERT INTO palmares_medalles (font, competicio, categoria, edicio, any_edicio, posicio, "
        "jugador) VALUES ('rfeb', 'Tres bandes', 'sub-17', ?, ?, ?, ?)",
        (edicio, any_, posicio, jugador),
    )


@pytest.mark.parametrize(
    "a, b, esperat",
    [
        ("Daniel Sánchez Gálvez", "DANIEL SÁNCHEZ", True),
        ("José A. Delgado", "J.ALBERTO DELGADO", True),
        ("Abel Garrucho", "ABEL GARRRUCHO", True),
        ("Josep Mª Mas", "José M. Mas Canadell", True),
        ("Daniel Sánchez Gálvez", "Daniel Peña", False),
        ("Rubén Legazpi", "Alfonso Legazpi", False),
    ],
)
def test_mateix_jugador_amb_noms_escurçats_o_mal_escrits(a, b, esperat):
    assert mateix_jugador(a, b) is esperat


def test_el_podi_coincideix_amb_dos_bronzes_dels_semifinalistes(conn):
    _prova(conn, "noticias2016/res_ce_3b_s17", "2017-01-12")
    for pos, nom in [
        (1, "IVÁN MAYOR"),
        (2, "JONÁS SOUTO"),
        (3, "SERGIO MARTÍNEZ"),
        (4, "D. GARCÉS"),
    ]:
        _fila(conn, "noticias2016/res_ce_3b_s17", pos, nom)
    for pos, nom in [
        (1, "Iván Mayor"),
        (2, "Jonás Souto"),
        (3, "Daniel Garcés"),
        (3, "Sergio Martínez"),
    ]:
        _medalla(conn, 2017, "XXVI", pos, nom)
    [c] = compara(conn)
    assert (c.estat, c.any_edicio) == ("coincideix", 2017)


def test_un_altre_segon_es_una_diferencia(conn):
    _prova(conn, "p", "2017-01-12")
    for pos, nom in [(1, "IVÁN MAYOR"), (2, "LUIS MIRA"), (3, "SERGIO MARTÍNEZ")]:
        _fila(conn, "p", pos, nom)
    for pos, nom in [(1, "Iván Mayor"), (2, "Jonás Souto"), (3, "Sergio Martínez")]:
        _medalla(conn, 2017, "XXVI", pos, nom)
    [c] = compara(conn)
    assert c.estat == "difereix"
    assert "Jonás Souto" in c.palmares


def test_sense_data_es_miren_els_dos_anys_de_la_temporada_i_cada_edicio(conn):
    _prova(conn, "p")
    for pos, nom in [(1, "IVÁN MAYOR"), (2, "JONÁS SOUTO"), (3, "SERGIO MARTÍNEZ")]:
        _fila(conn, "p", pos, nom)
    # Dues edicions el mateix any: la de la prova és la segona.
    for pos, nom in [(1, "Ana"), (2, "Bea"), (3, "Cris")]:
        _medalla(conn, 2017, "XXV", pos, nom)
    for pos, nom in [(1, "Iván Mayor"), (2, "Jonás Souto"), (3, "Sergio Martínez")]:
        _medalla(conn, 2017, "XXVI", pos, nom)
    [c] = compara(conn)
    assert c.estat == "coincideix"


def test_sense_palmares_ho_diu(conn):
    _prova(conn, "p", "2017-01-12")
    _fila(conn, "p", 1, "IVÁN MAYOR")
    [c] = compara(conn)
    assert c.estat == "sense palmarès"
