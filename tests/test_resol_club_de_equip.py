"""Resoldre el club d'un equip quan el nom porta la lletra.

A la classificació els equips es diuen «C.B. SANT ADRIÀ "A"» i al cens el club
és «C.B.SANT ADRIÀ». Normalitzats són «cbsantadriaa» i «cbsantadria»: prou a
prop per confondre i prou lluny per no casar mai.

Sense això, sis dels vuit equips del grup d'Honor de la 26/27 es publicaven
sense identificador de club, i qui hi clicava obria una fitxa buida.
"""

from __future__ import annotations

import pytest

from fcbillar.db.migrations import ensure_schema
from fcbillar.db.repository import Repository


@pytest.fixture
def repo(tmp_path):
    conn = ensure_schema(tmp_path / "t.db")
    for fcb_id, nom in (
        ("C.B.SANT ADRIÀ", "C.B.SANT ADRIÀ"),
        ("C.B.MANRESA", "C.B.MANRESA"),
        ("BC OLESA", "BC OLESA"),
    ):
        conn.execute("INSERT INTO clubs (fcb_id, nom) VALUES (?, ?)", (fcb_id, nom))
    conn.commit()
    return Repository(conn)


def _nom(repo: Repository, equip: str) -> str | None:
    cid = repo.resolve_club_id_by_nom(equip)
    fila = repo.conn.execute("SELECT nom FROM clubs WHERE id = ?", (cid,)).fetchone()
    return fila[0] if fila else None


def test_amb_la_lletra_entre_cometes(repo) -> None:
    assert _nom(repo, 'C.B. SANT ADRIÀ "A"') == "C.B.SANT ADRIÀ"


def test_amb_la_lletra_sense_cometes(repo) -> None:
    """La classificació històrica els escriu així."""
    assert _nom(repo, "C.B.MANRESA A") == "C.B.MANRESA"


def test_totes_les_lletres_van_al_mateix_club(repo) -> None:
    quins = {_nom(repo, f'C.B. SANT ADRIÀ "{lletra}"') for lletra in "ABCDE"}
    assert quins == {"C.B.SANT ADRIÀ"}


def test_el_nom_pelat_segueix_casant(repo) -> None:
    assert _nom(repo, "C.B.MANRESA") == "C.B.MANRESA"


def test_un_club_sense_lletra_no_es_toca(repo) -> None:
    """«B. C. OLESA» no acaba amb la lletra d'un equip: acaba amb el seu nom."""
    assert _nom(repo, "B. C. OLESA") == "BC OLESA"


def test_un_club_que_no_hi_es_segueix_sense_casar(repo) -> None:
    """Treure la lletra no pot convertir un desconegut en conegut."""
    assert repo.resolve_club_id_by_nom('C.B. INVENTAT "Z"') is None
    assert repo.resolve_club_id_by_nom("C.B. INVENTAT") is None
