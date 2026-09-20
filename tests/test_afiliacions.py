"""Amb quin club juga cadascú CADA competició.

Un jugador no té un club: en té un per competició. Passa de debò a la temporada
2026-27, i és el que cap columna sola de `players` pot dir:

- quatre jugadors van fitxats a la lliga de 4 Modalitats per un club i a la de
  tres bandes per un altre;
- i dos juguen el campionat individual per un club diferent del de la lliga.
"""

from __future__ import annotations

import sqlite3

import pytest

from fcbillar import afiliacions as A
from fcbillar.db.migrations import ensure_schema
from fcbillar.db.repository import Repository


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    c = ensure_schema(tmp_path / "t.db")
    for nom in ("C.B.BANYOLES", "B.C.GRANOLLERS", "C.B.MATARÓ", "C.B.SANT ADRIÀ"):
        c.execute("INSERT INTO clubs (fcb_id, nom) VALUES (?, ?)", (nom, nom))
    c.commit()
    return c


def _inscrit(conn, lliga_id, lliga, modalitat, club, jugador, fitxatge=0, posicio=1):
    conn.execute(
        "INSERT INTO lliga_inscrits (temporada, lliga_id, lliga, modalitat, club, "
        "club_id_extern, jugador, mitjana, fitxatge, posicio) "
        "VALUES ('2026/2027', ?, ?, ?, ?, 0, ?, 1.0, ?, ?)",
        (lliga_id, lliga, modalitat, club, jugador, fitxatge, posicio),
    )


def test_el_fitxatge_de_la_lliga_mana_sobre_el_club_propi(conn) -> None:
    """Qui ve fitxat surt a dues llistes, i juga per la que porta la marca.

    La federació el publica al seu club sense marca i al club que se l'endú amb
    `(Fitxatge)`, i totes dues files volen dir alguna cosa. Però «amb quin club
    juga la lliga» té una resposta sola: el club que el fitxa.
    """
    _inscrit(conn, 38, "Tres Bandes", "Tres bandes", "C.B.BANYOLES", "MAS, JOSEP")
    _inscrit(conn, 38, "Tres Bandes", "Tres bandes", "B.C.GRANOLLERS", "MAS, JOSEP", fitxatge=1)
    conn.commit()

    files, avisos = A.de_la_lliga(conn, "2026/2027")
    assert avisos == []
    assert len(files) == 1
    assert (files[0].club, files[0].fitxatge) == ("B.C.GRANOLLERS", True)


def test_dues_lligues_son_dues_afiliacions(conn) -> None:
    """El mateix jugador pot anar fitxat per clubs diferents a cada lliga.

    Són dues competicions, dues inscripcions i dos terminis. A la 2026-27 li
    passa a quatre jugadors.
    """
    _inscrit(conn, 38, "Tres Bandes", "Tres bandes", "C.B.MATARÓ", "CREGO, DIDIER", fitxatge=1)
    _inscrit(conn, 38, "Tres Bandes", "Tres bandes", "C.B.BANYOLES", "CREGO, DIDIER")
    _inscrit(
        conn, 39, "4 Modalitats", "4 Modalitats", "C.B.SANT ADRIÀ", "CREGO, DIDIER", fitxatge=1
    )
    _inscrit(conn, 39, "4 Modalitats", "4 Modalitats", "C.B.BANYOLES", "CREGO, DIDIER")
    conn.commit()

    files, avisos = A.de_la_lliga(conn, "2026/2027")
    assert avisos == []
    A.desa(conn, files)
    assert {(f.modalitat, f.club) for f in files} == {
        ("Tres bandes", "C.B.MATARÓ"),
        ("4 Modalitats", "C.B.SANT ADRIÀ"),
    }
    canvis = A.canvia_de_club(conn, "2026/2027")
    assert [j for j, _ in canvis] == ["CREGO, DIDIER"]


def test_dos_clubs_sense_marca_no_es_resol(conn) -> None:
    """Triar-ne un a l'atzar seria inventar-se un fitxatge.

    Passa amb dos jugadors de la lliga 38 de la 2026-27: dos clubs se'ls
    reclamen com a propis i cap fila no porta la marca. La font està malament i
    no hi ha res a deduir; va a la llista de coses per revisar.
    """
    _inscrit(conn, 38, "Tres Bandes", "Tres bandes", "C.B.MATARÓ", "FERNÁNDEZ, ALFREDO")
    _inscrit(conn, 38, "Tres Bandes", "Tres bandes", "C.B.BANYOLES", "FERNÁNDEZ, ALFREDO")
    conn.commit()

    files, avisos = A.de_la_lliga(conn, "2026/2027")
    assert files == []
    assert len(avisos) == 1 and "sense cap marca de fitxatge" in avisos[0]


def test_desa_no_esborra_amb_una_llista_buida(conn) -> None:
    """Una font que no s'ha sabut llegir no ha de buidar el que ja tenim."""
    _inscrit(conn, 38, "Tres Bandes", "Tres bandes", "C.B.BANYOLES", "MAS, JOSEP")
    conn.commit()
    files, _ = A.de_la_lliga(conn, "2026/2027")
    A.desa(conn, files)
    assert A.desa(conn, []) == 0
    assert conn.execute("SELECT COUNT(*) FROM afiliacions").fetchone()[0] == 1


def test_desa_una_competicio_no_toca_l_altra(conn) -> None:
    """La lliga i l'individual s'ingereixen per separat i per camins diferents."""
    conn.execute(
        "INSERT INTO afiliacions (temporada, competicio, modalitat, jugador, club, "
        "fitxatge, font) VALUES ('2026/2027','INDIVIDUAL','Tres bandes','MAS, JOSEP',"
        "'B.C.GRANOLLERS',0,'sorteig_fase')"
    )
    conn.commit()
    A.desa(
        conn,
        [
            A.Afiliacio(
                temporada="2026/2027",
                competicio=A.LLIGA,
                modalitat="Tres bandes",
                jugador="MAS, JOSEP",
                club="C.B.MATARÓ",
                fitxatge=True,
                font="lliga_inscrits",
            )
        ],
    )
    files = dict(
        conn.execute(
            "SELECT competicio, club FROM afiliacions WHERE temporada = '2026/2027'"
        ).fetchall()
    )
    assert files == {"INDIVIDUAL": "B.C.GRANOLLERS", "LLIGA": "C.B.MATARÓ"}


class SorteigFals:
    titol = "Prèvies 3 bandes Honor"

    def __init__(self, jugadors):
        self.jugadors = jugadors


class JugadorFals:
    def __init__(self, jugador, club):
        self.jugador, self.club = jugador, club


def test_el_club_del_sorteig_es_canonicalitza(conn) -> None:
    """El PDF escriu «GRANOLLERS» i el cens diu «B.C.GRANOLLERS».

    Es resol amb el resolutor del repositori, que és el mateix que fa servir la
    ingesta de lliga i que ja porta els àlies. Un club que no hi és de cap
    manera no s'inventa: va a la llista de coses per revisar.
    """
    sorteig = SorteigFals(
        [
            JugadorFals("MAS CANADELL, JOSEP Mª", "GRANOLLERS"),
            JugadorFals("LUQUE MARTÍNEZ, JESÚS", "SANT ADRIÀ"),
            JugadorFals("QUI SIGUI, ALGÚ", "CLUB QUE NO EXISTEIX"),
        ]
    )
    files, avisos = A.del_sorteig(Repository(conn), sorteig, "2026/2027", "Tres bandes")
    assert [(f.jugador, f.club) for f in files] == [
        ("MAS CANADELL, JOSEP Mª", "B.C.GRANOLLERS"),
        ("LUQUE MARTÍNEZ, JESÚS", "C.B.SANT ADRIÀ"),
    ]
    assert len(avisos) == 1 and "CLUB QUE NO EXISTEIX" in avisos[0]
    # El sorteig no marca els fitxatges: diu el club i prou.
    assert all(not f.fitxatge for f in files)
