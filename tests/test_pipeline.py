"""Tests del pipeline amb un stub del scraper i una BD temporal per test."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from fcbillar.db.migrations import ensure_schema
from fcbillar.db.repository import Repository
from fcbillar.pipeline import (
    backfill_modalitat,
    ingest_partides,
    ingest_ranking,
    sync_current_rankings,
)

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class StubSettings:
    """Settings mínims per a tests — només el que el pipeline llegeix."""

    base_url: str
    db_path: Path


class StubScraperClient:
    """Mock de ScraperClient que retorna fixtures per URL.

    Implementa la interfície que el pipeline necessita: `.settings` i `.fetch_html`.
    Llença KeyError si la URL no està mapejada — força que els tests siguin explícits.
    """

    def __init__(self, settings: StubSettings, url_to_fixture: dict[str, str]) -> None:
        self.settings = settings
        self.url_to_fixture = url_to_fixture
        self.fetched_urls: list[str] = []

    def fetch_html(self, url: str, use_cache: bool = True) -> str:
        self.fetched_urls.append(url)
        if url not in self.url_to_fixture:
            raise KeyError(f"URL no mapejada al stub: {url}")
        return (FIXTURES / self.url_to_fixture[url]).read_text(encoding="utf-8")


@pytest.fixture
def settings(tmp_path: Path) -> StubSettings:
    return StubSettings(
        base_url="https://www.fcbillar.cat",
        db_path=tmp_path / "test.db",
    )


# Mappings d'URL → fixture utilitzats en tots els tests.
URL_FIXTURES = {
    "https://www.fcbillar.cat/jugador/home": "jugador_home_authed.html",
    "https://www.fcbillar.cat/ca/jugador/ranking/datahome/121/1#red": "ranking_tres_bandes_121.html",
    "https://www.fcbillar.cat/ca/jugador/ranking/datahome/121/2#red": "ranking_lliure_121.html",
    "https://www.fcbillar.cat/ca/jugador/ranking/partideshome/121/2/566": "partideshome_lliure_121_p566.html",
    "https://www.fcbillar.cat/ca/jugador/ranking/partideshome/121/1/769": "partideshome_tresbandes_121_p769.html",
}


# ---------------- ingest_ranking ----------------


def test_ingest_ranking_inserts_players_and_entries(settings: StubSettings) -> None:
    client = StubScraperClient(settings, URL_FIXTURES)
    result = ingest_ranking(client, num_seq=121, modalitat_codi_fcb=2, settings=settings)

    assert result is not None
    assert result.players_upserted == 166
    assert result.entries_upserted == 166
    assert result.fetch.fmt == "datahome"

    counts = Repository(ensure_schema(settings.db_path)).counts()
    assert counts["rankings"] == 1
    assert counts["players"] == 166
    assert counts["ranking_entries"] == 166


def test_ingest_ranking_is_idempotent(settings: StubSettings) -> None:
    """Tornar a fer ingest del mateix rànquing no crea duplicats."""
    client = StubScraperClient(settings, URL_FIXTURES)
    ingest_ranking(client, 121, 2, settings=settings)
    ingest_ranking(client, 121, 2, settings=settings)
    counts = Repository(ensure_schema(settings.db_path)).counts()
    assert counts["rankings"] == 1
    assert counts["players"] == 166
    assert counts["ranking_entries"] == 166


# ---------------- ingest_partides ----------------


def test_ingest_partides_requires_ranking_in_db(settings: StubSettings) -> None:
    """Si el rànquing referenciat no està a la BD, ha de fallar amb missatge clar."""
    # Inserim primer el player però NO el rànquing.
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    from fcbillar.models import Player

    repo.upsert_player(Player(fcb_id="566", nom="VILALTA"))
    client = StubScraperClient(settings, URL_FIXTURES)
    with pytest.raises(ValueError, match="Rànquing 121/2 no està a la BD"):
        ingest_partides(client, 121, 2, "566", settings=settings)


def test_ingest_partides_requires_player_in_db(settings: StubSettings) -> None:
    """Si el player referenciat no està a la BD, missatge clar."""
    client = StubScraperClient(settings, URL_FIXTURES)
    ingest_ranking(client, 121, 2, settings=settings)
    with pytest.raises(ValueError, match="Player 99999 no està a la BD"):
        ingest_partides(client, 121, 2, "99999", settings=settings)


def test_ingest_partides_persists_games_and_links(settings: StubSettings) -> None:
    """Ingest end-to-end: 10 partides de Vilalta amb les 2 competicions (LLIGA/INDIVIDUAL)."""
    client = StubScraperClient(settings, URL_FIXTURES)
    ingest_ranking(client, 121, 2, settings=settings)

    res = ingest_partides(client, 121, 2, "566", settings=settings)
    assert res.games_upserted == 10
    assert res.games_skipped_missing_opponent == 0
    assert res.links_created == 10

    counts = Repository(ensure_schema(settings.db_path)).counts()
    assert counts["games"] == 10
    assert counts["ranking_game_links"] == 10
    assert counts["competicions"] == 2  # LLIGA + INDIVIDUAL


# ---------------- sync_current_rankings ----------------


def test_sync_ingests_what_stub_can_serve(settings: StubSettings) -> None:
    """Sync ha d'ingerir els rànquings que el stub serveix i ignorar la resta.

    `fetch_ranking_html` captura excepcions com a warning i retorna None;
    `sync_current_rankings` només marca com a `ingested` les que han anat bé.
    """
    fixtures = {
        "https://www.fcbillar.cat/jugador/home": "jugador_home_authed.html",
        "https://www.fcbillar.cat/ca/jugador/ranking/datahome/121/1#red": (
            "ranking_tres_bandes_121.html"
        ),
        "https://www.fcbillar.cat/ca/jugador/ranking/datahome/121/2#red": (
            "ranking_lliure_121.html"
        ),
    }
    client = StubScraperClient(settings, fixtures)
    result = sync_current_rankings(client, settings=settings)

    assert set(result.ingested) == {(121, 1), (121, 2)}
    assert result.skipped_existing == []

    counts = Repository(ensure_schema(settings.db_path)).counts()
    assert counts["rankings"] == 2


def test_sync_skips_when_db_at_or_above_current(settings: StubSettings) -> None:
    """Si la BD ja té el num_seq actual, sync no ingereix res."""
    # Pre-popular la BD amb el rànquing 121 per a totes les modalitats.
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    from fcbillar.models import Ranking

    for mod in (1, 2, 3, 4, 6):
        repo.upsert_ranking(
            Ranking(num_seq=121, modalitat_codi_fcb=mod, url="x", format_url="datahome")
        )

    client = StubScraperClient(
        settings,
        {"https://www.fcbillar.cat/jugador/home": "jugador_home_authed.html"},
    )
    result = sync_current_rankings(client, settings=settings)
    assert result.ingested == []
    assert len(result.skipped_existing) == 5


# ---------------- backfill_modalitat ----------------


def test_backfill_top_n_processes_only_top(settings: StubSettings) -> None:
    """backfill amb --top 1 processa només el jugador rànquing 1."""
    client = StubScraperClient(settings, URL_FIXTURES)
    result = backfill_modalitat(
        client, modalitat_codi_fcb=2, top_n=1, settings=settings
    )
    assert result.players_processed == 1
    # El jugador top 1 de lliure 121 és Vilalta (566); ha de tenir 10 partides.
    assert result.total_games_upserted == 10


def test_backfill_unknown_modalitat_raises(settings: StubSettings) -> None:
    client = StubScraperClient(
        settings, {"https://www.fcbillar.cat/jugador/home": "jugador_home_authed.html"}
    )
    with pytest.raises(ValueError, match="Modalitat 99"):
        backfill_modalitat(client, 99, settings=settings)


def test_backfill_only_followed_skips_non_followed(settings: StubSettings) -> None:
    """only_followed=True processa només jugadors amb seguiment=1."""
    client = StubScraperClient(settings, URL_FIXTURES)
    # Ingest del rànquing primer per poder marcar el follow.
    ingest_ranking(client, 121, 2, settings=settings)
    repo = Repository(ensure_schema(settings.db_path))
    repo.set_seguiment("566", True)

    # Re-runeixo backfill amb only_followed. Només ha de processar Vilalta.
    result = backfill_modalitat(
        client, modalitat_codi_fcb=2, only_followed=True, settings=settings
    )
    assert result.players_processed == 1
    assert result.total_games_upserted == 10
