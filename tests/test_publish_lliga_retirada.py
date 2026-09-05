"""Publicar una classificació incompleta no ha d'esborrar la que hi havia.

`publish_lliga` fa un upsert i després retira el que no acaba de publicar,
perquè les taules en viu són «la temporada en curs» i el que hi queda de més
surt duplicat al web.

El perill és que la publicació sigui incompleta sense que peti res.
`_fetch_official_lliga_standings` s'empassa els errors de xarxa a posta: un grup
que falla simplement no surt al resultat.

Dues maneres de perdre-hi dades, i la segona no es veu:

Un grup que encara no ha jugat cap encontre no té cap altra font que aquella
classificació —a la 2026-27 això són tots—, o sigui que amb la petició fallida
es queda sense cap fila i la retirada l'esborra sencer.

I un grup a MITJA temporada en treu, de files, perquè els encontres ingerits
n'hi posen: sembla publicat correctament. Però els encontres només diuen qui ha
jugat. Els equips que encara no hi surten no hi són, i la retirada se'ls
enduria. Per això la condició no pot ser «el grup ha donat files» sinó «la
classificació oficial ha respost», que és l'única que fa de cens dels equips.
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
        self._tram: tuple[int, int] | None = None

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

    def range(self, inici: int, fi: int) -> TaulaFalsa:
        """Com PostgREST: un tram tancat pels dos costats."""
        self._tram = (inici, fi)
        return self

    def execute(self) -> Any:
        files = self._m.setdefault(self._nom, [])
        if self._accio == "upsert":
            files.extend(self._files)
        elif self._accio == "delete":
            self._m[self._nom] = [f for f in files if any(f.get(c) != v for c, v in self._filtres)]
        dades = list(self._m.get(self._nom, []))
        if self._tram is not None:
            dades = dades[self._tram[0] : self._tram[1] + 1]
        return type("Res", (), {"data": dades, "count": 0})()


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


def _grup_a_mig_jugar(db) -> None:
    """Dos dels vuit equips del grup 343 ja han jugat; els altres sis, no."""
    import sqlite3

    conn = sqlite3.connect(db)
    for i, nom in enumerate(("C.B.MATARÓ", "C.B.LLEIDA"), start=1):
        conn.execute("INSERT INTO clubs (id, fcb_id, nom) VALUES (?,?,?)", (i, nom, nom))
        conn.execute("INSERT INTO equips (id, club_id, lletra) VALUES (?,?,'A')", (i, i))
    conn.execute(
        """
        INSERT INTO encontres_lliga
            (lliga_id, divisio_id, grup_id, jornada_id, encontre_id_extern, temporada_id,
             equip_local_id, equip_visitant_id, p_match_local, p_match_visitant,
             p_parcials_local, p_parcials_visitant)
        VALUES (38, 159, 343, 1, 1, 1, 1, 2, 3, 0, 6, 2)
        """
    )
    conn.commit()
    conn.close()


def test_un_grup_a_mig_jugar_amb_l_oficial_mut_no_perd_equips(entorn, monkeypatch) -> None:
    """El cas dolent de debò, i el que no es veu.

    Un grup que ja ha jugat treu files dels encontres encara que la petició
    oficial falli, o sigui que sembla publicat. Però els encontres només diuen
    qui HA JUGAT: els equips que encara no han sortit no hi són. Retirar a
    partir d'això se'ls enduria, i són justament els que no es poden defensar.
    """
    db, magatzem = entorn
    _grup_a_mig_jugar(db)
    magatzem["lliga_standings"] = [
        {"lliga_id": 38, "divisio_id": 159, "grup_id": 343, "equip": e, "posicio": i, "punts": 0}
        for i, e in enumerate(
            ("C.B.MATARÓ A", "C.B.LLEIDA A", "B. C. OLESA", "C.B.SANT BOI A"), start=1
        )
    ]
    # La federació no respon d'aquest grup, però sí de l'altre.
    monkeypatch.setattr(
        cloud_sync,
        "_fetch_official_lliga_standings",
        lambda claus, prog, lliga=38: {(159, 344): [_classificacio(1, "ALTRE", 0)]},
    )
    cloud_sync.publish_lliga(db_path=db, lliga_id=38)

    equips = {f["equip"] for f in magatzem["lliga_standings"]}
    assert "B. C. OLESA" in equips and "C.B.SANT BOI A" in equips, (
        "els equips que encara no han jugat no poden desaparèixer perquè la "
        "classificació oficial no hagi respost"
    )


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


def test_els_noms_dels_grups_de_temporades_velles_no_es_retiren(entorn, monkeypatch) -> None:
    """`lliga_groups` és el diccionari dels `grup_id`, no la temporada en curs.

    `lliga_encontres` es guarda els encontres de totes les temporades. Si en
    publicar-ne una de nova se n'anessin els noms dels grups de les anteriors,
    aquells encontres es quedarien orfes i ningú no podria dir de quin grup
    eren. Va passar de debò: 19 grups i 648 encontres.
    """
    db, magatzem = entorn
    magatzem["lliga_groups"].append(
        {
            "lliga_id": 36,
            "divisio_id": 148,
            "grup_id": 316,
            "divisio_nom": "HONOR",
            "grup_nom": "GRUP A",
        }
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
    vells = [f for f in magatzem["lliga_groups"] if f["lliga_id"] == 36]
    assert vells, "el nom del grup de la temporada passada s'ha de quedar"


def test_la_temporada_anterior_es_queda(entorn, monkeypatch) -> None:
    """Publicar una temporada no se n'endú l'anterior.

    Va semblar que `lliga_standings` era «la temporada en curs» i resulta que no:
    `lliga_encontres` es guarda els encontres de totes, i l'aplicació del club en
    penja el seguiment. Retirar-ne la 2025-26 va deixar el Banyoles sense
    classificacions ni resultats de tota la temporada passada. Cada fila porta el
    seu lliga_id; qui vulgui només la d'ara, que filtri.
    """
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
    assert [f for f in magatzem["lliga_standings"] if f["lliga_id"] == 36]
    # I la nova hi és igualment.
    assert [f for f in magatzem["lliga_standings"] if f["lliga_id"] == 38]
