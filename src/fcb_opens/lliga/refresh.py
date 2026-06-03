"""In-memory state for background league refreshes.

Used by the FastAPI lifespan and the POST /api/leagues/refresh endpoint
to coordinate a single refresh task per process. The state is
process-local: in this single-user local-tool deployment we don't need
distributed coordination.

Two pieces of state are tracked per competition_id:
  - whether a refresh is currently running
  - the result of the last completed refresh (timestamp + counts)

Reads are race-free because the API is single-threaded under uvicorn
without --workers; writes go through a small asyncio Lock that the
caller acquires before mutating.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class RefreshResult:
    """Outcome of a completed refresh attempt."""

    competition_id: int
    started_at: str
    finished_at: str
    success: bool
    divisions: int = 0
    groups: int = 0
    jornades: int = 0
    jornades_skipped: int = 0
    encontres: int = 0
    partides: int = 0
    error: str | None = None


@dataclass
class RefreshState:
    """Global, process-local refresh state."""

    in_progress: dict[int, str] = field(default_factory=dict)  # comp_id → started_at
    last_result: dict[int, RefreshResult] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def is_running(self, competition_id: int) -> bool:
        return competition_id in self.in_progress

    def started(self, competition_id: int) -> str:
        ts = datetime.now(timezone.utc).isoformat()
        self.in_progress[competition_id] = ts
        return ts


# Module-level singleton — survives across requests (uvicorn keeps the
# process alive between them). On worker restart it resets, which is
# fine: stale flags don't outlive the worker that set them.
state = RefreshState()
