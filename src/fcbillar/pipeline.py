"""Orquestració de la ingesta."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date

from fcbillar.config import Settings, get_settings
from fcbillar.db.migrations import ensure_schema
from fcbillar.db.repository import Repository
from fcbillar.models import (
    Club,
    EncontreLliga,
    Equip,
    Game,
    Ranking,
    RankingGameLink,
    Temporada,
)
from fcbillar.scraper.client import ScraperClient
from fcbillar.scraper.parsers import (
    HistorialEntry,
    HomeRankingsResult,
    LligaEncontre,
    LligaPartidaRow,
    RawGameRow,
    parse_home_current_rankings,
    parse_lliga_encontres,
    parse_lliga_partides,
    parse_partides_jugador,
    parse_ranking,
    parse_ranking_historial,
)
from fcbillar.scraper.url_builder import all_ranking_url_candidates

log = logging.getLogger(__name__)


@dataclass
class FetchResult:
    url: str
    fmt: str
    html: str


@dataclass
class IngestRankingResult:
    fetch: FetchResult
    players_upserted: int
    entries_upserted: int


def fetch_ranking_html(
    client: ScraperClient,
    num_seq: int,
    modalitat_codi_fcb: int,
    *,
    preferred_format: str | None = None,
) -> FetchResult | None:
    """Prova els formats d'URL i retorna el primer que retorni rànquing parsejable.

    Amb `preferred_format` (p.ex. 'data' o 'datahome'), prova aquest primer
    i l'altre com a fallback. Sense, l'ordre per defecte de
    `all_ranking_url_candidates` és 'datahome' primer (rànquing actual).
    """
    settings = client.settings
    candidates = all_ranking_url_candidates(settings.base_url, num_seq, modalitat_codi_fcb)
    if preferred_format is not None:
        candidates = sorted(
            candidates, key=lambda c: 0 if c[0] == preferred_format else 1
        )
    for fmt, url in candidates:
        try:
            html = client.fetch_html(url)
        except Exception as e:
            log.warning("Fallat fetch %s: %s", url, e)
            continue
        if _looks_like_valid_ranking(html):
            return FetchResult(url=url, fmt=fmt, html=html)
        log.info("URL %s retorna HTML però no sembla rànquing vàlid", url)
    return None


def _looks_like_valid_ranking(html: str) -> bool:
    """Heurística estricta: rànquing vàlid té la secció principal + una taula.

    El portal sovint serveix una pàgina d'error 'silenciosa' (200 OK, HTML
    petit) quan demanes un num_seq amb el format equivocat (p.ex. 'datahome'
    per a un rànquing antic). Aquesta heurística evita acceptar-la.
    """
    if not html or len(html) < 500:
        return False
    if "formloguinacion" in html:
        return False
    # La secció + taula són el marcador estructural del rànquing.
    if "three fourths padded" not in html or "<table" not in html:
        return False
    return True


def ingest_ranking(
    client: ScraperClient,
    num_seq: int,
    modalitat_codi_fcb: int,
    *,
    settings: Settings | None = None,
    preferred_format: str | None = None,
) -> IngestRankingResult | None:
    """Descarrega un rànquing, el parseja i el persisteix a la BD."""
    settings = settings or client.settings
    fetched = fetch_ranking_html(
        client, num_seq, modalitat_codi_fcb, preferred_format=preferred_format
    )
    if fetched is None:
        return None

    parsed = parse_ranking(fetched.html, num_seq, modalitat_codi_fcb)

    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    ranking_id = repo.upsert_ranking(
        Ranking(
            num_seq=num_seq,
            modalitat_codi_fcb=modalitat_codi_fcb,
            url=fetched.url,
            format_url=fetched.fmt,
        )
    )
    # Upsert primer tots els jugadors perquè les entries els referencien.
    for player in parsed.players:
        repo.upsert_player(player)
    for entry in parsed.entries:
        repo.upsert_ranking_entry(ranking_id, entry)

    log.info(
        "Ingerit rànquing %s/%s: %d jugadors, %d entries",
        num_seq,
        modalitat_codi_fcb,
        len(parsed.players),
        len(parsed.entries),
    )
    return IngestRankingResult(
        fetch=fetched,
        players_upserted=len(parsed.players),
        entries_upserted=len(parsed.entries),
    )


@dataclass
class IngestPartidesResult:
    games_upserted: int
    games_skipped_missing_opponent: int
    links_created: int


# Mapeig de format del rànquing → segment de la URL de partides per jugador.
# Mateix patró que rànquings: 'datahome' (actual) usa 'partideshome', 'data'
# (històric) usa 'partides'.
_PARTIDES_SEGMENT_BY_FORMAT = {
    "datahome": "partideshome",
    "data": "partides",
}


def _partides_url(
    base_url: str,
    num_seq: int,
    modalitat: int,
    player_fcb_id: str,
    format_url: str = "datahome",
) -> str:
    segment = _PARTIDES_SEGMENT_BY_FORMAT.get(format_url, "partideshome")
    return (
        f"{base_url.rstrip('/')}/ca/jugador/ranking/{segment}/"
        f"{num_seq}/{modalitat}/{player_fcb_id}"
    )


def ingest_partides(
    client: ScraperClient,
    num_seq: int,
    modalitat_codi_fcb: int,
    player_fcb_id: str,
    *,
    settings: Settings | None = None,
) -> IngestPartidesResult:
    """Descarrega partideshome d'un jugador en un rànquing i les persisteix.

    El portal exposa noms però no fcb_ids dels contraris. Resolem nom → fcb_id
    contra els players ja existents a la BD (vinguts d'un rànquing previ). Si
    el contrari no existeix, saltem la partida i ho comptabilitzem.

    Requereix que el rànquing (num_seq, modalitat) ja estigui inserit a la BD
    perquè la traçabilitat ranking_game_links pugui referenciar-lo.
    """
    settings = settings or client.settings
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)

    owner_nom = repo.get_player_nom_by_fcb_id(player_fcb_id)
    if owner_nom is None:
        raise ValueError(
            f"Player {player_fcb_id} no està a la BD; "
            f"ingest primer el rànquing on apareix."
        )
    format_url = repo.get_ranking_format_url(num_seq, modalitat_codi_fcb)
    if format_url is None:
        raise ValueError(
            f"Rànquing {num_seq}/{modalitat_codi_fcb} no està a la BD; "
            f"`ingest-ranking {num_seq} {modalitat_codi_fcb}` primer."
        )

    url = _partides_url(
        settings.base_url, num_seq, modalitat_codi_fcb, player_fcb_id, format_url=format_url
    )
    html = client.fetch_html(url)
    parsed = parse_partides_jugador(html)

    upserted = 0
    skipped = 0
    links = 0
    for row in parsed.rows:
        game = _build_game_from_raw_row(row, modalitat_codi_fcb, owner_nom, repo)
        if game is None:
            skipped += 1
            continue
        repo.upsert_game(game)
        upserted += 1
        repo.link_game_to_ranking(
            RankingGameLink(
                ranking_num_seq=num_seq,
                ranking_modalitat=modalitat_codi_fcb,
                game_id=game.id_natural,
                player_fcb_id_origen=player_fcb_id,
            )
        )
        links += 1

    log.info(
        "Partides %s/%s/%s: %d desades, %d saltades (contraris no a BD), %d links",
        num_seq,
        modalitat_codi_fcb,
        player_fcb_id,
        upserted,
        skipped,
        links,
    )
    return IngestPartidesResult(
        games_upserted=upserted,
        games_skipped_missing_opponent=skipped,
        links_created=links,
    )


def _build_game_from_raw_row(
    row: RawGameRow,
    modalitat_codi_fcb: int,
    owner_nom: str,
    repo: Repository,
) -> Game | None:
    """Resol noms a fcb_ids i construeix un Game. Retorna None si no es pot."""
    local_fcb = repo.get_player_fcb_id_by_nom(row.local_nom)
    visitant_fcb = repo.get_player_fcb_id_by_nom(row.visitant_nom)
    if local_fcb is None or visitant_fcb is None:
        log.debug(
            "Salto partida %s %s vs %s: local_fcb=%s visitant_fcb=%s",
            row.data_partida,
            row.local_nom,
            row.visitant_nom,
            local_fcb,
            visitant_fcb,
        )
        return None
    # Sanity check: l'owner ha de coincidir amb local o visitant.
    if owner_nom not in (row.local_nom, row.visitant_nom):
        log.warning(
            "Owner %r no apareix com a local/visitant a fila %s: %r vs %r",
            owner_nom,
            row.data_partida,
            row.local_nom,
            row.visitant_nom,
        )
    # Guanyador: el que té més punts (sistema lliga 0/1/2; en individual 0/2).
    guanyador_fcb: str | None = None
    if row.local_punts is not None and row.visitant_punts is not None:
        if row.local_punts > row.visitant_punts:
            guanyador_fcb = local_fcb
        elif row.visitant_punts > row.local_punts:
            guanyador_fcb = visitant_fcb
    return Game(
        data_partida=row.data_partida,
        competicio_nom=row.competicio,
        modalitat_codi_fcb=modalitat_codi_fcb,
        player1_fcb_id=local_fcb,
        player2_fcb_id=visitant_fcb,
        caramboles1=row.local_caramboles,
        caramboles2=row.visitant_caramboles,
        entrades=row.entrades,
        guanyador_fcb_id=guanyador_fcb,
        extras={
            "punts1": row.local_punts,
            "punts2": row.visitant_punts,
        },
    )


@dataclass
class SyncResult:
    discovered: HomeRankingsResult
    ingested: list[tuple[int, int]]  # llista de (num_seq, modalitat) nous ingerits
    skipped_existing: list[tuple[int, int]]


def discover_current_rankings(client: ScraperClient) -> HomeRankingsResult:
    """Descobreix els rànquings actuals consultant /jugador/home."""
    url = f"{client.settings.base_url.rstrip('/')}/jugador/home"
    html = client.fetch_html(url, use_cache=False)
    return parse_home_current_rankings(html)


def discover_historical_rankings(client: ScraperClient) -> list[HistorialEntry]:
    """Descobreix els rànquings històrics consultant /ca/jugador/ranking/historial.

    El portal mostra els ~15 més recents. Per a un backfill realment complet
    caldria iterar per num_seq més enrere consultant URLs directament, però per
    ara l'historial és la font primària.
    """
    url = f"{client.settings.base_url.rstrip('/')}/ca/jugador/ranking/historial"
    html = client.fetch_html(url, use_cache=False)
    return parse_ranking_historial(html)


def sync_current_rankings(
    client: ScraperClient, *, settings: Settings | None = None
) -> SyncResult:
    """Si la home mostra un rànquing nou per a alguna modalitat, l'ingereix."""
    settings = settings or client.settings
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    home = discover_current_rankings(client)
    ingested: list[tuple[int, int]] = []
    skipped: list[tuple[int, int]] = []
    for current in home.rankings:
        latest_db = repo.latest_ranking_num_seq(current.modalitat_codi_fcb) or 0
        if current.num_seq > latest_db:
            result = ingest_ranking(
                client, current.num_seq, current.modalitat_codi_fcb, settings=settings
            )
            if result is not None:
                ingested.append((current.num_seq, current.modalitat_codi_fcb))
        else:
            skipped.append((current.num_seq, current.modalitat_codi_fcb))
    return SyncResult(discovered=home, ingested=ingested, skipped_existing=skipped)


@dataclass
class BackfillResult:
    ranking_ingested: bool
    players_processed: int
    total_games_upserted: int
    total_games_skipped: int


@dataclass
class HistoricalBackfillResult:
    rankings_processed: list[tuple[int, int]]  # llista (num_seq, modalitat)
    rankings_failed: list[tuple[int, int]]
    total_players_processed: int
    total_games_upserted: int
    total_games_skipped: int


def backfill_ranking(
    client: ScraperClient,
    num_seq: int,
    modalitat_codi_fcb: int,
    *,
    top_n: int | None = None,
    only_followed: bool = False,
    settings: Settings | None = None,
    preferred_format: str | None = None,
) -> BackfillResult:
    """Ingest un rànquing concret + partides dels jugadors filtrats.

    Filtres aplicats sobre les entries del rànquing:
      - `top_n`: només els jugadors amb posició ≤ top_n.
      - `only_followed`: només els jugadors marcats com a seguits.
    """
    settings = settings or client.settings
    res = ingest_ranking(
        client, num_seq, modalitat_codi_fcb, settings=settings, preferred_format=preferred_format
    )
    if res is None:
        return BackfillResult(False, 0, 0, 0)

    conn = ensure_schema(settings.db_path)
    candidates: list[tuple[str, int | None]] = []
    rows = conn.execute(
        """
        SELECT p.fcb_id, e.posicio, p.seguiment
        FROM ranking_entries e
        JOIN players p ON p.id = e.player_id
        JOIN rankings r ON r.id = e.ranking_id
        JOIN modalitats m ON m.id = r.modalitat_id
        WHERE r.num_seq = ? AND m.codi_fcb = ?
        ORDER BY e.posicio ASC NULLS LAST
        """,
        (num_seq, modalitat_codi_fcb),
    ).fetchall()
    for fcb_id, posicio, seguiment in rows:
        if only_followed and not seguiment:
            continue
        if top_n is not None and posicio is not None and posicio > top_n:
            continue
        candidates.append((fcb_id, posicio))

    total_up = 0
    total_skip = 0
    for fcb_id, _ in candidates:
        try:
            r = ingest_partides(
                client, num_seq, modalitat_codi_fcb, fcb_id, settings=settings
            )
            total_up += r.games_upserted
            total_skip += r.games_skipped_missing_opponent
        except Exception as e:
            log.warning("Error ingerint partides de %s: %s", fcb_id, e)

    return BackfillResult(
        ranking_ingested=True,
        players_processed=len(candidates),
        total_games_upserted=total_up,
        total_games_skipped=total_skip,
    )


def backfill_modalitat(
    client: ScraperClient,
    modalitat_codi_fcb: int,
    *,
    top_n: int | None = None,
    only_followed: bool = False,
    settings: Settings | None = None,
) -> BackfillResult:
    """Backfill del rànquing actual d'una modalitat (descobert de /jugador/home)."""
    settings = settings or client.settings
    home = discover_current_rankings(client)
    current = next(
        (r for r in home.rankings if r.modalitat_codi_fcb == modalitat_codi_fcb), None
    )
    if current is None:
        raise ValueError(
            f"Modalitat {modalitat_codi_fcb} no apareix als rànquings actuals de la home"
        )
    return backfill_ranking(
        client,
        current.num_seq,
        modalitat_codi_fcb,
        top_n=top_n,
        only_followed=only_followed,
        settings=settings,
    )


def backfill_historical(
    client: ScraperClient,
    *,
    modalitat_codi_fcb: int | None = None,
    top_n: int | None = None,
    only_followed: bool = False,
    settings: Settings | None = None,
) -> HistoricalBackfillResult:
    """Backfill tots els rànquings que apareixen a l'historial.

    Si es passa `modalitat_codi_fcb`, només es processa aquesta modalitat.
    Iterem en ordre cronològic ascendent (rànquings antics primer) perquè
    els upserts mantinguin coherència temporal.
    """
    settings = settings or client.settings
    entries = discover_historical_rankings(client)
    # Aplanem a llista (num_seq, modalitat) ordenada cronològicament ascendent.
    flat: list[tuple[int, int]] = []
    flat_with_fmt: list[tuple[int, int, str]] = []
    for entry in sorted(entries, key=lambda e: e.data):
        for modalitat, (fmt, num_seq) in entry.rankings.items():
            if modalitat_codi_fcb is not None and modalitat != modalitat_codi_fcb:
                continue
            flat_with_fmt.append((num_seq, modalitat, fmt))

    processed: list[tuple[int, int]] = []
    failed: list[tuple[int, int]] = []
    total_players = 0
    total_up = 0
    total_skip = 0
    for num_seq, modalitat, fmt in flat_with_fmt:
        try:
            res = backfill_ranking(
                client,
                num_seq,
                modalitat,
                top_n=top_n,
                only_followed=only_followed,
                settings=settings,
                preferred_format=fmt,
            )
        except Exception as e:
            log.warning("Backfill històric: error a %s/%s: %s", num_seq, modalitat, e)
            failed.append((num_seq, modalitat))
            continue
        if not res.ranking_ingested:
            failed.append((num_seq, modalitat))
            continue
        processed.append((num_seq, modalitat))
        total_players += res.players_processed
        total_up += res.total_games_upserted
        total_skip += res.total_games_skipped

    return HistoricalBackfillResult(
        rankings_processed=processed,
        rankings_failed=failed,
        total_players_processed=total_players,
        total_games_upserted=total_up,
        total_games_skipped=total_skip,
    )


def set_follow(fcb_id: str, follow: bool, *, settings: Settings | None = None) -> bool:
    """Marca/desmarca un jugador com a seguit. Retorna True si existeix."""
    settings = settings or get_settings()
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    return repo.set_seguiment(fcb_id, follow)


# --------------------------- ingest de lliga catalana ---------------------------


# Patró d'un nom d'equip a la lliga: `<NOM_CLUB> "<LLETRA>"`.
_EQUIP_NOM_RE = re.compile(r'^(.+?)\s*"([A-Z0-9]+)"\s*$')


def _split_equip_nom(equip_nom: str) -> tuple[str, str]:
    """Separa "C.B. MATARÓ \"A\"" en ("C.B. MATARÓ", "A").

    Si el nom no segueix el patró amb cometes, retornem (nom_complet, "UNICO").
    """
    m = _EQUIP_NOM_RE.match(equip_nom.strip())
    if m is None:
        return equip_nom.strip(), "UNICO"
    return m.group(1).strip(), m.group(2).strip()


def _derive_temporada(d: date) -> str:
    """Deriva la temporada de billar (setembre-juny) d'una data: '2025-2026'."""
    if d.month >= 8:  # agost ja considerem temporada nova
        return f"{d.year}-{d.year + 1}"
    return f"{d.year - 1}-{d.year}"


def _ensure_club_equip(
    repo: Repository, equip_nom: str
) -> tuple[str, str, int]:
    """Crea/obté el club i l'equip a la BD. Retorna (club_fcb_id, lletra, equip_id)."""
    club_nom, lletra = _split_equip_nom(equip_nom)
    # Usem el nom del club com a fcb_id (el portal no exposa un id intern de club).
    club_fcb_id = club_nom
    repo.upsert_club(Club(fcb_id=club_fcb_id, nom=club_nom))
    equip_id = repo.upsert_equip(Equip(club_fcb_id=club_fcb_id, lletra=lletra))
    return club_fcb_id, lletra, equip_id


@dataclass
class IngestLligaEncontreResult:
    encontre_lliga_id: int
    partides_total: int
    games_upserted: int
    games_skipped_missing_player: int


def _lliga_partides_url(
    base_url: str, lliga: int, divisio: int, grup: int, jornada: int, encontre: int
) -> str:
    return (
        f"{base_url.rstrip('/')}/ca/lligues/partides/"
        f"{lliga}/{divisio}/{grup}/{jornada}/{encontre}"
    )


def ingest_lliga_encontre(
    client: ScraperClient,
    encontre: LligaEncontre,
    *,
    modalitat_codi_fcb: int,
    data: date | None = None,
    competicio_nom: str = "LLIGA",
    settings: Settings | None = None,
) -> IngestLligaEncontreResult:
    """Ingest les partides individuals d'un encontre + tot el context.

    Crea/obté clubs+equips+encontre_lliga a la BD. Llavors fetch les partides
    individuals i, per a cada una:
      - Resol noms a fcb_id (els jugadors han d'existir prèviament, p.ex.
        d'un ingest de rànquing).
      - Crea/actualitza el Game amb tot el context (equip1/2_id,
        encontre_lliga_id, temporada_id, arbitre, assistencia, sèrie major).
      - Deduplica via Game.id_natural — si la partida ja venia de partideshome,
        s'enriqueix amb els camps de lliga via COALESCE.
    """
    settings = settings or client.settings
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)

    # 1. Crear/obtenir clubs + equips i l'encontre.
    _, _, local_equip_id = _ensure_club_equip(repo, encontre.equip_local)
    _, _, visitant_equip_id = _ensure_club_equip(repo, encontre.equip_visitant)
    temporada_nom: str | None = None
    if data is not None:
        temporada_nom = _derive_temporada(data)
    temporada_id: int | None = None
    if temporada_nom:
        temporada_id = repo.upsert_temporada(Temporada(nom=temporada_nom))
    local_club, local_lletra = _split_equip_nom(encontre.equip_local)
    visitant_club, visitant_lletra = _split_equip_nom(encontre.equip_visitant)
    encontre_full = EncontreLliga(
        lliga_id=encontre.lliga_id,
        divisio_id=encontre.divisio_id,
        grup_id=encontre.grup_id,
        jornada_id=encontre.jornada_id,
        encontre_id_extern=encontre.encontre_id,
        equip_local=Equip(club_fcb_id=local_club, lletra=local_lletra),
        equip_visitant=Equip(club_fcb_id=visitant_club, lletra=visitant_lletra),
        data=data,
        temporada_nom=temporada_nom,
        p_parcials_local=encontre.p_parcials_local,
        p_match_local=encontre.p_match_local,
        p_parcials_visitant=encontre.p_parcials_visitant,
        p_match_visitant=encontre.p_match_visitant,
    )
    encontre_lliga_id = repo.upsert_encontre_lliga(encontre_full)

    # 2. Descarregar i parsejar les partides individuals de l'encontre.
    url = _lliga_partides_url(
        settings.base_url,
        encontre.lliga_id,
        encontre.divisio_id,
        encontre.grup_id,
        encontre.jornada_id,
        encontre.encontre_id,
    )
    html = client.fetch_html(url)
    partides = parse_lliga_partides(html)

    upserted = 0
    skipped = 0
    for row in partides:
        game = _build_game_from_lliga_row(
            row,
            encontre_data=data,
            modalitat_codi_fcb=modalitat_codi_fcb,
            competicio_nom=competicio_nom,
            local_equip_id=local_equip_id,
            visitant_equip_id=visitant_equip_id,
            encontre_lliga_id=encontre_lliga_id,
            temporada_id=temporada_id,
            repo=repo,
        )
        if game is None:
            skipped += 1
            continue
        repo.upsert_game(game)
        upserted += 1

    log.info(
        "Encontre lliga %d/%d/%d/%d/%d: %d partides, %d desades, %d saltades",
        encontre.lliga_id,
        encontre.divisio_id,
        encontre.grup_id,
        encontre.jornada_id,
        encontre.encontre_id,
        len(partides),
        upserted,
        skipped,
    )
    return IngestLligaEncontreResult(
        encontre_lliga_id=encontre_lliga_id,
        partides_total=len(partides),
        games_upserted=upserted,
        games_skipped_missing_player=skipped,
    )


def _build_game_from_lliga_row(
    row: LligaPartidaRow,
    *,
    encontre_data: date | None,
    modalitat_codi_fcb: int,
    competicio_nom: str,
    local_equip_id: int,
    visitant_equip_id: int,
    encontre_lliga_id: int,
    temporada_id: int | None,
    repo: Repository,
) -> Game | None:
    local_fcb = repo.get_player_fcb_id_by_nom(row.local_nom)
    visitant_fcb = repo.get_player_fcb_id_by_nom(row.visitant_nom)
    if local_fcb is None or visitant_fcb is None:
        log.debug(
            "Salto partida lliga %s vs %s: local_fcb=%s visitant_fcb=%s",
            row.local_nom,
            row.visitant_nom,
            local_fcb,
            visitant_fcb,
        )
        return None
    # data_partida: si la partida no porta data al row, fem servir la de l'encontre.
    data_partida = row.data_partida or encontre_data
    if data_partida is None:
        return None  # No podem construir id_natural sense data
    guanyador_fcb: str | None = None
    if row.local_punts is not None and row.visitant_punts is not None:
        if row.local_punts > row.visitant_punts:
            guanyador_fcb = local_fcb
        elif row.visitant_punts > row.local_punts:
            guanyador_fcb = visitant_fcb
    return Game(
        data_partida=data_partida,
        competicio_nom=competicio_nom,
        modalitat_codi_fcb=modalitat_codi_fcb,
        player1_fcb_id=local_fcb,
        player2_fcb_id=visitant_fcb,
        caramboles1=row.local_caramboles,
        caramboles2=row.visitant_caramboles,
        entrades=row.entrades,
        serie_max1=row.local_serie_major,
        serie_max2=row.visitant_serie_major,
        guanyador_fcb_id=guanyador_fcb,
        arbitre=row.arbitre,
        assistencia=row.assistencia,
        equip1_id=local_equip_id,
        equip2_id=visitant_equip_id,
        encontre_lliga_id=encontre_lliga_id,
        temporada_id=temporada_id,
        extras={
            "punts1": row.local_punts,
            "punts2": row.visitant_punts,
        },
    )


@dataclass
class IngestLligaJornadaResult:
    encontres_processed: int
    encontres_failed: int
    total_games_upserted: int
    total_games_skipped: int


def _lliga_encontres_url(
    base_url: str, lliga: int, divisio: int, grup: int, jornada: int
) -> str:
    return (
        f"{base_url.rstrip('/')}/ca/lligues/encontres/"
        f"{lliga}/{divisio}/{grup}/{jornada}"
    )


def ingest_lliga_jornada(
    client: ScraperClient,
    lliga_id: int,
    divisio_id: int,
    grup_id: int,
    jornada_id: int,
    *,
    modalitat_codi_fcb: int,
    data: date | None = None,
    competicio_nom: str = "LLIGA",
    settings: Settings | None = None,
) -> IngestLligaJornadaResult:
    """Ingest tots els encontres d'una jornada de lliga.

    Fetch la pàgina d'encontres → llista d'encontres → per cada un, fa
    `ingest_lliga_encontre` (que crea clubs/equips/encontre + partides).
    """
    settings = settings or client.settings
    url = _lliga_encontres_url(settings.base_url, lliga_id, divisio_id, grup_id, jornada_id)
    html = client.fetch_html(url)
    encontres = parse_lliga_encontres(html)

    processed = 0
    failed = 0
    total_up = 0
    total_skip = 0
    for encontre in encontres:
        try:
            res = ingest_lliga_encontre(
                client,
                encontre,
                modalitat_codi_fcb=modalitat_codi_fcb,
                data=data,
                competicio_nom=competicio_nom,
                settings=settings,
            )
        except Exception as e:
            log.warning(
                "Error ingerint encontre %d/%d/%d/%d/%d: %s",
                encontre.lliga_id,
                encontre.divisio_id,
                encontre.grup_id,
                encontre.jornada_id,
                encontre.encontre_id,
                e,
            )
            failed += 1
            continue
        processed += 1
        total_up += res.games_upserted
        total_skip += res.games_skipped_missing_player
    return IngestLligaJornadaResult(
        encontres_processed=processed,
        encontres_failed=failed,
        total_games_upserted=total_up,
        total_games_skipped=total_skip,
    )


def run_status(settings: Settings | None = None) -> dict[str, int]:
    settings = settings or get_settings()
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    return repo.counts()
