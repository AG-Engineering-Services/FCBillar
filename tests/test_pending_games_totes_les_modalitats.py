"""Les partides pendents i el rànquing provisional, a totes les modalitats amb rànquing.

`publish_pending_games` era un pilot de tres bandes (`modalitats=(1,)`). Les
partides de Lliure, Banda i Quadre de la temporada arribaven a `open_partides` i
a `lliga4m_partides`, però no a la fitxa del jugador ni al rànquing provisional,
que deia «0 amb partides noves» a quatre modalitats cada nit. Al núvol, les 646
files de `pending_games` eren totes de la modalitat 1.

La taula ja portava `modalitat_codi` i tots els qui la llegeixen filtren per
ell: no canvia de forma. El que es comprova aquí és que cada partida va a la
seva modalitat, que les de tres bandes surten exactament com abans, i que qui
no té fitxa segueix quedant fora —però ara es diu.
"""

from __future__ import annotations

import pytest

from fcbillar import cloud_sync
from fcbillar.db.migrations import ensure_schema
from tests.test_publish_lliga_retirada import ClientFals

#: codi de la federació -> nom, com a `modalitats`.
TRES_BANDES, LLIURE, QUADRE_47, BANDA, QUADRE_71 = 1, 2, 3, 4, 6


def _torneig(conn, tid: int, nom: str, temporada: int = 2) -> None:
    conn.execute(
        "INSERT INTO torneigs_individuals (torneig_id_extern, divisio_id_extern, nom, temporada_id) "
        "VALUES (?, ?, ?, ?)",
        (tid, tid * 2, nom, temporada),
    )


def _partida(conn, tid: int, j1: str, c1: int, j2: str, c2: int, ent: int, data: str) -> None:
    conn.execute(
        "INSERT INTO torneig_partides (torneig_id_extern, divisio_id_extern, fase_id, "
        "player1_nom, caramboles1, serie1, player2_nom, caramboles2, serie2, entrades, data) "
        "VALUES (?, ?, 1, ?, ?, 5, ?, ?, 4, ?, ?)",
        (tid, tid * 2, j1, c1, j2, c2, ent, data),
    )


def _de_lliga(conn, mod: int, j1: str, c1: int, j2: str, c2: int, ent: int) -> None:
    conn.execute(
        "INSERT INTO lliga_pending_partides (encontre_lliga_id, modalitat_codi, competicio, "
        "data, player1_nom, caramboles1, serie1, player2_nom, caramboles2, serie2, entrades) "
        "VALUES (900, ?, 'LLIGA', '2026-10-11', ?, ?, NULL, ?, ?, NULL, ?)",
        (mod, j1, c1, j2, c2, ent),
    )


@pytest.fixture
def entorn(tmp_path, monkeypatch):
    """Una temporada amb una mica de tot: campionats, un open, la lliga de 4 Modalitats.

    Quatre jugadors amb llicència, un amb fitxa de pedaç i un que no té fitxa.
    """
    db = tmp_path / "t.db"
    conn = ensure_schema(db)
    conn.execute("INSERT INTO temporades (id, nom) VALUES (1, '2025-2026')")
    conn.execute("INSERT INTO temporades (id, nom) VALUES (2, '2026-2027')")
    for pid, fcb, nom in (
        (1, "101", "ALBA, ANNA"),
        (2, "102", "BOSCH, BERNAT"),
        (3, "103", "COLL, CARLA"),
        (4, "104", "DURAN, DAVID"),
        (5, "name:ESTEVE, ENRIC", "ESTEVE, ENRIC"),
    ):
        conn.execute("INSERT INTO players (id, fcb_id, nom) VALUES (?,?,?)", (pid, fcb, nom))
    conn.execute(
        "INSERT INTO encontres_lliga (id, lliga_id, divisio_id, grup_id, jornada_id, data) "
        "VALUES (900, 39, 156, 355, 1, '2026-10-11')"
    )

    _torneig(conn, 216, "TRES BANDES INDIVIDUAL - HONOR")
    _torneig(conn, 217, "OPEN LLIURE PUNT D'ATAC")
    _torneig(conn, 218, "QUADRE 47/2 - HONOR")
    _torneig(conn, 219, "OPEN BANDA GRANOLLERS")
    _torneig(conn, 220, "BIATHLO")
    _torneig(conn, 195, "OPEN FEMENI TRES BANDES MATARO")
    _torneig(conn, 210, "QUADRE 71/2 - ÚNICA", temporada=1)  # de la temporada passada

    _partida(conn, 216, "ALBA, ANNA", 40, "BOSCH, BERNAT", 31, 38, "2026-10-03")
    _partida(conn, 217, "ALBA, ANNA", 200, "COLL, CARLA", 150, 12, "2026-09-05")
    _partida(conn, 218, "COLL, CARLA", 150, "DURAN, DAVID", 120, 15, "2026-10-03")
    _partida(conn, 219, "BOSCH, BERNAT", 80, "DURAN, DAVID", 61, 30, "2026-09-26")
    _partida(conn, 220, "ALBA, ANNA", 30, "BOSCH, BERNAT", 20, 25, "2026-10-17")
    _partida(conn, 195, "ALBA, ANNA", 25, "COLL, CARLA", 20, 40, "2026-09-12")
    _partida(conn, 210, "ALBA, ANNA", 100, "DURAN, DAVID", 90, 9, "2026-03-29")
    # Una de pedaç i una d'algú que no té fitxa de cap mena.
    _partida(conn, 218, "COLL, CARLA", 150, "ESTEVE, ENRIC", 90, 14, "2026-10-03")
    _partida(conn, 218, "DURAN, DAVID", 150, "FONT, FERRAN", 80, 13, "2026-10-03")

    # Un encontre de la Lliga de 4 Modalitats: una partida de cada.
    _de_lliga(conn, TRES_BANDES, "ALBA, ANNA", 30, "BOSCH, BERNAT", 22, 40)
    _de_lliga(conn, LLIURE, "COLL, CARLA", 150, "DURAN, DAVID", 97, 10)
    _de_lliga(conn, QUADRE_47, "ALBA, ANNA", 100, "COLL, CARLA", 88, 11)
    _de_lliga(conn, BANDA, "BOSCH, BERNAT", 60, "DURAN, DAVID", 44, 28)
    conn.commit()
    conn.close()

    magatzem: dict[str, list[dict]] = {"open_live": []}
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))
    return db, magatzem


def _de(magatzem, mod: int) -> list[dict]:
    return [f for f in magatzem["pending_games"] if f["modalitat_codi"] == mod]


def test_per_defecte_es_publiquen_les_cinc_modalitats_amb_ranquing() -> None:
    assert cloud_sync.MODALITATS_AMB_RANQUING == (1, 2, 3, 4, 6)


def test_cada_partida_va_a_la_modalitat_que_diu_el_seu_torneig(entorn) -> None:
    db, magatzem = entorn

    cloud_sync.publish_pending_games(db_path=db)

    def competicions(mod: int) -> set[str]:
        return {f["competicio"] for f in _de(magatzem, mod)}

    assert competicions(TRES_BANDES) == {"TRES BANDES INDIVIDUAL - HONOR", "LLIGA"}
    assert competicions(LLIURE) == {"OPEN LLIURE PUNT D'ATAC", "LLIGA"}
    assert competicions(QUADRE_47) == {"QUADRE 47/2 - HONOR", "LLIGA"}
    assert competicions(BANDA) == {"OPEN BANDA GRANOLLERS", "LLIGA"}
    # El Quadre 71/2 és de la temporada passada: no és pendent de res.
    assert _de(magatzem, QUADRE_71) == []


def test_una_fila_per_jugador_i_partida_amb_la_mateixa_forma_de_sempre(entorn) -> None:
    db, magatzem = entorn

    cloud_sync.publish_pending_games(db_path=db)

    de_l_open = [f for f in _de(magatzem, LLIURE) if f["font"] == "open"]
    assert {f["player_fcb_id"] for f in de_l_open} == {"101", "103"}
    de_l_anna = next(f for f in de_l_open if f["player_fcb_id"] == "101")
    assert de_l_anna == {
        "player_fcb_id": "101",
        "modalitat_codi": LLIURE,
        "signatura": de_l_anna["signatura"],
        "competicio": "OPEN LLIURE PUNT D'ATAC",
        "font": "open",
        "opponent_nom": "COLL, CARLA",
        "opponent_fcb_id": "103",
        "caramboles": 200,
        "caramboles_opp": 150,
        "entrades": 12,
        "serie": 5,
        "captured_at": None,
        "data": "2026-09-05",
    }


def test_les_de_tres_bandes_son_les_mateixes_que_amb_el_pilot(entorn) -> None:
    """Publicar les altres modalitats no toca ni una fila de la primera."""
    db, magatzem = entorn

    cloud_sync.publish_pending_games(db_path=db, modalitats=(1,))
    nomes_3b = sorted(magatzem["pending_games"], key=lambda f: (f["player_fcb_id"], f["signatura"]))
    assert {f["modalitat_codi"] for f in nomes_3b} == {1}

    magatzem["pending_games"] = []
    cloud_sync.publish_pending_games(db_path=db)

    assert sorted(_de(magatzem, 1), key=lambda f: (f["player_fcb_id"], f["signatura"])) == nomes_3b


def test_un_torneig_sense_modalitat_amb_ranquing_no_entra_enlloc(entorn) -> None:
    """El biatló no té rànquing de mitjana; i els femenins, com fins ara, tampoc."""
    db, magatzem = entorn

    cloud_sync.publish_pending_games(db_path=db)

    competicions = {f["competicio"] for f in magatzem["pending_games"]}
    assert "BIATHLO" not in competicions
    assert not any("FEMENI" in c for c in competicions)


def test_el_que_el_ranquing_ja_compta_deixa_de_ser_pendent(entorn) -> None:
    """La dedup contra `games` es fa dins de cada modalitat."""
    db, magatzem = entorn
    conn = ensure_schema(db)
    lliure = conn.execute("SELECT id FROM modalitats WHERE codi_fcb = 2").fetchone()[0]
    conn.execute(
        "INSERT INTO games (id, data_partida, modalitat_id, player1_id, player2_id, "
        "caramboles1, caramboles2, entrades) VALUES ('g1', '2026-09-05', ?, 1, 3, 200, 150, 12)",
        (lliure,),
    )
    conn.commit()
    conn.close()

    cloud_sync.publish_pending_games(db_path=db)

    assert {f["font"] for f in _de(magatzem, LLIURE)} == {"lliga"}, "l'open ja és a `games`"
    assert any(f["font"] == "open" for f in _de(magatzem, QUADRE_47)), "les altres no es toquen"


def test_qui_no_te_fitxa_no_hi_surt_pero_es_compta(entorn) -> None:
    """Ni la fitxa de pedaç ni el nom que no casa amb ningú tenen on penjar-se."""
    db, magatzem = entorn
    avisos: list[str] = []

    res = cloud_sync.publish_pending_games(db_path=db, on_progress=lambda _n, m: avisos.append(m))

    amos = {f["player_fcb_id"] for f in magatzem["pending_games"]}
    assert amos == {"101", "102", "103", "104"}
    assert res["pending_sense_fitxa"] == 2
    assert any("2 partides d'algú sense fitxa" in a for a in avisos)
    # La partida no es perd per al rival, que la té a la seva fitxa amb el nom.
    del_david = [f for f in _de(magatzem, QUADRE_47) if f["player_fcb_id"] == "104"]
    assert "FONT, FERRAN" in {f["opponent_nom"] for f in del_david}


def test_el_ranquing_provisional_es_mou_a_les_altres_modalitats(entorn) -> None:
    """Abans deia «0 amb partides noves» a tot el que no fos tres bandes."""
    db, magatzem = entorn
    conn = ensure_schema(db)
    quadre = conn.execute("SELECT id FROM modalitats WHERE codi_fcb = 3").fetchone()[0]
    conn.execute(
        "INSERT INTO rankings (id, num_seq, modalitat_id, url, format_url, data_pub, "
        "any_pub, mes_pub) VALUES (1, 126, ?, 'u', 'llistat', '2026-10-02', 2026, 10)",
        (quadre,),
    )
    for pid, posicio, mitjana in ((3, 1, 9.0), (4, 2, 8.0)):
        conn.execute(
            "INSERT INTO ranking_entries (ranking_id, player_id, posicio, mitjana_general) "
            "VALUES (1, ?, ?, ?)",
            (pid, posicio, mitjana),
        )
    conn.commit()
    conn.close()

    cloud_sync.publish_pending_games(db_path=db)
    cloud_sync.publish_provisional_ranking(db_path=db, modalitats=(QUADRE_47,))

    files = {f["player_fcb_id"]: f for f in magatzem["ranking_provisional"]}
    assert files["103"]["partides_post"] == 3
    assert files["103"]["mitjana_provisional"] is not None
    assert files["104"]["partides_post"] == 2
