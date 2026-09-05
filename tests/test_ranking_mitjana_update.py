"""Test que comprova que `mitjana_general` només s'actualitza si hi ha partides noves linkades."""

from __future__ import annotations

from datetime import date
import pytest

from fcbillar.models import Game, Player, Ranking, RankingEntry, RankingGameLink
import sqlite3
from pathlib import Path

from fcbillar.db.repository import Repository

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "src" / "fcbillar" / "db" / "schema.sql"


@pytest.fixture
def repo() -> Repository:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Repository(conn)


def test_mitjana_update_only_with_new_games(repo) -> None:
    # Crea un rànquing
    rid = repo.upsert_ranking(
        Ranking(num_seq=999, modalitat_codi_fcb=2, url="u", format_url="datahome")
    )

    # Create common opponent
    repo.upsert_player(Player(fcb_id="9999", nom="OPPONENT"))

    players = []
    # 10 jugadors, incloent Taza i Gómez
    names = [
        "TAZA, JOAN",
        "GÓMEZ, CARLA",
    ] + [f"PLAYER {i}" for i in range(3, 11)]

    base_fcb = 2000
    for i, nom in enumerate(names, start=1):
        fcb = str(base_fcb + i)
        repo.upsert_player(Player(fcb_id=fcb, nom=nom))
        players.append((fcb, nom))

    # Inserim per cada jugador 5 partides i linkeigs (partides == 5)
    for idx, (fcb, nom) in enumerate(players):
        initial_m = 20.0 + idx
        entry = RankingEntry(
            ranking_num_seq=999,
            ranking_modalitat=2,
            player_fcb_id=fcb,
            posicio=idx + 1,
            mitjana_general=initial_m,
            partides=5,
        )
        repo.upsert_ranking_entry(rid, entry)

        # create 5 games vs opponent and link them
        for j in range(5):
            g = Game(
                data_partida=date(2025, 1, 1 + j),
                competicio_nom="Copa Test",
                modalitat_codi_fcb=2,
                player1_fcb_id=fcb,
                player2_fcb_id="9999",
            )
            repo.upsert_game(g)
            repo.link_game_to_ranking(
                RankingGameLink(
                    ranking_num_seq=999,
                    ranking_modalitat=2,
                    game_id=g.id_natural,
                    player_fcb_id_origen=fcb,
                )
            )

    # Ara fem que alguns jugadors tinguin partides noves (2 més)
    updated_players = []
    for idx, (fcb, nom) in enumerate(players):
        # triem els pares amb índex parell per simular noves partides
        if idx % 2 == 0:
            # 2 noves partides
            for k in range(2):
                g = Game(
                    data_partida=date(2025, 2, 1 + k),
                    competicio_nom="Copa Test",
                    modalitat_codi_fcb=2,
                    player1_fcb_id=fcb,
                    player2_fcb_id="9999",
                )
                repo.upsert_game(g)
                repo.link_game_to_ranking(
                    RankingGameLink(
                        ranking_num_seq=999,
                        ranking_modalitat=2,
                        game_id=g.id_natural,
                        player_fcb_id_origen=fcb,
                    )
                )
            updated_players.append((fcb, nom))

    # Re-ingestem les entries amb una nova mitjana proposta -> només s'han d'actualitzar
    # per als jugadors amb partides noves
    for idx, (fcb, nom) in enumerate(players):
        new_m = 100.0 + idx
        entry = RankingEntry(
            ranking_num_seq=999,
            ranking_modalitat=2,
            player_fcb_id=fcb,
            posicio=idx + 1,
            mitjana_general=new_m,
            partides=5,  # el parsed continua dient 5
        )
        repo.upsert_ranking_entry(rid, entry)

    # Assert: jugadors actualitzats (índex parell) tenen la nova mitjana
    for idx, (fcb, nom) in enumerate(players):
        row = repo.conn.execute(
            "SELECT mitjana_general FROM ranking_entries re JOIN players p ON p.id=re.player_id WHERE p.fcb_id=? AND re.ranking_id=?",
            (fcb, rid),
        ).fetchone()
        assert row is not None
        mg = row[0]
        if idx % 2 == 0:
            assert mg == pytest.approx(100.0 + idx)
        else:
            assert mg == pytest.approx(20.0 + idx)
