"""La fase d'una partida es tradueix dins del seu torneig, no a cegues.

`torneig_partides.fase_id` porta dues menes de número. Als torneigs ingerits del
web nou és l'id intern de `torneig_fases`, i al núvol s'hi publica l'extern, que
és el que fan servir `open_fases` i `open_grups`. Als torneigs antics és un
número del web vell que no és a `torneig_fases`, i es publica tal qual.

Traduint sense mirar de quin torneig és la fase, un número antic casava amb
l'id intern d'una fase d'un altre torneig. Va sortir en ingerir l'Open de Mataró
pel seu id: les seves 8 fases noves van rebre ids interns que ja feien servir,
com a número antic, 58 partides de quatre torneigs de 2016 i 2023.
"""

from __future__ import annotations

from fcbillar import cloud_sync
from fcbillar.db.migrations import ensure_schema
from tests.test_publish_lliga_retirada import ClientFals

ANTIC, NOU = 48, 2831


def test_un_numero_antic_no_es_confon_amb_la_fase_d_un_altre_torneig(tmp_path, monkeypatch) -> None:
    db = tmp_path / "t.db"
    conn = ensure_schema(db)
    conn.execute("INSERT INTO temporades (id, nom) VALUES (1, '2025-2026')")
    for tid, extern, divisio in ((ANTIC, 154, 340), (NOU, 211, 447)):
        conn.execute(
            "INSERT INTO torneigs_individuals (id, torneig_id_extern, divisio_id_extern, "
            "nom, temporada_id) VALUES (?, ?, ?, 'OPEN', 1)",
            (tid, extern, divisio),
        )
    # La fase del torneig nou rep l'id intern 7, i el seu extern és 1185.
    conn.execute(
        "INSERT INTO torneig_fases (id, torneig_id, fase_id_extern, nom, tipus, ordre) "
        "VALUES (7, ?, 1185, 'FINAL', 'ko', 1)",
        (NOU,),
    )
    # I el torneig antic té una partida amb el 7 del web vell.
    for extern, divisio in ((154, 340), (211, 447)):
        conn.execute(
            "INSERT INTO torneig_partides (torneig_id_extern, divisio_id_extern, fase_id, "
            "player1_nom, caramboles1, player2_nom, caramboles2, entrades) "
            "VALUES (?, ?, 7, 'ROCA, ANNA', 30, 'PUIG, BERNAT', 20, 25)",
            (extern, divisio),
        )
    conn.commit()
    conn.close()
    magatzem: dict[str, list[dict]] = {}
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))

    cloud_sync.publish_open_partides(db_path=db)

    fases = {f["open_id"]: f["fase_id"] for f in magatzem["open_partides"]}
    assert fases == {ANTIC: 7, NOU: 1185}
