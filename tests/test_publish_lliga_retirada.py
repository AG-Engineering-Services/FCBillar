"""Publicar una classificació incompleta no ha d'esborrar la que hi havia.

`publish_lliga` fa un upsert i després retira el que no acaba de publicar,
perquè les taules en viu són «la temporada en curs» i el que hi queda de més
surt duplicat al web.

El perill és que la publicació sigui incompleta sense que peti res.
`_fetch_official_lliga_standings` s'empassa els errors de xarxa a posta —un grup
que falla simplement no hi surt—, i els grups que encara no han jugat cap
encontre no tenen cap altra font. A la temporada 2026-27 això són tots. Una
petició fallida esborraria una classificació bona i el web es quedaria sense
res, sense cap error que ho digués.
"""

from __future__ import annotations

from typing import Any

import pytest

from fcbillar import cloud_sync
from fcbillar.db.migrations import ensure_schema


class TaulaFalsa:
    """Recull què s'ha escrit i què s'ha esborrat, sense tocar cap xarxa."""

    def __init__(self, magatzem: dict[str, list[dict]], nom: str) -> None:
        self._m, self._nom = magatzem, nom
        self._filtres: list[tuple[str, Any]] = []
        self._accio = ""

    def select(self, *_a: Any, **_k: Any) -> TaulaFalsa:
        self._accio = "select"
        return self

    def upsert(self, files: list[dict], **_k: Any) -> TaulaFalsa:
        self._accio = "upsert"
        self._files = files
        return self

    def delete(self) -> TaulaFalsa:
        self._accio = "delete"
        return self

    def eq(self, camp: str, valor: Any) -> TaulaFalsa:
        self._filtres.append((camp, valor))
        return self

    def limit(self, _n: int) -> TaulaFalsa:
        return self

    def execute(self) -> Any:
        files = self._m.setdefault(self._nom, [])
        if self._accio == "upsert":
            files.extend(self._files)
        elif self._accio == "delete":
            self._m[self._nom] = [f for f in files if any(f.get(c) != v for c, v in self._filtres)]
        return type("Res", (), {"data": list(self._m.get(self._nom, [])), "count": 0})()


class ClientFals:
    def __init__(self, magatzem: dict[str, list[dict]]) -> None:
        self._m = magatzem

    def table(self, nom: str) -> TaulaFalsa:
        return TaulaFalsa(self._m, nom)


@pytest.fixture
def entorn(tmp_path, monkeypatch):
    """Una lliga de dos grups, cap encontre: tot depèn de la classificació."""
    conn = ensure_schema(tmp_path / "t.db")
    conn.execute("INSERT INTO temporades (id, nom) VALUES (1, '2026-2027')")
    for div, grup, nom in ((159, 0, "HONOR"), (159, 343, "GRUP A"), (159, 344, "GRUP B")):
        conn.execute(
            "INSERT INTO lliga_noms (lliga_id, divisio_id, grup_id, nom) VALUES (38,?,?,?)",
            (div, grup, nom),
        )
    conn.commit()
    conn.close()

    magatzem: dict[str, list[dict]] = {
        "lliga_groups": [
            {"lliga_id": 38, "divisio_id": 159, "grup_id": g, "divisio_nom": "HONOR", "grup_nom": n}
            for g, n in ((343, "GRUP A"), (344, "GRUP B"))
        ],
        "lliga_standings": [
            {
                "lliga_id": 38,
                "divisio_id": 159,
                "grup_id": g,
                "equip": f"EQUIP {g}",
                "posicio": 1,
                "punts": 3,
            }
            for g in (343, 344)
        ],
    }
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))
    return tmp_path / "t.db", magatzem


def _classificacio(posicio: int, equip: str, pm: int):
    from fcbillar.scraper.parsers import LligaClassificacioRow

    camps = LligaClassificacioRow.__dataclass_fields__
    valors = {"posicio": posicio, "equip": equip, "pm": pm}
    return LligaClassificacioRow(**{k: valors.get(k, 0) for k in camps})


def test_si_un_grup_no_respon_no_s_esborra_res(entorn, monkeypatch) -> None:
    """El cas que passa de debò: la federació falla en un grup i l'altre va bé."""
    db, magatzem = entorn
    monkeypatch.setattr(
        cloud_sync,
        "_fetch_official_lliga_standings",
        lambda claus, prog, lliga=38: {(159, 343): [_classificacio(1, "C.B.MATARÓ A", 0)]},
    )
    res = cloud_sync.publish_lliga(db_path=db, lliga_id=38)

    assert res["retirades"] == 0, "amb un grup mut no es pot saber què sobra"
    grups_vius = {f["grup_id"] for f in magatzem["lliga_standings"]}
    assert 344 in grups_vius, "la classificació del grup que no ha respost s'ha d'estar"


def test_si_no_respon_cap_grup_tampoc(entorn, monkeypatch) -> None:
    """Xarxa caiguda del tot: la taula ha de quedar com estava."""
    db, magatzem = entorn
    abans = list(magatzem["lliga_standings"])
    monkeypatch.setattr(
        cloud_sync, "_fetch_official_lliga_standings", lambda claus, prog, lliga=38: {}
    )
    res = cloud_sync.publish_lliga(db_path=db, lliga_id=38)

    assert res["retirades"] == 0
    assert magatzem["lliga_standings"] == abans


def test_quan_tot_respon_si_que_retira(entorn, monkeypatch) -> None:
    """La retirada segueix fent la seva feina: sense això tornen els duplicats."""
    db, magatzem = entorn
    monkeypatch.setattr(
        cloud_sync,
        "_fetch_official_lliga_standings",
        lambda claus, prog, lliga=38: {
            (159, 343): [_classificacio(1, "C.B.MATARÓ A", 0)],
            (159, 344): [_classificacio(1, "C.B.LLEIDA A", 0)],
        },
    )
    res = cloud_sync.publish_lliga(db_path=db, lliga_id=38)

    assert res["retirades"] == 2, "les dues files velles ja no surten a la publicació"
    equips = {f["equip"] for f in magatzem["lliga_standings"]}
    assert equips == {"C.B.MATARÓ A", "C.B.LLEIDA A"}


def test_la_temporada_anterior_es_retira_quan_la_nova_es_sencera(entorn, monkeypatch) -> None:
    db, magatzem = entorn
    magatzem["lliga_standings"].append(
        {"lliga_id": 36, "divisio_id": 148, "grup_id": 316, "equip": "VELL", "posicio": 1}
    )
    monkeypatch.setattr(
        cloud_sync,
        "_fetch_official_lliga_standings",
        lambda claus, prog, lliga=38: {
            (159, 343): [_classificacio(1, "A", 0)],
            (159, 344): [_classificacio(1, "B", 0)],
        },
    )
    cloud_sync.publish_lliga(db_path=db, lliga_id=38)
    assert not [f for f in magatzem["lliga_standings"] if f["lliga_id"] == 36]


def test_pero_no_si_la_nova_ve_coixa(entorn, monkeypatch) -> None:
    """Mig publicada, la temporada vella es queda: val més duplicat que perdut."""
    db, magatzem = entorn
    magatzem["lliga_standings"].append(
        {"lliga_id": 36, "divisio_id": 148, "grup_id": 316, "equip": "VELL", "posicio": 1}
    )
    monkeypatch.setattr(
        cloud_sync,
        "_fetch_official_lliga_standings",
        lambda claus, prog, lliga=38: {(159, 343): [_classificacio(1, "A", 0)]},
    )
    cloud_sync.publish_lliga(db_path=db, lliga_id=38)
    assert [f for f in magatzem["lliga_standings"] if f["lliga_id"] == 36]
