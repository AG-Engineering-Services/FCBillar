"""Tests del repository contra una BD SQLite en memòria amb el schema real."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from fcbillar.db.migrations import SCHEMA_VERSION, ensure_schema
from fcbillar.db.repository import Repository
from fcbillar.models import (
    Club,
    Competicio,
    EncontreLliga,
    Equip,
    Game,
    Modalitat,
    Player,
    Ranking,
    RankingEntry,
    RankingGameLink,
    Temporada,
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
        "temporades",
        "equips",
        "encontres_lliga",
    }


def test_upsert_modalitat_idempotent(repo: Repository) -> None:
    """Modalitat seedejada ja existeix; upsert l'ha de tornar amb el mateix id."""
    mid = repo.upsert_modalitat(Modalitat(codi_fcb=1, nom="Tres bandes"))
    mid2 = repo.upsert_modalitat(Modalitat(codi_fcb=1, nom="Tres bandes"))
    assert mid == mid2
    assert repo.counts()["modalitats"] == 5  # cap nova


# ---------------- entitats de lliga (v2) ----------------


def test_upsert_temporada_idempotent(repo: Repository) -> None:
    t1 = repo.upsert_temporada(Temporada(nom="2025-2026"))
    t2 = repo.upsert_temporada(Temporada(nom="2025-2026"))
    assert t1 == t2
    assert repo.counts()["temporades"] == 1


def test_upsert_equip_requires_club(repo: Repository) -> None:
    with pytest.raises(ValueError, match="Club NOEXIST no registrat"):
        repo.upsert_equip(Equip(club_fcb_id="NOEXIST", lletra="A"))


def test_upsert_equip_unique_per_club_and_lletra(repo: Repository) -> None:
    repo.upsert_club(Club(fcb_id="MATARÓ", nom="C.B. MATARÓ"))
    e1 = repo.upsert_equip(Equip(club_fcb_id="MATARÓ", lletra="A"))
    e2 = repo.upsert_equip(Equip(club_fcb_id="MATARÓ", lletra="A"))
    assert e1 == e2
    # Lletres diferents → equips diferents
    e3 = repo.upsert_equip(Equip(club_fcb_id="MATARÓ", lletra="B"))
    assert e3 != e1
    assert repo.counts()["equips"] == 2


def test_get_equip_id_by_club_and_lletra(repo: Repository) -> None:
    repo.upsert_club(Club(fcb_id="MATARÓ", nom="C.B. MATARÓ"))
    eid = repo.upsert_equip(Equip(club_fcb_id="MATARÓ", lletra="A"))
    assert repo.get_equip_id("MATARÓ", "A") == eid
    assert repo.get_equip_id("MATARÓ", "C") is None
    assert repo.get_equip_id("NOEXIST", "A") is None


def test_upsert_encontre_lliga_creates_equips_and_temporada(repo: Repository) -> None:
    repo.upsert_club(Club(fcb_id="MATARÓ", nom="C.B. MATARÓ"))
    repo.upsert_club(Club(fcb_id="SANTS", nom="C.B. SANTS"))
    eid = repo.upsert_encontre_lliga(
        EncontreLliga(
            lliga_id=36,
            divisio_id=148,
            grup_id=316,
            jornada_id=2593,
            encontre_id_extern=10939,
            equip_local=Equip(club_fcb_id="MATARÓ", lletra="A"),
            equip_visitant=Equip(club_fcb_id="SANTS", lletra="A"),
            data=date(2025, 9, 27),
            temporada_nom="2025-2026",
            p_parcials_local=8,
            p_match_local=3,
            p_parcials_visitant=0,
            p_match_visitant=0,
        )
    )
    assert eid is not None
    counts = repo.counts()
    assert counts["equips"] == 2  # MATARÓ A + SANTS A
    assert counts["temporades"] == 1
    assert counts["encontres_lliga"] == 1


def test_upsert_encontre_lliga_is_idempotent(repo: Repository) -> None:
    repo.upsert_club(Club(fcb_id="MATARÓ", nom="C.B. MATARÓ"))
    repo.upsert_club(Club(fcb_id="SANTS", nom="C.B. SANTS"))
    e = EncontreLliga(
        lliga_id=36,
        divisio_id=148,
        grup_id=316,
        jornada_id=2593,
        encontre_id_extern=10939,
        equip_local=Equip(club_fcb_id="MATARÓ", lletra="A"),
        equip_visitant=Equip(club_fcb_id="SANTS", lletra="A"),
    )
    id1 = repo.upsert_encontre_lliga(e)
    id2 = repo.upsert_encontre_lliga(e)
    assert id1 == id2


# ---------------- migració v1 → v2 ----------------


def test_migration_v1_to_v2_preserves_games(tmp_path: Path) -> None:
    """Una BD a versió 1 amb dades es migra a v2 sense perdre files.

    Construïm a mà una BD amb l'estructura v1 fidel (totes les columnes
    que schema.sql v2 referencia, però sense les noves de v2), apliquem
    ensure_schema, i comprovem que la migració afegeix tot el que falta.
    """
    import sqlite3

    db_path = tmp_path / "test_migration.db"
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.executescript(
        """
        CREATE TABLE clubs (id INTEGER PRIMARY KEY, fcb_id TEXT UNIQUE NOT NULL, nom TEXT NOT NULL);
        CREATE TABLE modalitats (id INTEGER PRIMARY KEY, codi_fcb INTEGER UNIQUE NOT NULL, nom TEXT NOT NULL);
        INSERT INTO modalitats (codi_fcb, nom) VALUES (1, 'Tres bandes');
        CREATE TABLE players (
            id INTEGER PRIMARY KEY,
            fcb_id TEXT UNIQUE NOT NULL,
            nom TEXT NOT NULL,
            club_id INTEGER REFERENCES clubs(id),
            seguiment INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO players (fcb_id, nom) VALUES ('566', 'VILALTA');
        INSERT INTO players (fcb_id, nom) VALUES ('424', 'PALLISA');
        CREATE TABLE competicions (
            id INTEGER PRIMARY KEY, nom TEXT NOT NULL, temporada TEXT,
            modalitat_id INTEGER REFERENCES modalitats(id)
        );
        CREATE TABLE rankings (
            id INTEGER PRIMARY KEY, num_seq INTEGER NOT NULL,
            modalitat_id INTEGER NOT NULL REFERENCES modalitats(id),
            url TEXT NOT NULL, format_url TEXT NOT NULL,
            any_pub INTEGER, mes_pub INTEGER,
            scraped_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE ranking_entries (
            id INTEGER PRIMARY KEY,
            ranking_id INTEGER NOT NULL REFERENCES rankings(id),
            player_id INTEGER NOT NULL REFERENCES players(id)
        );
        CREATE TABLE games (
            id TEXT PRIMARY KEY,
            data_partida TEXT NOT NULL,
            competicio_id INTEGER REFERENCES competicions(id),
            modalitat_id INTEGER NOT NULL REFERENCES modalitats(id),
            player1_id INTEGER NOT NULL REFERENCES players(id),
            player2_id INTEGER NOT NULL REFERENCES players(id),
            caramboles1 INTEGER, caramboles2 INTEGER,
            entrades INTEGER, mitjana1 REAL, mitjana2 REAL,
            serie_max1 INTEGER, serie_max2 INTEGER,
            guanyador_id INTEGER REFERENCES players(id),
            extras_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO games (id, data_partida, modalitat_id, player1_id, player2_id, caramboles1, caramboles2)
            VALUES ('gameold1', '2026-02-01', 1, 1, 2, 200, 53);
        CREATE TABLE ranking_game_links (
            ranking_id INTEGER, game_id TEXT, player_id_origen INTEGER,
            PRIMARY KEY (ranking_id, game_id, player_id_origen)
        );
        PRAGMA user_version = 1;
        """
    )
    conn.close()

    # Ara apliquem la migració amb ensure_schema.
    conn = ensure_schema(db_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

    # Game preservat.
    n_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    assert n_games == 1

    # Columnes noves presents amb valor NULL.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(games)").fetchall()}
    for c in ("equip1_id", "equip2_id", "encontre_lliga_id", "temporada_id", "arbitre", "assistencia"):
        assert c in cols

    # Taules noves creades.
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "temporades" in tables
    assert "equips" in tables
    assert "encontres_lliga" in tables
