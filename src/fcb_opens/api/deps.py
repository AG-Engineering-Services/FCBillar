"""Shared dependencies for the FastAPI app.

The DB path is resolved via `fcb_opens.paths.resolve_db_path`, which
honors the FCB_OPENS_DB environment variable when set and otherwise
anchors to the project root regardless of the current working
directory. See paths.py for the full resolution order.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

from .. import db
from ..paths import resolve_db_path


def get_db_path() -> Path:
    """Return the configured SQLite DB path."""
    return resolve_db_path()


def get_connection() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency that yields a SQLite connection per request.

    `init_db` is NOT called here — it ran once at app startup via the
    lifespan handler. Calling it per-request used to run UPDATE
    migrations on every hit, fighting the background lliga refresh for
    the single SQLite write lock and producing intermittent 500s with
    "database is locked".
    """
    db_path = get_db_path()
    conn = db.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()
