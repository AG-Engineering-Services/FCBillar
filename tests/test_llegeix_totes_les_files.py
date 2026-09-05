"""Llegir una taula del núvol vol dir llegir-la sencera.

PostgREST en torna mil i no ho diu enlloc: la resposta arriba bé, només que
curta. Amb 1.607 jugadors, mirar-ne mil és no mirar-ne sis-cents, i qui ho fa
servir per decidir si sobra alguna cosa decideix amb mitja taula.

El repositori ja ho tenia escrit en tres llocs («.range() explícit: PostgREST
talla a 1000 files en silenci») i tot i així hi vaig tornar a caure escrivint
l'avís de les fitxes de pedaç.
"""

from __future__ import annotations

import pytest

from fcbillar.cloud_sync import _totes_les_files


class _Taula:
    """Respon per trams, com PostgREST, i apunta quins li han demanat."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.trams: list[tuple[int, int]] = []
        self._a = self._b = 0

    def select(self, *_a: object, **_k: object) -> _Taula:
        return self

    def range(self, a: int, b: int) -> _Taula:
        self._a, self._b = a, b
        return self

    def execute(self) -> object:
        self.trams.append((self._a, self._b))
        files = [{"fcb_id": str(i)} for i in range(self._a, min(self._b + 1, self.total))]
        return type("R", (), {"data": files})()


class _Sb:
    def __init__(self, taula: _Taula) -> None:
        self._t = taula

    def table(self, _nom: str) -> _Taula:
        return self._t


@pytest.mark.parametrize("total", [0, 1, 999, 1000, 1001, 1607, 2500])
def test_les_llegeix_totes(total: int) -> None:
    taula = _Taula(total)
    assert len(_totes_les_files(_Sb(taula), "players", "fcb_id")) == total


def test_amb_menys_de_mil_no_demana_una_segona_pagina() -> None:
    """No té sentit pagar una petició de més quan la primera ja diu que s'ha acabat."""
    taula = _Taula(500)
    _totes_les_files(_Sb(taula), "players", "fcb_id")
    assert len(taula.trams) == 1


def test_amb_mil_justes_en_demana_una_altra() -> None:
    """Mil és exactament el tall: no se sap si n'hi ha més fins que ho preguntes."""
    taula = _Taula(1000)
    _totes_les_files(_Sb(taula), "players", "fcb_id")
    assert len(taula.trams) == 2


def test_els_trams_van_seguits_i_no_es_trepitgen() -> None:
    taula = _Taula(2500)
    _totes_les_files(_Sb(taula), "players", "fcb_id")
    assert taula.trams == [(0, 999), (1000, 1999), (2000, 2999)]
