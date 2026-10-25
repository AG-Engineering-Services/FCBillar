"""Les temporades passades de lliga passen soles a l'històric.

Les taules en viu es guarden totes les temporades, però el palmarès i el
selector de temporades llegeixen `lliga_standings_hist`, que fins ara només
s'omplia amb `arxiva-lliga-en-viu` a mà. Si ningú se'n recordava, la temporada
no hi era.
"""

from __future__ import annotations

import sqlite3

import pytest

from fcbillar import cloud_sync
from fcbillar.db.migrations import ensure_schema
from tests.test_publish_lliga_retirada import ClientFals


def _encontre(conn: sqlite3.Connection, lliga_id: int, data: str, ext: int) -> None:
    conn.execute(
        """
        INSERT INTO encontres_lliga
            (lliga_id, divisio_id, grup_id, jornada_id, encontre_id_extern, data)
        VALUES (?, 1, 1, 1, ?, ?)
        """,
        (lliga_id, ext, data),
    )


@pytest.fixture
def entorn(tmp_path, monkeypatch):
    """La 2025-26 (lliga 36) encara a les taules en viu, al costat de la 2026-27 (38)."""
    db = tmp_path / "t.db"
    conn = ensure_schema(db)
    _encontre(conn, 36, "2025-10-04", 1)
    _encontre(conn, 38, "2026-10-03", 2)
    conn.commit()
    conn.close()
    magatzem: dict[str, list[dict]] = {
        "lliga_groups": [
            {
                "lliga_id": 36,
                "divisio_id": 148,
                "grup_id": 333,
                "divisio_nom": "HONOR",
                "grup_nom": "FINAL HONOR",
            },
            {
                "lliga_id": 38,
                "divisio_id": 159,
                "grup_id": 343,
                "divisio_nom": "HONOR",
                "grup_nom": "GRUP A",
            },
        ],
        "lliga_standings": [
            {
                "lliga_id": 36,
                "divisio_id": 148,
                "grup_id": 333,
                "posicio": 1,
                "equip": "C.B.MATARÓ A",
                "punts": 36,
                "pf": 36,
            },
            {
                "lliga_id": 38,
                "divisio_id": 159,
                "grup_id": 343,
                "posicio": 1,
                "equip": "C.B.LLEIDA A",
                "punts": 3,
                "pf": 3,
            },
        ],
        "lliga_standings_hist": [],
    }
    sb = ClientFals(magatzem)
    return db, sb, magatzem


def _historic(db) -> list[tuple]:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT temporada, lliga, divisio, grup, posicio, equip FROM lliga_standings_hist"
        ).fetchall()
    finally:
        conn.close()


def test_arxiva_la_temporada_passada_i_no_la_d_ara(entorn) -> None:
    db, sb, _ = entorn
    n = cloud_sync.arxiva_lligues_passades(
        sb, db, 38, lambda *_: None, taules=cloud_sync._TAULES_3B
    )
    assert n == 1
    assert _historic(db) == [
        ("2025-2026", "LLIGA CATALANA TRES BANDES", "HONOR", "FINAL HONOR", 1, "C.B.MATARÓ A")
    ]


def test_no_la_torna_a_escriure(entorn) -> None:
    db, sb, _ = entorn
    for _ in range(2):
        cloud_sync.arxiva_lligues_passades(
            sb, db, 38, lambda *_: None, taules=cloud_sync._TAULES_3B
        )
    assert len(_historic(db)) == 1


def test_no_trepitja_la_que_ja_es_al_nuvol(entorn) -> None:
    """Una temporada importada des d'un altre PC és al núvol i no a la BD local."""
    db, sb, magatzem = entorn
    magatzem["lliga_standings_hist"].append(
        {"temporada": "2025-2026", "lliga": "LLIGA CATALANA TRES BANDES"}
    )
    n = cloud_sync.arxiva_lligues_passades(
        sb, db, 38, lambda *_: None, taules=cloud_sync._TAULES_3B
    )
    assert n == 0
    assert _historic(db) == []


def test_un_grup_sense_nom_no_s_arxiva_i_no_atura_res(entorn) -> None:
    db, sb, magatzem = entorn
    magatzem["lliga_groups"][0]["grup_nom"] = None
    avisos: list[str] = []
    n = cloud_sync.arxiva_lligues_passades(
        sb, db, 38, lambda nivell, msg: avisos.append(msg), taules=cloud_sync._TAULES_3B
    )
    assert n == 0
    assert _historic(db) == []
    assert any("no sé com es diu el grup" in a for a in avisos)


def test_sense_temporada_coneguda_no_s_arxiva(entorn) -> None:
    db, sb, magatzem = entorn
    magatzem["lliga_standings"].append({"lliga_id": 34, "divisio_id": 1, "grup_id": 1})
    avisos: list[str] = []
    cloud_sync.arxiva_lligues_passades(
        sb, db, 38, lambda nivell, msg: avisos.append(msg), taules=cloud_sync._TAULES_3B
    )
    assert any("lliga 34" in a for a in avisos)
    assert {f[0] for f in _historic(db)} == {"2025-2026"}


def test_la_comanda_troba_la_lliga_per_la_temporada(entorn, tmp_path, monkeypatch) -> None:
    """Amb dues temporades a les taules en viu, abans les arxivava barrejades."""
    from typer.testing import CliRunner

    from fcbillar import cli
    from fcbillar.config import Settings

    db, sb, _ = entorn
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(db_path=db, cache_dir=tmp_path))
    monkeypatch.setattr(cloud_sync, "get_client", lambda: sb)

    sec = CliRunner().invoke(cli.app, ["arxiva-lliga-en-viu", "--temporada", "2025-2026"])
    assert sec.exit_code == 0, sec.output
    assert _historic(db) == []

    fet = CliRunner().invoke(
        cli.app, ["arxiva-lliga-en-viu", "--temporada", "2025-2026", "--aplica"]
    )
    assert fet.exit_code == 0, fet.output
    assert [f[5] for f in _historic(db)] == ["C.B.MATARÓ A"]
