"""Un club, un nom.

Les equivalències no s'han tret de la semblança del nom, que és el que fa
equivocar, sinó de mirar les dades: set parelles tenien la fitxa nova buida, i
les dues que tenen dades a totes dues bandes —Coral Colón i Sant Feliu— surten
una sola vegada al cens oficial.
"""

from __future__ import annotations

import pytest

from fcbillar.clubs import ALIES, canonic, es_club, mateix_club, normalitza


@pytest.mark.parametrize(
    "vell, oficial",
    [
        ("SB FOMENT MOLINS", "S.B.F.MOLINS"),
        ("SANT ADRIÀ", "C.B.SANT ADRIÀ"),
        ("C.B. CANET", "C.B.CANET DE MAR"),
        ("CASAL DE CERVERA", "S.E.CASAL CERVERA"),
        ("CORAL COLÓN", "S.B.CORAL COLÓN"),
        ("B.C.SANT FELIU DE CODINES", "C.B.SANT FELIU"),
        ("B. EL MASNOU", "BILLAR EL MASNOU"),
        ("MATADEPERA", "C.B.MATADEPERA"),
        ("PUNT D'ATAC", "C.B.PUNT D'ATAC"),
    ],
)
def test_el_nom_vell_porta_a_l_oficial(vell: str, oficial: str) -> None:
    assert canonic(vell) == oficial
    assert mateix_club(vell, oficial)


def test_l_oficial_es_queda_com_esta() -> None:
    """No es toca el que ja és bo."""
    for oficial in set(ALIES.values()):
        assert canonic(oficial) == oficial


def test_els_accents_i_els_punts_no_compten() -> None:
    assert mateix_club("S.B. Coral Colón", "SB CORAL COLON")
    assert mateix_club("sant adria", "C.B.SANT ADRIÀ")


def test_no_ajunta_clubs_diferents() -> None:
    """El perill de fer-ho pel nom: aquests s'assemblen i no són el mateix."""
    assert not mateix_club("C.B.SANT ADRIÀ", "C.B.SANT BOI")
    assert not mateix_club("C.B.MATARÓ", "C.B.MATADEPERA")
    assert not mateix_club("C.B.SANTS", "C.B.SANT FELIU")


def test_el_que_no_coneixem_es_torna_tal_com_ve() -> None:
    """Val més un nom sense unificar que unificar-lo amb qui no toca."""
    assert canonic("B.C.OLESA") == "B.C.OLESA"
    assert canonic("CLUB QUE NO EXISTEIX") == "CLUB QUE NO EXISTEIX"


def test_la_federacio_i_els_independents_no_son_clubs() -> None:
    assert not es_club("FEDERACIO CATALANA DE BILLAR")
    assert not es_club("INDEPENDENT")
    assert es_club("C.B.BANYOLES")


def test_cap_alies_apunta_a_un_altre_alies() -> None:
    """Si un oficial fos alhora clau d'un àlies, `canonic` no convergiria."""
    claus = {normalitza(k) for k in ALIES}
    destins = {normalitza(v) for v in ALIES.values()}
    assert claus & destins == set()
