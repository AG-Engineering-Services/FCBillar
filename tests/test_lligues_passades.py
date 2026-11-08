"""Les lligues passades: els controls de `analitza` i la publicació sense trepitjar res.

Una lliga de Tres Bandes del 2020-21 (lliga 24), un sol grup de dos equips i dos
encontres. El segon encontre és de l'estiu i porta el `temporada_id` de la
temporada següent, que és el que passa de debò amb les promocions. Aquell any un
encontre guanyat valia 2 punts, no 3.
"""

from __future__ import annotations

import json

import pytest

from fcbillar import cloud_sync
from fcbillar import lligues_passades as lp
from fcbillar.db.migrations import ensure_schema
from fcbillar.scraper.parsers import LligaClassificacioRow
from tests.test_publish_lliga_retirada import ClientFals

LLIGA = 24
DIV, GRUP = 89, 300


def _game(conn, gid, enc, p1, p2, c1, c2, ent, *, guanya, s1=5, s2=4, eq1=1, mod=None):
    mod = mod or conn.execute("SELECT id FROM modalitats WHERE codi_fcb = 1").fetchone()[0]
    punts = (2, 0) if guanya == p1 else (0, 2) if guanya == p2 else (1, 1)
    conn.execute(
        """INSERT INTO games (id, data_partida, modalitat_id, player1_id, player2_id,
               caramboles1, caramboles2, entrades, serie_max1, serie_max2, guanyador_id,
               equip1_id, encontre_lliga_id, extras_json)
           VALUES (?, '2021-03-13', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (gid, mod, p1, p2, c1, c2, ent, s1, s2, guanya, eq1, enc,
         json.dumps({"punts1": punts[0], "punts2": punts[1]})),
    )  # fmt: skip


@pytest.fixture
def entorn(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    conn = ensure_schema(db)
    conn.execute("INSERT INTO temporades (id, nom) VALUES (9289, '2020-2021')")
    conn.execute("INSERT INTO temporades (id, nom) VALUES (1127, '2021-2022')")
    for i, nom in enumerate(("C.B.BANYOLES", "B.C.GRANOLLERS"), start=1):
        conn.execute("INSERT INTO clubs (id, fcb_id, nom) VALUES (?,?,?)", (i, nom, nom))
        conn.execute("INSERT INTO equips (id, club_id, lletra) VALUES (?,?,'A')", (i, i))
    # Jugadors 1-4 del Banyoles, 5-8 del Granollers.
    for p in range(1, 9):
        conn.execute("INSERT INTO players (id, fcb_id, nom) VALUES (?,?,?)", (p, str(p), f"J{p}"))
    for div, grup, nom in ((DIV, 0, "1a DIVISIÓ"), (DIV, GRUP, "GRUP A")):
        conn.execute(
            "INSERT INTO lliga_noms (lliga_id, divisio_id, grup_id, nom) VALUES (?,?,?,?)",
            (LLIGA, div, grup, nom),
        )
    # Encontre 1: Banyoles 6-2 Granollers (2 punts de matx). Encontre 2, a l'estiu
    # i amb el temporada_id de la següent: Granollers 4-4 Banyoles (1 i 1).
    conn.execute(
        """INSERT INTO encontres_lliga (id, lliga_id, divisio_id, grup_id, jornada_id,
               encontre_id_extern, data, temporada_id, equip_local_id, equip_visitant_id,
               p_parcials_local, p_match_local, p_parcials_visitant, p_match_visitant)
           VALUES (1, ?, ?, ?, 10, 501, '2021-03-13', 9289, 1, 2, 6, 2, 2, 0),
                  (2, ?, ?, ?, 11, 502, '2021-09-04', 1127, 2, 1, 4, 1, 4, 1)""",
        (LLIGA, DIV, GRUP, LLIGA, DIV, GRUP),
    )
    _game(conn, 1, 1, 1, 5, 25, 20, 40, guanya=1)
    _game(conn, 2, 1, 2, 6, 25, 22, 40, guanya=2)
    _game(conn, 3, 1, 3, 7, 25, 21, 40, guanya=3)
    _game(conn, 4, 1, 4, 8, 18, 25, 40, guanya=8)
    # L'encontre 2 és a casa del Granollers: jugador 1 = visitant del Banyoles?
    # No: aquí el jugador 1 és el del Granollers (equip1 = 2, el local).
    _game(conn, 5, 2, 5, 1, 25, 20, 40, guanya=5, eq1=2)
    _game(conn, 6, 2, 6, 2, 20, 25, 40, guanya=2, eq1=2)
    _game(conn, 7, 2, 7, 3, 25, 19, 40, guanya=7, eq1=2)
    _game(conn, 8, 2, 8, 4, 21, 25, 40, guanya=4, eq1=2)
    # Les lligues d'ara (38 i 39) i una de més nova que el llistat encara no diu.
    for lliga in (38, 39, 41):
        conn.execute(
            "INSERT INTO encontres_lliga (lliga_id, divisio_id, grup_id, jornada_id) "
            "VALUES (?, 900, 900, 1)",
            (lliga,),
        )
    conn.commit()
    conn.close()

    monkeypatch.setenv("FCB_LLIGA_3B_ID", "38")
    monkeypatch.setenv("FCB_LLIGA_4M_ID", "39")
    magatzem: dict[str, list[dict]] = {}
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))
    return db, magatzem


def _oficial(pm_banyoles=3, pm_granollers=1, pp=(10, 6), j=2):
    return {
        (DIV, GRUP): [
            LligaClassificacioRow(1, "C.B.BANYOLES A", pm_banyoles, pp[0], j),
            LligaClassificacioRow(2, "B.C.GRANOLLERS A", pm_granollers, pp[1], j),
        ]
    }


def _conn(db):
    import sqlite3

    return sqlite3.connect(str(db))


def test_nomes_les_passades_i_mai_les_d_ara(entorn) -> None:
    db, _ = entorn
    assert lp.lligues_passades(_conn(db)) == [LLIGA]


def test_mena_i_temporada_surten_de_les_dades(entorn) -> None:
    db, _ = entorn
    conn = _conn(db)
    assert lp.mena_per_dades(conn, LLIGA) == "3B"
    assert lp.temporada_de_lliga(conn, LLIGA) == "2020-2021"


def test_una_lliga_neta_es_publicable(entorn) -> None:
    db, _ = entorn
    inf = lp.analitza(_conn(db), LLIGA, _oficial())
    assert inf.publicable, [i.__dict__ for i in inf.incidencies]
    assert (inf.encontres, inf.amb_resultat, inf.partides) == (2, 2, 8)
    assert inf.equips_desquadrats == 0


def test_sense_oficial_no_es_publica(entorn) -> None:
    db, _ = entorn
    inf = lp.analitza(_conn(db), LLIGA, None)
    assert not inf.publicable
    assert {e.tipus for e in inf.errors} == {"sense_oficial"}


def test_la_classificacio_que_no_quadra_bloqueja(entorn) -> None:
    db, _ = entorn
    # La federació diu 2 punts al Banyoles i nosaltres en sumem 3: dos equips
    # comparats, un de desquadrat, és més del 10 %.
    inf = lp.analitza(_conn(db), LLIGA, _oficial(pm_banyoles=2))
    assert "classificacio_no_quadra" in {i.tipus for i in inf.incidencies}
    assert "classificacio_massa_desquadrada" in {e.tipus for e in inf.errors}


def test_detecta_les_partides_girades(entorn) -> None:
    db, _ = entorn
    conn = _conn(db)
    # Sense `equip1_id`, l'encontre 2 es llegeix al revés: 4-4 segueix sent 4-4,
    # o sigui que es gira el resultat de l'1 perquè es vegi.
    conn.execute("UPDATE encontres_lliga SET p_parcials_local = 2, p_parcials_visitant = 6 "
                 "WHERE id = 1")  # fmt: skip
    conn.commit()
    inf = lp.analitza(conn, LLIGA, _oficial())
    assert "partides_girades" in {i.tipus for i in inf.incidencies}


def test_errors_de_partida(entorn) -> None:
    db, _ = entorn
    conn = _conn(db)
    conn.execute("UPDATE games SET serie_max1 = 30 WHERE id = 1")  # més que les caramboles
    conn.execute("UPDATE games SET player2_id = player1_id WHERE id = 2")  # contra ell mateix
    conn.commit()
    tipus = {e.tipus for e in lp.analitza(conn, LLIGA, _oficial()).errors}
    assert "jugador_contra_si_mateix" in tipus


def test_massa_encontres_sense_resultat_bloqueja(entorn) -> None:
    db, _ = entorn
    conn = _conn(db)
    conn.execute("UPDATE encontres_lliga SET p_match_local = NULL WHERE id = 2")
    conn.commit()
    tipus = {e.tipus for e in lp.analitza(conn, LLIGA, _oficial()).errors}
    assert "sense_resultat_massius" in tipus


def test_tota_la_lliga_compta_la_fase_d_estiu_i_no_arxiva(entorn, monkeypatch) -> None:
    db, magatzem = entorn
    arxivats = []
    monkeypatch.setattr(
        cloud_sync, "arxiva_lligues_passades", lambda *a, **k: arxivats.append(a) or 0
    )
    monkeypatch.setattr(cloud_sync, "_fetch_official_lliga_standings", lambda *a: _oficial())
    cloud_sync.publish_lliga(db, None, True, LLIGA, tota_la_lliga=True, arxiva=False)
    assert not arxivats, "publicant una lliga passada, l'arxivat donaria per passada la d'ara"
    per_equip = {f["equip"]: f for f in magatzem["lliga_standings"]}
    banyoles = per_equip["C.B.BANYOLES A"]
    # Els dos encontres, també el d'estiu amb l'altre temporada_id.
    assert banyoles["pj"] == 2
    # 2 + 1 punts de matx, com els va donar la federació: cap penalització.
    assert banyoles["punts"] == 3
    assert banyoles["penalitzacio"] is None
    assert {g["temporada"] for g in magatzem["lliga_groups"]} == {"2020-2021"}


def test_sense_tota_la_lliga_es_perd_la_fase_d_estiu(entorn, monkeypatch) -> None:
    """El comportament de sempre, per a la lliga en curs, no canvia."""
    db, magatzem = entorn
    monkeypatch.setattr(cloud_sync, "arxiva_lligues_passades", lambda *a, **k: 0)
    monkeypatch.setattr(cloud_sync, "_fetch_official_lliga_standings", lambda *a: _oficial())
    cloud_sync.publish_lliga(db, None, True, LLIGA, temporada_id=9289)
    banyoles = next(f for f in magatzem["lliga_standings"] if f["equip"] == "C.B.BANYOLES A")
    assert banyoles["pj"] == 1


def test_les_partides_girades_es_publiquen_de_cara_i_amb_serie(entorn) -> None:
    db, magatzem = entorn
    conn = _conn(db)
    # La partida 1 es desa amb el jugador del Granollers primer i equip1 = 2 (el
    # visitant de l'encontre 1): s'ha de publicar girada.
    conn.execute(
        "UPDATE games SET player1_id = 5, player2_id = 1, caramboles1 = 20, caramboles2 = 25, "
        "serie_max1 = 4, serie_max2 = 5, equip1_id = 2 WHERE id = 1"
    )
    conn.commit()
    cloud_sync.publish_lliga_encontres(db, None, lliga_id=LLIGA, tota_la_lliga=True)
    files = [f for f in magatzem["lliga_partides"] if f["encontre_id"] == 501]
    primera = next(f for f in files if f["jugador_local"] == "J1")
    assert (primera["caramboles_local"], primera["caramboles_visitant"]) == (25, 20)
    assert (primera["serie_local"], primera["serie_visitant"]) == (5, 4)
    assert len(magatzem["lliga_encontres"]) == 2, "també l'encontre d'estiu"


def test_ja_arxivada_compara_la_mena_i_no_el_nom(entorn) -> None:
    db, magatzem = entorn
    conn = _conn(db)
    cloud_sync._crea_historic(conn)
    conn.execute(
        "INSERT INTO lliga_standings_hist VALUES "
        "('2019-2020', 'LLIGA CATALANA 3 BANDES', 'HONOR', 'A', 1, 'X', 10, 20)"
    )
    conn.commit()
    sb = ClientFals(magatzem)
    assert cloud_sync.ja_arxivada(conn, sb, "2019-2020", "LLIGA CATALANA TRES BANDES")
    assert not cloud_sync.ja_arxivada(conn, sb, "2019-2020", "LLIGA CATALANA 4 MODALITATS")


def test_publica_i_verifica(entorn, monkeypatch) -> None:
    db, _magatzem = entorn
    monkeypatch.setattr(cloud_sync, "_fetch_official_lliga_standings", lambda *a: _oficial())
    inf = lp.analitza(_conn(db), LLIGA, _oficial())
    counts = lp.publica(db, inf, lambda *_: None)
    assert counts["lliga_encontres"] == 2
    assert counts["lliga_partides"] == 8
    assert counts["lliga_player_rankings"] == 8


def test_no_publica_el_que_no_ha_superat_l_analisi(entorn) -> None:
    db, _ = entorn
    inf = lp.analitza(_conn(db), LLIGA, None)
    with pytest.raises(ValueError):
        lp.publica(db, inf, lambda *_: None)


def test_la_verificacio_salta_si_el_nuvol_no_te_el_que_s_ha_enviat(entorn, monkeypatch) -> None:
    db, _magatzem = entorn
    monkeypatch.setattr(cloud_sync, "_fetch_official_lliga_standings", lambda *a: _oficial())
    inf = lp.analitza(_conn(db), LLIGA, _oficial())
    counts = {"lliga_groups": 1, "lliga_encontres": 2, "lliga_partides": 8}
    with pytest.raises(lp.VerificacioFallida):
        lp.verifica(db, inf, cloud_sync._TAULES_3B, counts)


def test_les_jornades_de_descans_no_son_encontres(entorn) -> None:
    db, magatzem = entorn
    conn = _conn(db)
    conn.execute("INSERT INTO clubs (id, fcb_id, nom) VALUES (9, 'Descans', 'Descans')")
    conn.execute("INSERT INTO equips (id, club_id, lletra) VALUES (9, 9, 'UNICO')")
    conn.execute(
        "INSERT INTO encontres_lliga (lliga_id, divisio_id, grup_id, jornada_id, data, "
        "equip_local_id, equip_visitant_id) VALUES (?, ?, ?, 12, '2021-04-01', 1, 9)",
        (LLIGA, DIV, GRUP),
    )
    conn.commit()
    inf = lp.analitza(conn, LLIGA, _oficial())
    assert inf.encontres == 2 and inf.publicable
    cloud_sync.publish_lliga_encontres(db, None, lliga_id=LLIGA, tota_la_lliga=True)
    assert all("Descans" not in f["equip_visitant"] for f in magatzem["lliga_encontres"])


def test_una_taula_oficial_d_una_altra_fase_no_es_fa_servir(entorn, monkeypatch) -> None:
    db, magatzem = entorn
    conn = _conn(db)
    # Una final amb un sol encontre, i l'oficial de la final copia la del grup A.
    conn.execute(
        "INSERT INTO lliga_noms (lliga_id, divisio_id, grup_id, nom) VALUES (?, ?, 301, 'FINAL')",
        (LLIGA, DIV),
    )
    conn.execute(
        """INSERT INTO encontres_lliga (id, lliga_id, divisio_id, grup_id, jornada_id,
               encontre_id_extern, data, temporada_id, equip_local_id, equip_visitant_id,
               p_parcials_local, p_match_local, p_parcials_visitant, p_match_visitant)
           VALUES (100, ?, ?, 301, 20, 503, '2021-06-01', 9289, 2, 1, 8, 2, 0, 0)""",
        (LLIGA, DIV),
    )
    conn.commit()
    oficial = _oficial()
    oficial[(DIV, 301)] = list(oficial[(DIV, GRUP)])  # la mateixa taula: 2 jugats, no 1
    inf = lp.analitza(conn, LLIGA, oficial)
    assert inf.grups_oficial_d_altra_fase == {(DIV, 301)}
    assert inf.publicable
    monkeypatch.setattr(cloud_sync, "_fetch_official_lliga_standings", lambda *a: oficial)
    cloud_sync.publish_lliga(
        db, None, True, LLIGA, tota_la_lliga=True, arxiva=False,
        ignora_oficial=inf.grups_oficial_d_altra_fase,
    )  # fmt: skip
    final = {f["equip"]: f for f in magatzem["lliga_standings"] if f["grup_id"] == 301}
    # La de la final, calculada: el Granollers la guanya amb 2 punts.
    assert final["B.C.GRANOLLERS A"]["punts"] == 2 and final["B.C.GRANOLLERS A"]["posicio"] == 1


def test_una_serie_impossible_es_publica_buida(entorn) -> None:
    db, magatzem = entorn
    conn = _conn(db)
    conn.execute("UPDATE games SET serie_max1 = 30 WHERE id = 1")
    conn.commit()
    inf = lp.analitza(conn, LLIGA, _oficial())
    assert inf.publicable and "serie_impossible" in {i.tipus for i in inf.incidencies}
    cloud_sync.publish_lliga_encontres(db, None, lliga_id=LLIGA, tota_la_lliga=True)
    primera = next(f for f in magatzem["lliga_partides"] if f["jugador_local"] == "J1")
    assert primera["serie_local"] is None and primera["serie_visitant"] == 4


def test_l_equip_contra_ell_mateix_es_una_jornada_de_descans(entorn) -> None:
    db, magatzem = entorn
    conn = _conn(db)
    conn.execute(
        "INSERT INTO encontres_lliga (lliga_id, divisio_id, grup_id, jornada_id, data, "
        "equip_local_id, equip_visitant_id) VALUES (?, ?, ?, 12, '2021-04-01', 1, 1)",
        (LLIGA, DIV, GRUP),
    )
    conn.commit()
    inf = lp.analitza(conn, LLIGA, _oficial())
    assert inf.encontres == 2 and inf.publicable
    cloud_sync.publish_lliga_encontres(db, None, lliga_id=LLIGA, tota_la_lliga=True)
    assert len(magatzem["lliga_encontres"]) == 2


def test_una_promocio_en_una_altra_divisio_que_acumula_tota_la_lliga(entorn) -> None:
    db, _ = entorn
    conn = _conn(db)
    # Una promoció (divisió a part) amb un encontre; l'oficial hi suma tota la lliga.
    for div, grup, nom in ((95, 0, "PROMOCIÓ"), (95, 400, "GRUP ÚNIC")):
        conn.execute(
            "INSERT INTO lliga_noms (lliga_id, divisio_id, grup_id, nom) VALUES (?,?,?,?)",
            (LLIGA, div, grup, nom),
        )
    conn.execute(
        """INSERT INTO encontres_lliga (id, lliga_id, divisio_id, grup_id, jornada_id,
               encontre_id_extern, data, temporada_id, equip_local_id, equip_visitant_id,
               p_parcials_local, p_match_local, p_parcials_visitant, p_match_visitant)
           VALUES (101, ?, 95, 400, 30, 504, '2021-07-01', 9289, 1, 2, 4, 1, 4, 1)""",
        (LLIGA,),
    )
    conn.commit()
    oficial = _oficial()
    oficial[(95, 400)] = [
        LligaClassificacioRow(1, "C.B.BANYOLES A", 4, 14, 3),
        LligaClassificacioRow(2, "B.C.GRANOLLERS A", 2, 10, 3),
    ]
    inf = lp.analitza(conn, LLIGA, oficial)
    assert inf.equips_desquadrats == 0
    assert "fase_amb_punts_acumulats" in {i.tipus for i in inf.incidencies}


def test_l_oficial_que_compta_els_descansos_com_a_jugats_quadra(entorn) -> None:
    db, _ = entorn
    conn = _conn(db)
    # El Banyoles descansa una jornada; l'oficial li compta 3 jugats.
    conn.execute("INSERT INTO clubs (id, fcb_id, nom) VALUES (9, 'Descans', 'Descans')")
    conn.execute("INSERT INTO equips (id, club_id, lletra) VALUES (9, 9, 'UNICO')")
    conn.execute(
        "INSERT INTO encontres_lliga (lliga_id, divisio_id, grup_id, jornada_id, data, "
        "equip_local_id, equip_visitant_id) VALUES (?, ?, ?, 12, '2021-04-01', 1, 9)",
        (LLIGA, DIV, GRUP),
    )
    conn.commit()
    oficial = {
        (DIV, GRUP): [
            LligaClassificacioRow(1, "C.B.BANYOLES A", 3, 10, 3),
            LligaClassificacioRow(2, "B.C.GRANOLLERS A", 1, 6, 2),
        ]
    }
    inf = lp.analitza(conn, LLIGA, oficial)
    assert inf.equips_desquadrats == 0, [i.__dict__ for i in inf.incidencies]


def test_si_ens_falten_encontres_mana_l_oficial(entorn) -> None:
    db, _ = entorn
    # L'oficial diu 2 jugats al grup però amb més punts: ens falta un encontre,
    # no és la taula d'una altra fase (el grup té dues jornades).
    oficial = {
        (DIV, GRUP): [
            LligaClassificacioRow(1, "C.B.BANYOLES A", 3, 10, 2),
            LligaClassificacioRow(2, "B.C.GRANOLLERS A", 1, 6, 2),
        ]
    }
    conn = _conn(db)
    conn.execute(
        "UPDATE encontres_lliga SET p_match_local = NULL, p_match_visitant = NULL WHERE id = 2"
    )
    conn.commit()
    inf = lp.analitza(conn, LLIGA, oficial)
    assert inf.equips_desquadrats == 2
    assert inf.grups_oficial_d_altra_fase == set()
