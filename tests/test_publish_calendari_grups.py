"""El calendari de grups té font pròpia i no depèn del federatiu.

`publish_calendari` puja dues coses que vénen de PDF diferents: el calendari
esportiu de la federació (RFEB i FCB) i el calendari de cada grup de la lliga.

Si el federatiu no dona res, no es toca —buidar-lo a partir d'una lectura buida
se n'enduria el calendari sencer del web—, però això no és cap motiu per no
publicar el de grups, que ve d'una altra banda i pot ser perfectament vàlid.
"""

from __future__ import annotations

from typing import Any

from fcbillar import cloud_sync
from fcbillar.db.migrations import ensure_schema


class TaulaFalsa:
    def __init__(self, magatzem: dict[str, list[dict]], nom: str) -> None:
        self._m, self._nom = magatzem, nom
        self._filtres: list[tuple[str, Any]] = []
        self._accio = ""
        self._tram: tuple[int, int] | None = None

    def select(self, *_a: Any, **_k: Any) -> TaulaFalsa:
        self._accio = "select"
        return self

    def upsert(self, files: list[dict], **k: Any) -> TaulaFalsa:
        self._accio = "upsert"
        self._files = files
        self._clau = tuple((k.get("on_conflict") or "").split(","))
        return self

    def delete(self) -> TaulaFalsa:
        self._accio = "delete"
        return self

    def eq(self, camp: str, valor: Any) -> TaulaFalsa:
        self._filtres.append((camp, valor))
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
    def __init__(self, magatzem: dict[str, list[dict]]) -> None:
        self._m = magatzem

    def table(self, nom: str) -> TaulaFalsa:
        return TaulaFalsa(self._m, nom)


def _base_amb_grups(path) -> None:
    """Calendari de grups sí, calendari federatiu no: passa entre revisions."""
    conn = ensure_schema(path)
    conn.executemany(
        "INSERT INTO lliga_calendari "
        "(temporada, divisio, grup, jornada, data, local, visitant) VALUES (?,?,?,?,?,?,?)",
        [
            ("2026/2027", "1a", "B", 1, "2026-09-26", 'C.B. MANRESA "A"', 'C.B. BANYOLES "A"'),
            ("2026/2027", "1a", "B", 2, "2026-10-10", 'C.B. BANYOLES "A"', 'C.B. MOLLET "B"'),
        ],
    )
    conn.commit()
    conn.close()


def test_sense_calendari_federatiu_el_de_grups_es_publica_igual(tmp_path, monkeypatch) -> None:
    db = tmp_path / "t.db"
    _base_amb_grups(db)
    magatzem: dict[str, list[dict]] = {}
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))

    res = cloud_sync.publish_calendari(db_path=db)

    assert res["calendari_events"] == 0, "no hi ha res federatiu a publicar"
    assert res["lliga_calendari"] == 2, "però el de grups sí que té dades"
    assert len(magatzem["lliga_calendari"]) == 2


def test_sense_calendari_federatiu_no_es_buida_el_que_hi_ha_publicat(tmp_path, monkeypatch) -> None:
    """Una lectura buida no pot endur-se el calendari del web."""
    db = tmp_path / "t.db"
    _base_amb_grups(db)
    magatzem: dict[str, list[dict]] = {
        "calendari_events": [
            {"font": "FCB", "temporada": "2026/2027", "setmana": "2026-09-07", "titol": "hi era"}
        ]
    }
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))

    cloud_sync.publish_calendari(db_path=db)

    assert len(magatzem["calendari_events"]) == 1


def test_els_inscrits_de_la_lliga_es_publiquen(tmp_path, monkeypatch) -> None:
    """La font oficial de qui juga amb cada club també puja al núvol.

    És la que dona mitjana a qui no surt al rànquing general, i sense ella
    aquells socis van al final de la graella de participació amb un 0.
    """
    db = tmp_path / "t.db"
    _base_amb_grups(db)
    conn = ensure_schema(db)
    conn.executemany(
        "INSERT INTO lliga_inscrits (temporada, lliga_id, lliga, club, club_id_extern, "
        "jugador, mitjana, fitxatge, posicio) VALUES (?,?,?,?,?,?,?,?,?)",
        [
            (
                "2026/2027",
                38,
                "Lliga Catalana Tres Bandes",
                "C.B.BANYOLES",
                16,
                "GÓMEZ AMETLLER, ALBERT",
                0.57982,
                0,
                5,
            ),
            (
                "2026/2027",
                38,
                "Lliga Catalana Tres Bandes",
                "C.B.MONT-ROIG",
                22,
                "ARNAU ABILLEIRA, ALEIX",
                0.6176,
                1,
                6,
            ),
        ],
    )
    conn.commit()
    conn.close()
    magatzem: dict[str, list[dict]] = {}
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))

    res = cloud_sync.publish_calendari(db_path=db)

    assert res["lliga_inscrits"] == 2
    files = {f["jugador"]: f for f in magatzem["lliga_inscrits"]}
    # El 0/1 de SQLite ha d'arribar com a booleà: la columna de Postgres ho és.
    assert files["ARNAU ABILLEIRA, ALEIX"]["fitxatge"] is True
    assert files["GÓMEZ AMETLLER, ALBERT"]["fitxatge"] is False
    assert files["GÓMEZ AMETLLER, ALBERT"]["mitjana"] == 0.57982


def test_sense_inscrits_locals_no_es_toca_la_taula_publicada(tmp_path, monkeypatch) -> None:
    """Encara no s'ha ingerit res: no és motiu per buidar el que ja hi ha.

    La taula local buida NO vol dir que la federació no tingui ningú inscrit:
    `desa()` es nega a desar el buit precisament per no confondre les dues
    coses. Una base acabada de baixar o una ingesta que no ha corregut arriben
    aquí igual, i buidar el núvol a partir d'això se n'enduria la llista bona.
    """
    db = tmp_path / "t.db"
    _base_amb_grups(db)
    magatzem: dict[str, list[dict]] = {
        "lliga_inscrits": [
            {"lliga_id": 38, "club": "C.B.BANYOLES", "jugador": "hi era", "mitjana": 0.5}
        ]
    }
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))

    res = cloud_sync.publish_calendari(db_path=db)

    assert res["lliga_inscrits"] == 0
    assert len(magatzem["lliga_inscrits"]) == 1


def test_una_lliga_que_desapareix_del_local_es_retira_del_nuvol(tmp_path, monkeypatch) -> None:
    """Els àmbits són les lligues d'aquí I les publicades.

    Amb només les d'aquí, una lliga que ja no hi és no entraria mai a l'àmbit de
    reemplaçament i les seves files es quedarien publicades per sempre, encara
    que la competició ja no existeixi.

    Qui buida la lliga en local és `retira_lligues_tancades()`, quan deixa de
    sortir al llistat d'obertes de la federació; aquí es comprova l'altra meitat,
    que allò arribi al núvol. Les dues fan falta: sense la primera l'estat no es
    dona mai, i sense la segona no surt d'aquí.

    Que hi hagi files d'una altra lliga és el que diu que la ingesta funciona, i
    és el que fa que buidar-ne una sigui una decisió i no un accident: sense cap
    fila local no es toca res, i això ho diu la prova de sobre.
    """
    db = tmp_path / "t.db"
    _base_amb_grups(db)
    conn = ensure_schema(db)
    conn.execute(
        "INSERT INTO lliga_inscrits (temporada, lliga_id, lliga, club, club_id_extern, "
        "jugador, mitjana, fitxatge, posicio) VALUES (?,?,?,?,?,?,?,?,?)",
        ("2026/2027", 38, "Tres Bandes", "C.B.BANYOLES", 16, "QUI, HI ES", 0.5, 0, 1),
    )
    conn.commit()
    conn.close()

    magatzem: dict[str, list[dict]] = {
        "lliga_inscrits": [
            {"lliga_id": 38, "club": "C.B.BANYOLES", "jugador": "JA, NO HI ES", "mitjana": 0.4},
            {"lliga_id": 39, "club": "C.B.BANYOLES", "jugador": "D ALTRA, LLIGA", "mitjana": 0.4},
        ]
    }
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))

    cloud_sync.publish_calendari(db_path=db)

    queden = {f["jugador"] for f in magatzem["lliga_inscrits"]}
    assert "QUI, HI ES" in queden
    # De la seva lliga, qui ja no hi és se'n va.
    assert "JA, NO HI ES" not in queden
    # I la lliga sencera que ja no ingerim, també.
    assert "D ALTRA, LLIGA" not in queden
