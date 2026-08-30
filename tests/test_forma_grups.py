"""El repartiment en grups no pot deixar dos equips d'un club al mateix grup.

És la regla que la federació aplica al sorteig, i el generador de la Lliga 26/27
la implementa amb permutes sobre el serpentí. La primera versió amb quatre grups
mirava només si el club que ENTRAVA cabia al grup destí, no si el que en SORTIA
cabia a l'origen: les permutes es desfeien l'una a l'altra, el detector de cicle
abandonava i publicava un repartiment invàlid —Sant Feliu A i B al mateix grup, i
Mataró D i E a un altre.

Aquests tests comproven la propietat, no el camí: qualsevol implementació que
deixi dos equips d'un club junts els fa caure.
"""

from __future__ import annotations

import collections
import importlib.util
import sys
from pathlib import Path

import pytest

ARREL = Path(__file__).resolve().parents[1]


def _carrega_projeccio():
    spec = importlib.util.spec_from_file_location(
        "projeccio_lliga_2627", ARREL / "scripts" / "projeccio_lliga_2627.py"
    )
    assert spec is not None and spec.loader is not None
    modul = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modul
    spec.loader.exec_module(modul)
    return modul


P = _carrega_projeccio()


def clubs_repetits(ordre, grups) -> list[str]:
    """Els clubs que surten més d'una vegada dins d'un mateix grup."""
    dolents = []
    for g, lst in enumerate(grups):
        compte = collections.Counter(ordre[i][0] for i in lst)
        dolents += [
            f"grup {chr(ord('A') + g)}: {club} x{n}" for club, n in compte.items() if n > 1
        ]
    return dolents


@pytest.mark.parametrize("divisio", sorted(P.COMP))
def test_cap_club_repetit_dins_d_un_grup(divisio: str) -> None:
    ordre = P.COMP[divisio]
    grups, _ = P.forma_grups(ordre, P.GRUPS[divisio])
    assert clubs_repetits(ordre, grups) == []


@pytest.mark.parametrize("divisio", sorted(P.COMP))
def test_el_repartiment_no_perd_ni_repeteix_cap_equip(divisio: str) -> None:
    ordre = P.COMP[divisio]
    grups, _ = P.forma_grups(ordre, P.GRUPS[divisio])
    repartits = [i for lst in grups for i in lst]
    assert sorted(repartits) == list(range(len(ordre)))


@pytest.mark.parametrize("n_grups", [2, 3, 4])
def test_els_grups_queden_equilibrats(n_grups: int) -> None:
    """El serpentí reparteix de manera uniforme: com a molt un equip de diferència."""
    ordre = [(f"CLUB{i}", "A") for i in range(26)]
    grups, _ = P.forma_grups(ordre, n_grups)
    mides = sorted(len(g) for g in grups)
    assert mides[-1] - mides[0] <= 1


#: La 4a divisió del 2026-27 amb els 28 equips inscrits, en ordre de sembra.
#: És el cas que va destapar el defecte: la versió que mirava només si el club
#: entrant cabia al grup destí deixava Sant Feliu A i B junts al grup A, i
#: Mataró D i E junts al B, amb dues permutes que es desfeien l'una a l'altra
#: (24↔23 i 23↔24) fins que el detector de cicle abandonava.
QUARTA_2627 = [
    ("C.B.VILANOVA", ""), ("C.B. BORGES", ""), ("C.B. CANET", "C"),
    ("C.B.BLANES", "B"), ("C.B.MONT-ROIG", "C"), ("S.B.CORAL COLÓN", "B"),
    ("C.B.LLINARS", "D"), ("B.LA UNIÓ CORAL", "B"),
    ("B.C.SANT FELIU DE CODINES", ""), ("C.B.MONFORTE", "E"),
    ("S.B.ESPLUGUES L'AVENÇ", "B"), ("C.B.2000 CERDANYOLA", "C"),
    ("C.B.BANYOLES", "C"), ("C.B.MANRESA", "B"), ("C.B.MATARÓ", "D"),
    ("C.B.SANTS", "E"), ("C.B.LLEIDA", ""), ("C.B.VIC", ""),
    ("C.B.CARDONA", ""), ("C.B.SANT ADRIÀ", ""), ("B.C.GRANOLLERS", ""),
    ("S.B.LA GRAN PENYA", ""), ("B.LA UNIÓ CORAL", ""),
    ("B.C.SANT FELIU DE CODINES", ""), ("C.B.BANYOLES", ""),
    ("C.B.MATARÓ", ""), ("C.B.MATADEPERA", ""), ("C.B.PUNT D'ATAC", ""),
]


def test_la_quarta_del_2627_no_ajunta_equips_d_un_club() -> None:
    """Regressió del defecte real, amb la divisió que el va destapar."""
    grups, _ = P.forma_grups(QUARTA_2627, 4)
    assert clubs_repetits(QUARTA_2627, grups) == []
    assert sorted(i for lst in grups for i in lst) == list(range(len(QUARTA_2627)))


def test_cas_dificil_amb_molts_equips_del_mateix_club() -> None:
    """Quatre grups i tres clubs amb tres equips cadascun, tots seguits."""
    ordre = [
        ("A", "1"), ("A", "2"), ("A", "3"),
        ("B", "1"), ("B", "2"), ("B", "3"),
        ("C", "1"), ("C", "2"), ("C", "3"),
        ("D", "1"), ("E", "1"), ("F", "1"),
    ]
    grups, _ = P.forma_grups(ordre, 4)
    assert clubs_repetits(ordre, grups) == []


def test_quan_es_impossible_no_peta() -> None:
    """Cinc equips d'un club i només dos grups: no hi ha repartiment vàlid.

    El generador ho ha de deixar com pugui i tornar, no quedar-se en un bucle.
    """
    ordre = [("A", str(i)) for i in range(5)] + [("B", "1"), ("C", "1"), ("D", "1")]
    grups, permutes = P.forma_grups(ordre, 2)
    repartits = [i for lst in grups for i in lst]
    assert sorted(repartits) == list(range(len(ordre)))
    assert len(permutes) < 200
