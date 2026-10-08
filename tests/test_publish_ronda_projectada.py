"""La ronda projectada es publica, i el que hi havia de vell se'n va.

`publish_ronda_projectada` existia, tenia tests i s'importava a `publish-cloud`,
però no la cridava ningú: la ingesta calculava la projecció cada nit i al núvol
no hi arribava mai. L'octubre de 2026 hi havia 36 files de la PRÈVIA de dos
campionats que ja l'havien jugada, i les 22 de la FINAL que tocava ensenyar
només eren a la base local.
"""

from __future__ import annotations

import sqlite3

import pytest
from typer.testing import CliRunner

from fcbillar import cli, cloud_sync
from fcbillar.db.migrations import ensure_schema
from tests.test_publish_lliga_retirada import ClientFals

PRIMERA, SEGONA = 3161, 3162


def _fase(conn: sqlite3.Connection, torneig: int, extern: int, nom: str, ordre: int) -> int:
    cur = conn.execute(
        "INSERT INTO torneig_fases (torneig_id, fase_id_extern, nom, tipus, ordre) "
        "VALUES (?, ?, ?, 'grups', ?)",
        (torneig, extern, nom, ordre),
    )
    fase = int(cur.lastrowid or 0)
    conn.execute(
        "INSERT INTO torneig_fase_grups (fase_id, grup_nom, jugador_nom, posicio_grup, "
        "punts, mitjana, serie_major) VALUES (?, 'Grup A', 'ROCA, ANNA', 1, 4, 0.8, 5)",
        (fase,),
    )
    return fase


@pytest.fixture
def entorn(tmp_path, monkeypatch):
    """Dos campionats que ja han jugat la prèvia i tenen la FINAL projectada."""
    db = tmp_path / "t.db"
    conn = ensure_schema(db)
    conn.execute("INSERT INTO temporades (id, nom) VALUES (1, '2026-2027')")
    for tid, div in ((PRIMERA, 455), (SEGONA, 456)):
        conn.execute(
            "INSERT INTO torneigs_individuals (id, torneig_id_extern, divisio_id_extern, "
            "nom, temporada_id) VALUES (?, 216, ?, 'TRES BANDES INDIVIDUAL', 1)",
            (tid, div),
        )
        previa = _fase(conn, tid, div + 400, "PRÈVIA", 1)
        for i, jugador in enumerate(("ROCA, ANNA", "PUIG, BERNAT"), start=1):
            conn.execute(
                "INSERT INTO torneig_ronda_projectada (torneig_id, fase_origen_id, ronda, "
                "jugador_nom, posicio, bombo, grup_projectat, mida_grup) "
                "VALUES (?, ?, 'FINAL', ?, ?, ?, 'A', 4)",
                (tid, previa, jugador, i, i),
            )
    conn.commit()
    conn.close()

    # El que hi havia al núvol: la PRÈVIA projectada de quan encara no s'havia
    # jugat, i una fila sota un número de torneig que ja no és de ningú.
    magatzem: dict[str, list[dict]] = {
        "open_ronda_projectada": [
            {"open_id": tid, "ronda": "PRÈVIA", "jugador": j, "bombo": 1}
            for tid in (PRIMERA, SEGONA)
            for j in ("VELL, CARLES", "ROCA, ANNA")
        ]
        + [{"open_id": 2831, "ronda": "PRÈVIA", "jugador": "ORFE, DANIEL", "bombo": 2}]
    }
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))
    return db, magatzem


def test_puja_la_projeccio_local_i_retira_la_vella(entorn) -> None:
    db, magatzem = entorn

    counts = cloud_sync.publish_ronda_projectada(db_path=db)

    queden = {(f["open_id"], f["ronda"], f["jugador"]) for f in magatzem["open_ronda_projectada"]}
    assert queden == {
        (tid, "FINAL", jugador)
        for tid in (PRIMERA, SEGONA)
        for jugador in ("ROCA, ANNA", "PUIG, BERNAT")
    }
    assert counts["open_ronda_projectada"] == 4
    # Les quatre de la PRÈVIA ja jugada i la del torneig que no existeix.
    assert counts["ronda_projectada_retirades"] == 5


# ---------------- i que `publish-cloud` la cridi ----------------


@pytest.fixture
def publicadors(monkeypatch) -> list[str]:
    """Tots els `publish_*` de `cloud_sync` canviats per un que només s'apunta."""
    cridats: list[str] = []

    def _fals(nom: str):
        def _publica(*_a, **_k) -> dict[str, int]:
            cridats.append(nom)
            return {nom: 1}

        return _publica

    for nom in dir(cloud_sync):
        if nom.startswith("publish_"):
            monkeypatch.setattr(cloud_sync, nom, _fals(nom))
    return cridats


def test_publish_cloud_publica_la_ronda_projectada(publicadors) -> None:
    res = CliRunner().invoke(cli.app, ["publish-cloud"])

    assert res.exit_code == 0, res.output
    assert "publish_ronda_projectada" in publicadors
    # Després dels grups de debò: la projecció es retira mirant quines rondes ja
    # tenen grups publicats.
    assert publicadors.index("publish_ronda_projectada") > publicadors.index("publish_open_grups")


def test_si_la_projeccio_falla_la_resta_es_publica(publicadors, monkeypatch) -> None:
    def _peta(*_a, **_k):
        raise RuntimeError("connexió refusada")

    monkeypatch.setattr(cloud_sync, "publish_ronda_projectada", _peta)

    res = CliRunner().invoke(cli.app, ["publish-cloud"])

    assert res.exit_code == 0, res.output
    assert "Ronda projectada NO publicada" in res.output
    # El que ve darrere s'ha publicat igualment.
    assert "publish_open_ranking" in publicadors
    assert "publish_calendari" in publicadors
