"""Els tres primers de cada campionat carregat, contrastats amb el palmarès de medalles.

`palmares_medalles` (font `rfeb`) ve de la llista de medalles de la RFEB, que
arriba al 1993 i més enrere. `rfeb_classificacions` ve dels PDF de cada
campionat. Són dues fonts independents: el podi d'un campionat ha de ser el
mateix a totes dues. Aquí no es corregeix res; només es diu què no quadra.

L'any de l'edició del palmarès és el d'una data, i no sempre el mateix que el de
la prova: un campionat de la temporada 2016-2017 pot ser del 2016 o del 2017.
Per això, si la prova té data només es mira el seu any; si no, els dos de la
temporada, i es dona per bo el que coincideix.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

#: (modalitat, categoria) de `rfeb_proves` → (competició, categoria) de `palmares_medalles`.
_CORRESPONDENCIA = {
    ("3b", "absolut"): ("Tres bandes", "absolut"),
    ("3b", "femeni"): ("Tres bandes", "femení"),
    ("3b", "sub17"): ("Tres bandes", "sub-17"),
    ("3b", "sub21"): ("Tres bandes", "sub-21"),
    ("3b", "sub25"): ("Tres bandes", "sub-25"),
    ("banda", "absolut"): ("Una banda", "absolut"),
    ("lliure", "absolut"): ("Lliure", "absolut"),
    ("71_2", "absolut"): ("Quadre 71/2", "absolut"),
    ("47_2", "absolut"): ("Quadre 47/2", "absolut"),
}


@dataclass
class Comparacio:
    prova_id: str
    estat: str  # coincideix | difereix | sense palmarès
    any_edicio: int | None = None
    palmares: list[str] = field(default_factory=list)
    classificacio: list[str] = field(default_factory=list)


def _paraules(nom: str) -> list[str]:
    pla = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode().upper()
    return [w for w in re.split(r"[^A-Z]+", pla) if w]


def _mateixa_paraula(a: str, b: str) -> bool:
    """Iguals, o amb una errada d'escriptura («GARRRUCHO» i «GARRUCHO»)."""
    return a == b or (min(len(a), len(b)) >= 5 and SequenceMatcher(None, a, b).ratio() >= 0.88)


def mateix_jugador(a: str, b: str) -> bool:
    """Dos noms són el mateix jugador si comparteixen dues paraules, o una i les inicials quadren.

    «Josep Mª Mas» i «José M. Mas Canadell» no tenen cap nom de pila igual, però
    comparteixen «MAS» i les inicials de la resta hi caben. Amb una sola paraula
    en comú i res més, no es diu res.
    """
    pa, pb = _paraules(a), _paraules(b)
    comuns_a = {x for x in pa if len(x) > 1 and any(_mateixa_paraula(x, y) for y in pb)}
    comuns_b = {y for y in pb if len(y) > 1 and any(_mateixa_paraula(x, y) for x in pa)}
    if min(len(comuns_a), len(comuns_b)) >= 2:
        return True
    if not comuns_a:
        return False
    resta_a = [w for w in pa if w not in comuns_a]
    resta_b = [w for w in pb if w not in comuns_b]
    curt, llarg = (resta_a, resta_b) if len(resta_a) <= len(resta_b) else (resta_b, resta_a)
    return all(any(x.startswith(w[0]) for x in llarg) for w in curt)


def _classificacio(conn: sqlite3.Connection, prova_id: str) -> list[tuple[int, str]]:
    """(posició, jugador) de les quatre primeres posicions de la classificació."""
    return [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT COALESCE(posicio_empat, posicio), jugador FROM rfeb_classificacions "
            "WHERE prova_id = ? AND COALESCE(posicio_empat, posicio) <= 4 ORDER BY posicio",
            (prova_id,),
        )
    ]


def _coincideixen(podi: list[tuple[int, str]], classificacio: list[tuple[int, str]]) -> bool:
    """L'or i la plata són els mateixos, i els bronzes són entre els quatre primers.

    El palmarès dona dos bronzes en els campionats d'eliminatòries (els dos
    semifinalistes); a la classificació uns n'hi posen un a la 3a i l'altre a la 4a,
    i d'altres només el de la 3a. Per això els bronzes es miren contra els quatre primers.
    """
    for posicio in (1, 2):
        pal = [n for p, n in podi if p == posicio]
        cls = [n for p, n in classificacio if p == posicio]
        if not pal or not cls or not all(any(mateix_jugador(a, b) for b in cls) for a in pal):
            return False
    bronzes = [n for p, n in podi if p == 3]
    return all(any(mateix_jugador(b, n) for _p, n in classificacio) for b in bronzes)


def compara(conn: sqlite3.Connection, prova_ids: list[str] | None = None) -> list[Comparacio]:
    """Per cada Campionat d'Espanya carregat, si el seu podi és el d'alguna edició del palmarès."""
    sql = (
        "SELECT id, temporada, modalitat, categoria, data_inici FROM rfeb_proves "
        "WHERE tipus = 'ce' ORDER BY id"
    )
    sortida: list[Comparacio] = []
    for pid, temporada, modalitat, categoria, data_inici in conn.execute(sql).fetchall():
        if prova_ids is not None and pid not in prova_ids:
            continue
        clau = _CORRESPONDENCIA.get((modalitat, categoria))
        if clau is None:
            continue
        inici = int(temporada[:4])
        anys = [int(data_inici[:4])] if data_inici else [inici, inici + 1]
        cls = _classificacio(conn, pid)
        edicions: dict[tuple[int, str], list[tuple[int, str]]] = {}
        marques = ",".join("?" * len(anys))
        for any_, edicio, posicio, jugador in conn.execute(
            "SELECT any_edicio, edicio, posicio, jugador FROM palmares_medalles "
            f"WHERE font = 'rfeb' AND competicio = ? AND categoria = ? AND any_edicio IN ({marques}) "
            "AND posicio <= 3 ORDER BY any_edicio, edicio, posicio",
            (*clau, *anys),
        ):
            edicions.setdefault((any_, edicio), []).append((posicio, jugador))
        millor: Comparacio | None = None
        for (any_, _edicio), podi in edicions.items():
            cmp = Comparacio(
                pid,
                "coincideix" if _coincideixen(podi, cls) else "difereix",
                any_,
                [n for _p, n in podi],
                [n for _p, n in cls],
            )
            if cmp.estat == "coincideix":
                millor = cmp
                break
            millor = millor or cmp
        sortida.append(millor or Comparacio(pid, "sense palmarès", None, [], [n for _p, n in cls]))
    return sortida
