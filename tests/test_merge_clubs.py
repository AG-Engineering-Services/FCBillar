"""Fusionar dues fitxes del mateix club sense inventar-se ni perdre res.

El cas que fa mal no és moure els jugadors: és que totes dues fitxes tinguin un
equip «A». `equips` té UNIQUE(club_id, lletra), o sigui que no es poden moure i
prou, i el que es fa és apuntar els encontres i els games de l'A que sobra a
l'A que es queda. Aquí es comprova que no se'n perd cap pel camí.
"""

from __future__ import annotations

import sqlite3

import pytest

from fcbillar.db.migrations import ensure_schema
from fcbillar.db.repository import Repository


@pytest.fixture
def repo(tmp_path) -> Repository:
    return Repository(ensure_schema(tmp_path / "t.db"))


def _club(r: Repository, nom: str) -> int:
    r.conn.execute("INSERT INTO clubs (fcb_id, nom) VALUES (?, ?)", (nom, nom))
    return r.conn.execute("SELECT id FROM clubs WHERE fcb_id = ?", (nom,)).fetchone()[0]


def _equip(r: Repository, club_id: int, lletra: str) -> int:
    cur = r.conn.execute(
        "INSERT INTO equips (club_id, lletra) VALUES (?, ?) RETURNING id",
        (club_id, lletra),
    )
    return cur.fetchone()[0]


def _encontre(r: Repository, local: int, visitant: int, extern: int) -> None:
    r.conn.execute(
        """
        INSERT INTO encontres_lliga
            (lliga_id, divisio_id, grup_id, jornada_id, encontre_id_extern,
             equip_local_id, equip_visitant_id)
        VALUES (1, 1, 1, 1, ?, ?, ?)
        """,
        (extern, local, visitant),
    )


def test_els_encontres_de_l_equip_que_sobra_no_es_perden(repo: Repository) -> None:
    """El cas del Coral Colón: A històrica i A nova acaben sent la mateixa A."""
    vell, nou = _club(repo, "CORAL COLÓN"), _club(repo, "S.B.CORAL COLÓN")
    a_vella, a_nova = _equip(repo, vell, "A"), _equip(repo, nou, "A")
    altre = _equip(repo, _club(repo, "C.B.BANYOLES"), "A")
    _encontre(repo, a_vella, altre, 1)  # temporades velles
    _encontre(repo, altre, a_vella, 2)
    _encontre(repo, a_nova, altre, 3)  # la temporada nova

    repo.merge_clubs("CORAL COLÓN", "S.B.CORAL COLÓN")

    n = repo.conn.execute(
        "SELECT COUNT(*) FROM encontres_lliga WHERE equip_local_id = ? OR equip_visitant_id = ?",
        (a_nova, a_nova),
    ).fetchone()[0]
    assert n == 3, "els tres encontres han de quedar penjats de l'única A que queda"
    assert repo.conn.execute("SELECT COUNT(*) FROM encontres_lliga").fetchone()[0] == 3
    assert not repo.conn.execute("SELECT 1 FROM equips WHERE id = ?", (a_vella,)).fetchone()


def test_l_equip_amb_lletra_nova_nomes_canvia_de_club(repo: Repository) -> None:
    vell, nou = _club(repo, "SB FOMENT MOLINS"), _club(repo, "S.B.F.MOLINS")
    c = _equip(repo, vell, "C")
    repo.merge_clubs("SB FOMENT MOLINS", "S.B.F.MOLINS")
    assert repo.conn.execute("SELECT club_id FROM equips WHERE id = ?", (c,)).fetchone()[0] == nou


def test_el_nom_vell_queda_com_a_alies(repo: Repository) -> None:
    """És el que evita que la pròxima ingesta el torni a crear."""
    _club(repo, "MATADEPERA")
    nou = _club(repo, "C.B.MATADEPERA")
    repo.merge_clubs("MATADEPERA", "C.B.MATADEPERA")
    assert repo.resolve_club_id_by_nom("MATADEPERA") == nou
    assert not repo.conn.execute("SELECT 1 FROM clubs WHERE fcb_id = 'MATADEPERA'").fetchone()


def test_no_fusiona_dos_clubs_que_es_van_enfrontar(repo: Repository) -> None:
    """Si van jugar l'un contra l'altre no són el mateix club, i plantar-s'hi.

    Sense això, l'encontre acabaria sent un equip jugant contra ell mateix: un
    resultat inventat que després ningú no sabria d'on surt.
    """
    a, b = _club(repo, "C.B.SANT BOI"), _club(repo, "C.B.SANT ADRIÀ")
    _encontre(repo, _equip(repo, a, "A"), _equip(repo, b, "A"), 1)
    with pytest.raises(ValueError, match="l'un contra l'altre"):
        repo.merge_clubs("C.B.SANT BOI", "C.B.SANT ADRIÀ")
    assert repo.conn.execute("SELECT COUNT(*) FROM clubs").fetchone()[0] == 2


def test_si_peta_a_mig_fer_no_queda_mig_fusionat(repo: Repository) -> None:
    """La connexió és autocommit: sense transacció, un error deixaria destrossa."""
    vell, _nou = _club(repo, "PUNT D'ATAC"), _club(repo, "C.B.PUNT D'ATAC")
    _equip(repo, vell, "A")
    repo.conn.execute("INSERT INTO players (fcb_id, nom, club_id) VALUES ('x', 'X', ?)", (vell,))

    real = repo.conn

    class PetaAlFinal:
        """La connexió de debò, però l'última sentència de la fusió falla."""

        def __init__(self, conn: sqlite3.Connection) -> None:
            self._conn = conn

        def execute(self, sql: str, *args: object) -> sqlite3.Cursor:
            if sql.startswith("DELETE FROM clubs"):
                raise sqlite3.OperationalError("disc ple")
            return self._conn.execute(sql, *args)

        def __getattr__(self, nom: str) -> object:
            return getattr(self._conn, nom)

    repo.conn = PetaAlFinal(real)  # type: ignore[assignment]
    with pytest.raises(sqlite3.OperationalError):
        repo.merge_clubs("PUNT D'ATAC", "C.B.PUNT D'ATAC")
    repo.conn = real

    assert (
        repo.conn.execute("SELECT club_id FROM players WHERE fcb_id = 'x'").fetchone()[0] == vell
    ), "el jugador ha de tornar al club vell, no quedar-se a mig"
    assert (
        repo.conn.execute("SELECT COUNT(*) FROM equips WHERE club_id = ?", (vell,)).fetchone()[0]
        == 1
    )
