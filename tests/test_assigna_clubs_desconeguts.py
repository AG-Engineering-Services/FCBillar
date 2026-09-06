"""Donar club a qui no en té, a partir dels inscrits a la lliga.

`players.club_id` surt del cens de llicències, i qui s'acaba de federar encara
no hi és: es queda sense club. La llista d'inscrits, en canvi, sí que diu de
quin club juga —és ella qui l'inscriu—, i qualsevol pantalla que filtri per club
el deixa fora mentrestant.

Es va veure el 6 de setembre de 2026: en Jordi Soler i en Josep Carreras no
sortien al rànquing dels socis del club de NouProjecte tot i constar a la pàgina
de participants de la federació. N'hi havia 97 en aquella situació.
"""

from __future__ import annotations

import pytest

from fcbillar.db.migrations import ensure_schema
from fcbillar.inscrits_lliga import assigna_clubs_desconeguts

TEMPORADA = "2026/2027"


@pytest.fixture
def conn(tmp_path):
    c = ensure_schema(tmp_path / "t.db")
    for nom in ("C.B.BANYOLES", "C.B.LLINARS"):
        c.execute("INSERT INTO clubs (fcb_id, nom) VALUES (?, ?)", (nom, nom))
    c.commit()
    return c


def _jugador(conn, nom: str, club: str | None) -> int:
    cid = None
    if club:
        cid = conn.execute("SELECT id FROM clubs WHERE nom = ?", (club,)).fetchone()[0]
    cur = conn.execute(
        "INSERT INTO players (fcb_id, nom, club_id) VALUES (?, ?, ?)", (nom, nom, cid)
    )
    return cur.lastrowid


def _inscriu(conn, nom: str, club: str, fitxatge: int = 0, temporada: str = TEMPORADA) -> None:
    conn.execute(
        "INSERT INTO lliga_inscrits (temporada, lliga_id, lliga, club, club_id_extern, "
        "jugador, mitjana, fitxatge, posicio) VALUES (?, 38, 'Tres Bandes', ?, 16, ?, 0.3, ?, 1)",
        (temporada, club, nom, fitxatge),
    )
    conn.commit()


def _club_de(conn, nom: str) -> str | None:
    fila = conn.execute(
        "SELECT c.nom FROM players p LEFT JOIN clubs c ON c.id = p.club_id WHERE p.nom = ?",
        (nom,),
    ).fetchone()
    return fila[0] if fila else None


def test_qui_no_en_te_l_agafa_dels_inscrits(conn) -> None:
    _jugador(conn, "SOLER ARBUSSA, JORDI", None)
    _inscriu(conn, "SOLER ARBUSSA, JORDI", "C.B.BANYOLES")

    assert assigna_clubs_desconeguts(conn, TEMPORADA) == {"SOLER ARBUSSA, JORDI": "C.B.BANYOLES"}
    assert _club_de(conn, "SOLER ARBUSSA, JORDI") == "C.B.BANYOLES"


def test_qui_ja_en_te_no_es_toca(conn) -> None:
    """El cens no és pitjor font que la llista d'inscrits per a qui ja hi surt.

    Un jugador pot estar inscrit amb un altre club per un fitxatge, i sobreescriure
    el que ja hi consta seria decidir sobre una cosa que aquí no se sap.
    """
    _jugador(conn, "QUI, JA EN TE", "C.B.LLINARS")
    _inscriu(conn, "QUI, JA EN TE", "C.B.BANYOLES")

    assert assigna_clubs_desconeguts(conn, TEMPORADA) == {}
    assert _club_de(conn, "QUI, JA EN TE") == "C.B.LLINARS"


def test_un_fitxatge_va_al_club_que_se_l_endu(conn) -> None:
    """Surt a les dues llistes: la del club d'origen i la del que el fitxa."""
    _jugador(conn, "QUI, FITXA", None)
    _inscriu(conn, "QUI, FITXA", "C.B.LLINARS", fitxatge=0)
    _inscriu(conn, "QUI, FITXA", "C.B.BANYOLES", fitxatge=1)

    assigna_clubs_desconeguts(conn, TEMPORADA)
    assert _club_de(conn, "QUI, FITXA") == "C.B.BANYOLES"


def test_una_altra_temporada_no_compta(conn) -> None:
    _jugador(conn, "D ABANS, U", None)
    _inscriu(conn, "D ABANS, U", "C.B.BANYOLES", temporada="2025/2026")

    assert assigna_clubs_desconeguts(conn, TEMPORADA) == {}
    assert _club_de(conn, "D ABANS, U") is None


def test_un_club_que_no_es_al_cens_no_inventa_res(conn) -> None:
    _jugador(conn, "QUI, SIGUI", None)
    _inscriu(conn, "QUI, SIGUI", "C.B.INEXISTENT")

    assert assigna_clubs_desconeguts(conn, TEMPORADA) == {}
    assert _club_de(conn, "QUI, SIGUI") is None


def test_sense_inscrits_no_fa_res(conn) -> None:
    _jugador(conn, "TOT, SOL", None)
    assert assigna_clubs_desconeguts(conn, TEMPORADA) == {}
