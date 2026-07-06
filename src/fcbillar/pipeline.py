"""Orquestració de la ingesta."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from datetime import date

from fcbillar.config import Settings, get_settings
from fcbillar.db.migrations import ensure_schema
from fcbillar.db.repository import Repository
from fcbillar.ranking_dates import month_for_publication_date
from fcbillar.models import (
    Club,
    EncontreLliga,
    Equip,
    Game,
    Player,
    Ranking,
    RankingGameLink,
    Temporada,
    TorneigIndividualRecord,
    TorneigParticipantRecord,
)
from fcbillar.scraper.client import ScraperClient
from fcbillar.scraper.parsers import (
    ClubOficial,
    HistorialEntry,
    HomeRankingsResult,
    IndividualDivisio,
    IndividualParticipant,
    LligaDivisio,
    LligaEncontre,
    LligaGrup,
    LligaJornadaLink,
    LligaPartidaRow,
    RawGameRow,
    TorneigIndividual,
    parse_clubs_listing,
    parse_copa_encontresgrup,
    parse_copa_grups,
    parse_copa_jornades,
    parse_copa_partides,
    parse_home_current_rankings,
    parse_individuals_classificaciofinal,
    parse_individuals_divisions,
    parse_individuals_torneigs_list,
    parse_lliga_divisions,
    parse_lliga_encontres,
    parse_lliga_grups,
    parse_lliga_jornades,
    parse_lliga_partides,
    parse_partides_jugador,
    parse_ranking,
    parse_ranking_historial,
)
from fcbillar.scraper.url_builder import all_ranking_url_candidates
from fcbillar.torneig_naming import clean_torneig_nom

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
    data_pub: date | None = None,
) -> IngestRankingResult | None:
    """Descarrega un rànquing, el parseja i el persisteix a la BD.

    Si es passa `data_pub` (data real de publicació, p.ex. de l'historial),
    es desa i en deriva `any_pub`/`mes_pub` — font autoritativa que substitueix
    la vella heurística monòtona.
    """
    settings = settings or client.settings
    fetched = fetch_ranking_html(
        client, num_seq, modalitat_codi_fcb, preferred_format=preferred_format
    )
    if fetched is None:
        return None

    parsed = parse_ranking(fetched.html, num_seq, modalitat_codi_fcb)

    any_pub = mes_pub = None
    if data_pub is not None:
        any_pub, mes_pub = month_for_publication_date(data_pub)

    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    ranking_id = repo.upsert_ranking(
        Ranking(
            num_seq=num_seq,
            modalitat_codi_fcb=modalitat_codi_fcb,
            url=fetched.url,
            format_url=fetched.fmt,
            any_pub=any_pub,
            mes_pub=mes_pub,
            data_pub=data_pub.isoformat() if data_pub is not None else None,
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
    games_new: int = 0  # partides que NO existien abans (descàrrega real)


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


def _select_last_15_games(games: list[tuple[date, int | None, int | None]]) -> list[int]:
    """Selecciona els últims 15 games, amb desempat per mitjana si empat de data en frontera 15/16.
    
    Args:
        games: llista de tuples (data, caramboles, entrades) ordenades per data desc.
    
    Returns:
        llista d'índex dels games seleccionats (fins a 15 games).
    """
    if len(games) <= 15:
        return list(range(len(games)))
    
    # Si tenim més de 15 i la 15ena (índex 14) i 16ena (índex 15) són del mateix dia,
    # mantenir la 15ena excepte si la 16ena té millor mitjana.
    selected_idxs = list(range(15))  # indices 0..14 (15 games)
    
    date_15 = games[14][0]
    date_16 = games[15][0]
    
    if date_15 == date_16:
        # Comparar mitjanes (caramboles/entrades)
        car_15, ent_15 = games[14][1], games[14][2]
        car_16, ent_16 = games[15][1], games[15][2]
        
        avg_15 = (car_15 / ent_15) if ent_15 else 0
        avg_16 = (car_16 / ent_16) if ent_16 else 0
        
        if avg_16 > avg_15:
            # Triar la 16ena en comptes de la 15ena
            selected_idxs[14] = 15
    
    return selected_idxs


def ingest_partides(
    client: ScraperClient,
    num_seq: int,
    modalitat_codi_fcb: int,
    player_fcb_id: str,
    *,
    settings: Settings | None = None,
    create_missing_players: bool = False,
    use_cache: bool = True,
) -> IngestPartidesResult:
    """Descarrega partideshome d'un jugador en un rànquing i les persisteix.

    El portal exposa noms però no fcb_ids dels contraris. Resolem nom → fcb_id
    contra els players ja existents a la BD (vinguts d'un rànquing previ).

    Per defecte les partides amb un contrari no registrat es salten. Amb
    `create_missing_players=True` es crea un placeholder (fcb_id="name:<NOM>")
    i la partida es desa; si més tard l'fcb_id real apareix via ingest_ranking,
    el repository fusiona automàticament el placeholder al jugador real.

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
    html = client.fetch_html(url, use_cache=use_cache)
    parsed = parse_partides_jugador(html)

    upserted = 0
    skipped = 0
    links = 0
    new = 0
    
    # Primera passa: construir games i upsertarlos.
    # Recopilarem (data, caramboles_del_jugador, entrades) per filtrar darrers 15.
    games_info: list[tuple[date, Game, int | None, int | None]] = []
    
    for row in parsed.rows:
        game = _build_game_from_raw_row(
            row, modalitat_codi_fcb, owner_nom, repo,
            create_missing_players=create_missing_players,
        )
        if game is None:
            skipped += 1
            continue
        if not repo.game_exists(game.id_natural):
            new += 1
        repo.upsert_game(game)
        upserted += 1
        
        # Obtenim els caramboles del jugador consultat.
        if game.player1_fcb_id == player_fcb_id:
            car_jugador = game.caramboles1
        else:
            car_jugador = game.caramboles2
        
        games_info.append((game.data_partida, game, car_jugador, game.entrades))
    
    # Segona passa: seleccionar darrers 15 games i crear links.
    if games_info:
        # Preparar llista de (data, caramboles, entrades) per al filtre.
        game_stats = [(g[0], g[2], g[3]) for g in games_info]
        selected_idxs = _select_last_15_games(game_stats)
        
        for idx in selected_idxs:
            if idx < len(games_info):
                _, game, _, _ = games_info[idx]
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
        games_new=new,
    )


def _build_game_from_raw_row(
    row: RawGameRow,
    modalitat_codi_fcb: int,
    owner_nom: str,
    repo: Repository,
    *,
    create_missing_players: bool = False,
) -> Game | None:
    """Resol noms a fcb_ids i construeix un Game. Retorna None si no es pot."""
    if create_missing_players:
        local_fcb = repo.resolve_or_create_player_by_nom(row.local_nom)
        visitant_fcb = repo.resolve_or_create_player_by_nom(row.visitant_nom)
    else:
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


@dataclass
class RankingDateChange:
    num_seq: int
    data_pub: str
    old: tuple[int | None, int | None]  # (any_pub, mes_pub) abans
    new: tuple[int, int]  # (any_pub, mes_pub) derivat de la data real


@dataclass
class ReconcileDatesResult:
    changed: list[RankingDateChange]  # mes_pub/any_pub que canvien
    dated: int  # num_seq als quals s'ha (re)assignat data_pub
    not_in_db: list[int]  # num_seq de l'historial que no existeixen a la BD


def reconcile_ranking_dates(
    entries: list[HistorialEntry],
    *,
    settings: Settings | None = None,
) -> ReconcileDatesResult:
    """Aplica les dates reals de l'historial a la taula `rankings`.

    Per cada num_seq present a l'historial, desa `data_pub` i hi (re)deriva
    `any_pub`/`mes_pub` per a TOTES les files de modalitat existents (la data és
    global per num_seq). NO re-scrapeja entries; només corregeix l'etiqueta de mes.
    Retorna un informe amb els canvis de mes detectats.
    """
    settings = settings or get_settings()
    conn = ensure_schema(settings.db_path)

    # num_seq -> data (global; agafem la més recent si es repetís)
    by_seq: dict[int, date] = {}
    for e in entries:
        for _mod, (_fmt, num_seq) in e.rankings.items():
            by_seq[num_seq] = e.data

    changed: list[RankingDateChange] = []
    dated = 0
    not_in_db: list[int] = []
    for num_seq, d in sorted(by_seq.items()):
        ny, nm = month_for_publication_date(d)
        rows = conn.execute(
            "SELECT id, any_pub, mes_pub FROM rankings WHERE num_seq = ?",
            (num_seq,),
        ).fetchall()
        if not rows:
            not_in_db.append(num_seq)
            continue
        # Una entrada de canvi per num_seq (el mes és el mateix per totes les mod).
        first = rows[0]
        if (first["any_pub"], first["mes_pub"]) != (ny, nm):
            changed.append(
                RankingDateChange(
                    num_seq=num_seq,
                    data_pub=d.isoformat(),
                    old=(first["any_pub"], first["mes_pub"]),
                    new=(ny, nm),
                )
            )
        conn.execute(
            "UPDATE rankings SET data_pub = ?, any_pub = ?, mes_pub = ? WHERE num_seq = ?",
            (d.isoformat(), ny, nm, num_seq),
        )
        dated += 1

    return ReconcileDatesResult(changed=changed, dated=dated, not_in_db=not_in_db)


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
                client, current.num_seq, current.modalitat_codi_fcb, settings=settings,
                data_pub=home.data_ranking,
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
    data_pub: date | None = None,
) -> BackfillResult:
    """Ingest un rànquing concret + partides dels jugadors filtrats.

    Filtres aplicats sobre les entries del rànquing:
      - `top_n`: només els jugadors amb posició ≤ top_n.
      - `only_followed`: només els jugadors marcats com a seguits.
    """
    settings = settings or client.settings
    res = ingest_ranking(
        client, num_seq, modalitat_codi_fcb, settings=settings,
        preferred_format=preferred_format, data_pub=data_pub,
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
    # Aplanem a llista (num_seq, modalitat, fmt, data) ordenada cronològicament asc.
    flat_with_fmt: list[tuple[int, int, str, date]] = []
    for entry in sorted(entries, key=lambda e: e.data):
        for modalitat, (fmt, num_seq) in entry.rankings.items():
            if modalitat_codi_fcb is not None and modalitat != modalitat_codi_fcb:
                continue
            flat_with_fmt.append((num_seq, modalitat, fmt, entry.data))

    processed: list[tuple[int, int]] = []
    failed: list[tuple[int, int]] = []
    total_players = 0
    total_up = 0
    total_skip = 0
    for num_seq, modalitat, fmt, data_pub in flat_with_fmt:
        try:
            res = backfill_ranking(
                client,
                num_seq,
                modalitat,
                top_n=top_n,
                only_followed=only_followed,
                settings=settings,
                preferred_format=fmt,
                data_pub=data_pub,
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


# Patrons per parsejar el nom d'equip a la lliga.
# El portal usa múltiples formats que cal cobrir:
# - C.B. MATARÓ "A"          (cometes ASCII)
# - C.B. MATARÓ "A"          (cometes tipogràfiques)
# - 01 C.B. BARCELONA A      (prefix numèric per ordre + lletra sense cometes)
# - SANT ADRIÀ A             (sense cometes ni prefix)
# - C.B.SANTS                (sense lletra → equip únic)
_EQUIP_PREFIX_NUM_RE = re.compile(r"^\d{1,3}\s+")
_QUOTES = r"['‘’\"“”]"
# Exigim espai O cometa abans de la lletra final per no malinterpretar
# noms que simplement acaben en lletra (BANYOLES, MATADEPERA, etc.).
_EQUIP_NOM_RE = re.compile(
    rf"^(.+?)(?:\s+|{_QUOTES}\s*)([ABCDEFGH])\s*{_QUOTES}?\s*$"
)


def _split_equip_nom(equip_nom: str) -> tuple[str, str]:
    """Separa el nom d'equip en (club_nom, lletra).

    Cobreix les variants observades al portal: cometes ASCII, cometes
    tipogràfiques, prefix numèric "01 ", lletra sense cometes, sense lletra.
    Si no hi ha lletra detectable, retorna (nom, "UNICO").
    """
    s = equip_nom.strip()
    # Treure prefix d'ordre tipus "01 ", "12 " si n'hi ha.
    s = _EQUIP_PREFIX_NUM_RE.sub("", s)
    m = _EQUIP_NOM_RE.match(s)
    if m is None:
        return s, "UNICO"
    return m.group(1).strip(), m.group(2).strip()


def _derive_temporada(d: date) -> str:
    """Deriva la temporada de billar (setembre-juny) d'una data: '2025-2026'."""
    if d.month >= 8:  # agost ja considerem temporada nova
        return f"{d.year}-{d.year + 1}"
    return f"{d.year - 1}-{d.year}"


def _ensure_club_equip(
    repo: Repository, equip_nom: str
) -> tuple[str, str, int]:
    """Crea/obté el club i l'equip a la BD. Retorna (club_fcb_id, lletra, equip_id).

    Si ja existeix un club amb el mateix nom (matching exacte, normalitzat o
    via alias), el reutilitzem; sinó en creem un de nou amb el nom tal com
    apareix a la lliga.
    """
    club_nom, lletra = _split_equip_nom(equip_nom)
    existing_id = repo.resolve_club_id_by_nom(club_nom)
    if existing_id is not None:
        row = repo.conn.execute(
            "SELECT fcb_id FROM clubs WHERE id = ?", (existing_id,)
        ).fetchone()
        club_fcb_id = row[0]
    else:
        # Creem un nou club amb el nom tal com surt a la lliga.
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
    create_missing_players: bool = False,
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
    # _ensure_club_equip resol el club via match exacte / normalitzat / alias,
    # i retorna el club_fcb_id real (que pot diferir del nom variant que ve
    # de la lliga). Usem aquest fcb_id resolt per construir l'Equip.
    local_club_fcb, local_lletra, local_equip_id = _ensure_club_equip(
        repo, encontre.equip_local
    )
    visitant_club_fcb, visitant_lletra, visitant_equip_id = _ensure_club_equip(
        repo, encontre.equip_visitant
    )
    temporada_nom: str | None = None
    if data is not None:
        temporada_nom = _derive_temporada(data)
    temporada_id: int | None = None
    if temporada_nom:
        temporada_id = repo.upsert_temporada(Temporada(nom=temporada_nom))
    encontre_full = EncontreLliga(
        lliga_id=encontre.lliga_id,
        divisio_id=encontre.divisio_id,
        grup_id=encontre.grup_id,
        jornada_id=encontre.jornada_id,
        encontre_id_extern=encontre.encontre_id,
        equip_local=Equip(club_fcb_id=local_club_fcb, lletra=local_lletra),
        equip_visitant=Equip(club_fcb_id=visitant_club_fcb, lletra=visitant_lletra),
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

    # v11: desa les partides JUGADES (entrades>0) com a PENDENTS perquè surtin a la
    # fitxa fins que la ingesta oficial (partideshome) les incorpori a `games`.
    # publish_pending_games les dedup per signatura contra `games`. DELETE+INSERT per
    # encontre perquè un re-ingest les substitueixi. La modalitat ve del NOM de la
    # partida (lligues "4 modalitats" en barregen), amb fallback a la de l'ingest.
    _MOD_CODI = {"tres bandes": 1, "lliure": 2, "banda": 4, "quadre 47/2": 3, "quadre 71/2": 6}
    conn.execute(
        "DELETE FROM lliga_pending_partides WHERE encontre_lliga_id=?", (encontre_lliga_id,)
    )
    for row in partides:
        if not row.entrades or row.entrades <= 0:
            continue
        conn.execute(
            """INSERT INTO lliga_pending_partides
               (encontre_lliga_id, modalitat_codi, competicio, data, player1_nom,
                caramboles1, serie1, player2_nom, caramboles2, serie2, entrades)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                encontre_lliga_id,
                _MOD_CODI.get((row.modalitat or "").strip().lower(), modalitat_codi_fcb),
                competicio_nom,
                data.isoformat() if data else None,
                row.local_nom, row.local_caramboles, row.local_serie_major,
                row.visitant_nom, row.visitant_caramboles, row.visitant_serie_major,
                row.entrades,
            ),
        )

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
            create_missing_players=create_missing_players,
        )
        if game is None:
            skipped += 1
            continue
        # Cas normal: la partida ja ve de partideshome. La competició la classifica
        # (encontre/equips/sèrie) però NO discuteix la modalitat (autèntica, de
        # partideshome). Enriquim el game existent via signatura.
        if repo.enrich_game_by_signature(game):
            upserted += 1
            continue
        # No hi ha cap game previ a enriquir. Si la partida es va jugar però porta
        # entrades=0, la federació l'exclou de partideshome (no compta per la
        # mitjana), així que el game no existeix enlloc. La creem des de la pàgina
        # de lliga perquè els resultats de la competició quedin complets, imputant
        # les entrades reals quan es pot deduir que va anar al límit d'entrades.
        if not game.entrades:
            imputed = _impute_lliga_entrades(
                repo,
                lliga_id=encontre.lliga_id,
                divisio_id=encontre.divisio_id,
                grup_id=encontre.grup_id,
                modalitat_codi_fcb=game.modalitat_codi_fcb,
                caramboles1=game.caramboles1,
                caramboles2=game.caramboles2,
            )
            if imputed:
                game = replace(game, entrades=imputed)
            repo.upsert_game(game)
            upserted += 1
        else:
            skipped += 1

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


# Mapeig nom de modalitat (tal com surt a la pàgina de partides) → codi_fcb.
# A les lligues multi-modalitat (4 modalitats / Catalana) cada partida d'un
# encontre juga una modalitat diferent, així que NO es pot aplicar una sola
# modalitat a tot l'encontre: cal llegir-la per partida.
_MODALITAT_NOM_TO_CODI = {
    "tres bandes": 1,
    "3 bandes": 1,
    "lliure": 2,
    "quadre 47/2": 3,
    "banda": 4,
    "quadre 71/2": 6,
}


def _modalitat_codi_from_nom(nom: str | None, fallback: int) -> int:
    """Converteix el text 'Modalitat' d'una partida a codi_fcb (fallback si desconegut)."""
    if not nom:
        return fallback
    return _MODALITAT_NOM_TO_CODI.get(" ".join(nom.strip().lower().split()), fallback)


# Límit d'entrades conegut per modalitat (codi_fcb). A tres bandes sempre és 50.
# Per a la resta de modalitats s'infereix de les dades del grup.
_LLIGA_ENTRADES_LIMIT_BY_MODALITAT = {1: 50}  # 1 = tres bandes


def _impute_lliga_entrades(
    repo: Repository,
    *,
    lliga_id: int,
    divisio_id: int,
    grup_id: int,
    modalitat_codi_fcb: int,
    caramboles1: int | None,
    caramboles2: int | None,
) -> int | None:
    """Infereix les entrades reals d'una partida jugada que consta amb entrades=0.

    Si cap dels dos jugadors arriba a la distància del grup, la partida va anar
    fins al límit d'entrades → retorna aquest límit (50 a tres bandes, o el màxim
    observat al grup per a altres modalitats). Si algú arriba a la distància (la
    partida es va acabar abans) o no hi ha dades de referència, retorna None.
    """
    dist, inferred_limit = repo.infer_lliga_distance_limit(
        lliga_id=lliga_id,
        divisio_id=divisio_id,
        grup_id=grup_id,
        modalitat_codi_fcb=modalitat_codi_fcb,
    )
    limit = _LLIGA_ENTRADES_LIMIT_BY_MODALITAT.get(modalitat_codi_fcb, inferred_limit)
    if not dist or not limit:
        return None
    if max(caramboles1 or 0, caramboles2 or 0) < dist:
        return limit
    return None


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
    create_missing_players: bool = False,
) -> Game | None:
    # Partides fantasma: tauler sense jugador assignat o partida no disputada
    # (incompareixença). NO filtrem només per entrades=0: de vegades una partida
    # realment jugada té el resultat (caramboles) però les entrades no consten a
    # la federació, i en aquest cas s'ha d'importar igualment.
    noms = f"{row.local_nom or ''} {row.visitant_nom or ''}".lower()
    if "sense assignar" in noms:
        return None
    disputada = bool(
        row.entrades
        or row.local_caramboles
        or row.visitant_caramboles
        or (row.assistencia or "").strip().lower().startswith("partit disputat")
    )
    if not disputada:
        return None
    if create_missing_players:
        local_fcb = repo.resolve_or_create_player_by_nom(row.local_nom)
        visitant_fcb = repo.resolve_or_create_player_by_nom(row.visitant_nom)
    else:
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
        modalitat_codi_fcb=_modalitat_codi_from_nom(row.modalitat, modalitat_codi_fcb),
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
    create_missing_players: bool = False,
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
                create_missing_players=create_missing_players,
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


@dataclass
class ImportClubsResult:
    imported: int
    list_of_names: list[str]


def _clubs_listing_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/ca/clubs/5/Federacio"


def import_clubs_oficials(
    client: ScraperClient, *, settings: Settings | None = None
) -> ImportClubsResult:
    """Descarrega el listing oficial de clubs i els upsert a la BD.

    El nom és l'únic identificador disponible (no hi ha id intern al portal),
    així doncs s'usa com a `clubs.fcb_id`. Idempotent.
    """
    settings = settings or client.settings
    html = client.fetch_html(_clubs_listing_url(settings.base_url), use_cache=False)
    clubs = parse_clubs_listing(html)
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    for c in clubs:
        repo.upsert_club(Club(fcb_id=c.nom, nom=c.nom))
    return ImportClubsResult(
        imported=len(clubs), list_of_names=[c.nom for c in clubs]
    )


@dataclass
class LligaTree:
    """Estructura descoberta d'una lliga: divisions → grups → jornades."""

    lliga_id: int
    divisions: list[LligaDivisio]
    grups_by_div: dict[int, list[LligaGrup]]  # divisio_id → grups
    jornades_by_grup: dict[tuple[int, int], list[LligaJornadaLink]]  # (div, grup) → jornades


def _lliga_divisions_url(base_url: str, lliga_id: int) -> str:
    return f"{base_url.rstrip('/')}/ca/lligues/divisions/{lliga_id}"


def _lliga_grups_url(base_url: str, lliga_id: int, divisio_id: int) -> str:
    return f"{base_url.rstrip('/')}/ca/lligues/grups/{lliga_id}/{divisio_id}"


def discover_lliga(
    client: ScraperClient, lliga_id: int, *, depth: int = 2
) -> LligaTree:
    """Descobreix l'estructura d'una lliga sense ingerir res.

    `depth` controla quants nivells es descarreguen:
    - 1: només divisions
    - 2: divisions + grups (per cada divisió)
    - 3: divisions + grups + jornades (per cada grup)
    """
    base_url = client.settings.base_url
    html = client.fetch_html(_lliga_divisions_url(base_url, lliga_id))
    divisions = parse_lliga_divisions(html)
    grups_by_div: dict[int, list[LligaGrup]] = {}
    jornades_by_grup: dict[tuple[int, int], list[LligaJornadaLink]] = {}
    if depth >= 2:
        for div in divisions:
            html = client.fetch_html(_lliga_grups_url(base_url, lliga_id, div.divisio_id))
            grups = parse_lliga_grups(html)
            grups_by_div[div.divisio_id] = grups
            if depth >= 3:
                for grup in grups:
                    html = client.fetch_html(
                        _lliga_jornades_url(base_url, lliga_id, div.divisio_id, grup.grup_id)
                    )
                    jornades_by_grup[(div.divisio_id, grup.grup_id)] = parse_lliga_jornades(
                        html
                    )
    return LligaTree(
        lliga_id=lliga_id,
        divisions=divisions,
        grups_by_div=grups_by_div,
        jornades_by_grup=jornades_by_grup,
    )


@dataclass
class IngestLligaGrupResult:
    jornades_processed: int
    jornades_failed: int
    total_encontres: int
    total_games_upserted: int
    total_games_skipped: int


def _lliga_jornades_url(
    base_url: str, lliga: int, divisio: int, grup: int
) -> str:
    return f"{base_url.rstrip('/')}/ca/lligues/jornades/{lliga}/{divisio}/{grup}"


def ingest_lliga_grup(
    client: ScraperClient,
    lliga_id: int,
    divisio_id: int,
    grup_id: int,
    *,
    modalitat_codi_fcb: int,
    competicio_nom: str = "LLIGA",
    create_missing_players: bool = False,
    settings: Settings | None = None,
) -> IngestLligaGrupResult:
    """Ingest totes les jornades d'un grup de lliga.

    Fetch la pàgina de jornades del grup → llista de jornades amb data →
    per cada una, fa ingest_lliga_jornada (passant la data per derivar
    la temporada).
    """
    settings = settings or client.settings
    url = _lliga_jornades_url(settings.base_url, lliga_id, divisio_id, grup_id)
    html = client.fetch_html(url)
    jornades = parse_lliga_jornades(html)

    processed = 0
    failed = 0
    total_enc = 0
    total_up = 0
    total_skip = 0
    for jornada in jornades:
        try:
            res = ingest_lliga_jornada(
                client,
                lliga_id=jornada.lliga_id,
                divisio_id=jornada.divisio_id,
                grup_id=jornada.grup_id,
                jornada_id=jornada.jornada_id,
                modalitat_codi_fcb=modalitat_codi_fcb,
                data=jornada.data,
                competicio_nom=competicio_nom,
                settings=settings,
                create_missing_players=create_missing_players,
            )
        except Exception as e:
            log.warning(
                "Error ingerint jornada %d/%d/%d/%d: %s",
                jornada.lliga_id,
                jornada.divisio_id,
                jornada.grup_id,
                jornada.jornada_id,
                e,
            )
            failed += 1
            continue
        processed += 1
        total_enc += res.encontres_processed
        total_up += res.total_games_upserted
        total_skip += res.total_games_skipped
    return IngestLligaGrupResult(
        jornades_processed=processed,
        jornades_failed=failed,
        total_encontres=total_enc,
        total_games_upserted=total_up,
        total_games_skipped=total_skip,
    )


# --------------------------- macro: import_temporada ---------------------------


# Modalitats canòniques: les 5 que apareixen actualment a la home + historial.
_MODALITATS_CANONIQUES = (1, 2, 3, 4, 6)


@dataclass
class ImportTemporadaResult:
    clubs_imported: int
    sync_ingested: list[tuple[int, int]]
    historical_processed: int
    historical_failed: int
    historical_games_upserted: int


def import_temporada(
    client: ScraperClient,
    *,
    include_clubs: bool = True,
    include_sync: bool = True,
    include_historical: bool = False,
    historical_top_n: int | None = 0,
    only_followed: bool = False,
    modalitats: tuple[int, ...] = _MODALITATS_CANONIQUES,
    settings: Settings | None = None,
) -> ImportTemporadaResult:
    """Macro-orquestració del flux d'import d'una temporada.

    Encadena import-clubs → sync → backfill --historical, amb flags per
    seleccionar parts. Per defecte:
      - inclou clubs i sync (ràpid)
      - NO inclou historical (cal opt-in amb include_historical)
      - quan historical=True, historical_top_n=0 → només rànquings, sense
        partides. Posa a None per a TOTES les partides (lent, ~hores).
    """
    settings = settings or client.settings
    clubs_imported = 0
    sync_ingested: list[tuple[int, int]] = []
    historical_processed = 0
    historical_failed = 0
    historical_games = 0

    if include_clubs:
        res = import_clubs_oficials(client, settings=settings)
        clubs_imported = res.imported

    if include_sync:
        sync_res = sync_current_rankings(client, settings=settings)
        sync_ingested = sync_res.ingested

    if include_historical:
        for mod in modalitats:
            try:
                hist = backfill_historical(
                    client,
                    modalitat_codi_fcb=mod,
                    top_n=historical_top_n,
                    only_followed=only_followed,
                    settings=settings,
                )
            except Exception as e:
                log.warning("Historical mod %s: error %s", mod, e)
                continue
            historical_processed += len(hist.rankings_processed)
            historical_failed += len(hist.rankings_failed)
            historical_games += hist.total_games_upserted

    return ImportTemporadaResult(
        clubs_imported=clubs_imported,
        sync_ingested=sync_ingested,
        historical_processed=historical_processed,
        historical_failed=historical_failed,
        historical_games_upserted=historical_games,
    )


def find_club_grups(
    repo: Repository, club_fcb_id: str
) -> list[tuple[int, int, int]]:
    """Llista (lliga_id, divisio_id, grup_id) on hi ha equip d'un club.

    Requereix que prèviament s'hagi fet ingest dels grups de lliga amb
    encontres (ingest_lliga_jornada/grup) — l'identificador `equips.club_id`
    s'omple via _ensure_club_equip durant aquell ingest.
    """
    cid = repo.get_club_id_by_fcb_id(club_fcb_id)
    if cid is None:
        return []
    rows = repo.conn.execute(
        """
        SELECT DISTINCT enc.lliga_id, enc.divisio_id, enc.grup_id
        FROM encontres_lliga enc
        WHERE enc.equip_local_id IN (SELECT id FROM equips WHERE club_id = ?)
           OR enc.equip_visitant_id IN (SELECT id FROM equips WHERE club_id = ?)
        ORDER BY enc.lliga_id, enc.divisio_id, enc.grup_id
        """,
        (cid, cid),
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def find_club_players(
    repo: Repository, club_fcb_id: str
) -> list[tuple[str, str]]:
    """Llista (fcb_id, nom) dels jugadors que han jugat amb equip d'aquest club.

    Es deriva dels games (no de players.club_id, que pot estar buit).
    """
    cid = repo.get_club_id_by_fcb_id(club_fcb_id)
    if cid is None:
        return []
    rows = repo.conn.execute(
        """
        SELECT DISTINCT p.fcb_id, p.nom
        FROM games g
        JOIN equips e ON e.id IN (g.equip1_id, g.equip2_id)
        JOIN players p ON p.id IN (g.player1_id, g.player2_id)
        WHERE e.club_id = ?
          AND (
            (e.id = g.equip1_id AND p.id = g.player1_id)
            OR (e.id = g.equip2_id AND p.id = g.player2_id)
          )
        ORDER BY p.nom
        """,
        (cid,),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


# --------------------------- ingest individuals ---------------------------


@dataclass
class IngestIndividualsResult:
    torneigs_processed: int
    torneigs_failed: int
    total_participants: int


def _individuals_llistat_url(base_url: str, temporada: str | None) -> str:
    if temporada is None or temporada == "current":
        return f"{base_url.rstrip('/')}/ca/individuals/llistat"
    return f"{base_url.rstrip('/')}/ca/historial/llistatIndividual/{temporada}"


def ingest_individuals_temporada(
    client: ScraperClient,
    *,
    temporada: str | None = None,
    create_missing_players: bool = True,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> IngestIndividualsResult:
    """Ingest dels torneigs individuals d'una temporada.

    `temporada=None` o `'current'` → temporada actual (`/ca/individuals/llistat`).
    Per cada torneig, descobreix divisions i ingest classificació final.

    `use_cache=False` força fetch fresc — imprescindible per al re-scrape setmanal:
    detecta torneigs nous (apareixen amb ID més alt al llistat) i partides noves
    dins competicions encara obertes (no tancades fins a la classificació definitiva).
    """
    settings = settings or client.settings
    base = settings.base_url.rstrip("/")
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)

    # Si temporada no és string, deduïm de l'historial
    temporada_nom = temporada
    if temporada_nom is None:
        # Per a "current", agafem la temporada actual del context (deriva de data avui).
        from datetime import date as _date
        today = _date.today()
        if today.month >= 8:
            temporada_nom = f"{today.year}-{today.year + 1}"
        else:
            temporada_nom = f"{today.year - 1}-{today.year}"

    # 1. Fetch llistat de torneigs
    url = _individuals_llistat_url(base, temporada)
    try:
        html = client.fetch_html(url, use_cache=use_cache)
    except Exception as e:
        log.error("FAIL fetch individuals llistat: %s", e)
        return IngestIndividualsResult(0, 0, 0)
    torneigs = parse_individuals_torneigs_list(html)
    log.info("Individuals %s: %d torneigs descoberts", temporada_nom, len(torneigs))

    processed = 0
    failed = 0
    total_part = 0
    for torneig in torneigs:
        torneig_url = f"{base}/ca/individuals/divisions/{torneig.torneig_id_extern}"
        try:
            torneig_html = client.fetch_html(torneig_url, use_cache=use_cache)
        except Exception as e:
            log.warning("FAIL torneig %s: %s", torneig.nom, e)
            failed += 1
            continue
        divisions = parse_individuals_divisions(torneig_html)
        if not divisions:
            log.info("  %s: sense divisions parsejables", torneig.nom)
            failed += 1
            continue
        for div in divisions:
            classif_href = div.classif_href or (
                f"ca/individuals/classificaciofinal/{div.torneig_id}/{div.divisio_id_extern}"
            )
            classif_url = f"{base}/{classif_href.lstrip('/')}"
            try:
                classif_html = client.fetch_html(classif_url, use_cache=use_cache)
            except Exception as e:
                log.warning("    FAIL classif %s %s: %s", torneig.nom, div.nom, e)
                continue
            participants = parse_individuals_classificaciofinal(classif_html)
            # Nom complet del torneig: "TRES BANDES - 1A DIVISIÓ". clean_torneig_nom
            # treu el sufix redundant quan la divisió només repeteix el nom del
            # torneig (p.ex. "VI OPEN MATARÓ - OPEN MATARÓ").
            raw_nom = torneig.nom if div.nom == "UNICA" else f"{torneig.nom} - {div.nom}"
            nom_complet = clean_torneig_nom(raw_nom)
            try:
                repo.upsert_torneig_individual(
                    TorneigIndividualRecord(
                        torneig_id_extern=torneig.torneig_id_extern,
                        divisio_id_extern=div.divisio_id_extern,
                        nom=nom_complet,
                        temporada_nom=temporada_nom,
                    )
                )
            except Exception as e:
                log.warning("    FAIL upsert torneig %s: %s", nom_complet, e)
                continue
            # Participants
            n_ok = 0
            for p in participants:
                # Resoldre player_fcb_id
                fcb_id = repo.get_player_fcb_id_by_nom(p.jugador_nom)
                if fcb_id is None:
                    if create_missing_players:
                        fcb_id = repo.resolve_or_create_player_by_nom(p.jugador_nom)
                    else:
                        continue
                try:
                    repo.upsert_torneig_participant(
                        TorneigParticipantRecord(
                            torneig_id_extern=torneig.torneig_id_extern,
                            divisio_id_extern=div.divisio_id_extern,
                            player_fcb_id=fcb_id,
                            posicio=p.posicio,
                            partides_jugades=p.partides_jugades,
                            punts=p.punts,
                            caramboles=p.caramboles,
                            entrades=p.entrades,
                            mitjana_general=p.mitjana_general,
                            mitjana_particular=p.mitjana_particular,
                            serie_max=p.serie_max,
                            club_text=p.club,
                        ),
                        temporada_nom=temporada_nom,
                    )
                    n_ok += 1
                except Exception as e:
                    log.debug("FAIL participant %s: %s", p.jugador_nom, e)
            total_part += n_ok
            log.info("    %s %s: %d participants", torneig.nom, div.nom, n_ok)
        processed += 1
    return IngestIndividualsResult(
        torneigs_processed=processed,
        torneigs_failed=failed,
        total_participants=total_part,
    )


def _current_temporada_label(today: date | None = None) -> str:
    """Etiqueta de la temporada actual (p.ex. '2025-2026'); talla a l'agost."""
    today = today or date.today()
    if today.month >= 8:
        return f"{today.year}-{today.year + 1}"
    return f"{today.year - 1}-{today.year}"


def discover_individual_seasons(client: ScraperClient) -> list[str]:
    """Etiquetes de temporada amb individuals a /ca/historial (p.ex. '2024-2025').

    L'índex de l'historial enllaça cada temporada passada via
    `/ca/historial/llistatIndividual/{temporada}`. Retorna les etiquetes en
    l'ordre del portal (més recent primer), sense duplicats.
    """
    base = client.settings.base_url.rstrip("/")
    html = client.fetch_html(f"{base}/ca/historial", use_cache=False)
    seasons: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"/?ca/historial/llistatIndividual/([\w\-]+)", html):
        season = m.group(1)
        if season not in seen:
            seen.add(season)
            seasons.append(season)
    return seasons


def ingest_individuals_all_temporades(
    client: ScraperClient,
    *,
    create_missing_players: bool = True,
    settings: Settings | None = None,
    use_cache: bool = False,
) -> IngestIndividualsResult:
    """Ingest individuals de la temporada actual + totes les històriques.

    Descobreix les temporades passades a /ca/historial i les recorre una a una,
    a més de la temporada en curs (`/ca/individuals/llistat`). La temporada
    actual s'exclou de la llista històrica si hi apareix, per no fer-la dos cops.
    Cada temporada és aïllada: si una falla, continua amb la resta. Acumula el
    resultat. `use_cache=False` per defecte: és un reimport històric complet.
    """
    settings = settings or client.settings
    current = _current_temporada_label()
    seasons = [s for s in discover_individual_seasons(client) if s != current]
    targets: list[str | None] = [None, *seasons]  # None = temporada en curs
    log.info("Individuals històric: %d temporades (actual + %d passades)",
             len(targets), len(seasons))

    processed = 0
    failed = 0
    total_part = 0
    for target in targets:
        label = target or "current"
        try:
            res = ingest_individuals_temporada(
                client,
                temporada=target,
                create_missing_players=create_missing_players,
                settings=settings,
                use_cache=use_cache,
            )
        except Exception as e:  # aïllat: una temporada que peta no atura la resta
            log.warning("FAIL ingest individuals temporada %s: %s", label, e)
            failed += 1
            continue
        processed += res.torneigs_processed
        failed += res.torneigs_failed
        total_part += res.total_participants
    return IngestIndividualsResult(
        torneigs_processed=processed,
        torneigs_failed=failed,
        total_participants=total_part,
    )


# --------------------------- ingest de copa catalana ---------------------------


@dataclass
class IngestCopaResult:
    jornades: int
    grups: int
    encontres: int
    partides: int


def _copa_base(base_url: str) -> str:
    return base_url.rstrip("/") + "/ca/copa"


def ingest_copa_edicio(
    client: ScraperClient,
    edicio_id: int,
    *,
    jornada: int | None = None,
    use_cache: bool = False,
    settings: Settings | None = None,
) -> IngestCopaResult:
    """Ingest d'una edició de Copa: jornades → grups → encontres → partides.

    Recorre faseGrups/{ed} per descobrir les jornades; per a cada jornada,
    grups/{ed}/{jor}; per a cada grup, encontresGrup (classificació + encontres);
    i per a cada encontre, partidesGrup (partides individuals). Idempotent.

    `jornada` limita a una sola jornada (None = totes). `use_cache=False` força
    dades fresques (el que vol l'actualització nocturna).
    """
    settings = settings or client.settings
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    base = _copa_base(settings.base_url)

    n_jor = n_grups = n_enc = n_part = 0

    html = client.fetch_html(f"{base}/faseGrups/{edicio_id}", use_cache=use_cache)
    jornades = parse_copa_jornades(html)
    if jornada is not None:
        jornades = [j for j in jornades if j.jornada == jornada]

    for ordre, jor in enumerate(jornades, start=1):
        repo.upsert_copa_jornada(jor.edicio_id, jor.jornada, ordre, jor.nom)
        n_jor += 1

        ghtml = client.fetch_html(
            f"{base}/grups/{edicio_id}/{jor.jornada}", use_cache=use_cache
        )
        for g in parse_copa_grups(ghtml):
            n_grups += 1
            ehtml = client.fetch_html(
                f"{base}/encontresGrup/{edicio_id}/{jor.jornada}/{g.grup_id}",
                use_cache=use_cache,
            )
            data = parse_copa_encontresgrup(ehtml)
            grup_nom = data.grup_nom or g.nom

            for row in data.classificacio:
                repo.upsert_copa_classificacio(
                    edicio_id=edicio_id, jornada=jor.jornada, grup_id=g.grup_id,
                    grup_nom=grup_nom, posicio=row.posicio, equip=row.equip,
                    punts=row.punts, parcials=row.parcials, mitjana=row.mitjana,
                )

            for enc in data.encontres:
                enc_id = repo.upsert_copa_encontre(
                    edicio_id=edicio_id, jornada=jor.jornada, grup_id=g.grup_id,
                    grup_nom=grup_nom, enc_id_extern=enc.enc_id_extern,
                    team_a_extern=enc.team_a_extern, team_b_extern=enc.team_b_extern,
                    equip_local=enc.equip_local, equip_visitant=enc.equip_visitant,
                    p_match_local=enc.p_match_local, p_match_visitant=enc.p_match_visitant,
                )
                n_enc += 1
                phtml = client.fetch_html(
                    f"{base}/partidesGrup/{edicio_id}/{jor.jornada}/{g.grup_id}/"
                    f"{enc.enc_id_extern}/{enc.team_a_extern}/{enc.team_b_extern}",
                    use_cache=use_cache,
                )
                partides = parse_copa_partides(phtml)
                repo.replace_copa_partides(
                    enc_id,
                    [
                        (
                            p.ordre, p.local_nom, p.local_caramboles, p.local_serie,
                            p.visitant_nom, p.visitant_caramboles, p.visitant_serie,
                            p.entrades, p.punts_local, p.punts_visitant,
                        )
                        for p in partides
                    ],
                )
                n_part += len(partides)

    return IngestCopaResult(
        jornades=n_jor, grups=n_grups, encontres=n_enc, partides=n_part
    )


def run_status(settings: Settings | None = None) -> dict[str, int]:
    settings = settings or get_settings()
    conn = ensure_schema(settings.db_path)
    repo = Repository(conn)
    return repo.counts()
