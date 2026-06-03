"""Bulk re-sync of FCB-sourced data.

Drives the same scrape paths as the CLI (`scrape-ranking`,
`scrape-current-opens`, `scrape-lliga`) under a single in-memory
state object, so the API can expose a one-click "Sincronitza FCB"
that bypasses the local HTTP cache.

Concurrency: a single-instance lock (`sync_state`) prevents two
overlapping full-syncs in the same process. The league refresh has
its own lock in `lliga.refresh.state` — we deliberately take the
*same* lock when our full-sync touches the lliga so the two flows
never write to the league tables simultaneously.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from . import db
from .lliga.refresh import RefreshResult
from .lliga.refresh import state as league_refresh_state
from .lliga.scraper import incremental_refresh
from .paths import resolve_db_path
from .scraper import classificacio, ranking
from .scraper.open_live import (
    fetch_final_classification_id,
    fetch_individuals_llistat,
)


log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #


@dataclass
class TaskResult:
    """Outcome of a single sync sub-task (e.g. monthly ranking, opens)."""

    name: str
    success: bool
    saved: int = 0
    skipped: int = 0
    error: str | None = None
    detail: str | None = None  # short human-readable note (e.g. "month 121")


@dataclass
class SyncResult:
    """Outcome of a full FCB sync run."""

    started_at: str
    finished_at: str
    success: bool
    tasks: list[TaskResult] = field(default_factory=list)


@dataclass
class SyncState:
    """Process-local state for the full-sync task.

    A single-process lock is enough for this local-tool deployment:
    we never run multiple uvicorn workers and the API is single-threaded.
    """

    in_progress: bool = False
    started_at: str | None = None
    last_result: SyncResult | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


# Module-level singleton — survives across requests.
sync_state = SyncState()


# --------------------------------------------------------------------------- #
# Sub-task implementations
# --------------------------------------------------------------------------- #


def _refresh_all_monthly_rankings(
    conn: sqlite3.Connection,
    *,
    force: bool,
    forward_probe_limit: int = 12,
) -> TaskResult:
    """Refresh every stored monthly ranking AND probe forward for new ones.

    Strategy:
      1. Re-fetch each `month_id` already in the DB (with `force` to bypass
         the HTTP cache).
      2. Starting from `max(stored)+1`, probe forward and ingest any new
         months until either a probe fails (404 / no ranking table) or we
         hit `forward_probe_limit` consecutive misses. The probe stops at
         the first failure since FCB month_ids are monotonic.

    A failure on a single month doesn't abort the rest — counts and any
    error messages are aggregated into the returned `TaskResult.detail`.
    """
    stored_rows = conn.execute(
        "SELECT month_id FROM monthly_rankings ORDER BY month_id ASC"
    ).fetchall()
    stored_ids = [int(r["month_id"]) for r in stored_rows]

    if not stored_ids:
        return TaskResult(
            name="monthly_ranking",
            success=True,
            saved=0,
            detail=(
                "BD sense rànquings — usa `fcb-opens scrape-ranking <month_id>` "
                "per sembrar el primer abans de la sincronització"
            ),
        )

    saved_total = 0
    refreshed_ids: list[int] = []
    new_ids: list[int] = []
    errors: list[str] = []

    # 1) Re-fetch every stored month
    for month_id in stored_ids:
        try:
            result = ranking.fetch_ranking(month_id, force=force)
            db.save_monthly_ranking(conn, result)
            saved_total += len(result.entries)
            refreshed_ids.append(month_id)
        except Exception as exc:  # noqa: BLE001
            log.exception("refresh of monthly ranking %s failed", month_id)
            errors.append(f"month_id={month_id}: {type(exc).__name__}: {exc}")
    conn.commit()

    # 2) Probe forward for new months. The FCB publishes month_ids
    # monotonically, but we tolerate up to `MAX_CONSECUTIVE_MISSES`
    # consecutive failures before stopping — that way an isolated
    # skeleton/empty page (parse error) doesn't hide a published month
    # that follows it. Safety cap is `forward_probe_limit` total probes.
    MAX_CONSECUTIVE_MISSES = 3
    next_id = stored_ids[-1] + 1
    consecutive_misses = 0
    probes = 0
    while probes < forward_probe_limit and consecutive_misses < MAX_CONSECUTIVE_MISSES:
        probes += 1
        try:
            result = ranking.fetch_ranking(next_id, force=force)
            db.save_monthly_ranking(conn, result)
            saved_total += len(result.entries)
            new_ids.append(next_id)
            consecutive_misses = 0
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            consecutive_misses += 1
            log.debug(
                "monthly ranking probe miss at %s (consecutive=%d): %s",
                next_id, consecutive_misses, exc,
            )
        next_id += 1

    pieces: list[str] = []
    pieces.append(f"refrescats={len(refreshed_ids)}")
    if new_ids:
        pieces.append(f"nous={','.join(str(i) for i in new_ids)}")
    pieces.append(f"rang={stored_ids[0]}–{(new_ids[-1] if new_ids else stored_ids[-1])}")

    return TaskResult(
        name="monthly_ranking",
        success=len(errors) == 0,
        saved=saved_total,
        skipped=0,
        error="; ".join(errors[:5]) if errors else None,
        detail=" ".join(pieces),
    )


def _refresh_current_opens(
    conn: sqlite3.Connection,
    *,
    force: bool,
    season: str = "",
) -> TaskResult:
    """Re-scrape every published current-season Tres Bandes Open."""
    saved = 0
    skipped = 0
    errors: list[str] = []
    try:
        entries = fetch_individuals_llistat(force=force)
    except Exception as exc:  # noqa: BLE001
        return TaskResult(
            name="current_opens",
            success=False,
            error=f"llistat fetch failed: {type(exc).__name__}: {exc}",
        )

    for entry in entries:
        name_upper = entry.name.upper()
        if "OPEN" not in name_upper or "TRES BANDES" not in name_upper:
            continue
        if "FEMENI" in name_upper:
            continue
        try:
            clf_id = fetch_final_classification_id(entry.division_id, force=force)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{entry.division_id}: probe failed: {exc}")
            continue
        if clf_id is None:
            skipped += 1
            continue
        try:
            open_data = classificacio.fetch_classification(
                entry.division_id, clf_id, force=force
            )
            open_data.season = season
            db.save_open(conn, open_data)
            saved += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{entry.division_id}/{clf_id}: scrape failed: {exc}")
            continue
    conn.commit()

    return TaskResult(
        name="current_opens",
        success=len(errors) == 0,
        saved=saved,
        skipped=skipped,
        error="; ".join(errors[:5]) if errors else None,
    )


def _refresh_lliga(
    conn: sqlite3.Connection,
    competition_id: int,
    *,
    force: bool,
) -> TaskResult:
    """Run the existing incremental league refresh, optionally force-bypassing
    the HTTP cache. Acquires the league refresh state's in_progress flag so
    a parallel `/api/leagues/refresh` won't double-write."""
    started = datetime.now(timezone.utc).isoformat()
    if league_refresh_state.is_running(competition_id):
        return TaskResult(
            name="lliga",
            success=False,
            error=f"refresh already running for competition {competition_id}",
            detail=f"competition_id={competition_id}",
        )
    league_refresh_state.in_progress[competition_id] = started
    try:
        progress = incremental_refresh(conn, competition_id, force=force)
        result = RefreshResult(
            competition_id=competition_id,
            started_at=started,
            finished_at=datetime.now(timezone.utc).isoformat(),
            success=True,
            divisions=progress.divisions,
            groups=progress.groups,
            jornades=progress.jornades,
            jornades_skipped=progress.jornades_skipped,
            encontres=progress.encontres,
            partides=progress.partides,
        )
        league_refresh_state.last_result[competition_id] = result
        return TaskResult(
            name="lliga",
            success=True,
            saved=progress.partides,
            skipped=progress.jornades_skipped,
            detail=(
                f"competition_id={competition_id} "
                f"divisions={progress.divisions} groups={progress.groups} "
                f"jornades={progress.jornades}"
            ),
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("lliga refresh failed for competition %s", competition_id)
        league_refresh_state.last_result[competition_id] = RefreshResult(
            competition_id=competition_id,
            started_at=started,
            finished_at=datetime.now(timezone.utc).isoformat(),
            success=False,
            error=f"{type(exc).__name__}: {exc}",
        )
        return TaskResult(
            name="lliga",
            success=False,
            error=f"{type(exc).__name__}: {exc}",
            detail=f"competition_id={competition_id}",
        )
    finally:
        league_refresh_state.in_progress.pop(competition_id, None)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #


def run_full_sync(
    *,
    force: bool = True,
    competition_ids: tuple[int, ...] = (36,),
    season: str = "",
    on_progress: Callable[[str], None] | None = None,
) -> SyncResult:
    """Run a full FCB resync: latest monthly ranking + current Opens + lligues.

    Each sub-task is independent — a failure in one does not abort the others.
    The returned `SyncResult` reports per-task outcomes so callers can
    surface partial successes.
    """
    started_at = datetime.now(timezone.utc).isoformat()
    db_path = resolve_db_path()
    db.init_db(db_path)

    tasks: list[TaskResult] = []

    def _emit(msg: str) -> None:
        if on_progress is not None:
            try:
                on_progress(msg)
            except Exception:  # noqa: BLE001
                pass

    # 1) Monthly rankings (all stored + probe forward for new months)
    _emit("Refrescant rànquings FCB mensuals…")
    conn = db.connect(db_path)
    try:
        tasks.append(_refresh_all_monthly_rankings(conn, force=force))
    finally:
        conn.close()

    # 2) Current-season Opens
    _emit("Refrescant Opens vigents…")
    conn = db.connect(db_path)
    try:
        tasks.append(_refresh_current_opens(conn, force=force, season=season))
    finally:
        conn.close()

    # 3) Lligues
    for cid in competition_ids:
        _emit(f"Refrescant lliga (competition_id={cid})…")
        conn = db.connect(db_path)
        try:
            tasks.append(_refresh_lliga(conn, cid, force=force))
        finally:
            conn.close()

    return SyncResult(
        started_at=started_at,
        finished_at=datetime.now(timezone.utc).isoformat(),
        success=all(t.success for t in tasks),
        tasks=tasks,
    )
