"""Desar els inscrits al campionat individual i treure'n els fitxatges.

El PDF de divisions és la llista oficial de qui juga a quin club aquesta
temporada. Fins que no es va desar, els traspassos s'anotaven a mà i no hi havia
manera de saber quins eren bons.
"""

from __future__ import annotations

import pytest

from fcbillar.db.migrations import ensure_schema
from fcbillar.divisions_individual import Inscrit, ResDesar, desa, traspassos


@pytest.fixture
def conn(tmp_path):
    c = ensure_schema(tmp_path / "t.db")
    for nom in ("C.B.BANYOLES", "S.B.F.MOLINS", "C.B.SANT BOI"):
        c.execute("INSERT INTO clubs (fcb_id, nom) VALUES (?, ?)", (nom, nom))
    return c


def _jugador(conn, nom: str, club: str | None) -> None:
    cid = None
    if club is not None:
        cid = conn.execute("SELECT id FROM clubs WHERE nom = ?", (club,)).fetchone()[0]
    conn.execute("INSERT INTO players (fcb_id, nom, club_id) VALUES (?, ?, ?)", (nom, nom, cid))


def _inscrit(nom: str, club: str, divisio: str = "2ª") -> Inscrit:
    return Inscrit(divisio=divisio, posicio=1, jugador=nom, club=club, mitjana=0.5, definitiva=True)


def test_no_desa_el_buit_sobre_el_que_ja_hi_ha(conn) -> None:
    """Un PDF que ha canviat de format en dona zero, i zero s'ho enduria tot."""
    desa(conn, [_inscrit("A, A", "C.B.BANYOLES")], "2026/2027")
    with pytest.raises(ResDesar):
        desa(conn, [], "2026/2027")
    assert conn.execute("SELECT COUNT(*) FROM inscrits_individual").fetchone()[0] == 1


def test_el_club_es_desa_amb_el_nom_del_cens(conn) -> None:
    desa(conn, [_inscrit("A, A", "SB FOMENT MOLINS")], "2026/2027")
    assert conn.execute("SELECT club FROM inscrits_individual").fetchone()[0] == ("S.B.F.MOLINS")


def test_reemplaça_nomes_la_seva_temporada(conn) -> None:
    desa(conn, [_inscrit("A, A", "C.B.BANYOLES")], "2025/2026")
    desa(conn, [_inscrit("B, B", "C.B.BANYOLES")], "2026/2027")
    temporades = {t for (t,) in conn.execute("SELECT temporada FROM inscrits_individual")}
    assert temporades == {"2025/2026", "2026/2027"}


def test_el_fitxatge_es_el_canvi_de_club(conn) -> None:
    _jugador(conn, "MOGUT, UN", "C.B.SANT BOI")
    _jugador(conn, "QUIET, UN", "C.B.BANYOLES")
    desa(
        conn,
        [_inscrit("MOGUT, UN", "C.B.BANYOLES"), _inscrit("QUIET, UN", "C.B.BANYOLES")],
        "2026/2027",
    )
    assert traspassos(conn, "2026/2027") == [("MOGUT, UN", "C.B.SANT BOI", "C.B.BANYOLES")]


def test_el_mateix_club_escrit_de_dues_maneres_no_es_cap_fitxatge(conn) -> None:
    """El motiu de tot plegat: sense això, de 66 diferències només 30 eren certes."""
    _jugador(conn, "QUIET, UN", "S.B.F.MOLINS")
    desa(conn, [_inscrit("QUIET, UN", "SB FOMENT MOLINS")], "2026/2027")
    assert traspassos(conn, "2026/2027") == []


def test_qui_no_te_club_fitxat_no_compta_com_a_fitxatge(conn) -> None:
    """No sabem d'on ve; dir que ve de «sense club» seria inventar-s'ho."""
    _jugador(conn, "SENSE, CLUB", None)
    desa(conn, [_inscrit("SENSE, CLUB", "C.B.BANYOLES")], "2026/2027")
    assert traspassos(conn, "2026/2027") == []
