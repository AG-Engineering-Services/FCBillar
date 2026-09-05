"""Tests del vincle partides↔campionats (fcbillar.linking)."""

from __future__ import annotations

from fcbillar.db.migrations import ensure_schema
from fcbillar.linking import (
    GameRow,
    link_individual_games,
    match_partida_to_games,
    normalize_name,
)


def _g(**kw) -> GameRow:
    base = dict(
        id="g",
        modalitat_id=1,
        player1_id=1,
        player2_id=2,
        caramboles1=40,
        caramboles2=30,
        serie_max1=5,
        serie_max2=3,
        entrades=34,
    )
    base.update(kw)
    return GameRow(**base)


def test_normalize_name_strips_accents_and_case() -> None:
    assert normalize_name("SÁNCHEZ GÁLVEZ, DANIEL") == "sanchez galvez, daniel"
    assert normalize_name("  Mas   Canadell ") == "mas canadell"


def test_match_unique_by_caramboles_and_entrades() -> None:
    hits = match_partida_to_games(
        modalitat_id=1,
        caramboles=(30, 40),
        entrades=34,
        serie=(5, 3),
        candidates=[_g(), _g(id="other", caramboles1=40, caramboles2=20)],
    )
    assert [h.id for h in hits] == ["g"]


def test_match_filters_by_modality() -> None:
    hits = match_partida_to_games(
        modalitat_id=2,
        caramboles=(30, 40),
        entrades=34,
        serie=(5, 3),
        candidates=[_g(modalitat_id=1)],
    )
    assert hits == []


def test_match_unknown_modality_does_not_filter() -> None:
    hits = match_partida_to_games(
        modalitat_id=None,
        caramboles=(30, 40),
        entrades=34,
        serie=(5, 3),
        candidates=[_g(modalitat_id=4)],
    )
    assert len(hits) == 1


def test_match_entrades_mismatch_excluded() -> None:
    hits = match_partida_to_games(
        modalitat_id=1,
        caramboles=(30, 40),
        entrades=99,
        serie=(5, 3),
        candidates=[_g(entrades=34)],
    )
    assert hits == []


def test_match_serie_breaks_ties() -> None:
    a = _g(id="a", serie_max1=5, serie_max2=3)
    b = _g(id="b", serie_max1=7, serie_max2=2)
    hits = match_partida_to_games(
        modalitat_id=1,
        caramboles=(30, 40),
        entrades=34,
        serie=(7, 2),
        candidates=[a, b],
    )
    assert [h.id for h in hits] == ["b"]


def _setup_db(tmp_path):
    conn = ensure_schema(tmp_path / "t.db")
    conn.execute("INSERT INTO temporades(id, nom) VALUES (1, '2023-2024')")
    conn.executemany(
        "INSERT INTO players(id, fcb_id, nom) VALUES (?,?,?)",
        [
            (1, "p1", "PASTOR RIVAS, MANUEL"),
            (2, "p2", "MORENO CORTÉS, ARMAND"),
            (3, "p3", "MAS CANADELL, JOSEP"),
        ],
    )
    # competició INDIVIDUAL (modalitat 1 = Tres bandes, ja sembrada per schema.sql)
    conn.execute("INSERT INTO competicions(id, nom, modalitat_id) VALUES (100, 'INDIVIDUAL', 1)")
    conn.execute(
        "INSERT INTO torneigs_individuals(id, torneig_id_extern, divisio_id_extern, nom, modalitat_id, temporada_id)"
        " VALUES (500, 2, 2, 'TRES BANDES - 1A DIVISIÓ', 1, 1)"
    )
    return conn


def _ins_game(conn, gid, p1, p2, c1, c2, ent):
    conn.execute(
        "INSERT INTO games(id, data_partida, competicio_id, modalitat_id, player1_id, player2_id,"
        " caramboles1, caramboles2, entrades) VALUES (?,?,100,1,?,?,?,?,?)",
        (gid, "2024-02-10", p1, p2, c1, c2, ent),
    )


def test_link_individual_games_endtoend(tmp_path) -> None:
    conn = _setup_db(tmp_path)
    # game que casa amb la partida de campionat
    _ins_game(conn, "match", 1, 2, 40, 32, 34)
    # game de la mateixa parella però amb un altre resultat (no ha de vincular)
    _ins_game(conn, "nomatch", 1, 2, 40, 10, 20)
    # partida de campionat (player1/player2 en ordre invers, caramboles invertits)
    conn.execute(
        "INSERT INTO torneig_partides(torneig_id_extern, divisio_id_extern, fase_id,"
        " player1_nom, caramboles1, serie1, punts1,"
        " player2_nom, caramboles2, serie2, punts2, entrades)"
        " VALUES (2,2,66,'MORENO CORTÉS, ARMAND',32,4,0,'PASTOR RIVAS, MANUEL',40,7,2,34)"
    )
    # una partida amb un bye ("Descansa") — no resol
    conn.execute(
        "INSERT INTO torneig_partides(torneig_id_extern, divisio_id_extern, fase_id,"
        " player1_nom, caramboles1, serie1, punts1,"
        " player2_nom, caramboles2, serie2, punts2, entrades)"
        " VALUES (2,2,66,'PASTOR RIVAS, MANUEL',40,5,2,'Descansa',0,0,0,0)"
    )

    res = link_individual_games(conn)

    assert res.linked_games == 1
    assert res.matched_partides == 1
    assert res.unresolved_players == 1  # el bye
    row = conn.execute(
        "SELECT torneig_id, torneig_fase_id, torneig_link_method FROM games WHERE id='match'"
    ).fetchone()
    assert row["torneig_id"] == 500
    assert row["torneig_fase_id"] == 66
    assert row["torneig_link_method"] == "exacte"
    assert (
        conn.execute("SELECT torneig_id FROM games WHERE id='nomatch'").fetchone()["torneig_id"]
        is None
    )


def test_conflict_resolved_by_season(tmp_path) -> None:
    """Un game que casaria amb dos torneigs (parella+resultat idèntic en temporades
    diferents) s'assigna al torneig la temporada del qual coincideix amb la data."""
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO temporades(id, nom) VALUES (2, '2024-2025')")
    # torneig 500 ja és 2023-2024 (temporada 1). Afegim un segon a 2024-2025.
    conn.execute(
        "INSERT INTO torneigs_individuals(id, torneig_id_extern, divisio_id_extern, nom, modalitat_id, temporada_id)"
        " VALUES (501, 9, 9, 'OPEN ALTRE', 1, 2)"
    )
    # game jugat el 2024-10 → temporada 2024-2025 → ha de guanyar el torneig 501.
    conn.execute(
        "INSERT INTO games(id, data_partida, competicio_id, modalitat_id, player1_id, player2_id,"
        " caramboles1, caramboles2, entrades) VALUES ('x','2024-10-05',100,1,1,2,40,32,34)"
    )
    base = ("MORENO CORTÉS, ARMAND", 32, 4, 0, "PASTOR RIVAS, MANUEL", 40, 7, 2, 34)
    # mateixa partida (parella+resultat) a tots dos torneigs
    conn.execute(
        "INSERT INTO torneig_partides(torneig_id_extern, divisio_id_extern, fase_id,"
        " player1_nom, caramboles1, serie1, punts1, player2_nom, caramboles2, serie2, punts2, entrades)"
        " VALUES (2,2,66,?,?,?,?,?,?,?,?,?)",
        base,
    )
    conn.execute(
        "INSERT INTO torneig_partides(torneig_id_extern, divisio_id_extern, fase_id,"
        " player1_nom, caramboles1, serie1, punts1, player2_nom, caramboles2, serie2, punts2, entrades)"
        " VALUES (9,9,77,?,?,?,?,?,?,?,?,?)",
        base,
    )
    link_individual_games(conn)
    assert conn.execute("SELECT torneig_id FROM games WHERE id='x'").fetchone()["torneig_id"] == 501


def test_link_is_idempotent(tmp_path) -> None:
    conn = _setup_db(tmp_path)
    _ins_game(conn, "match", 1, 2, 40, 32, 34)
    conn.execute(
        "INSERT INTO torneig_partides(torneig_id_extern, divisio_id_extern, fase_id,"
        " player1_nom, caramboles1, serie1, punts1,"
        " player2_nom, caramboles2, serie2, punts2, entrades)"
        " VALUES (2,2,66,'PASTOR RIVAS, MANUEL',40,7,2,'MORENO CORTÉS, ARMAND',32,4,0,34)"
    )
    first = link_individual_games(conn)
    second = link_individual_games(conn)
    assert first.linked_games == second.linked_games == 1
    assert conn.execute("SELECT COUNT(*) FROM games WHERE torneig_id=500").fetchone()[0] == 1
