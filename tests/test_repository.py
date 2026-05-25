"""Tests del repository contra una BD SQLite en memòria amb el schema real."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from fcbillar.db.repository import Repository
from fcbillar.models import (
    Club,
    Competicio,
    Game,
    Modalitat,
    Player,
    Ranking,
    RankingEntry,
    RankingGameLink,
)

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "src" / "fcbillar" / "db" / "schema.sql"


@pytest.fixture
def repo() -> Repository:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Repository(conn)


def test_schema_seeds_five_modalitats(repo: Repository) -> None:
    """schema.sql ha de seedejar les 5 modalitats automàticament."""
    counts = repo.counts()
    assert counts["modalitats"] == 5
    # I han de ser els codis esperats.
    rows = repo.conn.execute("SELECT codi_fcb, nom FROM modalitats ORDER BY codi_fcb").fetchall()
    assert [(r[0], r[1]) for r in rows] == [
        (1, "Tres bandes"),
        (2, "Lliure"),
        (3, "Quadre 47/2"),
        (4, "Banda"),
        (6, "Quadre 71/2"),
    ]


def test_upsert_player_is_idempotent(repo: Repository) -> None:
    p = Player(fcb_id="566", nom="VILALTA PARÉ, VALENTÍ")
    pid1 = repo.upsert_player(p)
    pid2 = repo.upsert_player(p)
    assert pid1 == pid2
    assert repo.counts()["players"] == 1


def test_upsert_player_updates_nom_keeps_id(repo: Repository) -> None:
    repo.upsert_player(Player(fcb_id="566", nom="VILALTA ORIGINAL"))
    pid = repo.upsert_player(Player(fcb_id="566", nom="VILALTA UPDATED"))
    assert repo.get_player_nom_by_fcb_id("566") == "VILALTA UPDATED"
    assert repo.get_player_id_by_fcb_id("566") == pid


def test_set_seguiment_toggles(repo: Repository) -> None:
    repo.upsert_player(Player(fcb_id="566", nom="VILALTA"))
    assert repo.set_seguiment("566", True) is True
    assert repo.conn.execute("SELECT seguiment FROM players WHERE fcb_id='566'").fetchone()[0] == 1
    assert repo.set_seguiment("566", False) is True
    assert repo.conn.execute("SELECT seguiment FROM players WHERE fcb_id='566'").fetchone()[0] == 0


def test_set_seguiment_unknown_returns_false(repo: Repository) -> None:
    assert repo.set_seguiment("nonexistent", True) is False


def test_get_player_fcb_id_by_nom_returns_unique(repo: Repository) -> None:
    repo.upsert_player(Player(fcb_id="566", nom="VILALTA PARÉ, VALENTÍ"))
    assert repo.get_player_fcb_id_by_nom("VILALTA PARÉ, VALENTÍ") == "566"
    assert repo.get_player_fcb_id_by_nom("NO EXISTEIX") is None


def test_get_player_fcb_id_by_nom_homonyms_returns_none(repo: Repository) -> None:
    """Si hi ha dos jugadors amb el mateix nom, no resolem (evitem associar malament)."""
    repo.upsert_player(Player(fcb_id="111", nom="GARCIA, JOAN"))
    repo.upsert_player(Player(fcb_id="222", nom="GARCIA, JOAN"))
    assert repo.get_player_fcb_id_by_nom("GARCIA, JOAN") is None


def test_upsert_ranking_requires_modalitat(repo: Repository) -> None:
    with pytest.raises(ValueError, match="Modalitat 99"):
        repo.upsert_ranking(
            Ranking(num_seq=1, modalitat_codi_fcb=99, url="x", format_url="datahome")
        )


def test_upsert_ranking_is_idempotent(repo: Repository) -> None:
    rid1 = repo.upsert_ranking(
        Ranking(num_seq=121, modalitat_codi_fcb=2, url="u", format_url="datahome")
    )
    rid2 = repo.upsert_ranking(
        Ranking(num_seq=121, modalitat_codi_fcb=2, url="u", format_url="datahome")
    )
    assert rid1 == rid2


def test_latest_ranking_num_seq(repo: Repository) -> None:
    assert repo.latest_ranking_num_seq(2) is None
    repo.upsert_ranking(Ranking(num_seq=120, modalitat_codi_fcb=2, url="", format_url="data"))
    repo.upsert_ranking(Ranking(num_seq=121, modalitat_codi_fcb=2, url="", format_url="datahome"))
    repo.upsert_ranking(Ranking(num_seq=100, modalitat_codi_fcb=2, url="", format_url="data"))
    assert repo.latest_ranking_num_seq(2) == 121
    assert repo.latest_ranking_num_seq(1) is None


def test_upsert_ranking_entry_requires_player(repo: Repository) -> None:
    repo.upsert_ranking(
        Ranking(num_seq=121, modalitat_codi_fcb=2, url="", format_url="datahome")
    )
    rid = repo.get_ranking_id(121, 2)
    assert rid is not None
    with pytest.raises(ValueError, match="Player 999 no registrat"):
        repo.upsert_ranking_entry(
            rid,
            RankingEntry(
                ranking_num_seq=121, ranking_modalitat=2, player_fcb_id="999", posicio=1
            ),
        )


def test_upsert_game_dedupes_by_natural_id(repo: Repository) -> None:
    """La mateixa partida vista des dels dos jugadors té el mateix id_natural."""
    repo.upsert_player(Player(fcb_id="566", nom="VILALTA"))
    repo.upsert_player(Player(fcb_id="424", nom="PALLISA"))
    g1 = Game(
        data_partida=date(2026, 2, 1),
        competicio_nom="LLIGA",
        modalitat_codi_fcb=2,
        player1_fcb_id="566",
        player2_fcb_id="424",
        caramboles1=200,
        caramboles2=53,
        entrades=9,
    )
    # Mateixa partida vista "des de" l'altre costat — local/visitant intercanviats.
    g2 = Game(
        data_partida=date(2026, 2, 1),
        competicio_nom="LLIGA",
        modalitat_codi_fcb=2,
        player1_fcb_id="424",
        player2_fcb_id="566",
        caramboles1=53,
        caramboles2=200,
        entrades=9,
    )
    assert g1.id_natural == g2.id_natural
    repo.upsert_game(g1)
    repo.upsert_game(g2)
    assert repo.counts()["games"] == 1


def test_upsert_game_requires_both_players(repo: Repository) -> None:
    repo.upsert_player(Player(fcb_id="566", nom="VILALTA"))
    g = Game(
        data_partida=date(2026, 2, 1),
        competicio_nom="LLIGA",
        modalitat_codi_fcb=2,
        player1_fcb_id="566",
        player2_fcb_id="999",  # no existeix
    )
    with pytest.raises(ValueError, match="Jugadors no registrats"):
        repo.upsert_game(g)


def test_link_game_to_ranking_dedupes(repo: Repository) -> None:
    """Crear el mateix link dues vegades no falla i no duplica."""
    repo.upsert_player(Player(fcb_id="566", nom="VILALTA"))
    repo.upsert_player(Player(fcb_id="424", nom="PALLISA"))
    repo.upsert_ranking(
        Ranking(num_seq=121, modalitat_codi_fcb=2, url="", format_url="datahome")
    )
    g = Game(
        data_partida=date(2026, 2, 1),
        competicio_nom="LLIGA",
        modalitat_codi_fcb=2,
        player1_fcb_id="566",
        player2_fcb_id="424",
    )
    repo.upsert_game(g)
    link = RankingGameLink(
        ranking_num_seq=121,
        ranking_modalitat=2,
        game_id=g.id_natural,
        player_fcb_id_origen="566",
    )
    repo.link_game_to_ranking(link)
    repo.link_game_to_ranking(link)
    assert repo.counts()["ranking_game_links"] == 1


def test_link_game_to_ranking_distinct_owners_both_kept(repo: Repository) -> None:
    """Dos owners diferents per al mateix joc → dos links."""
    repo.upsert_player(Player(fcb_id="566", nom="VILALTA"))
    repo.upsert_player(Player(fcb_id="424", nom="PALLISA"))
    repo.upsert_ranking(
        Ranking(num_seq=121, modalitat_codi_fcb=2, url="", format_url="datahome")
    )
    g = Game(
        data_partida=date(2026, 2, 1),
        competicio_nom="LLIGA",
        modalitat_codi_fcb=2,
        player1_fcb_id="566",
        player2_fcb_id="424",
    )
    repo.upsert_game(g)
    for origen in ("566", "424"):
        repo.link_game_to_ranking(
            RankingGameLink(
                ranking_num_seq=121,
                ranking_modalitat=2,
                game_id=g.id_natural,
                player_fcb_id_origen=origen,
            )
        )
    assert repo.counts()["ranking_game_links"] == 2


def test_upsert_club_and_player_with_club(repo: Repository) -> None:
    repo.upsert_club(Club(fcb_id="C5", nom="C.B. SANTS"))
    pid = repo.upsert_player(
        Player(fcb_id="566", nom="VILALTA", club_fcb_id="C5")
    )
    row = repo.conn.execute(
        "SELECT club_id FROM players WHERE id = ?", (pid,)
    ).fetchone()
    expected_club_id = repo.get_club_id_by_fcb_id("C5")
    assert row[0] == expected_club_id


def test_upsert_competicio_dedupes_on_key(repo: Repository) -> None:
    c1 = repo.upsert_competicio(
        Competicio(nom="LLIGA", temporada="2025-2026", modalitat_codi_fcb=1)
    )
    c2 = repo.upsert_competicio(
        Competicio(nom="LLIGA", temporada="2025-2026", modalitat_codi_fcb=1)
    )
    assert c1 == c2


def test_counts_returns_all_tables(repo: Repository) -> None:
    counts = repo.counts()
    assert set(counts.keys()) == {
        "clubs",
        "players",
        "modalitats",
        "competicions",
        "rankings",
        "ranking_entries",
        "games",
        "ranking_game_links",
    }


def test_upsert_modalitat_idempotent(repo: Repository) -> None:
    """Modalitat seedejada ja existeix; upsert l'ha de tornar amb el mateix id."""
    mid = repo.upsert_modalitat(Modalitat(codi_fcb=1, nom="Tres bandes"))
    mid2 = repo.upsert_modalitat(Modalitat(codi_fcb=1, nom="Tres bandes"))
    assert mid == mid2
    assert repo.counts()["modalitats"] == 5  # cap nova
