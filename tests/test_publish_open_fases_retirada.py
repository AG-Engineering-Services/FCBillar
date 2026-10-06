"""Les fases que la base local ja no té se'n van del núvol.

L'`open_id` és l'identificador intern d'un torneig i no és estable: en tornar a
ingerir-lo en pot rebre un altre, i el que tenia abans passa a ser d'un altre
torneig. `publish_open_fases` només feia un upsert, o sigui que les fases
publicades amb el número vell es quedaven al núvol penjades del torneig que ara
porta aquell número. L'octubre del 2026 la pre-prèvia de 1a sortia també dins de
2a, i la de 2a dins d'Honor.

El mateix passava amb la ronda projectada, per un altre camí: quan la base local
es queda sense cap projecció no es retira res —una taula buida també pot voler
dir que no s'ha pogut calcular—, i la d'una ronda que la federació ja ha publicat
no marxava mai.
"""

from __future__ import annotations

import sqlite3

import pytest

from fcbillar import cloud_sync
from fcbillar.db.migrations import ensure_schema
from tests.test_publish_lliga_retirada import ClientFals

#: Els dos campionats tal com queden després de la renumeració.
PRIMERA, SEGONA = 3161, 3162


def _fase(conn: sqlite3.Connection, torneig: int, extern: int, nom: str, ordre: int) -> int:
    cur = conn.execute(
        "INSERT INTO torneig_fases (torneig_id, fase_id_extern, nom, tipus, ordre) "
        "VALUES (?, ?, ?, 'grups', ?)",
        (torneig, extern, nom, ordre),
    )
    return int(cur.lastrowid or 0)


def _al_grup(conn: sqlite3.Connection, fase: int, jugador: str, posicio: int) -> None:
    conn.execute(
        "INSERT INTO torneig_fase_grups (fase_id, grup_nom, jugador_nom, posicio_grup, "
        "punts, mitjana, serie_major) VALUES (?, 'Grup A', ?, ?, 4, 0.8, 5)",
        (fase, jugador, posicio),
    )


@pytest.fixture
def entorn(tmp_path, monkeypatch):
    """1a ha jugat pre-prèvia i prèvia; 2a, només la pre-prèvia."""
    db = tmp_path / "t.db"
    conn = ensure_schema(db)
    conn.execute("INSERT INTO temporades (id, nom) VALUES (1, '2026-2027')")
    for tid, div, nom in ((PRIMERA, 455, "1A"), (SEGONA, 456, "2A")):
        conn.execute(
            "INSERT INTO torneigs_individuals (id, torneig_id_extern, divisio_id_extern, "
            "nom, temporada_id) VALUES (?, 216, ?, ?, 1)",
            (tid, div, f"TRES BANDES INDIVIDUAL - {nom}"),
        )
    pre_1a = _fase(conn, PRIMERA, 809, "PRE-PRÈVIA", 1)
    previa_1a = _fase(conn, PRIMERA, 815, "PRÈVIA", 2)
    pre_2a = _fase(conn, SEGONA, 810, "PRE-PRÈVIA", 1)
    _al_grup(conn, pre_1a, "ROCA, ANNA", 1)
    _al_grup(conn, previa_1a, "ROCA, ANNA", 1)
    _al_grup(conn, pre_2a, "PUIG, BERNAT", 1)
    conn.commit()
    conn.close()

    magatzem: dict[str, list[dict]] = {}
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))
    return db, magatzem


def _fases(magatzem: dict[str, list[dict]]) -> set[tuple[int, int]]:
    return {(f["open_id"], f["fase_id"]) for f in magatzem.get("open_fases", [])}


def test_la_fase_d_un_numero_vell_se_n_va(entorn) -> None:
    db, magatzem = entorn
    # El que va deixar la publicació d'abans de renumerar: la pre-prèvia de 1a
    # (809) sota el número que ara és de 2a, amb el seu rànquing.
    magatzem["open_fases"] = [
        {"open_id": SEGONA, "fase_id": 809, "nom": "PRE-PRÈVIA", "tipus": "grups", "ordre": 1}
    ]
    magatzem["open_fase_ranquing"] = [
        {"open_id": SEGONA, "fase_id": 809, "jugador": "ROCA, ANNA", "posicio": 1}
    ]

    counts = cloud_sync.publish_open_fases(db_path=db)

    assert _fases(magatzem) == {(PRIMERA, 809), (PRIMERA, 815), (SEGONA, 810)}
    assert counts["open_fases_retirades"] == 1


def test_un_jugador_que_ja_no_es_al_grup_se_n_va_del_ranquing(entorn) -> None:
    db, magatzem = entorn
    magatzem["open_fase_ranquing"] = [
        {"open_id": SEGONA, "fase_id": 810, "jugador": "VELL, CARLES", "posicio": 2}
    ]

    counts = cloud_sync.publish_open_fases(db_path=db)

    de_segona = {f["jugador"] for f in magatzem["open_fase_ranquing"] if f["open_id"] == SEGONA}
    assert de_segona == {"PUIG, BERNAT"}
    assert counts["open_fase_ranquing_retirades"] == 1


def test_sense_cap_fase_local_no_es_retira_res(tmp_path, monkeypatch) -> None:
    """Una base local buida vol dir «no en sé res», no «no n'hi ha cap»."""
    db = tmp_path / "buida.db"
    ensure_schema(db).close()
    magatzem = {
        "open_fases": [
            {"open_id": PRIMERA, "fase_id": 809, "nom": "PRE-PRÈVIA", "tipus": "grups", "ordre": 1}
        ]
    }
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))

    counts = cloud_sync.publish_open_fases(db_path=db)

    assert _fases(magatzem) == {(PRIMERA, 809)}
    assert counts["open_fases_retirades"] == 0


def test_la_projeccio_d_una_ronda_ja_publicada_se_n_va_encara_que_no_es_projecti_res(
    entorn,
) -> None:
    db, magatzem = entorn
    magatzem["open_ronda_projectada"] = [
        # 1a ja té la prèvia publicada: aquesta projecció sobra.
        {"open_id": PRIMERA, "ronda": "PRÈVIA", "jugador": "ROCA, ANNA", "bombo": 1},
        # 2a encara no: aquesta s'ha de quedar.
        {"open_id": SEGONA, "ronda": "PRÈVIA", "jugador": "PUIG, BERNAT", "bombo": 1},
    ]

    counts = cloud_sync.publish_ronda_projectada(db_path=db)

    queden = {(f["open_id"], f["jugador"]) for f in magatzem["open_ronda_projectada"]}
    assert queden == {(SEGONA, "PUIG, BERNAT")}
    assert counts["ronda_projectada_retirades"] == 1
