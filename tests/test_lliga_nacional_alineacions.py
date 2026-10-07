"""Les alineacions de la Lliga Nacional, i res més del document on venen.

L'«orden de fuerza» porta, al costat dels jugadors de cada equip, l'adreça del
club i el nom, el telèfon i el correu dels seus directius. D'allà només n'han de
sortir els jugadors.

El PDF de debò no pot ser al repositori, justament per això. La prova es fa amb
una pàgina inventada que en copia la disposició: la banda de contacte a
l'esquerra, i a la dreta dues columnes de jugadors amb el seu número.
"""

from __future__ import annotations

import pytest

from fcbillar import lliga_nacional as LN
from fcbillar.db.migrations import ensure_schema
from fcbillar.lliga_nacional import _Paraula


def _linia(y: float, *trossos: tuple[float, str]) -> list[_Paraula]:
    """Una línia de paraules: cada tros és (x, text), i el text es parteix per espais."""
    out: list[_Paraula] = []
    for x, text in trossos:
        for paraula in text.split():
            out.append(_Paraula(paraula, x, x + 5 * len(paraula), y))
            x += 5 * len(paraula) + 4
    return out


#: Una pàgina amb dos grups i tres clubs, amb totes les menes de línia que hi ha.
PAGINA = [
    _linia(10, (252, "PRIMERA A")),
    _linia(20, (138, "C.B. MIJAS"), (346, "Mijas (MÁLAGA)")),
    _linia(30, (256, "1 José Muñoz Muñoz"), (380, "7 José Antonio Stand")),
    _linia(40, (135, "C/ Estornino s/n")),
    _linia(50, (256, "2 Sebastián Castaño"), (380, "8 Cristian Ávila")),
    _linia(
        60,
        (72, "Presidente: Enrique Martín (600111222)"),
        (256, "3 Ángel Fernández"),
        (380, "9 Enrique Martín"),
    ),
    _linia(70, (72, "directiu@exemple.cat"), (256, "4 Gregorio Moreno"), (378, "10")),
    # La província sense parèntesis, i en majúscules com el nom del club.
    _linia(80, (140, "C.B. SEVILLA"), (360, "SEVILLA")),
    _linia(90, (118, "Telf. Club:"), (256, "1 Pablo Cano López"), (380, "2 José Lazo")),
    _linia(100, (252, "PRIMERA B")),
    # La província de dues paraules.
    _linia(110, (135, "C.B. SOLLER"), (334, "Sóller (ISLAS BALEARES)")),
    _linia(120, (256, "1 Alain Lagúe Roldan")),
]


def test_cada_jugador_amb_el_seu_equip_el_seu_grup_i_el_seu_ordre() -> None:
    alineacions = LN._alineacions_de_linies(PAGINA)
    assert [(a.grup, a.equip, a.ordre, a.jugador) for a in alineacions] == [
        ("A", "C.B. MIJAS", 1, "José Muñoz Muñoz"),
        ("A", "C.B. MIJAS", 7, "José Antonio Stand"),
        ("A", "C.B. MIJAS", 2, "Sebastián Castaño"),
        ("A", "C.B. MIJAS", 8, "Cristian Ávila"),
        ("A", "C.B. MIJAS", 3, "Ángel Fernández"),
        ("A", "C.B. MIJAS", 9, "Enrique Martín"),
        ("A", "C.B. MIJAS", 4, "Gregorio Moreno"),
        ("A", "C.B. SEVILLA", 1, "Pablo Cano López"),
        ("A", "C.B. SEVILLA", 2, "José Lazo"),
        ("B", "C.B. SOLLER", 1, "Alain Lagúe Roldan"),
    ]


def test_no_en_surt_cap_dada_de_contacte() -> None:
    """Ni telèfons, ni correus, ni adreces, ni el càrrec de ningú."""
    alineacions = LN._alineacions_de_linies(PAGINA)
    tot = " ".join(f"{a.equip} {a.jugador}" for a in alineacions)
    for prohibit in ("600111222", "@", "Presidente", "Estornino", "Telf", "exemple"):
        assert prohibit not in tot
    # Un número sense nom és una plaça buida, no un jugador.
    assert all(a.jugador for a in alineacions)
    # La població i la província no són part del nom del club.
    assert {a.equip for a in alineacions} == {"C.B. MIJAS", "C.B. SEVILLA", "C.B. SOLLER"}


def test_el_csv_net_nomes_te_quatre_columnes(tmp_path) -> None:
    alineacions = LN._alineacions_de_linies(PAGINA)
    cami = tmp_path / "alineacions.csv"
    LN.escriu_alineacions_csv(alineacions, cami)
    assert cami.read_text(encoding="utf-8").splitlines()[0] == "grup,equip,ordre,jugador"
    assert LN.llegeix_alineacions_csv(cami) == alineacions


def test_es_desen_i_es_reemplacen(tmp_path) -> None:
    conn = ensure_schema(tmp_path / "t.db")
    alineacions = LN._alineacions_de_linies(PAGINA)
    assert LN.desa_alineacions(conn, alineacions, "1", "2026-2027") == 10
    LN.desa_alineacions(conn, alineacions[:3], "1", "2026-2027")
    assert conn.execute("SELECT COUNT(*) FROM nacional_alineacions").fetchone()[0] == 3
    with pytest.raises(ValueError, match="Cap alineació"):
        LN.desa_alineacions(conn, [], "1", "2026-2027")


def test_un_document_sense_jugadors_ho_diu() -> None:
    with pytest.raises(LN.FormatDesconegut):
        LN._alineacions_de_linies([_linia(10, (100, "CAP COSA"))])
