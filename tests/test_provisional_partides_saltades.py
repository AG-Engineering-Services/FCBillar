"""La projecció del proper rànquing no ressuscita una partida que la federació ha saltat.

La finestra oficial és «les últimes N que computen», i n'hi ha que la federació es
deixa: AMETLLER CONGOST té la del 21/03/2026 fora de la seva —que recula fins a
l'abril i el maig de 2025 per completar les quinze— i ha tingut dos rànquings per
comptar-la, l'1 i el 27 de juliol de 2026. La seva mitjana oficial no s'ha mogut en
cap dels dos.

Agafant les més recents de `games` sense mirar res, la projecció la tornava a posar i
la fitxa la marcava «proper», com si hagués d'entrar al rànquing que ve. No hi
entrarà: si la federació l'hagués de comptar ja ho hauria fet. I la mitjana
projectada sortia esbiaixada: la seva era 0,809 amb la partida saltada i 0,8195
sense.
"""

from __future__ import annotations

import pytest

from fcbillar import cloud_sync
from fcbillar.db.migrations import ensure_schema
from tests.test_publish_lliga_retirada import ClientFals

#: La finestra d'aquest rànquing de mentida: tres partides, no quinze.
FINESTRA = 3


@pytest.fixture
def entorn(tmp_path, monkeypatch):
    """Un rànquing publicat el 2026-07-27 amb una finestra de tres partides.

    El jugador en té quatre de jugades abans del rànquing: tres que la federació
    compta i una del 21/03 que es va saltar. I una de pendent, de setembre.
    """
    db = tmp_path / "t.db"
    conn = ensure_schema(db)
    mod_id = conn.execute("SELECT id FROM modalitats WHERE codi_fcb = 1").fetchone()[0]
    for pid, fcb, nom in ((1, "591", "AMETLLER CONGOST, LLUIS"), (2, "999", "UN RIVAL")):
        conn.execute("INSERT INTO players (id, fcb_id, nom) VALUES (?,?,?)", (pid, fcb, nom))
    conn.execute(
        "INSERT INTO rankings (id, num_seq, modalitat_id, url, format_url, data_pub, "
        "any_pub, mes_pub) VALUES (1, 124, ?, 'u', 'llistat', '2026-07-27', 2026, 8)",
        (mod_id,),
    )
    conn.execute(
        "INSERT INTO ranking_entries (ranking_id, player_id, posicio, mitjana_general) "
        "VALUES (1, 1, 36, 0.7)"
    )

    # (id, data, caramboles propis, entrades) — el rival sempre en fa 10.
    partides = [
        ("g-vella-1", "2025-04-12", 35, 50),
        ("g-vella-2", "2025-05-03", 35, 50),
        ("g-bona", "2026-03-28", 40, 40),
        ("g-saltada", "2026-03-21", 10, 50),  # la que la federació no compta
    ]
    for gid, data, car, ent in partides:
        conn.execute(
            "INSERT INTO games (id, data_partida, modalitat_id, player1_id, player2_id, "
            "caramboles1, caramboles2, entrades) VALUES (?,?,?,1,2,?,10,?)",
            (gid, data, mod_id, car, ent),
        )
    # La finestra oficial: les dues velles i la bona. La del 21/03 no hi és.
    for gid in ("g-vella-1", "g-vella-2", "g-bona"):
        conn.execute(
            "INSERT INTO ranking_game_links (ranking_id, game_id, player_id_origen) "
            "VALUES (1, ?, 1)",
            (gid,),
        )
    conn.commit()
    conn.close()

    magatzem: dict[str, list[dict]] = {
        "pending_games": [
            {
                "player_fcb_id": "591",
                "modalitat_codi": 1,
                "caramboles": 35,
                "caramboles_opp": 20,
                "entrades": 35,
            }
        ]
    }
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))
    return db, magatzem


def _fila(magatzem) -> dict:
    files = [f for f in magatzem["ranking_provisional"] if f["player_fcb_id"] == "591"]
    assert files, "no s'ha publicat cap fila del jugador"
    return files[-1]


def test_la_partida_saltada_no_entra_a_la_projeccio(entorn) -> None:
    db, magatzem = entorn
    cloud_sync.publish_provisional_ranking(db_path=db, modalitats=(1,))

    f = _fila(magatzem)
    assert "g-saltada" not in (f["window_game_ids"] or []), (
        "la federació ja l'ha vista dues vegades i no l'ha comptada"
    )
    # La finestra: la pendent i les dues MES RECENTS de les que la federacio compta.
    assert set(f["window_game_ids"]) == {"g-bona", "g-vella-2"}
    assert f["partides_post"] == 1
    # 35/35 (pendent) + 40/40 + 35/50 = 110 caramboles en 125 entrades.
    assert round(f["mitjana_provisional"], 4) == round(110 / 125, 4)


def test_les_que_la_federacio_compta_si_que_hi_son(entorn) -> None:
    """El filtre no s'endú res del que la federació compta: només el que va saltar."""
    db, magatzem = entorn
    cloud_sync.publish_provisional_ranking(db_path=db, modalitats=(1,))

    f = _fila(magatzem)
    assert set(f["current_game_ids"]) == {"g-vella-1", "g-vella-2", "g-bona"}
    assert f["proj_won"] + f["proj_lost"] + f["proj_tie"] == FINESTRA
