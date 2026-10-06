"""La classificació final que la base local ja no té se'n va del núvol.

Quan dos torneigs s'intercanvien el número intern en reingerir-se, cap dels dos
deixa d'existir, i la poda dels torneigs desapareguts no hi veu res: la
classificació de l'un es queda penjada de l'altre. L'octubre del 2026 un jugador
sortia sisè a l'Open de Banda sense haver-hi jugat cap partida; era la seva fila
de l'Open de Lliure, que abans tenia aquell número.
"""

from __future__ import annotations

from fcbillar import cloud_sync
from fcbillar.db.migrations import ensure_schema
from tests.test_publish_lliga_retirada import ClientFals
from tests.test_publish_opens_en_joc import _torneig

BANDA, LLIURE = 3159, 3160


def _base(tmp_path):
    """Dos opens acabats; el jugador 424 només ha jugat el de lliure."""
    db = tmp_path / "t.db"
    c = ensure_schema(db)
    c.execute("INSERT INTO temporades (id, nom) VALUES (2, '2026-2027')")
    _torneig(c, BANDA, "OPEN BANDA GRANOLLERS", 2, [(1, "PRÈVIA"), (2, "FASE FINAL")])
    _torneig(c, LLIURE, "OPEN LLIURE PUNT D'ATAC", 2, [(1, "PRÈVIA"), (2, "FASE FINAL")])
    c.execute("INSERT INTO players (id, fcb_id, nom) VALUES (1, '424', 'PALLISA, JOSEP')")
    c.execute("INSERT INTO players (id, fcb_id, nom) VALUES (2, '900', 'ALTRE, PERE')")
    c.execute(
        "INSERT INTO torneig_participants (torneig_id, player_id, posicio) VALUES (?, 1, 6)",
        (LLIURE,),
    )
    c.execute(
        "INSERT INTO torneig_participants (torneig_id, player_id, posicio) VALUES (?, 2, 1)",
        (BANDA,),
    )
    c.commit()
    c.close()
    return db


def test_la_fila_que_va_quedar_sota_el_numero_d_un_altre_torneig_se_n_va(
    tmp_path, monkeypatch
) -> None:
    db = _base(tmp_path)
    magatzem: dict[str, list[dict]] = {
        "opens": [{"open_id": BANDA}, {"open_id": LLIURE}],
        # D'abans que els dos opens s'intercanviessin el número.
        "open_classifications": [{"open_id": BANDA, "player_fcb_id": "424", "posicio": 6}],
    }
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))

    counts = cloud_sync.publish_opens(db_path=db)

    queden = {(f["open_id"], f["player_fcb_id"]) for f in magatzem["open_classifications"]}
    assert queden == {(LLIURE, "424"), (BANDA, "900")}
    assert counts["classificacions_retirades"] == 1


def test_sense_cap_classificacio_local_no_es_retira_res(tmp_path, monkeypatch) -> None:
    """Una base local buida vol dir «no en sé res», no «no n'hi ha cap»."""
    db = tmp_path / "buida.db"
    ensure_schema(db).close()
    magatzem: dict[str, list[dict]] = {
        "open_classifications": [{"open_id": BANDA, "player_fcb_id": "424", "posicio": 6}]
    }
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))

    counts = cloud_sync.publish_opens(db_path=db)

    assert len(magatzem["open_classifications"]) == 1
    assert counts["classificacions_retirades"] == 0
