"""Desar i publicar la Lliga Nacional, sense tocar res de la federació catalana.

La llicència espanyola i la catalana són independents, i les partides de la
lliga nacional no compten per al rànquing català. La prova que més importa
d'aquest fitxer és la que mira que desar una jornada no ha creat cap jugador,
cap club ni cap partida fora de les taules `nacional_*`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fcbillar import cloud_sync
from fcbillar import lliga_nacional as LN
from fcbillar.db.migrations import ensure_schema
from tests.test_publish_lliga_retirada import ClientFals

NACIONAL = Path(__file__).parent / "fixtures" / "nacional"

TAULES = (
    "nacional_classificacio",
    "nacional_encontres",
    "nacional_partides",
    "nacional_jugadors",
    "nacional_millors_series",
)


@pytest.fixture(scope="module")
def jornada() -> LN.Jornada:
    return LN.llegeix_jornada(NACIONAL / "liga_nal_1_j1_2627.pdf")


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    return ensure_schema(tmp_path / "t.db")


def _files(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TAULES}


def test_la_temporada_surt_de_la_data() -> None:
    from datetime import date

    assert LN.temporada_de(date(2026, 9, 12)) == "2026-2027"
    assert LN.temporada_de(date(2027, 2, 20)) == "2026-2027"
    assert LN.temporada_de(date(2027, 8, 1)) == "2027-2028"


def test_es_desa_una_jornada_sencera(conn, jornada) -> None:
    assert LN.desa_jornada(conn, jornada, "1") == "2026-2027"
    assert _files(conn) == {
        "nacional_classificacio": 16,
        "nacional_encontres": 8,
        "nacional_partides": 32,
        "nacional_jugadors": 0,
        "nacional_millors_series": 10,
    }
    fila = conn.execute(
        "SELECT grup, data, local, punts_local, punts_visitant, visitant FROM nacional_encontres "
        "WHERE visitant LIKE '%SANT ADRI%'"
    ).fetchone()
    assert tuple(fila) == ("B", "2026-09-12", "INVIKTCUES GRANOLLERS 'B'", 3, 5, "C.B. SANT ADRIÁ")


def test_tornar_a_desar_la_no_duplica_res(conn, jornada) -> None:
    LN.desa_jornada(conn, jornada, "1")
    abans = _files(conn)
    LN.desa_jornada(conn, jornada, "1")
    assert _files(conn) == abans


def test_no_toca_res_de_la_federacio_catalana(conn, jornada) -> None:
    """Ni jugadors, ni clubs, ni partides de rànquing: les dues federacions no es barregen."""
    # Totes les taules de la base que no són de la lliga nacional, sense triar-ne:
    # si demà se n'afegeix una, la prova també la vigila.
    alienes = [
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        if not r[0].startswith(("nacional_", "sqlite_"))
    ]
    assert {"players", "clubs", "games"} <= set(alienes)
    abans = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in alienes}
    LN.desa_jornada(conn, jornada, "1")
    LN.desa_classificacio_de_jugadors(
        conn,
        LN.llegeix_classificacio_de_jugadors(NACIONAL / "liga_nal_1_cjug_2627.pdf"),
        "1",
        "2026-2027",
    )
    assert {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in alienes} == abans


def test_la_classificacio_de_jugadors_es_reemplaca(conn) -> None:
    jugadors = LN.llegeix_classificacio_de_jugadors(NACIONAL / "liga_nal_1_cjug_2627.pdf")
    assert LN.desa_classificacio_de_jugadors(conn, jugadors, "1", "2026-2027") == 79
    LN.desa_classificacio_de_jugadors(conn, jugadors[:10], "1", "2026-2027")
    assert _files(conn)["nacional_jugadors"] == 10


def test_una_divisio_inventada_no_es_desa(conn, jornada) -> None:
    with pytest.raises(ValueError, match="Divisió desconeguda"):
        LN.desa_jornada(conn, jornada, "tercera")


def test_es_publica_i_es_retira_el_que_ja_no_hi_es(conn, jornada, tmp_path, monkeypatch) -> None:
    LN.desa_jornada(conn, jornada, "1")
    conn.close()
    magatzem: dict[str, list[dict]] = {
        "nacional_encontres": [
            # D'una lectura anterior de la mateixa temporada i divisió: ha de marxar.
            {
                "temporada": "2026-2027",
                "divisio": "1",
                "grup": "A",
                "jornada": 1,
                "ordre": 99,
                "local": "X",
                "visitant": "Y",
            },
            # D'una altra temporada: no es toca.
            {
                "temporada": "2025-2026",
                "divisio": "1",
                "grup": "A",
                "jornada": 1,
                "ordre": 1,
                "local": "X",
                "visitant": "Y",
            },
        ]
    }
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))

    counts = cloud_sync.publish_nacional(db_path=tmp_path / "t.db")

    assert counts["nacional_encontres"] == 8
    assert counts["nacional_partides"] == 32
    ordres = {
        (f["temporada"], f["ordre"]) for f in magatzem["nacional_encontres"] if f["grup"] == "A"
    }
    assert ("2026-2027", 99) not in ordres
    assert ("2025-2026", 1) in ordres


def test_sense_dades_locals_no_es_publica_ni_es_retira_res(tmp_path, monkeypatch) -> None:
    ensure_schema(tmp_path / "buida.db").close()
    magatzem = {"nacional_jugadors": [{"temporada": "2026-2027", "divisio": "1", "jugador": "X"}]}
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))

    assert cloud_sync.publish_nacional(db_path=tmp_path / "buida.db") == {}
    assert len(magatzem["nacional_jugadors"]) == 1
