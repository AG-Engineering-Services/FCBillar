"""Retirar del núvol els clubs que ja no són al cens.

La publicació de clubs només fa upsert, o sigui que un club fusionat es queda
allà per sempre: la pàgina en va estar ensenyant cinquanta-set quan n'hi havia
quaranta-vuit, amb «C.B. CANET» al costat de «C.B.CANET DE MAR».

Retirar-ne és esborrar, i esborrar demana estar segur. Un club amb jugadors, amb
classificacions o amb rànquings a sobre no és un duplicat oblidat: és un club
que es fa servir, i treure'l deixaria aquelles files apuntant al no-res.
"""

from __future__ import annotations

from typing import Any

from fcbillar.cloud_sync import _retira_clubs_fusionats

#: El tall de PostgREST. Una resposta més llarga arriba retallada i no ho diu.
TALL = 1000


class TaulaFalsa:
    def __init__(self, magatzem: dict[str, list[dict]], nom: str) -> None:
        self._m, self._nom = magatzem, nom
        self._filtres: list[tuple[str, Any]] = []
        self._accio = ""
        self._tram: tuple[int, int] | None = None
        self._limit: int | None = None

    def select(self, *_a: Any, **_k: Any) -> TaulaFalsa:
        self._accio = "select"
        return self

    def delete(self) -> TaulaFalsa:
        self._accio = "delete"
        return self

    def eq(self, camp: str, valor: Any) -> TaulaFalsa:
        self._filtres.append((camp, valor))
        return self

    def in_(self, camp: str, valors: list) -> TaulaFalsa:
        self._filtres.append((camp, list(valors)))
        return self

    def limit(self, n: int) -> TaulaFalsa:
        self._limit = n
        return self

    def range(self, inici: int, fi: int) -> TaulaFalsa:
        self._tram = (inici, fi)
        return self

    def _casa(self, f: dict) -> bool:
        for camp, valor in self._filtres:
            if isinstance(valor, list):
                if f.get(camp) not in valor:
                    return False
            elif f.get(camp) != valor:
                return False
        return True

    def execute(self) -> Any:
        files = self._m.setdefault(self._nom, [])
        if self._accio == "delete":
            self._m[self._nom] = [f for f in files if not self._casa(f)]
            return type("Res", (), {"data": [], "count": 0})()

        vistes = [f for f in files if self._casa(f)]
        # PostgREST talla, tant si li demanes un tram com si no.
        vistes = vistes[self._tram[0] : self._tram[1] + 1] if self._tram else vistes[:TALL]
        if self._limit is not None:
            vistes = vistes[: self._limit]
        return type("Res", (), {"data": vistes, "count": len(vistes)})()


class ClientFals:
    def __init__(self, magatzem: dict[str, list[dict]]) -> None:
        self._m = magatzem

    def table(self, nom: str) -> TaulaFalsa:
        return TaulaFalsa(self._m, nom)


def _res(*_a: Any) -> None:
    pass


def test_retira_el_que_ja_no_es_al_cens() -> None:
    m = {"clubs": [{"fcb_id": "C.B.BANYOLES"}, {"fcb_id": "C.B. CANET"}]}
    assert _retira_clubs_fusionats(ClientFals(m), {"C.B.BANYOLES"}, _res) == 1
    assert [c["fcb_id"] for c in m["clubs"]] == ["C.B.BANYOLES"]


def test_no_retira_un_club_amb_jugadors() -> None:
    """No és un duplicat oblidat: és un club que es fa servir."""
    m = {
        "clubs": [{"fcb_id": "C.B.BANYOLES"}, {"fcb_id": "C.B. CANET"}],
        "players": [{"club_fcb_id": "C.B. CANET"}],
    }
    assert _retira_clubs_fusionats(ClientFals(m), {"C.B.BANYOLES"}, _res) == 0
    assert len(m["clubs"]) == 2


def test_un_club_amb_moltes_referencies_no_amaga_el_seguent() -> None:
    """El cas que es preguntava tot de cop amb un `in_`.

    Amb la llista sencera en una sola consulta, les mil primeres files són totes
    del primer club i les del segon queden fora del tall: el segon sembla lliure
    i se n'aniria tenint jugadors a sobre. Es pregunta club a club justament per
    això.
    """
    m = {
        "clubs": [
            {"fcb_id": "C.B.BANYOLES"},
            {"fcb_id": "A DE MOLTS"},
            {"fcb_id": "B DE POCS"},
        ],
        "players": [{"club_fcb_id": "A DE MOLTS"} for _ in range(TALL + 500)]
        + [{"club_fcb_id": "B DE POCS"}],
    }
    assert _retira_clubs_fusionats(ClientFals(m), {"C.B.BANYOLES"}, _res) == 0
    assert {c["fcb_id"] for c in m["clubs"]} == {"C.B.BANYOLES", "A DE MOLTS", "B DE POCS"}


def test_sense_res_a_retirar_no_fa_res() -> None:
    m = {"clubs": [{"fcb_id": "C.B.BANYOLES"}]}
    assert _retira_clubs_fusionats(ClientFals(m), {"C.B.BANYOLES"}, _res) == 0


def test_els_lliures_se_n_van_i_els_ocupats_es_queden() -> None:
    m = {
        "clubs": [{"fcb_id": "VIU"}, {"fcb_id": "LLIURE"}, {"fcb_id": "OCUPAT"}],
        "lliga_standings": [{"club_fcb_id": "OCUPAT"}],
    }
    assert _retira_clubs_fusionats(ClientFals(m), {"VIU"}, _res) == 1
    assert {c["fcb_id"] for c in m["clubs"]} == {"VIU", "OCUPAT"}
