"""Un torneig que ja no surt al llistat s'ingereix pel seu id, i un sol cop.

La ingesta nocturna només recorre `individuals/llistat`, que només porta la
temporada en curs. L'Open de Mataró del juliol de 2026 (211/447) hi va quedar a
mitges: 130 partides a la base i cap participant, perquè la federació no en va
crear la classificació i el torneig va sortir del llistat abans que la ingesta
aprengués a deduir-la.

Les fixtures són les de l'Open de Mataró que ja hi havia (les divisions, les
fases, un grup i una eliminatòria), o sigui que el que se'n desa és una part del
torneig. Per al que es prova aquí n'hi ha prou.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fcbillar import pipeline
from fcbillar.db.migrations import ensure_schema
from fcbillar.scraper import urls as U
from fcbillar.scraper.parsers import parse_individuals_torneig_nom
from tests.test_classificacio_final_oficial import ClientAmbClassificacio, captura

NOU = Path(__file__).parent / "fixtures" / "nou"
MATARO = (211, 447)


@pytest.fixture
def conn(tmp_path, monkeypatch) -> sqlite3.Connection:
    monkeypatch.setattr(pipeline, "TORNEIGS_FORA_DEL_LLISTAT", ((211, "2025-2026"),))
    return ensure_schema(tmp_path / "test.db")


def _n(conn: sqlite3.Connection, taula: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {taula}").fetchone()[0]


def test_el_nom_del_torneig_surt_de_la_seva_pagina() -> None:
    html = (NOU / "individuals_divisions_211.html").read_text(encoding="utf-8")
    assert parse_individuals_torneig_nom(html) == "OPEN TRES BANDES MATARO"


def test_s_ingereix_amb_el_nom_i_la_temporada_que_li_toquen(conn) -> None:
    client = ClientAmbClassificacio({MATARO: captura(*MATARO)})

    resum = pipeline._ingereix_fora_del_llistat(client, conn, al_llistat={216, 217})

    assert resum["torneigs"] == 1
    assert resum["participants"] > 0 and resum["deduides"] == 1 and resum["oficials"] == 0
    fila = conn.execute(
        "SELECT ti.nom, te.nom FROM torneigs_individuals ti "
        "JOIN temporades te ON te.id = ti.temporada_id"
    ).fetchall()
    # Del 2025-2026, encara que la ingesta corri a la temporada següent.
    assert [tuple(f) for f in fila] == [("OPEN TRES BANDES MATARO", "2025-2026")]
    assert _n(conn, "torneig_participants") == resum["participants"]
    assert _n(conn, "torneig_partides") == resum["partides"] > 0


def test_la_segona_nit_no_torna_a_baixar_el_quadre(conn) -> None:
    pipeline._ingereix_fora_del_llistat(
        ClientAmbClassificacio({MATARO: captura(*MATARO)}), conn, al_llistat=set()
    )
    participants = _n(conn, "torneig_participants")

    client = ClientAmbClassificacio({MATARO: captura(*MATARO)})
    resum = pipeline._ingereix_fora_del_llistat(client, conn, al_llistat=set())

    # Una sola petició: la de la classificació final, que és l'única cosa d'un
    # torneig acabat que encara pot canviar.
    assert client.demanades == [U.individuals_classificacio_final(*MATARO)]
    assert resum["torneigs"] == 0
    assert _n(conn, "torneig_participants") == participants


def test_el_dia_que_la_federacio_crea_la_classificacio_entra_sola(conn) -> None:
    pipeline._ingereix_fora_del_llistat(
        ClientAmbClassificacio({MATARO: captura(*MATARO)}), conn, al_llistat=set()
    )
    # La classificació d'un altre open fa de la de Mataró: el que es prova és
    # que, quan n'hi ha, mana.
    client = ClientAmbClassificacio({MATARO: captura(217, 452)})

    resum = pipeline._ingereix_fora_del_llistat(client, conn, al_llistat=set())

    assert resum["oficials"] == 1
    assert _n(conn, "torneig_participants") == 24
    amb_club = conn.execute(
        "SELECT COUNT(*) FROM torneig_participants WHERE TRIM(COALESCE(club_text, '')) <> ''"
    ).fetchone()[0]
    assert amb_club == 24

    # I a partir d'aquí ja no es demana res més: no hi queda res per canviar.
    despres = ClientAmbClassificacio({MATARO: captura(217, 452)})
    pipeline._ingereix_fora_del_llistat(despres, conn, al_llistat=set())
    assert despres.demanades == []


def test_un_torneig_que_torna_al_llistat_es_deixa_per_al_llistat(conn) -> None:
    client = ClientAmbClassificacio({MATARO: captura(*MATARO)})
    resum = pipeline._ingereix_fora_del_llistat(client, conn, al_llistat={211})
    assert resum["torneigs"] == 0
    assert client.demanades == []


def test_que_un_falli_no_atura_res(conn) -> None:
    class ClientTrencat:
        def fetch_html(self, url: str, *, use_cache: bool = True) -> str:
            raise RuntimeError("HTTP 500")

    resum = pipeline._ingereix_fora_del_llistat(ClientTrencat(), conn, al_llistat=set())
    assert resum["torneigs"] == 0
    assert _n(conn, "torneig_participants") == 0


def test_per_id_es_respecta_la_temporada_que_el_torneig_ja_te(conn) -> None:
    """Sense dir-la, la temporada és la de la base: és part de la clau del torneig."""
    client = ClientAmbClassificacio({MATARO: captura(*MATARO)})
    pipeline.ingest_torneig_per_id(client, conn, 211, temporada="2025-2026")
    pipeline.ingest_torneig_per_id(client, conn, 211)
    assert _n(conn, "torneigs_individuals") == 1
