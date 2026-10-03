"""Qui una temporada només juga la lliga també hi té club.

`player_clubs` sortia de dues fonts: les classificacions dels campionats
individuals i `lliga_player_clubs`, que un script va omplir un sol cop des de
l'historial i s'acaba a la 2024-2025. Qui la 2025-2026 no va jugar cap individual
s'hi quedava sense fila: AMETLLER CONGOST, LLUIS no sortia com a jugador del
C.B.BANYOLES havent-hi jugat catorze partides de lliga.

Les partides de lliga porten l'equip de cadascú, i cada reingesta les porta. I
qui només juga la copa el té a `copa_encontres`.
"""

from __future__ import annotations

import pytest

from fcbillar import cloud_sync
from fcbillar.db.migrations import ensure_schema
from tests.test_publish_lliga_retirada import ClientFals


def _partida(conn, gid: str, p1: int, p2: int, equip1: int, equip2: int, temporada_id: int) -> None:
    conn.execute(
        "INSERT INTO games (id, data_partida, modalitat_id, player1_id, player2_id, "
        "equip1_id, equip2_id, encontre_lliga_id, temporada_id) VALUES (?,?,1,?,?,?,?,1,?)",
        (gid, "2025-11-01", p1, p2, equip1, equip2, temporada_id),
    )


@pytest.fixture
def entorn(tmp_path, monkeypatch):
    """Dos clubs i quatre jugadors: lliga i prou, amb individual, sense fitxa, copa i prou."""
    conn = ensure_schema(tmp_path / "t.db")
    conn.execute("INSERT INTO temporades (id, nom) VALUES (1, '2025-2026')")
    conn.execute("INSERT INTO clubs (id, fcb_id, nom) VALUES (1, 'C.B.BANYOLES', 'C.B.BANYOLES')")
    conn.execute("INSERT INTO clubs (id, fcb_id, nom) VALUES (2, 'C.B.MOLLET', 'C.B.MOLLET')")
    conn.execute("INSERT INTO equips (id, club_id, lletra) VALUES (1, 1, 'A')")
    conn.execute("INSERT INTO equips (id, club_id, lletra) VALUES (2, 2, 'A')")
    for pid, fcb, nom in (
        (1, "591", "AMETLLER CONGOST, LLUIS"),
        (2, "100", "RIVAL AMB INDIVIDUAL, PERE"),
        (3, "name:sense fitxa, joan", "SENSE FITXA, JOAN"),
        (4, "200", "NOMES COPA, MARTA"),
    ):
        conn.execute("INSERT INTO players (id, fcb_id, nom) VALUES (?,?,?)", (pid, fcb, nom))
    if not conn.execute("SELECT 1 FROM modalitats WHERE id = 1").fetchone():
        conn.execute("INSERT INTO modalitats (id, codi, nom) VALUES (1, 1, 'Tres bandes')")
    conn.execute(
        "INSERT INTO encontres_lliga (id, lliga_id, divisio_id, grup_id, jornada_id, temporada_id, "
        "equip_local_id, equip_visitant_id) VALUES (1, 38, 1, 1, 1, 1, 1, 2)"
    )
    # En Lluís juga de local i de visitant: el seu equip és el del seu costat.
    _partida(conn, "g1", 1, 2, 1, 2, 1)
    _partida(conn, "g2", 2, 1, 2, 1, 1)
    _partida(conn, "g3", 3, 2, 1, 2, 1)
    # El rival va jugar un individual, i hi consta amb un altre club.
    conn.execute(
        "INSERT INTO torneigs_individuals "
        "(id, torneig_id_extern, divisio_id_extern, nom, temporada_id) "
        "VALUES (10, 10, 10, 'TRES BANDES - 3A DIVISIÓ', 1)"
    )
    conn.execute(
        "INSERT INTO torneig_participants (torneig_id, player_id, club_text, posicio) "
        "VALUES (10, 2, 'C.B.SANTS', 1)"
    )
    # En Lluís consta sense club a la classificació d'un individual.
    conn.execute(
        "INSERT INTO torneig_participants (torneig_id, player_id, club_text, posicio) "
        "VALUES (10, 1, 'Cap', 2)"
    )
    # La copa: a `games` la partida no porta ni equip ni temporada. L'equip és a
    # `copa_encontres`, i la temporada surt de la data de la partida.
    conn.execute("INSERT INTO competicions (id, nom, modalitat_id) VALUES (3, 'COPA', 1)")
    conn.execute(
        "INSERT INTO copa_encontres (id, edicio_id, jornada, grup_id, enc_id_extern, "
        "team_a_extern, team_b_extern, equip_local, equip_visitant) "
        "VALUES (1, 7, 1, 1, 1, 1, 2, 'C.B.MOLLET \"B\"', 'C.B.BANYOLES')"
    )
    conn.execute(
        "INSERT INTO copa_partides (encontre_copa_id, ordre, local_nom, local_caramboles, "
        "visitant_nom, visitant_caramboles, entrades) "
        "VALUES (1, 1, 'NOMES COPA, MARTA', 30, 'AMETLLER CONGOST, LLUIS', 21, 33)"
    )
    conn.execute(
        "INSERT INTO games (id, data_partida, competicio_id, modalitat_id, player1_id, "
        "player2_id, caramboles1, caramboles2, entrades) "
        "VALUES ('c1', '2026-05-30', 3, 1, 4, 1, 30, 21, 33)"
    )
    conn.commit()
    conn.close()

    magatzem: dict[str, list[dict]] = {}
    monkeypatch.setattr(cloud_sync, "get_client", lambda: ClientFals(magatzem))
    return tmp_path / "t.db", magatzem


def _publicat(entorn) -> dict[tuple[str, str], str]:
    db, magatzem = entorn
    cloud_sync.publish_player_clubs(db_path=db)
    return {(f["player_fcb_id"], f["temporada"]): f["club"] for f in magatzem["player_clubs"]}


def test_qui_nomes_juga_la_lliga_te_el_club_de_les_partides(entorn) -> None:
    """I el «Cap» de la classificació d'un individual no li pren."""
    assert _publicat(entorn)[("591", "2025-2026")] == "C.B.BANYOLES"


def test_les_partides_no_corregeixen_el_club_de_l_individual(entorn) -> None:
    assert _publicat(entorn)[("100", "2025-2026")] == "C.B.SANTS"


def test_un_jugador_sense_fitxa_no_es_publica(entorn) -> None:
    assert not [clau for clau in _publicat(entorn) if clau[0].startswith("name:")]


def test_qui_nomes_juga_la_copa_te_el_club_de_l_encontre(entorn) -> None:
    assert _publicat(entorn)[("200", "2025-2026")] == "C.B.MOLLET"
