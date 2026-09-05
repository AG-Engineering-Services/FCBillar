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
    ingest_lliga_grup,
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
    "https://www.fcbillar.cat/frontend/rankings/llistat": "nou/rankings_llistat.html",
    "https://www.fcbillar.cat/frontend/rankings/llistat-dades?idranking=124&idmodalitat=1": "nou/rankings_dades_vigent_124_1.html",
    "https://www.fcbillar.cat/frontend/rankings/llistat-dades?idranking=124&idmodalitat=6": "nou/rankings_dades_historic_123_6.html",
    "https://www.fcbillar.cat/frontend/rankings/llistat-partides?idranking=124&idmodalitat=1&idjugador=843": "nou/rankings_partides_vigent_124_1_843.html",
    "https://www.fcbillar.cat/frontend/rankings/historial-partides?idranking=123&idmodalitat=1&idjugador=843": "nou/rankings_partides_historic_123_1_843.html",
}


# ---------------- ingest_ranking ----------------


def test_ingest_ranking_inserts_players_and_entries(settings: StubSettings) -> None:
    client = StubScraperClient(settings, URL_FIXTURES)
    result = ingest_ranking(client, num_seq=124, modalitat_codi_fcb=1, settings=settings)

    assert result is not None
    assert result.players_upserted == 715
    assert result.entries_upserted == 715
    assert result.fetch.fmt == "llistat"

    counts = Repository(ensure_schema(settings.db_path)).counts()
    assert counts["rankings"] == 1
    assert counts["players"] == 715
    assert counts["ranking_entries"] == 715


def test_ingest_ranking_is_idempotent(settings: StubSettings) -> None:
    """Tornar a fer ingest del mateix rànquing no crea duplicats."""
    client = StubScraperClient(settings, URL_FIXTURES)
    ingest_ranking(client, 124, 1, settings=settings)
    ingest_ranking(client, 124, 1, settings=settings)
    counts = Repository(ensure_schema(settings.db_path)).counts()
    assert counts["rankings"] == 1
    assert counts["players"] == 715
    assert counts["ranking_entries"] == 715


# ---------------- ingest_partides ----------------


def test_ingest_partides_requires_ranking_in_db(settings: StubSettings) -> None:
    """Si el rànquing referenciat no està a la BD, ha de fallar amb missatge clar."""
    # Inserim primer el player però NO el rànquing.
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    from fcbillar.models import Player

    repo.upsert_player(Player(fcb_id="843", nom="MAS CANADELL, JOSEP Mª"))
    client = StubScraperClient(settings, URL_FIXTURES)
    with pytest.raises(ValueError, match="Rànquing 124/1 no està a la BD"):
        ingest_partides(client, 124, 1, "843", settings=settings)


def test_ingest_partides_requires_player_in_db(settings: StubSettings) -> None:
    """Si el player referenciat no està a la BD, missatge clar."""
    client = StubScraperClient(settings, URL_FIXTURES)
    ingest_ranking(client, 124, 1, settings=settings)
    with pytest.raises(ValueError, match="Player 99999 no està a la BD"):
        ingest_partides(client, 124, 1, "99999", settings=settings)


def test_ingest_partides_persists_games_and_links(settings: StubSettings) -> None:
    """Ingest de punta a punta: les partides de Mas Canadell al rànquing vigent."""
    client = StubScraperClient(settings, URL_FIXTURES)
    ingest_ranking(client, 124, 1, settings=settings)

    res = ingest_partides(client, 124, 1, "843", settings=settings)
    assert res.games_upserted == 15
    assert res.games_skipped_missing_opponent == 0
    assert res.links_created == 15

    counts = Repository(ensure_schema(settings.db_path)).counts()
    assert counts["games"] == 15
    assert counts["ranking_game_links"] == 15
    assert counts["competicions"] == 2  # LLIGA + INDIVIDUAL


# ---------------- sync_current_rankings ----------------


def test_sync_ingests_what_stub_can_serve(settings: StubSettings) -> None:
    """Sync ha d'ingerir els rànquings que el stub serveix i ignorar la resta.

    `fetch_ranking_html` captura excepcions com a warning i retorna None;
    `sync_current_rankings` només marca com a `ingested` les que han anat bé.
    """
    fixtures = {
        "https://www.fcbillar.cat/frontend/rankings/llistat": "nou/rankings_llistat.html",
        "https://www.fcbillar.cat/frontend/rankings/llistat-dades?idranking=124&idmodalitat=1": (
            "nou/rankings_dades_vigent_124_1.html"
        ),
        "https://www.fcbillar.cat/frontend/rankings/llistat-dades?idranking=124&idmodalitat=6": (
            "nou/rankings_dades_historic_123_6.html"
        ),
    }
    client = StubScraperClient(settings, fixtures)
    result = sync_current_rankings(client, settings=settings)

    assert set(result.ingested) == {(124, 1), (124, 6)}
    assert result.skipped_existing == []

    counts = Repository(ensure_schema(settings.db_path)).counts()
    assert counts["rankings"] == 2


def test_sync_skips_when_db_at_or_above_current(settings: StubSettings) -> None:
    """Si la BD ja té el num_seq actual, sync no ingereix res."""
    # Pre-popular la BD amb el rànquing 124 per a totes les modalitats.
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    from fcbillar.models import Ranking

    for mod in (1, 2, 3, 4, 6):
        repo.upsert_ranking(
            Ranking(num_seq=124, modalitat_codi_fcb=mod, url="x", format_url="llistat")
        )

    client = StubScraperClient(
        settings,
        {"https://www.fcbillar.cat/frontend/rankings/llistat": "nou/rankings_llistat.html"},
    )
    result = sync_current_rankings(client, settings=settings)
    assert result.ingested == []
    assert len(result.skipped_existing) == 5


# ---------------- backfill_modalitat ----------------


def test_backfill_top_n_processes_only_top(settings: StubSettings) -> None:
    """backfill amb --top 1 processa només el jugador rànquing 1."""
    client = StubScraperClient(settings, URL_FIXTURES)
    result = backfill_modalitat(client, modalitat_codi_fcb=1, top_n=1, settings=settings)
    assert result.players_processed == 1
    # El número 1 de tres bandes és Mas Canadell (843), amb 15 partides.
    assert result.total_games_upserted == 15


def test_backfill_unknown_modalitat_raises(settings: StubSettings) -> None:
    client = StubScraperClient(
        settings,
        {"https://www.fcbillar.cat/frontend/rankings/llistat": "nou/rankings_llistat.html"},
    )
    with pytest.raises(ValueError, match="Modalitat 99"):
        backfill_modalitat(client, 99, settings=settings)


def test_backfill_only_followed_skips_non_followed(settings: StubSettings) -> None:
    """only_followed=True processa només jugadors amb seguiment=1."""
    client = StubScraperClient(settings, URL_FIXTURES)
    # Ingest del rànquing primer per poder marcar el follow.
    ingest_ranking(client, 124, 1, settings=settings)
    repo = Repository(ensure_schema(settings.db_path))
    repo.set_seguiment("843", True)

    # Torno a fer backfill amb only_followed: només ha de processar Mas Canadell.
    result = backfill_modalitat(client, modalitat_codi_fcb=1, only_followed=True, settings=settings)
    assert result.players_processed == 1
    assert result.total_games_upserted == 15


# ---------------- backfill_historical ----------------


def test_backfill_ranking_with_no_partides(settings: StubSettings) -> None:
    """backfill_ranking amb top_n=0 ingest només el rànquing, no les partides."""
    client = StubScraperClient(settings, URL_FIXTURES)
    res = backfill_ranking(client, 124, 1, top_n=0, settings=settings)
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
        "https://www.fcbillar.cat/frontend/rankings/llistat": "nou/rankings_llistat.html",
        "https://www.fcbillar.cat/frontend/rankings/historial-dades?idranking=123&idmodalitat=6": (
            "nou/rankings_dades_historic_123_6.html"
        ),
    }
    client = StubScraperClient(settings, fixtures)
    res = backfill_historical(client, modalitat_codi_fcb=6, top_n=0, settings=settings)
    # 1 OK (el 123/6, que és el que tenim capturat) + 14 sense fixture.
    assert res.rankings_processed == [(123, 6)]
    assert len(res.rankings_failed) == 14
    assert res.total_players_processed == 0  # top_n=0 evita partides
    assert res.total_games_upserted == 0


def test_backfill_historical_filters_by_modalitat(settings: StubSettings) -> None:
    """Amb modalitat_codi_fcb=None, processa totes les modalitats (15×5=75 entries)."""
    fixtures = {
        "https://www.fcbillar.cat/frontend/rankings/llistat": "nou/rankings_llistat.html",
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
        "https://www.fcbillar.cat/frontend/lligues/partides/36/148/316/2593/10939": (
            "nou/lligues_partides_RECONSTRUIT_36_148_316_2593_10939.html"
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
    # Cap game NOU: `games` s'alimenta de partideshome, que és el rànquing
    # oficial, i la pàgina de lliga només l'enriqueix amb el context de la
    # competició. Aquí no s'ha ingerit partideshome, o sigui que no hi ha res a
    # enriquir i les quatre partides queden pendents.
    assert result.games_upserted == 0
    assert result.games_skipped_missing_player == 4

    counts = repo.counts()
    assert counts["clubs"] == 2  # C.B. SANTS + SB FOMENT MOLINS
    assert counts["equips"] == 2  # ambdós amb lletra A
    assert counts["encontres_lliga"] == 1
    assert counts["temporades"] == 1  # derivada de la data

    # Però no es perden: van a `lliga_pending_partides`, que és d'on surten les
    # partides jugades que el rànquing oficial encara no ha recollit.
    pendents = conn.execute(
        "SELECT player1_nom, caramboles1, entrades, encontre_lliga_id "
        "FROM lliga_pending_partides ORDER BY player1_nom"
    ).fetchall()
    assert len(pendents) == 4
    assert all(r[3] == result.encontre_lliga_id for r in pendents)
    assert all(r[2] > 0 for r in pendents), "sense entrades no serien partides jugades"

    # El context de la competició sí que s'ha desat: l'encontre, els equips i la
    # temporada derivada de la data.
    enc = conn.execute(
        "SELECT equip_local_id, equip_visitant_id, temporada_id FROM encontres_lliga"
    ).fetchone()
    assert enc[0] is not None and enc[1] is not None
    assert enc[2] is not None


def test_ingest_lliga_encontre_skips_unknown_players(settings: StubSettings) -> None:
    """Sense pre-popular jugadors, totes les 4 partides es salten."""
    fixtures = {
        "https://www.fcbillar.cat/frontend/lligues/partides/36/148/316/2593/10939": (
            "nou/lligues_partides_RECONSTRUIT_36_148_316_2593_10939.html"
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
        "https://www.fcbillar.cat/frontend/lligues/partides/36/148/316/2593/10939": (
            "nou/lligues_partides_RECONSTRUIT_36_148_316_2593_10939.html"
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


def test_build_game_from_lliga_row_keeps_played_with_zero_entrades(
    settings: StubSettings,
) -> None:
    """Una partida realment jugada (amb caramboles) NO s'ha de descartar encara
    que les entrades constin a 0 a la federacio. Cas real: Jornada 12,
    Banyoles A-Barcelona A, Ametller 28-27 Gutierrez amb Entrades 0."""
    from fcbillar.pipeline import _build_game_from_lliga_row
    from fcbillar.scraper.parsers import LligaPartidaRow

    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)

    row = LligaPartidaRow(
        data_partida=date(2026, 1, 15),
        modalitat="Tres bandes",
        local_nom="AMETLLER CONGOST, LLUIS",
        local_caramboles=28,
        local_serie_major=4,
        local_punts=2,
        visitant_nom="GUTIERREZ CONTRERAS, ARNOLD",
        visitant_caramboles=27,
        visitant_serie_major=3,
        visitant_punts=0,
        entrades=0,
        arbitre=None,
        assistencia="Partit disputat",
    )
    game = _build_game_from_lliga_row(
        row,
        encontre_data=date(2026, 1, 15),
        modalitat_codi_fcb=1,
        competicio_nom="LLIGA",
        local_equip_id=1,
        visitant_equip_id=2,
        encontre_lliga_id=10,
        temporada_id=None,
        repo=repo,
        create_missing_players=True,
    )
    assert game is not None
    assert game.caramboles1 == 28
    assert game.caramboles2 == 27
    assert game.entrades == 0


def test_build_game_from_lliga_row_skips_real_walkover(
    settings: StubSettings,
) -> None:
    """Una incompareixença real (cap resultat: 0 caramboles, 0 entrades, sense
    assistència) sí que s'ha de seguir descartant."""
    from fcbillar.pipeline import _build_game_from_lliga_row
    from fcbillar.scraper.parsers import LligaPartidaRow

    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)

    row = LligaPartidaRow(
        data_partida=date(2026, 1, 15),
        modalitat="Tres bandes",
        local_nom="JUGADOR LOCAL, A",
        local_caramboles=0,
        local_serie_major=0,
        local_punts=0,
        visitant_nom="JUGADOR VISITANT, B",
        visitant_caramboles=0,
        visitant_serie_major=0,
        visitant_punts=0,
        entrades=0,
        arbitre=None,
        assistencia=None,
    )
    game = _build_game_from_lliga_row(
        row,
        encontre_data=date(2026, 1, 15),
        modalitat_codi_fcb=1,
        competicio_nom="LLIGA",
        local_equip_id=1,
        visitant_equip_id=2,
        encontre_lliga_id=10,
        temporada_id=None,
        repo=repo,
        create_missing_players=True,
    )
    assert game is None


class _FakeRepoDistLimit:
    """Repo minim que nomes respon infer_lliga_distance_limit, per provar la regla."""

    def __init__(self, dist: int | None, lim: int | None) -> None:
        self._d = (dist, lim)

    def infer_lliga_distance_limit(self, **_kwargs: object) -> tuple[int | None, int | None]:
        return self._d


def test_impute_lliga_entrades_full_distance_match() -> None:
    """28-27 amb distancia 40: ningu hi arriba -> entrades = limit (50)."""
    from fcbillar.pipeline import _impute_lliga_entrades

    repo = _FakeRepoDistLimit(40, 50)
    assert (
        _impute_lliga_entrades(
            repo,
            lliga_id=36,
            divisio_id=148,
            grup_id=317,
            modalitat_codi_fcb=1,
            caramboles1=28,
            caramboles2=27,
        )
        == 50
    )


def test_impute_lliga_entrades_someone_reached_distance() -> None:
    """Si un jugador arriba a la distancia, la partida es va acabar abans del
    limit i no es pot inferir -> None."""
    from fcbillar.pipeline import _impute_lliga_entrades

    repo = _FakeRepoDistLimit(40, 50)
    assert (
        _impute_lliga_entrades(
            repo,
            lliga_id=36,
            divisio_id=148,
            grup_id=317,
            modalitat_codi_fcb=1,
            caramboles1=40,
            caramboles2=15,
        )
        is None
    )


def test_impute_lliga_entrades_uses_tres_bandes_constant_limit() -> None:
    """A tres bandes el limit es 50 encara que no s'inferexi de les dades."""
    from fcbillar.pipeline import _impute_lliga_entrades

    repo = _FakeRepoDistLimit(40, None)  # limit no inferible del grup
    assert (
        _impute_lliga_entrades(
            repo,
            lliga_id=36,
            divisio_id=148,
            grup_id=317,
            modalitat_codi_fcb=1,
            caramboles1=28,
            caramboles2=27,
        )
        == 50
    )


def test_impute_lliga_entrades_no_reference_data() -> None:
    """Sense distancia de referencia no es pot imputar -> None."""
    from fcbillar.pipeline import _impute_lliga_entrades

    repo = _FakeRepoDistLimit(None, None)
    assert (
        _impute_lliga_entrades(
            repo,
            lliga_id=36,
            divisio_id=148,
            grup_id=317,
            modalitat_codi_fcb=1,
            caramboles1=28,
            caramboles2=27,
        )
        is None
    )


# ---------------- unificació de noms de clubs ----------------


def test_ingest_lliga_reuses_existing_club_via_normalization(
    settings: StubSettings,
) -> None:
    """Si la BD ja té un club amb nom canònic (ex. 'C.B.SANTS' del listing oficial),
    ingest_lliga reutilitza aquest club enlloc de crear-ne un de nou amb el
    nom variant ('C.B. SANTS') de la lliga."""
    from fcbillar.models import Club

    fixtures = {
        "https://www.fcbillar.cat/frontend/lligues/partides/36/148/316/2593/10939": (
            "nou/lligues_partides_RECONSTRUIT_36_148_316_2593_10939.html"
        ),
    }
    client = StubScraperClient(settings, fixtures)

    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    # Pre-popular els clubs amb noms canònics del listing oficial.
    repo.upsert_club(Club(fcb_id="C.B.SANTS", nom="C.B.SANTS"))
    repo.upsert_club(Club(fcb_id="S.B.F.MOLINS", nom="S.B.F.MOLINS"))
    # Afegim alias per al cas que la normalització no captura.
    repo.add_club_alias("SB FOMENT MOLINS", "S.B.F.MOLINS")
    assert repo.counts()["clubs"] == 2

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
    ingest_lliga_encontre(
        client,
        encontre,
        modalitat_codi_fcb=1,
        data=date(2025, 9, 27),
        create_missing_players=True,
        settings=settings,
    )

    # Cap club nou: els dos existeixen al listing i s'han reutilitzat.
    counts = repo.counts()
    assert counts["clubs"] == 2
    assert counts["equips"] == 2  # C.B.SANTS A + S.B.F.MOLINS A


# ---------------- create_missing_players ----------------


def test_ingest_lliga_encontre_create_missing_persists_all(
    settings: StubSettings,
) -> None:
    """Amb create_missing_players=True es crea el jugador encara que no el tinguem.

    Els placeholders no són per desar el game -els games venen de partideshome-
    sinó perquè la partida pendent i el context de la competició puguin apuntar a
    algú. Quan el rànquing porti el jugador de debò, es fusionen.
    """
    fixtures = {
        "https://www.fcbillar.cat/frontend/lligues/partides/36/148/316/2593/10939": (
            "nou/lligues_partides_RECONSTRUIT_36_148_316_2593_10939.html"
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
    result = ingest_lliga_encontre(
        client,
        encontre,
        modalitat_codi_fcb=1,
        data=date(2025, 9, 27),
        create_missing_players=True,
        settings=settings,
    )
    assert result.games_upserted == 0
    assert result.games_skipped_missing_player == 4

    conn = ensure_schema(settings.db_path)
    counts = Repository(conn).counts()
    assert counts["players"] == 8  # tots placeholders
    # Les quatre partides queden pendents fins que el rànquing oficial les
    # reculli; el que s'ha creat són els jugadors, no els games.
    assert conn.execute("SELECT COUNT(*) FROM lliga_pending_partides").fetchone()[0] == 4


def test_placeholder_fusion_after_ranking_ingest(settings: StubSettings) -> None:
    """Si primer ingerim lliga amb placeholders i després el rànquing amb fcb_id
    real, els placeholders es fusionen automàticament i el que hi apuntava NO es
    perd: la promoció conserva l'id intern."""
    # Pas 1: ingest lliga amb placeholders
    lliga_fixtures = {
        "https://www.fcbillar.cat/frontend/lligues/partides/36/148/316/2593/10939": (
            "nou/lligues_partides_RECONSTRUIT_36_148_316_2593_10939.html"
        ),
    }
    client = StubScraperClient(settings, lliga_fixtures)
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
    ingest_lliga_encontre(
        client,
        encontre,
        modalitat_codi_fcb=1,
        data=date(2025, 9, 27),
        create_missing_players=True,
        settings=settings,
    )

    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    counts_before = repo.counts()
    assert counts_before["players"] == 8

    # Pas 2: upsert d'un Player real amb mateix nom → fusió
    from fcbillar.models import Player

    # VARELA LOSADA, FRANCESC apareixia com a placeholder; ara arriba amb fcb_id real "60".
    placeholder_player_id = repo.get_player_id_by_fcb_id("name:VARELA LOSADA, FRANCESC")
    assert placeholder_player_id is not None
    real_player_id = repo.upsert_player(Player(fcb_id="60", nom="VARELA LOSADA, FRANCESC"))

    # Mateix id intern → la fila game segueix apuntant al mateix players.id
    assert real_player_id == placeholder_player_id
    # El placeholder ha desaparegut, el real existeix
    assert repo.get_player_id_by_fcb_id("name:VARELA LOSADA, FRANCESC") is None
    assert repo.get_player_id_by_fcb_id("60") == real_player_id
    # Cap player nou: 8 → 8 (el placeholder s'ha promogut a real, no s'ha creat un altre)
    assert repo.counts()["players"] == 8
    # Conservar l'id és tota la gràcia: qualsevol fila que apunti al jugador
    # -els games que arribin de partideshome, els enllaços del rànquing- hi
    # segueix apuntant sense haver-la de tocar.
    assert repo.get_player_id_by_fcb_id("60") == placeholder_player_id


# ---------------- ingest_lliga_jornada ----------------


def test_ingest_lliga_jornada_processes_all_encontres(settings: StubSettings) -> None:
    """La jornada té 4 encontres; cadascun amb 4 partides individuals.

    Reutilitzem la mateixa fixture de partides per als 4 encontres (no és exacte,
    però permet validar el flow end-to-end: 4 encontres × 4 partides = 16 vistes).
    """
    fixtures = {
        "https://www.fcbillar.cat/frontend/lligues/encontres/36/148/316/2593": (
            "nou/lligues_encontres_36_148_316_2593.html"
        ),
        # Mateixa fixture per als 4 encontres → 16 vistes amb molts noms iguals
        # (els 8 jugadors de la fixture).
        "https://www.fcbillar.cat/frontend/lligues/partides/36/148/316/2593/10939": (
            "nou/lligues_partides_RECONSTRUIT_36_148_316_2593_10939.html"
        ),
        "https://www.fcbillar.cat/frontend/lligues/partides/36/148/316/2593/10941": (
            "nou/lligues_partides_RECONSTRUIT_36_148_316_2593_10939.html"
        ),
        "https://www.fcbillar.cat/frontend/lligues/partides/36/148/316/2593/10943": (
            "nou/lligues_partides_RECONSTRUIT_36_148_316_2593_10939.html"
        ),
        "https://www.fcbillar.cat/frontend/lligues/partides/36/148/316/2593/10945": (
            "nou/lligues_partides_RECONSTRUIT_36_148_316_2593_10939.html"
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


# ---------------- ingest_lliga_grup ----------------


def test_ingest_lliga_grup_iterates_jornades(settings: StubSettings) -> None:
    """ingest_lliga_grup descobreix les 14 jornades del GRUP A HONOR i les itera.

    Només mappejem fixtures per la jornada 01 (les altres 13 fallaran a fetch
    encontres, però el comptador failed ho reflectirà sense petar).
    """
    fixtures = {
        "https://www.fcbillar.cat/frontend/lligues/jornades/36/148/316": (
            "nou/lligues_jornades_36_148_316.html"
        ),
        # Només jornada 01 té fixture; els altres jornada_id fallaran amb KeyError.
        "https://www.fcbillar.cat/frontend/lligues/encontres/36/148/316/2593": (
            "nou/lligues_encontres_36_148_316_2593.html"
        ),
        "https://www.fcbillar.cat/frontend/lligues/partides/36/148/316/2593/10939": (
            "nou/lligues_partides_RECONSTRUIT_36_148_316_2593_10939.html"
        ),
        "https://www.fcbillar.cat/frontend/lligues/partides/36/148/316/2593/10941": (
            "nou/lligues_partides_RECONSTRUIT_36_148_316_2593_10939.html"
        ),
        "https://www.fcbillar.cat/frontend/lligues/partides/36/148/316/2593/10943": (
            "nou/lligues_partides_RECONSTRUIT_36_148_316_2593_10939.html"
        ),
        "https://www.fcbillar.cat/frontend/lligues/partides/36/148/316/2593/10945": (
            "nou/lligues_partides_RECONSTRUIT_36_148_316_2593_10939.html"
        ),
    }
    client = StubScraperClient(settings, fixtures)
    result = ingest_lliga_grup(
        client,
        lliga_id=36,
        divisio_id=148,
        grup_id=316,
        modalitat_codi_fcb=1,
        create_missing_players=True,  # perquè la jornada 01 desi els games
        settings=settings,
    )
    # 14 jornades trobades, 1 processada OK (la 01), 13 fallades (KeyError).
    assert result.jornades_processed == 1
    assert result.jornades_failed == 13
    assert result.total_encontres == 4  # només de la jornada 01
    # Cap game nou: `games` s'alimenta de partideshome i la pàgina de lliga
    # només l'enriqueix. Aquí no s'ha ingerit, o sigui que les 16 partides
    # queden pendents en comptes de crear-se.
    assert result.total_games_upserted == 0
    assert result.total_games_skipped == 16
