"""La classificació final oficial mana sobre la deduïda del quadre.

La federació la va tornar a publicar l'octubre de 2026, en una adreça nova
(`individuals/divisio-classificacio-final/{torneig}/{divisio}`), i comparada amb
la que deduíem no deia el mateix: a l'Open de Lliure del Punt d'Atac en diferien
5 posicions de 24. A més porta el club de cadascú, que no és enlloc més.

Les fixtures són captures del 2026-10-08: la de l'Open de Lliure (217/452), que
la té, i la de l'Open de Mataró (211/447), que diu «No s'ha creat la
classificació».
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fcbillar.db.migrations import ensure_schema
from fcbillar.individuals import (
    Divisio,
    Fase,
    Partida,
    desa,
    llegeix,
    te_classificacio_oficial,
)
from fcbillar.scraper import urls as U
from fcbillar.scraper.parsers import IndividualParticipant, parse_individuals_classificacio_final
from tests.test_individuals_open import ClientFals

NOU = Path(__file__).parent / "fixtures" / "nou"


def captura(torneig: int, divisio: int) -> str:
    return (NOU / f"classificacio_final_{torneig}_{divisio}.html").read_text(encoding="utf-8")


class ClientAmbClassificacio(ClientFals):
    """El client de sempre, i a més la pàgina de la classificació final.

    `respostes` diu què torna cada divisió: l'HTML, o una excepció que es llança.
    """

    def __init__(self, respostes: dict[tuple[int, int], str | Exception]) -> None:
        super().__init__()
        self._respostes = {
            U.individuals_classificacio_final(t, d): r for (t, d), r in respostes.items()
        }

    def fetch_html(self, url: str, *, use_cache: bool = True) -> str:
        if url in self._respostes:
            self.demanades.append(url)
            resposta = self._respostes[url]
            if isinstance(resposta, Exception):
                raise resposta
            return resposta
        return super().fetch_html(url, use_cache=use_cache)


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    return ensure_schema(tmp_path / "test.db")


def _participants(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return {
        r["nom"]: r
        for r in conn.execute(
            "SELECT p.nom, t.* FROM torneig_participants t JOIN players p ON p.id = t.player_id"
        )
    }


# ---------------- el parser ----------------


def test_la_pagina_oficial_es_llegeix_per_nom_de_columna() -> None:
    files = parse_individuals_classificacio_final(captura(217, 452))
    assert len(files) == 24
    assert [f.posicio for f in files] == list(range(1, 25))
    assert files[0] == IndividualParticipant(
        posicio=1,
        jugador_nom="CARBONELL TRILLA, MATEU",
        club="S.E.CASAL CERVERA",
        # «Punts» va abans de «Partides», al revés que a la pàgina vella.
        partides_jugades=7,
        punts=14,
        caramboles=1550,
        entrades=35,
        mitjana_general=44.2857,
        mitjana_particular=200.0,
        serie_max=None,
    )
    # Tothom porta club: és l'única pàgina del torneig que el diu.
    assert all(f.club for f in files)


def test_una_classificacio_que_no_s_ha_creat_es_una_llista_buida() -> None:
    assert parse_individuals_classificacio_final(captura(211, 447)) == []


# ---------------- la lectura ----------------


def test_llegeix_demana_la_classificacio_de_cada_divisio() -> None:
    client = ClientAmbClassificacio({(217, 452): captura(217, 452)})
    d = llegeix(client, 217, "OPEN LLIURE PUNT D'ATAC")[0]
    assert U.individuals_classificacio_final(217, 452) in client.demanades
    assert d.oficial is not None and len(d.oficial) == 24


def test_sense_classificacio_la_divisio_ho_diu_amb_una_llista_buida() -> None:
    d = llegeix(ClientAmbClassificacio({(217, 452): captura(211, 447)}), 217, "OPEN")[0]
    assert d.oficial == []


def test_si_la_pagina_falla_no_es_perd_el_torneig() -> None:
    d = llegeix(ClientAmbClassificacio({(217, 452): RuntimeError("HTTP 500")}), 217, "OPEN")[0]
    assert d.oficial is None
    assert len(d.partides) == 4


# ---------------- el desat ----------------


def test_l_oficial_mana_sobre_la_deduida(conn) -> None:
    d = llegeix(
        ClientAmbClassificacio({(217, 452): captura(217, 452)}), 217, "OPEN LLIURE PUNT D'ATAC"
    )[0]
    n = desa(conn, d, "2026-2027")

    # De les partides capturades la deducció en treia 5; l'oficial en porta 24.
    assert n["participants"] == 24
    files = _participants(conn)
    assert len(files) == 24
    assert all(r["club_text"] for r in files.values())

    campio = files["CARBONELL TRILLA, MATEU"]
    assert (campio["posicio"], campio["punts"], campio["partides_jugades"]) == (1, 14, 7)
    assert campio["club_text"] == "S.E.CASAL CERVERA"
    assert campio["mitjana_particular"] == 200.0
    # La sèrie major no és a la pàgina oficial: es conserva la de les partides.
    assert campio["serie_max"] == 196

    # Les dues posicions que la deducció girava: el quadre el feia vuitè.
    assert files["TUSET MALLOL, CARLES"]["posicio"] == 5
    assert files["ESPINASA SÁNCHEZ, JOAN"]["posicio"] == 7
    assert te_classificacio_oficial(conn, 1)


def test_sense_oficial_es_dedueix_com_sempre(conn) -> None:
    d = llegeix(ClientAmbClassificacio({(217, 452): captura(211, 447)}), 217, "OPEN")[0]
    n = desa(conn, d, "2026-2027")
    assert n["participants"] == 5
    files = _participants(conn)
    assert files["CARBONELL TRILLA, MATEU"]["posicio"] == 1
    assert not any(r["club_text"] for r in files.values())
    assert not te_classificacio_oficial(conn, 1)


def test_quan_arriba_l_oficial_substitueix_la_deduida_que_hi_havia(conn) -> None:
    """La nit que la federació crea la classificació, la deduïda se'n va."""
    desa(conn, llegeix(ClientFals(), 217, "OPEN")[0], "2026-2027")
    assert len(_participants(conn)) == 5

    d = llegeix(ClientAmbClassificacio({(217, 452): captura(217, 452)}), 217, "OPEN")[0]
    desa(conn, d, "2026-2027")
    assert len(_participants(conn)) == 24


def _quadre(oficial) -> Divisio:
    """Una final a dos, i un tercer que era al grup i no hi va jugar res."""
    return Divisio(
        torneig_id_extern=900,
        divisio_id_extern=901,
        nom="OPEN DE PROVA",
        fases=[Fase(1, "FINAL", "ko", 1)],
        partides=[
            Partida(1, None, None, "ROCA, ANNA", 30, 6, "PUIG, BERNAT", 20, 4, 25, None, None),
            Partida(1, None, None, "ROCA, ANNA", 30, 5, "ABSENT, CARLES", 10, 2, 25, None, None),
        ],
        oficial=oficial,
    )


def _fila(posicio: int, jugador: str, club: str) -> IndividualParticipant:
    return IndividualParticipant(posicio, jugador, club, 1, 2, 30, 25, 1.2, 1.2, None)


def test_qui_no_es_a_l_oficial_surt_de_la_classificacio(conn) -> None:
    """La deducció hi posa tothom que surt al quadre; la federació, no sempre."""
    desa(conn, _quadre([]), "2026-2027")
    assert set(_participants(conn)) == {"ROCA, ANNA", "PUIG, BERNAT", "ABSENT, CARLES"}

    oficial = [_fila(1, "PUIG, BERNAT", "C.B.PROVA"), _fila(2, "ROCA, ANNA", "C.B.ALTRE")]
    desa(conn, _quadre(oficial), "2026-2027")

    files = _participants(conn)
    assert set(files) == {"ROCA, ANNA", "PUIG, BERNAT"}
    # I l'ordre és el de la federació, encara que el quadre digui el contrari.
    assert files["PUIG, BERNAT"]["posicio"] == 1
    assert files["ROCA, ANNA"]["posicio"] == 2
    assert files["ROCA, ANNA"]["serie_max"] == 6


def test_una_nit_sense_resposta_no_torna_a_la_deduida(conn) -> None:
    """Amb l'oficial ja desada, que la pàgina falli no ha de canviar cap posició."""
    oficial = [_fila(1, "PUIG, BERNAT", "C.B.PROVA"), _fila(2, "ROCA, ANNA", "C.B.ALTRE")]
    desa(conn, _quadre(oficial), "2026-2027")

    n = desa(conn, _quadre(None), "2026-2027")

    files = _participants(conn)
    assert n["participants"] == 2
    assert files["PUIG, BERNAT"]["posicio"] == 1
    assert files["ROCA, ANNA"]["posicio"] == 2
    assert files["PUIG, BERNAT"]["club_text"] == "C.B.PROVA"


def test_sense_resposta_i_sense_res_desat_es_dedueix(conn) -> None:
    n = desa(conn, _quadre(None), "2026-2027")
    assert n["participants"] == 3
    assert _participants(conn)["ROCA, ANNA"]["posicio"] == 1
