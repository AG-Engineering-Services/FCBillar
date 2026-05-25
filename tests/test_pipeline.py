"""Tests del pipeline amb un stub del scraper i una BD temporal per test."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from fcbillar.db.migrations import ensure_schema
from fcbillar.db.repository import Repository
from fcbillar.pipeline import (
    _derive_temporada,
    _split_equip_nom,
    backfill_historical,
    backfill_modalitat,
    backfill_ranking,
    ingest_lliga_encontre,
    ingest_lliga_jornada,
    ingest_partides,
    ingest_ranking,
    sync_current_rankings,
)
from fcbillar.scraper.parsers import LligaEncontre

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


# ---------------- backfill_historical ----------------


def test_backfill_ranking_with_no_partides(settings: StubSettings) -> None:
    """backfill_ranking amb top_n=0 ingest només el rànquing, no les partides."""
    client = StubScraperClient(settings, URL_FIXTURES)
    res = backfill_ranking(client, 121, 2, top_n=0, settings=settings)
    assert res.ranking_ingested is True
    assert res.players_processed == 0
    assert res.total_games_upserted == 0

    counts = Repository(ensure_schema(settings.db_path)).counts()
    assert counts["rankings"] == 1
    assert counts["games"] == 0


def test_backfill_historical_processes_what_stub_can_serve(
    settings: StubSettings,
) -> None:
    """Donat l'historial real (15 dates × 5 modalitats) i fixtures per a un sol
    (num_seq, modalitat), només aquest es processa OK; la resta queden a failed."""
    fixtures = {
        "https://www.fcbillar.cat/ca/jugador/ranking/historial": "ranking_historial.html",
        # Reutilitzem la fixture del 121 com a fake del 112 (mateixa estructura).
        # fetch_ranking_html prova primer 'datahome', després 'data'.
        "https://www.fcbillar.cat/ca/jugador/ranking/data/112/2#red": "ranking_lliure_121.html",
    }
    client = StubScraperClient(settings, fixtures)
    res = backfill_historical(
        client, modalitat_codi_fcb=2, top_n=0, settings=settings
    )
    # 1 OK (el 112/2 amb fixture) + 14 fallats (la resta sense fixture).
    assert res.rankings_processed == [(112, 2)]
    assert len(res.rankings_failed) == 14
    assert res.total_players_processed == 0  # top_n=0 evita partides
    assert res.total_games_upserted == 0


def test_backfill_historical_filters_by_modalitat(settings: StubSettings) -> None:
    """Amb modalitat_codi_fcb=None, processa totes les modalitats (15×5=75 entries)."""
    fixtures = {
        "https://www.fcbillar.cat/ca/jugador/ranking/historial": "ranking_historial.html",
    }
    client = StubScraperClient(settings, fixtures)
    # Sense fixture per a cap rànquing → tots fallen.
    res = backfill_historical(client, modalitat_codi_fcb=None, top_n=0, settings=settings)
    assert len(res.rankings_processed) == 0
    # 15 entries × 5 modalitats = 75 intents fallats.
    assert len(res.rankings_failed) == 75


# ---------------- helpers de lliga ----------------


def test_split_equip_nom_with_lletra() -> None:
    assert _split_equip_nom('C.B. MATARÓ "A"') == ("C.B. MATARÓ", "A")
    assert _split_equip_nom('SB FOMENT MOLINS "A"') == ("SB FOMENT MOLINS", "A")
    assert _split_equip_nom('SANT ADRIÀ "B"') == ("SANT ADRIÀ", "B")


def test_split_equip_nom_without_lletra_uses_unico() -> None:
    assert _split_equip_nom("CLUB UNIC SENSE LLETRA") == ("CLUB UNIC SENSE LLETRA", "UNICO")


def test_derive_temporada_september_starts_new() -> None:
    assert _derive_temporada(date(2025, 9, 27)) == "2025-2026"
    assert _derive_temporada(date(2025, 12, 20)) == "2025-2026"
    assert _derive_temporada(date(2026, 4, 25)) == "2025-2026"
    # Juliol cau a la temporada anterior.
    assert _derive_temporada(date(2025, 7, 15)) == "2024-2025"


# ---------------- ingest_lliga_encontre ----------------


def test_ingest_lliga_encontre_creates_full_context(settings: StubSettings) -> None:
    """Ingest d'un encontre amb la fixture real: crea clubs, equips, encontre,
    i 4 games amb context complet. Salta partides on els jugadors no són a la BD."""
    fixtures = {
        # URL de partides del primer encontre de la jornada 01 GRUP A HONOR.
        "https://www.fcbillar.cat/ca/lligues/partides/36/148/316/2593/10939": (
            "lliga_3b_encontre_partides.html"
        ),
    }
    client = StubScraperClient(settings, fixtures)
    encontre = LligaEncontre(
        lliga_id=36,
        divisio_id=148,
        grup_id=316,
        jornada_id=2593,
        encontre_id=10939,
        equip_local='C.B. SANTS "A"',
        p_parcials_local=5,
        p_match_local=3,
        equip_visitant='SB FOMENT MOLINS "A"',
        p_parcials_visitant=3,
        p_match_visitant=0,
    )

    # Pre-popular jugadors perquè el resolver nom→fcb_id funcioni.
    # La fixture té VARELA LOSADA + PERALES SANZ + MARTÍN LIMA + SÁNCHEZ GALLEGO +
    # BOTERO BERRIO + FONTANET BELLES + VEIGA CARRETE + SÁNCHEZ BARRERA.
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    from fcbillar.models import Player

    noms_4_partides = [
        ("60", "VARELA LOSADA, FRANCESC"),
        ("70", "PERALES SANZ, JOAN"),
        ("80", "MARTÍN LIMA, MELCHOR"),
        ("90", "SÁNCHEZ GALLEGO, JOEL"),
        ("100", "BOTERO BERRIO, CARLOS ALBERTO"),
        ("110", "FONTANET BELLES, JOAN CARLES"),
        ("120", "VEIGA CARRETE, DAVID"),
        ("130", "SÁNCHEZ BARRERA, MIGUEL"),
    ]
    for fcb_id, nom in noms_4_partides:
        repo.upsert_player(Player(fcb_id=fcb_id, nom=nom))

    result = ingest_lliga_encontre(
        client, encontre, modalitat_codi_fcb=1, data=date(2025, 9, 27), settings=settings
    )

    assert result.partides_total == 4
    assert result.games_upserted == 4
    assert result.games_skipped_missing_player == 0

    counts = repo.counts()
    assert counts["clubs"] == 2  # C.B. SANTS + SB FOMENT MOLINS
    assert counts["equips"] == 2  # ambdós amb lletra A
    assert counts["encontres_lliga"] == 1
    assert counts["games"] == 4
    assert counts["temporades"] == 1  # derivada de la data

    # Verifico que tots els games tenen context omplert.
    row = conn.execute(
        "SELECT arbitre, equip1_id, equip2_id, encontre_lliga_id, temporada_id, serie_max1 "
        "FROM games LIMIT 1"
    ).fetchone()
    assert row[0] is not None  # arbitre
    assert row[1] is not None and row[2] is not None  # equips
    assert row[3] == result.encontre_lliga_id
    assert row[4] is not None  # temporada derivada de la data
    assert row[5] is not None  # serie_max1 (camp ric de lliga)


def test_ingest_lliga_encontre_skips_unknown_players(settings: StubSettings) -> None:
    """Sense pre-popular jugadors, totes les 4 partides es salten."""
    fixtures = {
        "https://www.fcbillar.cat/ca/lligues/partides/36/148/316/2593/10939": (
            "lliga_3b_encontre_partides.html"
        ),
    }
    client = StubScraperClient(settings, fixtures)
    encontre = LligaEncontre(
        lliga_id=36, divisio_id=148, grup_id=316, jornada_id=2593, encontre_id=10939,
        equip_local='C.B. SANTS "A"', p_parcials_local=5, p_match_local=3,
        equip_visitant='SB FOMENT MOLINS "A"', p_parcials_visitant=3, p_match_visitant=0,
    )
    result = ingest_lliga_encontre(
        client, encontre, modalitat_codi_fcb=1, data=date(2025, 9, 27), settings=settings
    )
    assert result.games_upserted == 0
    assert result.games_skipped_missing_player == 4
    # L'encontre, clubs i equips sí s'han creat (per estar disponibles per a
    # ingestes posteriors).
    counts = Repository(ensure_schema(settings.db_path)).counts()
    assert counts["encontres_lliga"] == 1
    assert counts["clubs"] == 2
    assert counts["equips"] == 2


def test_ingest_lliga_encontre_enriches_existing_game(settings: StubSettings) -> None:
    """Si una partida ja venia de partideshome (sense club/àrbitre), ingest_lliga
    la complementa amb els camps de lliga via COALESCE."""
    fixtures = {
        "https://www.fcbillar.cat/ca/lligues/partides/36/148/316/2593/10939": (
            "lliga_3b_encontre_partides.html"
        ),
    }
    client = StubScraperClient(settings, fixtures)

    # Pre-popular els 2 jugadors de la 1a partida.
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    from datetime import date as _date
    from fcbillar.models import Game, Player

    repo.upsert_player(Player(fcb_id="60", nom="VARELA LOSADA, FRANCESC"))
    repo.upsert_player(Player(fcb_id="70", nom="PERALES SANZ, JOAN"))
    # Crear el game "antic" (com el faria ingest_partides): mínim, sense camps de lliga.
    old_game = Game(
        data_partida=_date(2025, 9, 27),
        competicio_nom="LLIGA",
        modalitat_codi_fcb=1,
        player1_fcb_id="60",
        player2_fcb_id="70",
        caramboles1=40,
        caramboles2=24,
        entrades=40,
    )
    repo.upsert_game(old_game)

    encontre = LligaEncontre(
        lliga_id=36, divisio_id=148, grup_id=316, jornada_id=2593, encontre_id=10939,
        equip_local='C.B. SANTS "A"', p_parcials_local=5, p_match_local=3,
        equip_visitant='SB FOMENT MOLINS "A"', p_parcials_visitant=3, p_match_visitant=0,
    )
    # Per a aquesta verificació només cal que un dels jugadors resolgui, però
    # la fixture té 4 partides i 8 jugadors; els altres es saltaran sense impacte.
    ingest_lliga_encontre(
        client, encontre, modalitat_codi_fcb=1, data=_date(2025, 9, 27), settings=settings
    )

    # Verificar que el game existent s'ha enriquit (arbitre + serie_max + equips).
    row = conn.execute(
        "SELECT arbitre, serie_max1, serie_max2, equip1_id, equip2_id, temporada_id "
        "FROM games WHERE id = ?",
        (old_game.id_natural,),
    ).fetchone()
    assert row[0] == "BOTERO"  # arbitre afegit
    assert row[1] == 6  # serie_max1 afegida
    assert row[2] == 3
    assert row[3] is not None and row[4] is not None
    assert row[5] is not None  # temporada derivada de 2025-09-27 = "2025-2026"


# ---------------- ingest_lliga_jornada ----------------


def test_ingest_lliga_jornada_processes_all_encontres(settings: StubSettings) -> None:
    """La jornada té 4 encontres; cadascun amb 4 partides individuals.

    Reutilitzem la mateixa fixture de partides per als 4 encontres (no és exacte,
    però permet validar el flow end-to-end: 4 encontres × 4 partides = 16 vistes).
    """
    fixtures = {
        "https://www.fcbillar.cat/ca/lligues/encontres/36/148/316/2593": (
            "lliga_3b_jornada01_encontres.html"
        ),
        # Mateixa fixture per als 4 encontres → 16 vistes amb molts noms iguals
        # (els 8 jugadors de la fixture).
        "https://www.fcbillar.cat/ca/lligues/partides/36/148/316/2593/10939": (
            "lliga_3b_encontre_partides.html"
        ),
        "https://www.fcbillar.cat/ca/lligues/partides/36/148/316/2593/10941": (
            "lliga_3b_encontre_partides.html"
        ),
        "https://www.fcbillar.cat/ca/lligues/partides/36/148/316/2593/10943": (
            "lliga_3b_encontre_partides.html"
        ),
        "https://www.fcbillar.cat/ca/lligues/partides/36/148/316/2593/10945": (
            "lliga_3b_encontre_partides.html"
        ),
    }
    client = StubScraperClient(settings, fixtures)
    # Sense pre-popular jugadors → totes les partides es saltaran. Verifiquem
    # només l'orquestració d'encontres.
    result = ingest_lliga_jornada(
        client,
        lliga_id=36,
        divisio_id=148,
        grup_id=316,
        jornada_id=2593,
        modalitat_codi_fcb=1,
        data=date(2025, 9, 27),
        settings=settings,
    )
    assert result.encontres_processed == 4
    assert result.encontres_failed == 0
    assert result.total_games_skipped == 16  # 4 encontres × 4 partides
    assert result.total_games_upserted == 0

    # Tots els encontres + 8 equips (4 locals + 4 visitants) creats; 7 clubs
    # perquè SANT ADRIÀ té tant equip A com B → mateix club, dos equips.
    counts = Repository(ensure_schema(settings.db_path)).counts()
    assert counts["encontres_lliga"] == 4
    assert counts["equips"] == 8
    assert counts["clubs"] == 7
