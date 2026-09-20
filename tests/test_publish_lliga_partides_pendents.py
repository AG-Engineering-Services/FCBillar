"""Les partides d'un encontre han de sortir abans que el rànquing les publiqui.

La ingesta de lliga no desa a `games` una partida que el rànquing encara no ha
publicat: deixa que l'autoritat sigui el rànquing i mentrestant l'apunta a
`lliga_pending_partides`. El rànquing surt un cop al mes.

Conseqüència que es va cobrar la temporada 26/27: entre la jornada i el rànquing
següent no hi havia CAP fila per publicar, i el web ensenyava el resultat de
l'encontre i res més. Les 28 partides de la primera jornada no hi arribaven de cap
manera.

Ara es publiquen les dues fonts, amb dedup per signatura: quan el rànquing
publica la partida, la fila pendent deixa d'afegir-s'hi i no en surten dues.
"""

from __future__ import annotations

import sqlite3

import pytest

from fcbillar import cloud_sync
from fcbillar.db.migrations import ensure_schema
from tests.test_publish_lliga_retirada import ClientFals


@pytest.fixture
def entorn(tmp_path, monkeypatch):
    """Un encontre jugat de la lliga 38 amb quatre partides a l'acta."""
    db = tmp_path / "t.db"
    conn = ensure_schema(db)
    conn.execute("INSERT INTO temporades (id, nom) VALUES (1, '2026-2027')")
    # Les modalitats les sembra l'esquema; aquí només cal saber quin id té la de
    # tres bandes per penjar-hi el `game` del segon test.
    mod_3b = conn.execute("SELECT id FROM modalitats WHERE codi_fcb = 1").fetchone()[0]
    for i, nom in enumerate(("C.B.BANYOLES", "B.C.GRANOLLERS"), start=1):
        conn.execute("INSERT INTO clubs (id, fcb_id, nom) VALUES (?,?,?)", (i, nom, nom))
        conn.execute("INSERT INTO equips (id, club_id, lletra) VALUES (?,?,'A')", (i, i))
    conn.execute(
        """
        INSERT INTO encontres_lliga
            (id, lliga_id, divisio_id, grup_id, jornada_id, encontre_id_extern, temporada_id,
             equip_local_id, equip_visitant_id, p_match_local, p_match_visitant, jornada_num)
        VALUES (500, 38, 159, 343, 2790, 11656, 1, 1, 2, 0, 3, 1)
        """
    )
    for j1, c1, j2, c2, ent in [
        ("SÁNCHEZ MARTÍNEZ, PASCUAL", 27, "HERNÁNDEZ PARRA, ANTONI", 39, 50),
        ("GASCÓN REYES, RAFAEL", 37, "ESPINASA SÁNCHEZ, JOAN", 40, 43),
        ("PASTOR RIVAS, MANUEL", 20, "MAS CANADELL, CÉSAR", 40, 39),
        ("MEGIAS NAVAS, MATEU", 23, "NAVARRO CARMONA, JOAN ANT.", 40, 35),
    ]:
        conn.execute(
            """INSERT INTO lliga_pending_partides
               (encontre_lliga_id, modalitat_codi, competicio, data, player1_nom,
                caramboles1, serie1, player2_nom, caramboles2, serie2, entrades)
               VALUES (500, 1, 'LLIGA', '2026-09-26', ?, ?, NULL, ?, ?, NULL, ?)""",
            (j1, c1, j2, c2, ent),
        )
    conn.commit()
    conn.close()

    magatzem: dict[str, list[dict]] = {}
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))
    monkeypatch.setattr(cloud_sync, "LLIGA_3B_ID", 38)
    return db, magatzem, mod_3b


def test_les_partides_pendents_es_publiquen(entorn) -> None:
    db, magatzem, _mod = entorn
    counts = cloud_sync.publish_lliga_encontres(db_path=db)

    assert counts["lliga_partides"] == 4, "sense això la jornada surt sense resultats"
    files = magatzem["lliga_partides"]
    assert {f["ordre"] for f in files} == {1, 2, 3, 4}
    primera = next(f for f in files if f["jugador_local"] == "SÁNCHEZ MARTÍNEZ, PASCUAL")
    assert (primera["caramboles_local"], primera["caramboles_visitant"]) == (27, 39)
    assert primera["entrades"] == 50
    assert primera["encontre_id"] == 500


def test_quan_el_ranquing_la_publica_no_surt_dues_vegades(entorn) -> None:
    """La dedup va per signatura: parella de noms, caramboles i entrades.

    És la mateixa que fa servir `publish_pending_games`, i cal perquè la fila
    pendent no s'esborra quan el rànquing arriba: `lliga_pending_partides` és un
    mirall de l'acta i es reescriu a cada reingesta.
    """
    db, magatzem, mod_3b = entorn
    conn = sqlite3.connect(db)
    for i, nom in enumerate(("SÁNCHEZ MARTÍNEZ, PASCUAL", "HERNÁNDEZ PARRA, ANTONI"), start=1):
        conn.execute("INSERT INTO players (id, fcb_id, nom) VALUES (?,?,?)", (i, str(i), nom))
    conn.execute(
        """INSERT INTO games (id, data_partida, modalitat_id, player1_id, player2_id,
           caramboles1, caramboles2, entrades, encontre_lliga_id, temporada_id)
           VALUES ('x1', '2026-09-26', ?, 1, 2, 27, 39, 50, 500, 1)""",
        (mod_3b,),
    )
    conn.commit()
    conn.close()

    counts = cloud_sync.publish_lliga_encontres(db_path=db)
    files = magatzem["lliga_partides"]
    assert counts["lliga_partides"] == 4, "quatre partides, no cinc"
    noms = [f["jugador_local"] for f in files]
    assert noms.count("SÁNCHEZ MARTÍNEZ, PASCUAL") == 1
