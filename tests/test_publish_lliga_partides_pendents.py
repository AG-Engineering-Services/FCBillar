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
    # L'id de la federació (`encontre_id_extern`), no l'`id` local (500).
    assert primera["encontre_id"] == 11656


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


def test_l_id_publicat_no_depen_de_l_id_local(entorn) -> None:
    """La clau d'un encontre al núvol surt de la font, no de la base local.

    Ho feia de l'`id` local, i per això es veien encontres DUPLICATS: el mateix
    enfrontament dues vegades, amb el mateix resultat i la mateixa data. Un id
    local no és per sempre -la migració v23 va refer `encontres_lliga` i els va
    tornar a repartir- ni és el mateix a dues màquines, i la feina nocturna publica
    des de la seva còpia de la base de dades. Cada vegada que els ids ballaven, el
    que hi havia publicat quedava orfe al costat del nou.

    Aquí es publica dues vegades el mateix encontre amb un `id` local diferent, com
    si la taula s'hagués refet entremig: la clau publicada ha de ser la mateixa i no
    n'han de quedar dues.
    """
    db, magatzem, _mod = entorn
    cloud_sync.publish_lliga_encontres(db_path=db)
    assert {f["encontre_id"] for f in magatzem["lliga_encontres"]} == {11656}

    conn = sqlite3.connect(db)
    conn.execute("UPDATE encontres_lliga SET id = 900 WHERE id = 500")
    conn.execute("UPDATE lliga_pending_partides SET encontre_lliga_id = 900")
    conn.commit()
    conn.close()

    counts = cloud_sync.publish_lliga_encontres(db_path=db)

    assert {f["encontre_id"] for f in magatzem["lliga_encontres"]} == {11656}
    assert counts["lliga_encontres_retirats"] == 0, "no hi ha res a retirar: la clau no ha canviat"


def test_el_que_hi_havia_amb_la_clau_vella_es_retira(entorn) -> None:
    """El núvol no pot tenir el mateix encontre dues vegades.

    Les files publicades abans del canvi porten l'`id` local, i cap d'elles és una
    clau que ara es publiqui: se n'han d'anar. La retirada va per DIVISIONS -les
    que s'acaben de publicar- i no per tota la taula, perquè el núvol guarda també
    les temporades anteriors, cada temporada té els seus ids de divisió i aquesta
    publicació només porta la lliga de tres bandes de la temporada en curs.

    Les partides se'n van soles: la clau forana té `on delete cascade`.
    """
    db, magatzem, _mod = entorn
    magatzem["lliga_encontres"] = [
        # El mateix encontre amb l'id local d'abans de la v23...
        {
            "encontre_id": 500,
            "divisio_id": 159,
            "grup_id": 343,
            "jornada": 1,
            "data": "2026-09-26",
            "equip_local": "C.B.BANYOLES A",
            "equip_visitant": "B.C.GRANOLLERS A",
            "gols_local": 0,
            "gols_visitant": 3,
        },
        # ...i un de la temporada passada, que ningú no republica i s'ha de quedar.
        {
            "encontre_id": 16528,
            "divisio_id": 152,
            "grup_id": 315,
            "jornada": 9,
            "data": "2025-09-13",
            "equip_local": "C.B. BORGES",
            "equip_visitant": "C.B.BARCELONA C",
            "gols_local": 3,
            "gols_visitant": 0,
        },
    ]
    magatzem["lliga_partides"] = [
        {"encontre_id": 500, "ordre": 1, "jugador_local": "QUI SIGUI"},
    ]

    counts = cloud_sync.publish_lliga_encontres(db_path=db)

    assert counts["lliga_encontres_retirats"] == 1
    ids = {f["encontre_id"] for f in magatzem["lliga_encontres"]}
    assert ids == {11656, 16528}, "fora el de la clau vella, i la temporada passada es queda"


def test_un_encontre_sense_jugar_te_clau_i_no_es_l_id_local(entorn) -> None:
    """Els que no s'han jugat no tenen id de la federació i també necessiten clau.

    La federació publica tots els enfrontaments des del primer dia -amb els dos
    equips i l'estat «Oberta»- però sense enllaç i sense id: en tenen un quan es
    juguen, i d'aquesta temporada només 7 dels 672. La clau d'aquells es fa amb el
    que sí que ve de la federació, el `jornada_id`, i amb el lloc de l'encontre dins
    la jornada per nom de l'equip de casa, que és igual a totes les màquines.
    """
    db, magatzem, _mod = entorn
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO clubs (id, fcb_id, nom) VALUES (3, 'C.B.MONFORTE', 'C.B.MONFORTE')")
    conn.execute("INSERT INTO equips (id, club_id, lletra) VALUES (3, 3, 'A')")
    conn.execute(
        """
        INSERT INTO encontres_lliga
            (id, lliga_id, divisio_id, grup_id, jornada_id, encontre_id_extern, temporada_id,
             equip_local_id, equip_visitant_id, jornada_num, estat)
        VALUES (501, 38, 159, 343, 2790, NULL, 1, 3, 1, 1, 'Oberta')
        """
    )
    conn.commit()
    conn.close()

    cloud_sync.publish_lliga_encontres(db_path=db)

    per_equip = {f["equip_local"]: f["encontre_id"] for f in magatzem["lliga_encontres"]}
    # Dos encontres a la jornada 2790: BANYOLES i MONFORTE, per aquest ordre.
    assert per_equip["C.B.BANYOLES A"] == 11656, "el jugat, amb l'id de la federació"
    assert per_equip["C.B.MONFORTE A"] == 10_000_000 + 2790 * 100 + 2
