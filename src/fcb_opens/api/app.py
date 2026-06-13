"""FastAPI application exposing the fcb-opens package.

All routes are under /api/* to leave the root free for the SvelteKit
frontend when it's served from the same origin (production deploy).

In development the frontend runs on Vite at :5173 and proxies /api/*
to this backend at :8000, so CORS is configured permissively for
localhost origins.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from dataclasses import asdict
from .. import __version__, db
from ..club_resolution import (
    PlayerClubSources,
    resolve_clubs_bulk,
    resolve_player_club,
    set_manual_club,
)
from ..diff import diff_rankings
from ..generator import Tournament, generate_tournament
from ..lliga.refresh import RefreshResult, state as refresh_state
from ..lliga.scraper import incremental_refresh
from ..models import normalize_name
from ..paths import resolve_db_path
from ..player_matching import Player, build_matcher, normalize_for_matching
from ..reglament.ordenacio import InscriptionEntry, sort_inscriptions
from ..reglament.open_match import map_pdf_columns_to_window
from ..reglament.ranquing_opens import (
    OpensRankingEntry,
    apply_official_penalties,
    compute_opens_ranking,
    count_opens_in_window,
    get_window_opens,
    load_player_fcb_averages,
)
from ..scraper.http import fetch as _http_fetch
from ..scraper.official_pdf import (
    OFFICIAL_RANKING_URL,
    fetch_official_ranking_pdf,
    parse_official_ranking,
)
from ..scraper.open_live import (
    _norm_name,
    division_url,
    fetch_doc_pdf,
    fetch_has_final_classification,
    fetch_individuals_llistat,
    fetch_live_state,
    fetch_opens_docs,
    filter_docs_for_division,
    parse_division_page,
)
from ..sync import SyncResult, run_full_sync, sync_state
from ..validator import validate_inscriptions
from ..lliga.stats import (
    division_aggregate,
    group_aggregate,
    partides_for_player,
    player_ranking_for_division,
    player_ranking_for_group,
    slot_performance_for_player,
    team_aggregates_for_group,
)
from .deps import get_connection
from .schemas import (
    AnomalyResponse,
    ClubOption,
    DiffDiscrepancy,
    DiffOpen,
    DiffOverrideRow,
    DiffOverrideUpsertRequest,
    DiffPlayerRef,
    DiffReportResponse,
    EnrichedInscription,
    GeneratorRequest,
    GeneratorResponse,
    GroupResponse,
    GroupSlotResponse,
    HealthResponse,
    InscriptionInput,
    LeagueDivisionDetail,
    LeagueDivisionGroupRef,
    LeagueDivisionSummary,
    LeagueEncontreDetail,
    LeagueEncontreRow,
    LeagueGroupDetail,
    LeagueGroupSummary,
    LeagueJornadaRow,
    LeagueJornadasResponse,
    LeaguePartidaRow,
    LeagueTeamDetail,
    LeagueRefreshLastResult,
    LeagueRefreshStatus,
    LeagueRefreshTriggerResponse,
    LeagueSummary,
    LiveGroup,
    LiveIndexEntry,
    LiveMatch,
    LiveOpenResponse,
    LivePhase,
    LiveSnapshotSummary,
    LiveStanding,
    OpenDocument,
    RankingBandEntry,
    RankingBandResponse,
    ProvisionalQualifier as ProvisionalQualifierSchema,
    MonthlyRankingDetail,
    MonthlyRankingRow,
    MonthlyRankingSummary,
    OpenClassificationRow,
    OpenDetail,
    OpenSummary,
        OpenBreakdown,
    OpensRankingResponse,
    OpensRankingRow,
    PhaseResponse,
    PlayerClubSourcesResponse,
    PlayerLeagueGroupSummary,
    PlayerLeaguePartidaRow,
    PlayerLeagueProfile,
    PlayerLeagueRankingRow,
    PlayerListEntry,
    PlayerRankingHistoryEntry,
    SetManualClubRequest,
    SlotPerformanceRow,
    PlayerOpenResult,
    PlayerProfile,
    StatsResponse,
    SyncResultResponse,
    SyncRunResponse,
    SyncStatusResponse,
    SyncTaskResult,
    TeamStandingRow,
    TournamentResponse,
    ValidatorRequest,
    ValidatorResponse,
)


log = logging.getLogger(__name__)


# Tres Bandes is the only league we actively track. Listed here so the
# startup hook knows what to refresh; new competitions can be added
# later by editing this constant or wiring it through configuration.
DEFAULT_LEAGUE_COMPETITION_IDS: tuple[int, ...] = (36,)


def _run_incremental_refresh_sync(competition_id: int) -> RefreshResult:
    """Open a fresh DB connection, run incremental_refresh, return a result.

    Designed to run inside `asyncio.to_thread` so the event loop stays
    responsive. Errors are caught here and reported via the result object
    rather than propagated, so the task's caller can record them as state
    instead of crashing the server.
    """
    started_at = datetime.now(timezone.utc).isoformat()
    db_path = resolve_db_path()
    db.init_db(db_path)
    conn = db.connect(db_path)
    try:
        progress = incremental_refresh(conn, competition_id)
        return RefreshResult(
            competition_id=competition_id,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            success=True,
            divisions=progress.divisions,
            groups=progress.groups,
            jornades=progress.jornades,
            jornades_skipped=progress.jornades_skipped,
            encontres=progress.encontres,
            partides=progress.partides,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("incremental_refresh failed for competition %s", competition_id)
        return RefreshResult(
            competition_id=competition_id,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            success=False,
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        conn.close()


async def _trigger_refresh(competition_id: int) -> RefreshResult | None:
    """Start an incremental refresh if one isn't already running.

    Returns the completed RefreshResult, or None if a refresh was already
    in flight (the caller should poll the status endpoint).
    """
    async with refresh_state.lock:
        if refresh_state.is_running(competition_id):
            return None
        refresh_state.started(competition_id)
    try:
        result = await asyncio.to_thread(
            _run_incremental_refresh_sync, competition_id
        )
        refresh_state.last_result[competition_id] = result
        return result
    finally:
        async with refresh_state.lock:
            refresh_state.in_progress.pop(competition_id, None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the DB once at startup, then kick off a background
    refresh for each tracked league.

    Running migrations per-request used to fight the background lliga
    refresh for the SQLite write lock; doing it once here at startup
    fixes that. We also switch the DB to WAL journal mode so readers
    can proceed concurrently with the long-running league writer.
    """
    # 1) DB schema + migrations — run once. Errors here should crash
    # startup loudly rather than be hidden behind per-request 500s.
    db_path = resolve_db_path()
    db.init_db(db_path)

    # 2) Switch journal mode to WAL so reads don't block on a writing
    # transaction (huge improvement for the API while a scrape runs).
    # PRAGMA writes are persistent at the DB level, so this only needs
    # to happen once per file.
    bootstrap_conn = db.connect(db_path)
    try:
        bootstrap_conn.execute("PRAGMA journal_mode = WAL").fetchall()
        bootstrap_conn.execute("PRAGMA synchronous = NORMAL").fetchall()
        bootstrap_conn.commit()
    finally:
        bootstrap_conn.close()

    # 3) Background league refresh tasks — fire-and-forget.
    tasks = []
    for cid in DEFAULT_LEAGUE_COMPETITION_IDS:
        tasks.append(asyncio.create_task(_trigger_refresh(cid)))
    try:
        yield
    finally:
        # Don't await on shutdown: a running scrape may take minutes and
        # blocking shutdown defeats the purpose of fire-and-forget. The
        # tasks are best-effort; uvicorn's process exit cancels them.
        for t in tasks:
            if not t.done():
                t.cancel()


def create_app() -> FastAPI:
    app = FastAPI(
        title="fcb-opens API",
        version=__version__,
        description="Backend for the FCB Opens Tres Bandes tooling.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_routes(app)
    return app


# --------------------------------------------------------------------------- #
# Route registration
# --------------------------------------------------------------------------- #


def register_routes(app: FastAPI) -> None:
    @app.get("/api/health", response_model=HealthResponse)
    def health():
        return HealthResponse(status="ok", version=__version__)

    @app.get("/api/stats", response_model=StatsResponse)
    def stats(conn: sqlite3.Connection = Depends(get_connection)):
        n_rankings = db.count_monthly_rankings(conn)
        n_opens = db.count_opens(conn)
        n_players = conn.execute("SELECT COUNT(*) AS n FROM players").fetchone()["n"]
        latest_month_row = conn.execute(
            "SELECT month_id FROM monthly_rankings ORDER BY month_id DESC LIMIT 1"
        ).fetchone()
        latest_month_id = latest_month_row["month_id"] if latest_month_row else None
        latest_open_row = conn.execute(
            "SELECT name FROM opens ORDER BY fcb_division_id DESC LIMIT 1"
        ).fetchone()
        latest_open_name = latest_open_row["name"] if latest_open_row else None
        return StatsResponse(
            monthly_rankings=n_rankings,
            opens=n_opens,
            players=int(n_players),
            latest_month_id=latest_month_id,
            latest_open_name=latest_open_name,
        )

    # --------------------------------------------------------------------- #
    # Monthly rankings
    # --------------------------------------------------------------------- #

    @app.get("/api/rankings/monthly", response_model=list[MonthlyRankingSummary])
    def list_monthly_rankings(conn: sqlite3.Connection = Depends(get_connection)):
        rows = conn.execute(
            """
            SELECT
                mr.month_id,
                mr.fetched_at,
                (SELECT COUNT(*) FROM monthly_ranking_entries mre
                 WHERE mre.ranking_id = mr.id) AS entry_count
            FROM monthly_rankings mr
            ORDER BY mr.month_id DESC
            """
        ).fetchall()
        return [
            MonthlyRankingSummary(
                month_id=row["month_id"],
                fetched_at=row["fetched_at"],
                entry_count=int(row["entry_count"]),
            )
            for row in rows
        ]

    @app.get("/api/rankings/monthly/{month_id}", response_model=MonthlyRankingDetail)
    def get_monthly_ranking(
        month_id: int,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        ranking_row = conn.execute(
            "SELECT id, month_id, fetched_at FROM monthly_rankings WHERE month_id = ?",
            (month_id,),
        ).fetchone()
        if ranking_row is None:
            raise HTTPException(404, detail=f"No monthly ranking for month_id={month_id}")
        entry_rows = conn.execute(
            """
            SELECT mre.position, p.id AS player_id, p.display_name, p.current_club,
                   mre.average, mre.matches_scored, mre.matches_max, mre.is_definitive
            FROM monthly_ranking_entries mre
            JOIN players p ON p.id = mre.player_id
            WHERE mre.ranking_id = ?
            ORDER BY mre.position
            """,
            (ranking_row["id"],),
        ).fetchall()
        # Resolve the canonical assigned club per player so the displayed
        # value matches everywhere — the manual override (if any) wins,
        # else Opens, else Lliga, else the snapshot's own club value.
        player_ids = [int(r["player_id"]) for r in entry_rows]
        sources = resolve_clubs_bulk(conn, player_ids)
        entries = []
        for row in entry_rows:
            pid = int(row["player_id"])
            resolved = sources.get(pid)
            club = (
                resolved.resolved_club
                if resolved and resolved.resolved_club
                else row["current_club"]
            )
            entries.append(
                MonthlyRankingRow(
                    position=row["position"],
                    player_id=pid,
                    player_name=row["display_name"],
                    current_club=club,
                    average=row["average"],
                    matches_scored=row["matches_scored"],
                    matches_max=row["matches_max"],
                    is_definitive=bool(row["is_definitive"]),
                )
            )
        return MonthlyRankingDetail(
            month_id=ranking_row["month_id"],
            fetched_at=ranking_row["fetched_at"],
            entries=entries,
        )

    # --------------------------------------------------------------------- #
    # Opens ranking (computed)
    # --------------------------------------------------------------------- #

    @app.get("/api/rankings/opens", response_model=OpensRankingResponse)
    def opens_ranking(
        window: int = 5,
        apply_penalties: bool = True,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        entries = compute_opens_ranking(conn, num_recent_opens=window)
        in_window = count_opens_in_window(conn, num_recent_opens=window)

        # Fold PDF -20 penalties into the computed totals when a cached
        # official PDF is available. Set apply_penalties=false on the
        # query to inspect the raw HTML-derived ranking.
        if apply_penalties and entries:
            entries = _apply_pdf_penalties_if_available(conn, entries, window)

        # Bulk-resolve assigned clubs so the displayed value matches the
        # one in /players, the diff page, and the monthly ranking.
        sources = resolve_clubs_bulk(conn, [e.player_id for e in entries])
        return OpensRankingResponse(
            window_size=window,
            opens_in_window=in_window,
            entries=[
                OpensRankingRow(
                    rank=i + 1,
                    player_id=e.player_id,
                    display_name=e.display_name,
                    club=(
                        sources[e.player_id].resolved_club
                        if e.player_id in sources and sources[e.player_id].resolved_club
                        else e.club
                    ),
                    total_points=e.total_points,
                    max_single_open=e.max_single_open,
                    opens_played=e.opens_played,
                    breakdown=[OpenBreakdown(**asdict(b)) for b in e.breakdown],
                )
                for i, e in enumerate(entries)
            ],
        )

    # --------------------------------------------------------------------- #
    # Opens (stored)
    # --------------------------------------------------------------------- #

    @app.get("/api/opens", response_model=list[OpenSummary])
    def list_opens(conn: sqlite3.Connection = Depends(get_connection)):
        rows = conn.execute(
            """
            SELECT
                o.id, o.fcb_division_id, o.fcb_classification_id, o.name, o.season,
                (SELECT COUNT(*) FROM open_classifications oc WHERE oc.open_id = o.id) AS player_count
            FROM opens o
            ORDER BY o.fcb_division_id DESC
            """
        ).fetchall()
        return [
            OpenSummary(
                id=row["id"],
                fcb_division_id=row["fcb_division_id"],
                fcb_classification_id=row["fcb_classification_id"],
                name=row["name"],
                season=row["season"],
                player_count=int(row["player_count"]),
            )
            for row in rows
        ]

    @app.get("/api/opens/projections")
    def list_open_projections(conn: sqlite3.Connection = Depends(get_connection)):
        """Provisional brackets computed from inscrits PDFs (pre-publication)."""
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "season": row["season"],
                "num_inscriptions": row["num_inscriptions"],
                "fcb_division_id": row["fcb_division_id"],
                "created_at": row["created_at"],
            }
            for row in db.list_projections(conn)
        ]

    @app.get("/api/opens/projections/{projection_id}")
    def get_open_projection(
        projection_id: int, conn: sqlite3.Connection = Depends(get_connection)
    ):
        """Full projected bracket payload for one Open."""
        import json as _json

        row = db.get_projection(conn, projection_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Projecció no trobada")
        payload = _json.loads(row["payload_json"])
        payload["id"] = row["id"]
        payload["created_at"] = row["created_at"]
        payload["fcb_division_id"] = row["fcb_division_id"]
        return payload

    @app.post("/api/opens/projections/{projection_id}/link")
    def link_projection_division(
        projection_id: int, fcb_division_id: int,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        """Link a projection to its live federation division (once groups publish)."""
        if db.get_projection(conn, projection_id) is None:
            raise HTTPException(status_code=404, detail="Projecció no trobada")
        db.set_projection_division(conn, projection_id, fcb_division_id)
        return {"ok": True, "projection_id": projection_id, "fcb_division_id": fcb_division_id}

    @app.get("/api/opens/projections/{projection_id}/compare")
    def compare_projection_with_live(
        projection_id: int, force: bool = False,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        """Compare the projected group placement against the real published draw.

        Returns {"published": false} until the projection is linked to a live
        division and that division exposes group data on fcbillar.cat.
        """
        import json as _json
        import re

        row = db.get_projection(conn, projection_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Projecció no trobada")
        division_id = row["fcb_division_id"]
        if not division_id:
            return {"published": False, "reason": "no_division_linked"}

        def _norm(s: str) -> str:
            return re.sub(r",\s*", ", ", s or "").strip().upper()

        # Projected placement: player name -> "phase · group".
        payload = _json.loads(row["payload_json"])
        projected: dict[str, str] = {}
        for ph in payload.get("phases", []):
            for g in ph.get("groups", []):
                for p in g.get("players", []):
                    if p.get("kind") == "player" and p.get("player_name"):
                        projected[_norm(p["player_name"])] = f"{ph['title']} · Grup {g['label']}"

        try:
            state = fetch_live_state(division_id, force=force)
        except Exception as exc:  # noqa: BLE001
            return {"published": False, "reason": "live_unreachable", "error": str(exc)}

        real: dict[str, str] = {}
        real_phases = []
        for ph in state.phases:
            if ph.ref.kind != "group":
                continue
            groups_out = []
            for g in ph.groups:
                names = [s.player_name for s in g.standings]
                groups_out.append({"label": g.label, "players": names})
                for s in g.standings:
                    real[_norm(s.player_name)] = f"{ph.ref.label} · {g.label}"
            real_phases.append({"label": ph.ref.label, "groups": groups_out})

        if not real:
            return {"published": False, "reason": "no_real_groups_yet", "real_phases": real_phases}

        moves = []
        for name_norm, proj_loc in projected.items():
            if name_norm in real:
                moves.append({
                    "player": name_norm,
                    "projected": proj_loc,
                    "real": real[name_norm],
                })
        return {
            "published": True,
            "n_matched": len(moves),
            "moves": sorted(moves, key=lambda m: m["player"]),
            "real_phases": real_phases,
        }

    @app.get("/api/opens/live", response_model=list[LiveIndexEntry])
    def list_live_competitions(
        force: bool = False,
        only_ongoing: bool = True,
        only_opens: bool = True,
    ):
        """Return the FCB 'individuals/llistat' — current-season competitions.

        By default (`only_ongoing=True`, `only_opens=True`), filters down to
        competitions whose name contains 'Open' AND whose landing page does
        NOT yet expose a final classification link — i.e., Opens currently
        in progress.

        The filter costs one extra FCB fetch per competition (cached 1h).
        Pass `only_ongoing=false` and `only_opens=false` to get the raw list.
        """
        try:
            entries = fetch_individuals_llistat(force=force)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, detail=f"FCB fetch failed: {exc}") from exc

        def passes(e) -> bool:
            name_upper = e.name.upper()
            if only_opens and "OPEN" not in name_upper:
                return False
            # Women's Opens (OPEN FEMENI) follow a different format we don't
            # track live; treat them as already-played and exclude from the
            # ongoing list.
            if only_ongoing and "FEMENI" in name_upper:
                return False
            if only_ongoing:
                try:
                    if fetch_has_final_classification(e.division_id, force=force):
                        return False
                except Exception:  # noqa: BLE001
                    # A fetch failure for a single division shouldn't drop the
                    # whole endpoint — treat the entry as ongoing to be safe.
                    pass
            return True

        filtered = [e for e in entries if passes(e)]
        return [
            LiveIndexEntry(division_id=e.division_id, name=e.name, index=e.index)
            for e in filtered
        ]

    @app.get(
        "/api/opens/live/{division_id}",
        response_model=LiveOpenResponse,
    )
    def get_open_live(
        division_id: int,
        force: bool = False,
        persist: bool = False,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        """Return the live state of an ongoing Open (groups + KO rounds).

        Fetches directly from fcbillar.cat using the shared HTTP cache
        (1h TTL by default; `force=true` bypasses it for a full refresh).
        When `persist=true`, the rendered response is also appended to
        `open_live_snapshots` so the timeline can be reconstructed later.
        """
        from datetime import datetime, timezone

        # Ordre de sorteig dels grups encara no jugats = ordre del rànquing d'Opens.
        # Si el càlcul falla, deixem l'ordre de la federació (rank_by_name=None).
        try:
            _opens_rank = compute_opens_ranking(conn)
            rank_by_name = {
                _norm_name(e.display_name): i + 1 for i, e in enumerate(_opens_rank)
            }
        except Exception:  # noqa: BLE001
            rank_by_name = None

        try:
            state = fetch_live_state(
                division_id, force=force, rank_by_name=rank_by_name
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, detail=f"FCB fetch failed: {exc}") from exc

        def match_to_schema(m) -> LiveMatch:
            return LiveMatch(
                player_a=m.player_a,
                player_b=m.player_b,
                punts_a=m.punts_a,
                punts_b=m.punts_b,
                caramboles_a=m.caramboles_a,
                caramboles_b=m.caramboles_b,
                serie_major_a=m.serie_major_a,
                serie_major_b=m.serie_major_b,
                entrades=m.entrades,
                arbitre=m.arbitre,
                is_played=m.is_played,
            )

        phases: list[LivePhase] = []
        for detail in state.phases:
            groups_out: list[LiveGroup] = []
            for g in detail.groups:
                played = sum(1 for m in g.matches if m.is_played)
                groups_out.append(
                    LiveGroup(
                        label=g.label,
                        url=g.url,
                        venue=g.venue,
                        standings=[
                            LiveStanding(
                                player_name=s.player_name,
                                club=s.club,
                                punts=s.punts,
                                mitjana=s.mitjana,
                            )
                            for s in g.standings
                        ],
                        matches=[match_to_schema(m) for m in g.matches],
                        n_matches_played=played,
                        n_matches_total=len(g.matches),
                    )
                )
            ko_out = [match_to_schema(m) for m in detail.ko_matches]
            # "active" = has some played matches AND some still pending
            if detail.ref.kind == "group":
                played_total = sum(g.n_matches_played for g in groups_out)
                pending_total = sum(
                    g.n_matches_total - g.n_matches_played for g in groups_out
                )
                is_active = played_total > 0 and pending_total > 0
            else:
                is_active = len(ko_out) > 0 and any(not m.is_played for m in ko_out)
            prov_matches_out = [match_to_schema(m) for m in detail.provisional_matches]
            phases.append(
                LivePhase(
                    label=detail.ref.label,
                    kind=detail.ref.kind,
                    url=detail.ref.url,
                    groups=groups_out,
                    ko_matches=ko_out,
                    is_active=is_active,
                    provisional_qualifiers=[
                        ProvisionalQualifierSchema(
                            group_label=q.group_label,
                            position_in_group=q.position_in_group,
                            player_name=q.player_name,
                            club=q.club,
                            punts=q.punts,
                            mitjana=q.mitjana,
                            serie_major=q.serie_major,
                        )
                        for q in detail.provisional_qualifiers
                    ],
                    provisional_matches=prov_matches_out,
                )
            )

        response = LiveOpenResponse(
            division_id=state.structure.division_id,
            name=state.structure.name,
            phase_id=state.structure.phase_id,
            phases=phases,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
        if persist:
            db.save_live_snapshot(
                conn,
                fcb_division_id=division_id,
                payload_json=response.model_dump_json(),
                captured_at=response.fetched_at,
            )
            conn.commit()
        return response

    @app.get(
        "/api/opens/live/{division_id}/by-ranking-band",
        response_model=RankingBandResponse,
    )
    def get_open_live_by_ranking_band(
        division_id: int,
        month_id: int | None = None,
        force: bool = False,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        """Parallel real-time classifications partitioned by FCB ranking band.

        For each player currently visible in the Open's group standings,
        look up their position in the FCB monthly ranking at `month_id`
        (defaults to the latest stored ranking — the snapshot in force at
        the moment of convocatòria for ongoing Opens) and bucket them:

          * band_61_180   — FCB positions 61..180
          * band_181_plus — FCB positions ≥ 181
          * unranked      — Definitiva / Provisional / never in the ranking

        Each bucket is sorted by live mitjana (descending), with punts as
        the tiebreaker. The top-60 are intentionally excluded — they're
        the natural focus of the main standings view already.
        """
        from datetime import datetime, timezone

        try:
            state = fetch_live_state(division_id, force=force)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, detail=f"FCB fetch failed: {exc}") from exc

        # Resolve the convocatòria-time monthly ranking (default: latest).
        if month_id is not None:
            ranking_row = conn.execute(
                "SELECT id, month_id FROM monthly_rankings WHERE month_id = ?",
                (month_id,),
            ).fetchone()
            if ranking_row is None:
                raise HTTPException(404, detail=f"No monthly ranking for month_id={month_id}")
        else:
            ranking_row = conn.execute(
                "SELECT id, month_id FROM monthly_rankings ORDER BY month_id DESC LIMIT 1"
            ).fetchone()
            if ranking_row is None:
                raise HTTPException(404, detail="No monthly ranking stored in the DB yet")

        resolved_month_id = ranking_row["month_id"]
        rows = conn.execute(
            """
            SELECT p.normalized_name, mre.position, mre.is_definitive
            FROM monthly_ranking_entries mre
            JOIN players p ON p.id = mre.player_id
            WHERE mre.ranking_id = ?
            """,
            (ranking_row["id"],),
        ).fetchall()
        ranking_by_name: dict[str, dict] = {row["normalized_name"]: dict(row) for row in rows}

        # Walk all group standings across all phases. A player advancing
        # through phases may appear in more than one (their finished PPP
        # group + their current PP group). The later occurrence in the
        # phase list wins — phases come from FCB in least-advanced first
        # order, so iterating naturally gives us the current location.
        # Also: KO matches have no standings (just pairings) so they're
        # naturally excluded.
        latest_by_player: dict[str, RankingBandEntry] = {}
        for phase in state.phases:
            for group in phase.groups:
                for s in group.standings:
                    key = normalize_name(s.player_name)
                    match = ranking_by_name.get(key)
                    fcb_pos = match["position"] if match else None
                    fcb_def = bool(match["is_definitive"]) if match else False
                    latest_by_player[key] = RankingBandEntry(
                        player_name=s.player_name,
                        club=s.club,
                        fcb_position=fcb_pos,
                        fcb_is_definitive=fcb_def,
                        phase_label=phase.ref.label,
                        group_label=group.label,
                        punts=s.punts,
                        mitjana=s.mitjana,
                    )

        band_61_180: list[RankingBandEntry] = []
        band_181_plus: list[RankingBandEntry] = []
        unranked: list[RankingBandEntry] = []
        for entry in latest_by_player.values():
            pos = entry.fcb_position
            if pos is None:
                unranked.append(entry)
            elif 61 <= pos <= 180:
                band_61_180.append(entry)
            elif pos >= 181:
                band_181_plus.append(entry)
            # pos < 61 → top-tier; intentionally dropped from this view.

        # Sort each band by live performance: mitjana DESC, punts DESC.
        def sort_key(e: RankingBandEntry) -> tuple[float, int]:
            return (-e.mitjana, -e.punts)

        band_61_180.sort(key=sort_key)
        band_181_plus.sort(key=sort_key)
        unranked.sort(key=sort_key)

        return RankingBandResponse(
            division_id=state.structure.division_id,
            open_name=state.structure.name,
            month_id=resolved_month_id,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            band_61_180=band_61_180,
            band_181_plus=band_181_plus,
            unranked=unranked,
        )

    @app.get("/api/opens/docs/{doc_id}/pdf")
    def get_doc_pdf(doc_id: int, force: bool = False):
        """Proxy the underlying FCB PDF through our backend.

        The app is the single entry point — the frontend never links
        directly to fcbillar.cat media URLs. Cached locally via the shared
        HTTP cache so repeated downloads are instant.
        """
        try:
            pdf_bytes, filename = fetch_doc_pdf(doc_id, force=force)
        except ValueError as exc:
            raise HTTPException(404, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, detail=f"FCB fetch failed: {exc}") from exc
        # Inline disposition so PDFs open in the browser tab by default.
        safe_name = filename.replace('"', "")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{safe_name}"',
                # Tell proxies/browsers they can cache for an hour, matching
                # our upstream TTL. The frontend can still force-refresh.
                "Cache-Control": "public, max-age=3600",
            },
        )

    @app.get("/api/opens/docs", response_model=list[OpenDocument])
    def list_opens_docs(force: bool = False):
        """Return all published Opens documents (convocatòries, organigrames,
        horaris, grups, setzens…) for the current season, newest first."""
        try:
            docs = fetch_opens_docs(force=force)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, detail=f"FCB fetch failed: {exc}") from exc
        return [
            OpenDocument(
                doc_id=d.doc_id,
                title=d.title,
                date=d.date,
                view_url=d.view_url,
            )
            for d in docs
        ]

    @app.get(
        "/api/opens/live/{division_id}/documents",
        response_model=list[OpenDocument],
    )
    def list_docs_for_open(division_id: int, force: bool = False):
        """Return documents linked to a specific Open (by title keyword match)."""
        try:
            html = _http_fetch(division_url(division_id), force=force)
            structure = parse_division_page(html, division_id)
            docs = fetch_opens_docs(force=force)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, detail=f"FCB fetch failed: {exc}") from exc
        matched = filter_docs_for_division(docs, division_id, structure.name)
        return [
            OpenDocument(
                doc_id=d.doc_id,
                title=d.title,
                date=d.date,
                view_url=d.view_url,
            )
            for d in matched
        ]

    @app.get(
        "/api/opens/live/{division_id}/snapshots",
        response_model=list[LiveSnapshotSummary],
    )
    def list_snapshots(
        division_id: int,
        limit: int = 100,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        rows = db.list_live_snapshots(conn, division_id, limit=limit)
        return [
            LiveSnapshotSummary(id=r["id"], captured_at=r["captured_at"])
            for r in rows
        ]

    @app.get(
        "/api/opens/live/snapshot/{snapshot_id}",
        response_model=LiveOpenResponse,
    )
    def get_snapshot(
        snapshot_id: int,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        row = db.get_live_snapshot(conn, snapshot_id)
        if row is None:
            raise HTTPException(404, detail=f"Snapshot {snapshot_id} not found")
        import json
        payload = json.loads(row["payload_json"])
        return LiveOpenResponse(**payload)

    @app.get("/api/opens/{open_id}", response_model=OpenDetail)
    def get_open(open_id: int, conn: sqlite3.Connection = Depends(get_connection)):
        open_row = conn.execute(
            "SELECT id, fcb_division_id, fcb_classification_id, name, season FROM opens WHERE id = ?",
            (open_id,),
        ).fetchone()
        if open_row is None:
            raise HTTPException(404, detail=f"No Open with id={open_id}")
        clf_rows = conn.execute(
            """
            SELECT oc.position, p.id AS player_id, p.display_name, oc.club,
                   oc.matches_played, oc.match_points, oc.caramboles, oc.entries,
                   oc.general_average, oc.particular_average, oc.best_series, oc.open_points
            FROM open_classifications oc
            JOIN players p ON p.id = oc.player_id
            WHERE oc.open_id = ?
            ORDER BY oc.position
            """,
            (open_id,),
        ).fetchall()
        return OpenDetail(
            id=open_row["id"],
            fcb_division_id=open_row["fcb_division_id"],
            fcb_classification_id=open_row["fcb_classification_id"],
            name=open_row["name"],
            season=open_row["season"],
            classification=[
                OpenClassificationRow(
                    position=row["position"],
                    player_id=row["player_id"],
                    player_name=row["display_name"],
                    club=row["club"],
                    matches_played=row["matches_played"],
                    match_points=row["match_points"],
                    caramboles=row["caramboles"],
                    entries=row["entries"],
                    general_average=row["general_average"],
                    particular_average=row["particular_average"],
                    best_series=row["best_series"],
                    open_points=row["open_points"],
                )
                for row in clf_rows
            ],
        )

    # --------------------------------------------------------------------- #
    # Player profile
    # --------------------------------------------------------------------- #

    @app.get("/api/clubs", response_model=list[ClubOption])
    def list_clubs(conn: sqlite3.Connection = Depends(get_connection)):
        """Return every distinct *club* (institution) we have ever seen.

        Three layers of deduplication:
          1. `extract_club_name` strips trailing team suffix
             (`B.C. GRANOLLERS "A"` → `B.C. GRANOLLERS`).
          2. `canonical_club_key` collapses formatting variants
             (`C.B.Vilanova`, `C.B. Vilanova`, `C.B. VILANOVA` → same club).
          3. The display form is the most-frequent variant, breaking ties
             by preferring the form that contains spaces (the one the user
             is more likely to expect from FCB publications).

        Sources: Opens classifications, monthly ranking entries, league
        encontres (home + away), and existing players.current_club /
        players.manual_club.
        """
        from collections import defaultdict

        from ..models import canonical_club_key, extract_club_name

        # variant_counts[key][display] = occurrences
        variant_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        sources_for: dict[str, set[str]] = defaultdict(set)
        total_counts: dict[str, int] = defaultdict(int)

        def _add(value: object, source: str, weight: int = 1) -> None:
            display = extract_club_name(value if isinstance(value, str) else None)
            if not display:
                return
            key = canonical_club_key(display)
            if not key:
                return
            variant_counts[key][display] += weight
            sources_for[key].add(source)
            total_counts[key] += weight

        for row in conn.execute(
            "SELECT club, COUNT(*) AS n FROM open_classifications "
            "WHERE club IS NOT NULL GROUP BY club"
        ).fetchall():
            _add(row["club"], "opens", int(row["n"] or 0))
        for row in conn.execute(
            "SELECT club, COUNT(*) AS n FROM monthly_ranking_entries "
            "WHERE club IS NOT NULL GROUP BY club"
        ).fetchall():
            _add(row["club"], "monthly_ranking", int(row["n"] or 0))
        for row in conn.execute(
            "SELECT home_team_name AS name, COUNT(*) AS n FROM league_encontres "
            "GROUP BY home_team_name"
        ).fetchall():
            _add(row["name"], "lliga", int(row["n"] or 0))
        for row in conn.execute(
            "SELECT away_team_name AS name, COUNT(*) AS n FROM league_encontres "
            "GROUP BY away_team_name"
        ).fetchall():
            _add(row["name"], "lliga", int(row["n"] or 0))
        for row in conn.execute(
            "SELECT current_club, COUNT(*) AS n FROM players "
            "WHERE current_club IS NOT NULL GROUP BY current_club"
        ).fetchall():
            _add(row["current_club"], "players_current", int(row["n"] or 0))
        for row in conn.execute(
            "SELECT manual_club, COUNT(*) AS n FROM players "
            "WHERE manual_club IS NOT NULL GROUP BY manual_club"
        ).fetchall():
            _add(row["manual_club"], "manual", int(row["n"] or 0))

        def _pick_display(variants: dict[str, int]) -> str:
            # Sort by: most frequent first; tie-break preferring forms with
            # spaces (more readable, matches FCB publication style); final
            # tie-break alphabetical for determinism.
            return sorted(
                variants.items(),
                key=lambda kv: (-kv[1], 0 if " " in kv[0] else 1, kv[0]),
            )[0][0]

        result = [
            ClubOption(
                name=_pick_display(variants),
                sources=sorted(sources_for[key]),
                occurrences=total_counts[key],
            )
            for key, variants in variant_counts.items()
        ]
        result.sort(key=lambda c: c.name.casefold())
        return result

    @app.get("/api/players", response_model=list[PlayerListEntry])
    def list_players(
        q: str | None = None,
        missing_club: bool = False,
        limit: int = 200,
        offset: int = 0,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        """List players with their resolved club source.

        Filters:
          * `q` — case-insensitive substring of display name or normalized name
          * `missing_club` — only players whose resolved club is None
                             (no Opens, no Lliga, no manual override)
          * `limit`/`offset` — paging; default 200 keeps the response light.
        """
        where: list[str] = []
        params: list[object] = []
        if q:
            where.append(
                "(LOWER(p.display_name) LIKE ? OR LOWER(p.normalized_name) LIKE ?)"
            )
            like = f"%{q.strip().lower()}%"
            params.extend([like, like])
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            f"""
            SELECT
                p.id, p.display_name, p.normalized_name, p.current_club, p.manual_club,
                (SELECT COUNT(*) FROM open_classifications oc
                 WHERE oc.player_id = p.id) AS opens_played,
                (SELECT COUNT(*) FROM league_partides lp
                 WHERE lp.home_player_id = p.id OR lp.away_player_id = p.id)
                    AS lliga_partides
            FROM players p
            {where_sql}
            ORDER BY p.display_name ASC
            LIMIT ? OFFSET ?
            """,
            params + [max(1, min(limit, 1000)), max(0, offset)],
        ).fetchall()

        if not rows:
            return []

        ids = [int(r["id"]) for r in rows]
        sources = resolve_clubs_bulk(conn, ids)

        out: list[PlayerListEntry] = []
        for r in rows:
            pid = int(r["id"])
            s = sources.get(pid)
            csr = _club_sources_to_response(s) if s else PlayerClubSourcesResponse(
                opens_club=None, lliga_club=None, manual_club=None,
                resolved_club=None, source="none",
            )
            if missing_club and csr.resolved_club is not None:
                continue
            out.append(
                PlayerListEntry(
                    id=pid,
                    display_name=r["display_name"],
                    normalized_name=r["normalized_name"],
                    club_sources=csr,
                    opens_played=int(r["opens_played"] or 0),
                    lliga_partides=int(r["lliga_partides"] or 0),
                )
            )
        return out

    @app.patch("/api/players/{player_id}/club", response_model=PlayerClubSourcesResponse)
    def patch_player_manual_club(
        player_id: int,
        req: SetManualClubRequest,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        exists = conn.execute(
            "SELECT 1 FROM players WHERE id = ?", (player_id,)
        ).fetchone()
        if exists is None:
            raise HTTPException(404, detail=f"No player with id={player_id}")
        set_manual_club(conn, player_id, req.manual_club)
        conn.commit()
        sources = resolve_player_club(conn, player_id)
        return _club_sources_to_response(sources)

    @app.get("/api/players/{player_id}", response_model=PlayerProfile)
    def get_player(player_id: int, conn: sqlite3.Connection = Depends(get_connection)):
        player = conn.execute(
            "SELECT id, display_name, normalized_name, current_club FROM players WHERE id = ?",
            (player_id,),
        ).fetchone()
        if player is None:
            raise HTTPException(404, detail=f"No player with id={player_id}")
        latest_entry = conn.execute(
            """
            SELECT mre.position, mre.average, mre.matches_scored, mre.matches_max,
                   mre.is_definitive, p.current_club, p.display_name, p.id AS player_id
            FROM monthly_ranking_entries mre
            JOIN players p ON p.id = mre.player_id
            JOIN monthly_rankings mr ON mr.id = mre.ranking_id
            WHERE mre.player_id = ?
            ORDER BY mr.month_id DESC
            LIMIT 1
            """,
            (player_id,),
        ).fetchone()
        latest = None
        if latest_entry is not None:
            latest = MonthlyRankingRow(
                position=latest_entry["position"],
                player_id=latest_entry["player_id"],
                player_name=latest_entry["display_name"],
                current_club=latest_entry["current_club"],
                average=latest_entry["average"],
                matches_scored=latest_entry["matches_scored"],
                matches_max=latest_entry["matches_max"],
                is_definitive=bool(latest_entry["is_definitive"]),
            )
        history_rows = conn.execute(
            """
            SELECT o.id AS open_id, o.name AS open_name, o.fcb_division_id,
                   oc.position, oc.general_average, oc.open_points
            FROM open_classifications oc
            JOIN opens o ON o.id = oc.open_id
            WHERE oc.player_id = ?
            ORDER BY o.fcb_division_id DESC
            """,
            (player_id,),
        ).fetchall()
        opens_history = [
            PlayerOpenResult(
                open_id=row["open_id"],
                open_name=row["open_name"],
                position=row["position"],
                general_average=row["general_average"],
                open_points=row["open_points"],
            )
            for row in history_rows
        ]
        total_points = sum(r.open_points for r in opens_history)
        sources = resolve_player_club(conn, player_id)

        # Full monthly-ranking history for this player, ordered oldest → newest
        # so the frontend can render the mitjana evolution in a single pass.
        ranking_history_rows = conn.execute(
            """
            SELECT mr.month_id, mr.fetched_at, mre.position, mre.average,
                   mre.matches_scored, mre.matches_max, mre.is_definitive,
                   mre.club
            FROM monthly_ranking_entries mre
            JOIN monthly_rankings mr ON mr.id = mre.ranking_id
            WHERE mre.player_id = ?
            ORDER BY mr.month_id ASC
            """,
            (player_id,),
        ).fetchall()
        ranking_history = [
            PlayerRankingHistoryEntry(
                month_id=int(r["month_id"]),
                fetched_at=str(r["fetched_at"]),
                position=int(r["position"]),
                average=float(r["average"]),
                matches_scored=int(r["matches_scored"] or 0),
                matches_max=int(r["matches_max"] or 0),
                is_definitive=bool(r["is_definitive"]),
                club=r["club"],
            )
            for r in ranking_history_rows
        ]

        return PlayerProfile(
            id=player["id"],
            display_name=player["display_name"],
            normalized_name=player["normalized_name"],
            current_club=player["current_club"],
            club_sources=_club_sources_to_response(sources),
            latest_monthly_ranking=latest,
            total_opens_points=total_points,
            opens_history=opens_history,
            ranking_history=ranking_history,
        )

    # --------------------------------------------------------------------- #
    # Lliga (league) endpoints
    # --------------------------------------------------------------------- #

    @app.get(
        "/api/leagues/refresh-status",
        response_model=LeagueRefreshStatus,
    )
    def get_refresh_status():
        """Return the in-progress/last-result map for league refreshes.

        UI polls this while a refresh is running. Once the refresh
        finishes, `last_result[competition_id]` carries counters and any
        error so the frontend can render a green/red toast.
        """
        return LeagueRefreshStatus(
            in_progress=list(refresh_state.in_progress.keys()),
            last_result={
                cid: LeagueRefreshLastResult(**r.__dict__)
                for cid, r in refresh_state.last_result.items()
            },
        )

    @app.post(
        "/api/leagues/refresh",
        response_model=LeagueRefreshTriggerResponse,
        status_code=202,
    )
    async def trigger_refresh(competition_id: int = 36):
        """Schedule a background incremental refresh for a competition.

        Returns 202 immediately. The task runs to completion in the
        background; clients should poll /api/leagues/refresh-status to know
        when it's done. If a refresh is already running for this competition
        the request is accepted as a no-op (`already_running=True`).
        """
        async with refresh_state.lock:
            already = refresh_state.is_running(competition_id)
        if already:
            return LeagueRefreshTriggerResponse(
                competition_id=competition_id,
                accepted=True,
                already_running=True,
            )
        asyncio.create_task(_trigger_refresh(competition_id))
        return LeagueRefreshTriggerResponse(
            competition_id=competition_id,
            accepted=True,
            already_running=False,
        )

    @app.get("/api/leagues", response_model=list[LeagueSummary])
    def list_leagues(conn: sqlite3.Connection = Depends(get_connection)):
        """Return all stored leagues with their division/group tree.

        Each group carries lightweight counters (teams, jornades, partides
        played) so the index page can render KPI cards without a second
        round-trip per group.
        """
        leagues = conn.execute(
            """
            SELECT id, fcb_competition_id, name, season, fetched_at
            FROM leagues
            ORDER BY fcb_competition_id
            """
        ).fetchall()
        out: list[LeagueSummary] = []
        for lg in leagues:
            divisions = conn.execute(
                """
                SELECT id, fcb_division_id, name
                FROM league_divisions
                WHERE league_id = ?
                ORDER BY fcb_division_id
                """,
                (lg["id"],),
            ).fetchall()
            div_summaries: list[LeagueDivisionSummary] = []
            for d in divisions:
                groups = conn.execute(
                    """
                    SELECT lg.id, lg.fcb_group_id, lg.name,
                           (SELECT COUNT(*) FROM league_team_standings ts
                              WHERE ts.group_id = lg.id) AS teams_count,
                           (SELECT COUNT(*) FROM league_jornades lj
                              WHERE lj.group_id = lg.id) AS jornades_count,
                           (SELECT COUNT(*)
                              FROM league_partides lp
                              JOIN league_encontres le ON le.id = lp.encontre_id
                              JOIN league_jornades lj ON lj.id = le.jornada_id
                              WHERE lj.group_id = lg.id AND lp.is_played = 1
                           ) AS partides_played
                    FROM league_groups lg
                    WHERE lg.division_id = ?
                    ORDER BY lg.name
                    """,
                    (d["id"],),
                ).fetchall()
                group_summaries: list[LeagueGroupSummary] = []
                for g in groups:
                    st_rows = conn.execute(
                        """
                        SELECT position, team_name,
                               match_points, set_points, matches_played
                        FROM league_team_standings
                        WHERE group_id = ?
                        ORDER BY position
                        """,
                        (g["id"],),
                    ).fetchall()
                    aggregates = team_aggregates_for_group(conn, g["id"])
                    overall = group_aggregate(conn, g["id"])
                    last_jornada = _last_jornada_for_group(conn, g["id"])
                    group_summaries.append(
                        LeagueGroupSummary(
                            id=g["id"],
                            fcb_group_id=g["fcb_group_id"],
                            name=g["name"],
                            teams_count=int(g["teams_count"]),
                            jornades_count=int(g["jornades_count"]),
                            partides_played=int(g["partides_played"]),
                            standings=[
                                _team_standing_row(r, aggregates)
                                for r in st_rows
                            ],
                            caramboles=overall.caramboles,
                            entrades=overall.entrades,
                            average=overall.average,
                            last_jornada=last_jornada,
                        )
                    )
                div_summaries.append(
                    LeagueDivisionSummary(
                        id=d["id"],
                        fcb_division_id=d["fcb_division_id"],
                        name=d["name"],
                        groups=group_summaries,
                    )
                )
            out.append(
                LeagueSummary(
                    id=lg["id"],
                    fcb_competition_id=lg["fcb_competition_id"],
                    name=lg["name"],
                    season=lg["season"],
                    fetched_at=lg["fetched_at"],
                    divisions=div_summaries,
                )
            )
        return out

    @app.get("/api/leagues/groups/{group_id}", response_model=LeagueGroupDetail)
    def get_league_group(
        group_id: int,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        """Group page payload: team standings + per-player ranking by category."""
        group_row = conn.execute(
            """
            SELECT lg.id, lg.fcb_group_id, lg.name,
                   ld.id AS division_id, ld.name AS division_name,
                   l.name AS league_name, l.season, l.id AS league_id
            FROM league_groups lg
            JOIN league_divisions ld ON ld.id = lg.division_id
            JOIN leagues l ON l.id = ld.league_id
            WHERE lg.id = ?
            """,
            (group_id,),
        ).fetchone()
        if group_row is None:
            raise HTTPException(404, detail=f"No league group with id={group_id}")

        st_rows = conn.execute(
            """
            SELECT position, team_name, match_points, set_points, matches_played
            FROM league_team_standings
            WHERE group_id = ?
            ORDER BY position
            """,
            (group_id,),
        ).fetchall()
        aggregates = team_aggregates_for_group(conn, group_id)
        overall = group_aggregate(conn, group_id)

        ranking = player_ranking_for_group(conn, group_id)

        return LeagueGroupDetail(
            id=group_row["id"],
            fcb_group_id=group_row["fcb_group_id"],
            name=group_row["name"],
            division_id=group_row["division_id"],
            division_name=group_row["division_name"],
            league_name=group_row["league_name"],
            league_id=group_row["league_id"],
            season=group_row["season"],
            caramboles=overall.caramboles,
            entrades=overall.entrades,
            average=overall.average,
            standings=[_team_standing_row(r, aggregates) for r in st_rows],
            player_ranking=[_ranking_row(e, i + 1) for i, e in enumerate(ranking)],
        )

    @app.get(
        "/api/leagues/groups/{group_id}/teams/{team_name}",
        response_model=LeagueTeamDetail,
    )
    def get_league_team(
        group_id: int,
        team_name: str,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        """Team detail within a group: standing row, aggregate, ranked players.

        `team_name` must match `league_team_standings.team_name` exactly
        (URL-decoded). Players are filtered to those who appeared on the
        team's side in any played partida; their KPIs come from the same
        per-group aggregation used elsewhere.
        """
        meta = conn.execute(
            """
            SELECT lg.id AS group_id, lg.name AS group_name,
                   ld.id AS division_id, ld.name AS division_name,
                   l.id AS league_id, l.name AS league_name, l.season
            FROM league_groups lg
            JOIN league_divisions ld ON ld.id = lg.division_id
            JOIN leagues l ON l.id = ld.league_id
            WHERE lg.id = ?
            """,
            (group_id,),
        ).fetchone()
        if meta is None:
            raise HTTPException(404, detail=f"No league group with id={group_id}")

        # The team must exist either in standings or as one of the encounter
        # sides. Standings is the canonical source; reject early if absent.
        st_row = conn.execute(
            """
            SELECT position, team_name, match_points, set_points, matches_played
            FROM league_team_standings
            WHERE group_id = ? AND team_name = ?
            """,
            (group_id, team_name),
        ).fetchone()
        if st_row is None:
            # Some teams may exist as encounter sides without a standings
            # row yet (early in the season). Allow that, but verify the
            # team appears on at least one encontre.
            seen = conn.execute(
                """
                SELECT 1 FROM league_encontres le
                JOIN league_jornades lj ON lj.id = le.jornada_id
                WHERE lj.group_id = ?
                  AND (le.home_team_name = ? OR le.away_team_name = ?)
                LIMIT 1
                """,
                (group_id, team_name, team_name),
            ).fetchone()
            if seen is None:
                raise HTTPException(
                    404, detail=f"Team {team_name!r} not found in group {group_id}"
                )

        aggregates = team_aggregates_for_group(conn, group_id)
        standing_row = (
            _team_standing_row(st_row, aggregates) if st_row is not None else None
        )

        all_ranking = player_ranking_for_group(conn, group_id)
        team_players = [r for r in all_ranking if r.team_name == team_name]
        # Re-rank within the team (1..n) so the UI shows team-internal positions.
        return LeagueTeamDetail(
            group_id=meta["group_id"],
            group_name=meta["group_name"],
            division_id=meta["division_id"],
            division_name=meta["division_name"],
            league_id=meta["league_id"],
            league_name=meta["league_name"],
            season=meta["season"],
            team_name=team_name,
            standing=standing_row,
            player_ranking=[_ranking_row(e, i + 1) for i, e in enumerate(team_players)],
        )

    @app.get(
        "/api/leagues/divisions/{division_id}",
        response_model=LeagueDivisionDetail,
    )
    def get_league_division(
        division_id: int,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        """Division/category page payload: cross-group player ranking.

        Aggregates V/E/D, MP, caramboles, entrades and best sèrie across
        every group of the division (typically GRUP A + GRUP B for Tres
        Bandes). Useful for the "rànquing de categoria" view that the FCB
        does not publish directly.
        """
        div_row = conn.execute(
            """
            SELECT ld.id, ld.fcb_division_id, ld.name,
                   l.id AS league_id, l.name AS league_name, l.season
            FROM league_divisions ld
            JOIN leagues l ON l.id = ld.league_id
            WHERE ld.id = ?
            """,
            (division_id,),
        ).fetchone()
        if div_row is None:
            raise HTTPException(
                404, detail=f"No league division with id={division_id}"
            )

        group_rows = conn.execute(
            """
            SELECT lg.id, lg.name,
                   (SELECT COUNT(*) FROM league_team_standings ts
                      WHERE ts.group_id = lg.id) AS teams_count,
                   (SELECT COUNT(*)
                      FROM league_partides lp
                      JOIN league_encontres le ON le.id = lp.encontre_id
                      JOIN league_jornades lj ON lj.id = le.jornada_id
                      WHERE lj.group_id = lg.id AND lp.is_played = 1
                   ) AS partides_played
            FROM league_groups lg
            WHERE lg.division_id = ?
            ORDER BY lg.name
            """,
            (division_id,),
        ).fetchall()

        ranking = player_ranking_for_division(conn, division_id)
        overall = division_aggregate(conn, division_id)

        return LeagueDivisionDetail(
            id=div_row["id"],
            fcb_division_id=div_row["fcb_division_id"],
            name=div_row["name"],
            league_id=div_row["league_id"],
            league_name=div_row["league_name"],
            season=div_row["season"],
            caramboles=overall.caramboles,
            entrades=overall.entrades,
            average=overall.average,
            groups=[
                LeagueDivisionGroupRef(
                    id=g["id"],
                    name=g["name"],
                    teams_count=int(g["teams_count"]),
                    partides_played=int(g["partides_played"]),
                )
                for g in group_rows
            ],
            player_ranking=[_ranking_row(e, i + 1) for i, e in enumerate(ranking)],
        )

    @app.get(
        "/api/leagues/groups/{group_id}/jornades",
        response_model=LeagueJornadasResponse,
    )
    def get_league_jornades(
        group_id: int,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        """All jornades of a group with their encontres (totals only)."""
        if not conn.execute(
            "SELECT 1 FROM league_groups WHERE id = ?", (group_id,)
        ).fetchone():
            raise HTTPException(404, detail=f"No league group with id={group_id}")
        jornades = conn.execute(
            """
            SELECT id, fcb_jornada_id, number, played_on
            FROM league_jornades
            WHERE group_id = ?
            ORDER BY number
            """,
            (group_id,),
        ).fetchall()
        out: list[LeagueJornadaRow] = []
        for j in jornades:
            enc_rows = conn.execute(
                """
                SELECT le.id, le.fcb_encontre_id,
                       le.home_team_name, le.away_team_name,
                       le.home_match_points, le.away_match_points,
                       le.home_set_points, le.away_set_points,
                       (SELECT COUNT(*) FROM league_partides lp
                          WHERE lp.encontre_id = le.id) AS partides_total,
                       (SELECT COUNT(*) FROM league_partides lp
                          WHERE lp.encontre_id = le.id AND lp.is_played = 1) AS partides_played
                FROM league_encontres le
                WHERE le.jornada_id = ?
                ORDER BY le.fcb_encontre_id
                """,
                (j["id"],),
            ).fetchall()
            out.append(
                LeagueJornadaRow(
                    id=j["id"],
                    fcb_jornada_id=j["fcb_jornada_id"],
                    number=j["number"],
                    played_on=j["played_on"],
                    encontres=[
                        LeagueEncontreRow(
                            id=e["id"],
                            fcb_encontre_id=e["fcb_encontre_id"],
                            home_team_name=e["home_team_name"],
                            away_team_name=e["away_team_name"],
                            home_match_points=e["home_match_points"],
                            away_match_points=e["away_match_points"],
                            home_set_points=e["home_set_points"],
                            away_set_points=e["away_set_points"],
                            partides_total=int(e["partides_total"]),
                            partides_played=int(e["partides_played"]),
                        )
                        for e in enc_rows
                    ],
                )
            )
        return LeagueJornadasResponse(group_id=group_id, jornades=out)

    @app.get(
        "/api/leagues/encontres/{encontre_id}",
        response_model=LeagueEncontreDetail,
    )
    def get_league_encontre(
        encontre_id: int,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        """Full encontre detail: 4 individual partides with caramboles, sèrie, punts."""
        row = conn.execute(
            """
            SELECT le.id, le.fcb_encontre_id,
                   le.home_team_name, le.away_team_name,
                   le.home_match_points, le.away_match_points,
                   le.home_set_points, le.away_set_points,
                   lj.number AS jornada_number, lj.played_on,
                   lg.name AS group_name,
                   ld.name AS division_name,
                   l.name AS league_name
            FROM league_encontres le
            JOIN league_jornades lj ON lj.id = le.jornada_id
            JOIN league_groups lg ON lg.id = lj.group_id
            JOIN league_divisions ld ON ld.id = lg.division_id
            JOIN leagues l ON l.id = ld.league_id
            WHERE le.id = ?
            """,
            (encontre_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, detail=f"No encontre with id={encontre_id}")

        partides = conn.execute(
            """
            SELECT lp.slot,
                   lp.home_player_id, hp.display_name AS home_name,
                   lp.home_caramboles, lp.home_serie_major, lp.home_punts,
                   lp.away_player_id, ap.display_name AS away_name,
                   lp.away_caramboles, lp.away_serie_major, lp.away_punts,
                   lp.entrades, lp.arbitre, lp.attendance, lp.modalitat,
                   lp.is_played
            FROM league_partides lp
            LEFT JOIN players hp ON hp.id = lp.home_player_id
            LEFT JOIN players ap ON ap.id = lp.away_player_id
            WHERE lp.encontre_id = ?
            ORDER BY lp.slot
            """,
            (encontre_id,),
        ).fetchall()

        return LeagueEncontreDetail(
            id=row["id"],
            fcb_encontre_id=row["fcb_encontre_id"],
            home_team_name=row["home_team_name"],
            away_team_name=row["away_team_name"],
            home_match_points=row["home_match_points"],
            away_match_points=row["away_match_points"],
            home_set_points=row["home_set_points"],
            away_set_points=row["away_set_points"],
            jornada_number=row["jornada_number"],
            played_on=row["played_on"],
            group_name=row["group_name"],
            division_name=row["division_name"],
            league_name=row["league_name"],
            partides=[
                LeaguePartidaRow(
                    slot=p["slot"],
                    home_player_id=p["home_player_id"],
                    home_player_name=p["home_name"],
                    home_caramboles=p["home_caramboles"],
                    home_serie_major=p["home_serie_major"],
                    home_punts=p["home_punts"],
                    away_player_id=p["away_player_id"],
                    away_player_name=p["away_name"],
                    away_caramboles=p["away_caramboles"],
                    away_serie_major=p["away_serie_major"],
                    away_punts=p["away_punts"],
                    entrades=p["entrades"],
                    arbitre=p["arbitre"],
                    attendance=p["attendance"],
                    modalitat=p["modalitat"],
                    is_played=bool(p["is_played"]),
                )
                for p in partides
            ],
        )

    @app.get(
        "/api/players/{player_id}/lliga",
        response_model=PlayerLeagueProfile,
    )
    def get_player_league_profile(
        player_id: int,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        """Player's league history: per-group KPI summary + every partida.

        The summary mirrors the row the same player would get on the per-
        group ranking page (V/E/D, mitjana, punts), repeated once per group
        the player has appeared in.
        """
        player = conn.execute(
            "SELECT id, display_name, current_club FROM players WHERE id = ?",
            (player_id,),
        ).fetchone()
        if player is None:
            raise HTTPException(404, detail=f"No player with id={player_id}")

        # Per-group KPIs.
        group_rows = conn.execute(
            """
            SELECT DISTINCT lg.id AS group_id,
                   ld.name AS division_name,
                   lg.name AS group_name
            FROM league_partides lp
            JOIN league_encontres le ON le.id = lp.encontre_id
            JOIN league_jornades lj ON lj.id = le.jornada_id
            JOIN league_groups lg ON lg.id = lj.group_id
            JOIN league_divisions ld ON ld.id = lg.division_id
            WHERE lp.home_player_id = ? OR lp.away_player_id = ?
            ORDER BY ld.name, lg.name
            """,
            (player_id, player_id),
        ).fetchall()
        summaries: list[PlayerLeagueGroupSummary] = []
        for g in group_rows:
            ranking = player_ranking_for_group(conn, g["group_id"])
            for entry in ranking:
                if entry.player_id == player_id:
                    summaries.append(
                        PlayerLeagueGroupSummary(
                            group_id=g["group_id"],
                            division_name=g["division_name"],
                            group_name=g["group_name"],
                            team_name=entry.team_name,
                            matches_played=entry.matches_played,
                            wins=entry.wins,
                            draws=entry.draws,
                            losses=entry.losses,
                            match_points=entry.match_points,
                            caramboles=entry.caramboles,
                            entrades=entry.entrades,
                            average=entry.average,
                            best_serie=entry.best_serie,
                            s1=entry.s1,
                            s2=entry.s2,
                            s3=entry.s3,
                            s4=entry.s4,
                        )
                    )
                    break

        # Per-partida history.
        partides = partides_for_player(conn, player_id)
        # Resolve opponent player_id by looking it up via the original
        # league_partides row — partides_for_player intentionally only
        # carries the name, but we want a clickable link in the UI.
        opp_ids = conn.execute(
            """
            SELECT lp.id AS partida_id,
                   CASE WHEN lp.home_player_id = ? THEN lp.away_player_id
                        ELSE lp.home_player_id END AS opp_id
            FROM league_partides lp
            WHERE lp.home_player_id = ? OR lp.away_player_id = ?
            """,
            (player_id, player_id, player_id),
        ).fetchall()
        opp_id_map = {r["partida_id"]: r["opp_id"] for r in opp_ids}

        slot_perf = slot_performance_for_player(conn, player_id)
        return PlayerLeagueProfile(
            player_id=player["id"],
            display_name=player["display_name"],
            current_club=player["current_club"],
            summary=summaries,
            slot_performance=[
                SlotPerformanceRow(
                    slot=sp.slot,
                    matches_played=sp.matches_played,
                    wins=sp.wins,
                    draws=sp.draws,
                    losses=sp.losses,
                    match_points=sp.match_points,
                    caramboles=sp.caramboles,
                    entrades=sp.entrades,
                    average=sp.average,
                    win_rate=sp.win_rate,
                    best_serie=sp.best_serie,
                )
                for sp in slot_perf
            ],
            partides=[
                PlayerLeaguePartidaRow(
                    partida_id=p.partida_id,
                    encontre_id=p.encontre_id,
                    fcb_encontre_id=p.fcb_encontre_id,
                    jornada_number=p.jornada_number,
                    played_on=p.played_on,
                    division_name=p.division_name,
                    group_name=p.group_name,
                    own_team_name=p.own_team_name,
                    opponent_player_id=opp_id_map.get(p.partida_id),
                    opponent_name=p.opponent_name,
                    opponent_team_name=p.opponent_team_name,
                    was_home=p.was_home,
                    own_caramboles=p.own_caramboles,
                    own_serie_major=p.own_serie_major,
                    own_punts=p.own_punts,
                    opp_caramboles=p.opp_caramboles,
                    opp_serie_major=p.opp_serie_major,
                    opp_punts=p.opp_punts,
                    entrades=p.entrades,
                    is_played=p.is_played,
                    result=p.result,
                )
                for p in partides
            ],
        )

    # --------------------------------------------------------------------- #
    # Generator
    # --------------------------------------------------------------------- #

    @app.post("/api/generator", response_model=GeneratorResponse)
    def run_generator(
        req: GeneratorRequest,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        enriched, unmatched = _enrich_inscriptions(
            conn, req.inscriptions, req.auto_enrich, req.month_id
        )
        entries = [_enriched_to_entry(e) for e in enriched]
        ordered = sort_inscriptions(entries)
        # Map ordered entries back to EnrichedInscription form (preserving order)
        by_name = {normalize_name(e.player_name): e for e in enriched}
        ordered_enriched = [by_name[normalize_name(en.player_name)] for en in ordered]

        anomalies = validate_inscriptions(entries)
        tournament_response = None
        try:
            tournament = generate_tournament(len(enriched))
            tournament_response = _tournament_to_response(tournament, ordered_enriched)
        except NotImplementedError:
            tournament_response = None

        return GeneratorResponse(
            enriched_inscriptions=enriched,
            ordered_inscriptions=ordered_enriched,
            unmatched=unmatched,
            tournament=tournament_response,
            anomalies=[_anomaly_to_response(a) for a in anomalies],
        )

    # --------------------------------------------------------------------- #
    # Validator (standalone, no group generation)
    # --------------------------------------------------------------------- #

    @app.post("/api/validator", response_model=ValidatorResponse)
    def run_validator(
        req: ValidatorRequest,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        enriched, unmatched = _enrich_inscriptions(
            conn, req.inscriptions, req.auto_enrich, req.month_id
        )
        entries = [_enriched_to_entry(e) for e in enriched]
        anomalies = validate_inscriptions(entries)
        return ValidatorResponse(
            enriched_inscriptions=enriched,
            unmatched=unmatched,
            anomalies=[_anomaly_to_response(a) for a in anomalies],
        )

    # --------------------------------------------------------------------- #
    # Diff (computed Opens ranking vs official FCB PDF)
    # --------------------------------------------------------------------- #

    @app.get("/api/diff/official", response_model=DiffReportResponse)
    def get_official_diff(
        force: bool = False,
        use_cache_only: bool = False,
        url: str = OFFICIAL_RANKING_URL,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        """Compare the computed Opens ranking against the official FCB PDF.

        By default reuses the local PDF cache (1h TTL). Pass `force=true`
        to bypass the cache, or `use_cache_only=true` to fail if the cache
        is missing rather than hitting the network.
        """
        try:
            pdf_bytes = fetch_official_ranking_pdf(
                url=url, force=force, use_cache_only=use_cache_only
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, detail=f"PDF fetch failed: {exc}") from exc

        try:
            official = parse_official_ranking(pdf_bytes, source_url=url)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, detail=f"PDF parse failed: {exc}") from exc

        # Window must match the PDF's column count. The diff is meaningless
        # if these don't cover the same set of Opens — we surface both lists
        # so the user can verify visually.
        n_official = len(official.opens)
        computed = compute_opens_ranking(conn, num_recent_opens=n_official)
        computed_window = get_window_opens(conn, num_recent_opens=n_official)
        rows = list(db.all_players(conn))
        players = [
            Player(display_name=r["display_name"], club=r["current_club"])
            for r in rows
        ]
        id_by_norm = {
            normalize_for_matching(r["display_name"]): int(r["id"]) for r in rows
        }
        matcher = build_matcher(players)

        def _lookup_player_id(name: str) -> int | None:
            matched = matcher(name)
            if matched is None:
                return None
            return id_by_norm.get(normalize_for_matching(matched.display_name))

        report = diff_rankings(official, computed, _lookup_player_id)

        counts: dict[str, int] = {}
        for d in report.discrepancies:
            counts[d.kind] = counts.get(d.kind, 0) + 1

        # Load existing overrides keyed by (normalized name, kind) so the
        # frontend can render decisions inline.
        override_rows = conn.execute(
            "SELECT * FROM diff_overrides ORDER BY updated_at DESC"
        ).fetchall()
        overrides_by_key: dict[tuple[str, str], dict] = {}
        for r in override_rows:
            key = (
                normalize_for_matching(r["player_name"]),
                str(r["discrepancy_kind"]),
            )
            overrides_by_key[key] = dict(r)

        def _override_for(d, current_kind: str) -> DiffOverrideRow | None:
            # First try (name, current_kind), then any override for that name
            # regardless of kind so users see an outdated decision when the
            # discrepancy reclassifies on a re-sync.
            norm = normalize_for_matching(d.player.display_name)
            key = (norm, current_kind)
            row = overrides_by_key.get(key)
            if row is None:
                # Look for any override on this player.
                for (n, _k), r2 in overrides_by_key.items():
                    if n == norm:
                        row = r2
                        break
            if row is None:
                return None
            return DiffOverrideRow(
                player_name=row["player_name"],
                discrepancy_kind=row["discrepancy_kind"],
                decision=row["decision"],
                note=row["note"],
                official_total=row["official_total"],
                computed_total=row["computed_total"],
                updated_at=row["updated_at"],
            )

        # Open-set comparison: match by venue keywords (MATARO, LLINARS,
        # SANT ADRIA, MANRESA, SANTS, ...) since the PDF titles are far
        # more verbose than the DB names. Special alias: the FCB Opens
        # at Sants are titled "MEMORIAL JOAQUIN DOMINGO" in the PDF, so
        # any name containing JOAQUIN/JOAQUIM DOMINGO matches SANTS.
        def _opens_match(off_opens, comp_window) -> bool:
            if len(off_opens) != len(comp_window):
                return False
            pdf_keys = [_open_match_keys(o.full_name) for o in off_opens]
            db_keys = [_open_match_keys(o.name) for o in comp_window]
            # Bipartite matching: each DB Open must claim a UNIQUE PDF
            # entry that shares at least one venue keyword with it.
            used: set[int] = set()
            for db_set in db_keys:
                if not db_set:
                    return False
                hit = False
                for i, pdf_set in enumerate(pdf_keys):
                    if i in used:
                        continue
                    if db_set & pdf_set:
                        used.add(i)
                        hit = True
                        break
                if not hit:
                    return False
            return True

        official_opens_payload = [
            DiffOpen(
                index=o.index,
                label=o.label,
                name=o.full_name,
                season=o.season,
                fcb_division_id=None,
            )
            for o in official.opens
        ]
        computed_opens_payload = [
            DiffOpen(
                index=i,
                label=o.name,
                name=o.name,
                season=o.season or None,
                fcb_division_id=o.fcb_division_id,
            )
            for i, o in enumerate(computed_window)
        ]

        return DiffReportResponse(
            official_source=report.official_source,
            official_size=report.official_size,
            computed_size=report.computed_size,
            matched_count=report.matched_count,
            counts_by_kind=counts,
            discrepancies=[
                DiffDiscrepancy(
                    kind=d.kind,
                    player=DiffPlayerRef(
                        display_name=d.player.display_name,
                        club=d.player.club,
                        player_id=d.player.player_id,
                    ),
                    official_position=d.official_position,
                    computed_position=d.computed_position,
                    official_total=d.official_total,
                    computed_total=d.computed_total,
                    details=d.details,
                    n_penalties=d.n_penalties,
                    override=_override_for(d, d.kind),
                )
                for d in report.discrepancies
            ],
            penalty_adjusted_count=report.penalty_adjusted_count,
            penalty_cascade_count=report.penalty_cascade_count,
            source_mismatch_count=report.source_mismatch_count,
            position_cascade_count=report.position_cascade_count,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            official_opens=official_opens_payload,
            computed_opens=computed_opens_payload,
            opens_set_match=_opens_match(official.opens, computed_window),
        )

    # --------------------------------------------------------------------- #
    # Diff overrides (per-discrepancy human decisions)
    # --------------------------------------------------------------------- #

    _ALLOWED_DECISIONS = {"keep_computed", "use_official", "dismissed"}

    @app.get("/api/diff/overrides", response_model=list[DiffOverrideRow])
    def list_diff_overrides(conn: sqlite3.Connection = Depends(get_connection)):
        rows = conn.execute(
            "SELECT * FROM diff_overrides ORDER BY updated_at DESC"
        ).fetchall()
        return [
            DiffOverrideRow(
                player_name=r["player_name"],
                discrepancy_kind=r["discrepancy_kind"],
                decision=r["decision"],
                note=r["note"],
                official_total=r["official_total"],
                computed_total=r["computed_total"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    @app.post("/api/diff/overrides", response_model=DiffOverrideRow)
    def upsert_diff_override(
        req: DiffOverrideUpsertRequest,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        if req.decision not in _ALLOWED_DECISIONS:
            raise HTTPException(
                400,
                detail=f"decision must be one of {sorted(_ALLOWED_DECISIONS)}",
            )
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO diff_overrides
                (player_name, discrepancy_kind, decision, note,
                 official_total, computed_total, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_name, discrepancy_kind) DO UPDATE SET
                decision       = excluded.decision,
                note           = excluded.note,
                official_total = excluded.official_total,
                computed_total = excluded.computed_total,
                updated_at     = excluded.updated_at
            """,
            (
                req.player_name,
                req.discrepancy_kind,
                req.decision,
                req.note,
                req.official_total,
                req.computed_total,
                now,
            ),
        )
        conn.commit()
        return DiffOverrideRow(
            player_name=req.player_name,
            discrepancy_kind=req.discrepancy_kind,
            decision=req.decision,
            note=req.note,
            official_total=req.official_total,
            computed_total=req.computed_total,
            updated_at=now,
        )

    @app.delete("/api/diff/overrides")
    def delete_diff_override(
        player_name: str,
        discrepancy_kind: str,
        conn: sqlite3.Connection = Depends(get_connection),
    ):
        cur = conn.execute(
            "DELETE FROM diff_overrides WHERE player_name = ? AND discrepancy_kind = ?",
            (player_name, discrepancy_kind),
        )
        conn.commit()
        return {"deleted": cur.rowcount}

    # --------------------------------------------------------------------- #
    # Full FCB sync (force-refresh of monthly ranking + opens + lligues)
    # --------------------------------------------------------------------- #

    def _sync_result_to_response(r: SyncResult) -> SyncResultResponse:
        return SyncResultResponse(
            started_at=r.started_at,
            finished_at=r.finished_at,
            success=r.success,
            tasks=[
                SyncTaskResult(
                    name=t.name,
                    success=t.success,
                    saved=t.saved,
                    skipped=t.skipped,
                    error=t.error,
                    detail=t.detail,
                )
                for t in r.tasks
            ],
        )

    async def _trigger_full_sync(force: bool) -> SyncResult | None:
        async with sync_state.lock:
            if sync_state.in_progress:
                return None
            sync_state.in_progress = True
            sync_state.started_at = datetime.now(timezone.utc).isoformat()
        try:
            result = await asyncio.to_thread(run_full_sync, force=force)
            sync_state.last_result = result
            return result
        finally:
            async with sync_state.lock:
                sync_state.in_progress = False
                sync_state.started_at = None

    @app.post("/api/sync/run", response_model=SyncRunResponse)
    async def trigger_full_sync(force: bool = True):
        """Force-refresh all FCB-sourced data: latest monthly ranking,
        current Opens, and tracked lligues. Runs in the background; poll
        `/api/sync/status` for progress and results."""
        if sync_state.in_progress:
            return SyncRunResponse(accepted=False, already_running=True)
        # Fire and forget: result is exposed via /api/sync/status.
        asyncio.create_task(_trigger_full_sync(force=force))
        return SyncRunResponse(accepted=True, already_running=False)

    @app.get("/api/sync/status", response_model=SyncStatusResponse)
    def get_sync_status():
        last = (
            _sync_result_to_response(sync_state.last_result)
            if sync_state.last_result is not None
            else None
        )
        return SyncStatusResponse(
            in_progress=sync_state.in_progress,
            started_at=sync_state.started_at,
            last_result=last,
        )


# --------------------------------------------------------------------------- #
# Internal conversion helpers
# --------------------------------------------------------------------------- #


# Open-name matching now lives in `reglament.open_match` so the
# ranking-with-penalties code can reuse the same keyword logic.
from ..reglament.open_match import open_match_keys as _open_match_keys  # noqa: E402


def _apply_pdf_penalties_if_available(
    conn: sqlite3.Connection,
    base_entries: list[OpensRankingEntry],
    window: int,
) -> list[OpensRankingEntry]:
    """Fold PDF -20 penalties into a base ranking when a cached official
    PDF is available. Silent fall-back to the base ranking on any error
    so this never blocks a ranking response on network/FCB issues.

    Resolution:
      1. Read the official PDF from local cache only (no network hit).
         If no cache, return base ranking unchanged.
      2. Map PDF columns to DB window Opens via venue keywords.
      3. Match each PDF entry to a DB player via the existing fuzzy
         player matcher.
      4. Build the {player_id: {open_id: penalty_points}} dict and
         hand off to the pure `apply_official_penalties`.
    """
    try:
        pdf_bytes = fetch_official_ranking_pdf(use_cache_only=True)
    except FileNotFoundError:
        return base_entries
    except Exception:  # noqa: BLE001
        log.exception("PDF fetch for ranking penalties failed; returning base")
        return base_entries
    try:
        official = parse_official_ranking(pdf_bytes, source_url=OFFICIAL_RANKING_URL)
    except Exception:  # noqa: BLE001
        log.exception("PDF parse for ranking penalties failed; returning base")
        return base_entries

    window_opens = get_window_opens(conn, num_recent_opens=window)
    if not window_opens:
        return base_entries

    pdf_to_window = map_pdf_columns_to_window(
        [o.full_name for o in official.opens],
        [o.name for o in window_opens],
    )
    if not pdf_to_window:
        return base_entries

    # Build a fuzzy matcher over our DB players so PDF names with
    # slight spelling drift still resolve to the right player_id.
    rows = list(db.all_players(conn))
    players = [
        Player(display_name=r["display_name"], club=r["current_club"]) for r in rows
    ]
    id_by_norm = {
        normalize_for_matching(r["display_name"]): int(r["id"]) for r in rows
    }
    matcher = build_matcher(players)

    pdf_penalties: dict[int, dict[int, int]] = {}
    for off in official.entries:
        matched = matcher(off.display_name)
        if matched is None:
            continue
        pid = id_by_norm.get(normalize_for_matching(matched.display_name))
        if pid is None:
            continue
        for pdf_idx, points in enumerate(off.points_per_open):
            if points is None or points >= 0:
                continue  # 0 = justified absence; positive = real played points
            window_idx = pdf_to_window.get(pdf_idx)
            if window_idx is None:
                continue
            open_id = window_opens[window_idx].open_id
            pdf_penalties.setdefault(pid, {})[open_id] = points

    if not pdf_penalties:
        return base_entries

    fcb_averages = load_player_fcb_averages(conn)
    return apply_official_penalties(
        base_entries, window_opens, pdf_penalties, fcb_averages=fcb_averages
    )


def _club_sources_to_response(s: PlayerClubSources) -> PlayerClubSourcesResponse:
    return PlayerClubSourcesResponse(
        opens_club=s.opens_club,
        opens_old_club=s.opens_old_club,
        lliga_club=s.lliga_club,
        manual_club=s.manual_club,
        resolved_club=s.resolved_club,
        source=s.source,
    )


def _ranking_row(stats, rank: int) -> PlayerLeagueRankingRow:
    """Project a `PlayerLeagueStats` into the API ranking row shape."""
    return PlayerLeagueRankingRow(
        rank=rank,
        player_id=stats.player_id,
        display_name=stats.display_name,
        team_name=stats.team_name,
        matches_played=stats.matches_played,
        wins=stats.wins,
        draws=stats.draws,
        losses=stats.losses,
        match_points=stats.match_points,
        caramboles=stats.caramboles,
        entrades=stats.entrades,
        average=stats.average,
        best_serie=stats.best_serie,
        s1=stats.s1,
        s2=stats.s2,
        s3=stats.s3,
        s4=stats.s4,
    )


def _last_jornada_for_group(
    conn: sqlite3.Connection, group_id: int
) -> LeagueJornadaRow | None:
    """Return the highest-numbered jornada with at least one played partida.

    Used by the /api/leagues index to surface "darreres resultats" cards
    without forcing the UI to fetch every jornada per group.
    """
    j_row = conn.execute(
        """
        SELECT lj.id, lj.fcb_jornada_id, lj.number, lj.played_on
        FROM league_jornades lj
        WHERE lj.group_id = ?
          AND EXISTS (
            SELECT 1
            FROM league_encontres le
            JOIN league_partides lp ON lp.encontre_id = le.id
            WHERE le.jornada_id = lj.id AND lp.is_played = 1
          )
        ORDER BY lj.number DESC
        LIMIT 1
        """,
        (group_id,),
    ).fetchone()
    if j_row is None:
        return None
    enc_rows = conn.execute(
        """
        SELECT le.id, le.fcb_encontre_id,
               le.home_team_name, le.away_team_name,
               le.home_match_points, le.away_match_points,
               le.home_set_points, le.away_set_points,
               (SELECT COUNT(*) FROM league_partides lp
                  WHERE lp.encontre_id = le.id) AS partides_total,
               (SELECT COUNT(*) FROM league_partides lp
                  WHERE lp.encontre_id = le.id AND lp.is_played = 1) AS partides_played
        FROM league_encontres le
        WHERE le.jornada_id = ?
        ORDER BY le.fcb_encontre_id
        """,
        (j_row["id"],),
    ).fetchall()
    return LeagueJornadaRow(
        id=j_row["id"],
        fcb_jornada_id=j_row["fcb_jornada_id"],
        number=j_row["number"],
        played_on=j_row["played_on"],
        encontres=[
            LeagueEncontreRow(
                id=e["id"],
                fcb_encontre_id=e["fcb_encontre_id"],
                home_team_name=e["home_team_name"],
                away_team_name=e["away_team_name"],
                home_match_points=e["home_match_points"],
                away_match_points=e["away_match_points"],
                home_set_points=e["home_set_points"],
                away_set_points=e["away_set_points"],
                partides_total=int(e["partides_total"]),
                partides_played=int(e["partides_played"]),
            )
            for e in enc_rows
        ],
    )


def _team_standing_row(row, aggregates) -> TeamStandingRow:
    """Merge an FCB-published standing row with the locally computed
    team mitjana (Σ caramboles / Σ entrades from played partides)."""
    agg = aggregates.get(row["team_name"])
    caramboles = agg.caramboles if agg else 0
    entrades = agg.entrades if agg else 0
    average = (caramboles / entrades) if entrades else 0.0
    return TeamStandingRow(
        position=row["position"],
        team_name=row["team_name"],
        match_points=row["match_points"],
        set_points=row["set_points"],
        matches_played=row["matches_played"],
        caramboles=caramboles,
        entrades=entrades,
        average=average,
    )


def _enrich_inscriptions(
    conn: sqlite3.Connection,
    inputs: list[InscriptionInput],
    auto_enrich: bool,
    month_id: int | None,
) -> tuple[list[EnrichedInscription], list[str]]:
    """Look up each inscription against the monthly ranking and Opens ranking.

    Fields explicitly provided by the caller win over DB lookups.
    """
    ranking_row = None
    if auto_enrich:
        if month_id is not None:
            ranking_row = conn.execute(
                "SELECT id FROM monthly_rankings WHERE month_id = ?", (month_id,)
            ).fetchone()
        else:
            ranking_row = conn.execute(
                "SELECT id FROM monthly_rankings ORDER BY month_id DESC LIMIT 1"
            ).fetchone()

    # Build a name→ranking_entry map once
    ranking_by_name: dict[str, dict] = {}
    if ranking_row is not None:
        rows = conn.execute(
            """
            SELECT p.display_name, p.normalized_name, p.current_club,
                   mre.position, mre.average, mre.is_definitive
            FROM monthly_ranking_entries mre
            JOIN players p ON p.id = mre.player_id
            WHERE mre.ranking_id = ?
            """,
            (ranking_row["id"],),
        ).fetchall()
        for row in rows:
            ranking_by_name[row["normalized_name"]] = dict(row)

    # Pre-compute Opens points per player
    opens_points_by_name: dict[str, int] = {}
    if auto_enrich:
        opens_entries = compute_opens_ranking(conn)
        for e in opens_entries:
            opens_points_by_name[normalize_name(e.display_name)] = e.total_points

    enriched: list[EnrichedInscription] = []
    unmatched: list[str] = []
    for inp in inputs:
        key = normalize_name(inp.player_name)
        ranking_match = ranking_by_name.get(key) if auto_enrich else None
        opens_points = (
            inp.opens_points
            if inp.opens_points is not None
            else opens_points_by_name.get(key, 0)
        )
        fcb_pos = (
            inp.fcb_ranking_position
            if inp.fcb_ranking_position is not None
            else (ranking_match["position"] if ranking_match else None)
        )
        is_def = (
            inp.fcb_ranking_is_definitive
            if inp.fcb_ranking_is_definitive is not None
            else (bool(ranking_match["is_definitive"]) if ranking_match else False)
        )
        avg = (
            inp.fcb_ranking_average
            if inp.fcb_ranking_average is not None
            else (ranking_match["average"] if ranking_match else 0.0)
        )
        club = inp.club or (ranking_match["current_club"] if ranking_match else "")
        enriched.append(
            EnrichedInscription(
                player_name=inp.player_name,
                club=club or "",
                opens_points=opens_points,
                fcb_ranking_position=fcb_pos,
                fcb_ranking_is_definitive=is_def,
                fcb_ranking_average=avg,
                matched=ranking_match is not None,
            )
        )
        if auto_enrich and ranking_match is None:
            unmatched.append(inp.player_name)
    return enriched, unmatched


def _enriched_to_entry(e: EnrichedInscription) -> InscriptionEntry:
    return InscriptionEntry(
        player_name=e.player_name,
        club=e.club,
        opens_points=e.opens_points,
        fcb_ranking_position=e.fcb_ranking_position,
        fcb_ranking_is_definitive=e.fcb_ranking_is_definitive,
        fcb_ranking_average=e.fcb_ranking_average,
    )


def _anomaly_to_response(a) -> AnomalyResponse:
    return AnomalyResponse(
        code=a.code,
        severity=a.severity,
        message=a.message,
        affected_players=a.affected_players,
    )


def _tournament_to_response(
    tournament: Tournament,
    ordered: list[EnrichedInscription],
) -> TournamentResponse:
    """Convert a Tournament dataclass into the API response shape.

    Direct seeds are resolved to player names using the ordered
    inscription list (position N = ordered[N-1]).
    """
    def resolve_slot(slot) -> GroupSlotResponse:
        if slot.inscription_position is not None:
            idx = slot.inscription_position - 1
            player = ordered[idx] if 0 <= idx < len(ordered) else None
            return GroupSlotResponse(
                label=slot.label,
                inscription_position=slot.inscription_position,
                placeholder_rank=None,
                placeholder_phase=None,
                player_name=player.player_name if player else None,
                club=player.club if player else None,
            )
        return GroupSlotResponse(
            label=slot.label,
            inscription_position=None,
            placeholder_rank=slot.placeholder_rank,
            placeholder_phase=slot.placeholder_phase,
            player_name=None,
            club=None,
        )

    phases = {}
    for phase_name, phase in tournament.phases.items():
        phases[phase_name] = PhaseResponse(
            name=phase.name,
            groups=[
                GroupResponse(
                    label=g.label,
                    slots=[resolve_slot(s) for s in g.slots],
                )
                for g in phase.groups
            ],
        )
    return TournamentResponse(
        num_inscriptions=tournament.num_inscriptions,
        phases=phases,
    )


# --------------------------------------------------------------------------- #
# Module-level app instance
# --------------------------------------------------------------------------- #

app = create_app()
