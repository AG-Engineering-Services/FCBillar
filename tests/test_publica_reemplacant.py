"""Reemplaçar el que hi ha publicat no pot deixar-ho buit si la pujada falla.

El patró d'abans era esborrar l'àmbit sencer i tornar-hi a escriure. Entre les
dues coses la taula és buida, i si la pujada falla —xarxa, una fila dolenta, la
taula que encara no existeix— s'hi queda: el calendari desapareix del web i el
que ho diu és un avís que ningú no mira.

Escrivint primer i retirant després, una fallada deixa les dades velles al seu
lloc. Poden quedar-hi files de més fins a la propera publicació; això es veu i
es resol tornant a publicar, i una taula buida, no.
"""

from __future__ import annotations

from typing import Any

import pytest

from fcbillar.cloud_sync import _publica_reemplaçant


class TaulaFalsa:
    def __init__(self, magatzem: dict[str, list[dict]], nom: str, peta_a_upsert: bool) -> None:
        self._m, self._nom, self._peta = magatzem, nom, peta_a_upsert
        self._filtres: list[tuple[str, Any]] = []
        self._accio = ""
        self._tram: tuple[int, int] | None = None

    def select(self, *_a: Any, **_k: Any) -> TaulaFalsa:
        self._accio = "select"
        return self

    def upsert(self, files: list[dict], **k: Any) -> TaulaFalsa:
        if self._peta:
            raise RuntimeError("la pujada ha fallat")
        self._accio = "upsert"
        self._files = files
        # Com PostgREST: el que xoca és la clau de conflicte, no la fila sencera.
        self._clau = tuple((k.get("on_conflict") or "").split(","))
        return self

    def delete(self) -> TaulaFalsa:
        self._accio = "delete"
        return self

    def eq(self, camp: str, valor: Any) -> TaulaFalsa:
        self._filtres.append((camp, valor))
        return self

    def limit(self, _n: int) -> TaulaFalsa:
        return self

    def range(self, inici: int, fi: int) -> TaulaFalsa:
        """Com PostgREST: un tram tancat pels dos costats."""
        self._tram = (inici, fi)
        return self

    def execute(self) -> Any:
        files = self._m.setdefault(self._nom, [])
        if self._accio == "upsert":

            def clau(f: dict) -> tuple:
                return tuple(str(f.get(c)) for c in self._clau)

            noves = {clau(f) for f in self._files}
            files[:] = [f for f in files if clau(f) not in noves]
            files.extend(self._files)
        elif self._accio == "delete":
            self._m[self._nom] = [
                f for f in files if any(str(f.get(c)) != str(v) for c, v in self._filtres)
            ]
        vistes = [
            f
            for f in self._m.get(self._nom, [])
            if all(str(f.get(c)) == str(v) for c, v in self._filtres)
        ]
        if self._tram is not None:
            vistes = vistes[self._tram[0] : self._tram[1] + 1]
        return type("Res", (), {"data": vistes, "count": len(vistes)})()


class ClientFals:
    def __init__(self, magatzem: dict[str, list[dict]], peta_a_upsert: bool = False) -> None:
        self._m, self._peta = magatzem, peta_a_upsert

    def table(self, nom: str) -> TaulaFalsa:
        return TaulaFalsa(self._m, nom, self._peta)


CLAU = ("font", "temporada", "setmana")
AMBIT = ("font", "temporada")


def _fila(setmana: str, titol: str, font: str = "FCB", temp: str = "2026/2027") -> dict:
    return {"font": font, "temporada": temp, "setmana": setmana, "titol": titol}


def test_si_la_pujada_falla_el_que_hi_havia_es_queda() -> None:
    """El dany que es volia evitar: quedar-se sense calendari."""
    magatzem = {"cal": [_fila("2026-09-07", "abans"), _fila("2026-09-14", "abans")]}
    sb = ClientFals(magatzem, peta_a_upsert=True)
    with pytest.raises(RuntimeError):
        _publica_reemplaçant(sb, "cal", [_fila("2026-09-07", "ara")], CLAU, AMBIT, _prog)
    assert len(magatzem["cal"]) == 2
    assert {f["titol"] for f in magatzem["cal"]} == {"abans"}


def test_el_que_ja_no_hi_es_es_retira() -> None:
    magatzem = {"cal": [_fila("2026-09-07", "abans"), _fila("2026-09-14", "que marxa")]}
    sb = ClientFals(magatzem)
    _publica_reemplaçant(sb, "cal", [_fila("2026-09-07", "ara")], CLAU, AMBIT, _prog)
    assert [(f["setmana"], f["titol"]) for f in magatzem["cal"]] == [("2026-09-07", "ara")]


def test_no_toca_el_que_es_fora_de_l_ambit() -> None:
    """D'una font i temporada se'n treu el que sobra; de les altres, res."""
    magatzem = {
        "cal": [
            _fila("2026-09-07", "de la RFEB", font="RFEB"),
            _fila("2026-09-07", "d'una altra temporada", temp="2025/2026"),
            _fila("2026-09-14", "que marxa"),
        ]
    }
    sb = ClientFals(magatzem)
    _publica_reemplaçant(sb, "cal", [_fila("2026-09-07", "ara")], CLAU, AMBIT, _prog)
    titols = {f["titol"] for f in magatzem["cal"]}
    assert "de la RFEB" in titols
    assert "d'una altra temporada" in titols
    assert "que marxa" not in titols


def test_un_ambit_que_es_queda_sense_files_es_buida() -> None:
    """Una revisió del PDF que no canvia res deixa `calendari_canvis` buit.

    Els àmbits no es poden deduir de les files que es pugen: si un es queda sense
    cap, no hi sortiria i les seves files velles no marxarien mai. Per això la
    llista d'àmbits va explícita.
    """
    magatzem = {"cal": [_fila("2026-09-07", "d'una revisió anterior")]}
    sb = ClientFals(magatzem)
    _publica_reemplaçant(sb, "cal", [], CLAU, AMBIT, _prog, {("FCB", "2026/2027")})
    assert magatzem["cal"] == []


def test_un_ambit_buit_no_toca_els_altres() -> None:
    magatzem = {
        "cal": [
            _fila("2026-09-07", "de la RFEB", font="RFEB"),
            _fila("2026-09-07", "que marxa"),
        ]
    }
    sb = ClientFals(magatzem)
    _publica_reemplaçant(sb, "cal", [], CLAU, AMBIT, _prog, {("FCB", "2026/2027")})
    assert [f["titol"] for f in magatzem["cal"]] == ["de la RFEB"]


def test_sense_ambits_explicits_es_dedueixen_de_les_files() -> None:
    """El comportament de sempre, per a qui no en passa."""
    magatzem = {"cal": [_fila("2026-09-14", "que marxa")]}
    sb = ClientFals(magatzem)
    _publica_reemplaçant(sb, "cal", [_fila("2026-09-07", "ara")], CLAU, AMBIT, _prog)
    assert [f["titol"] for f in magatzem["cal"]] == ["ara"]


def test_publicar_el_mateix_dues_vegades_no_duplica() -> None:
    magatzem: dict[str, list[dict]] = {"cal": []}
    sb = ClientFals(magatzem)
    files = [_fila("2026-09-07", "ara"), _fila("2026-09-14", "ara")]
    _publica_reemplaçant(sb, "cal", files, CLAU, AMBIT, _prog)
    _publica_reemplaçant(sb, "cal", files, CLAU, AMBIT, _prog)
    assert len(magatzem["cal"]) == 2


def _prog(_nivell: str, _missatge: str) -> None:
    return None
