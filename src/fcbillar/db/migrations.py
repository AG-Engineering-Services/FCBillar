"""Gestió simple d'esquema via PRAGMA user_version."""

from __future__ import annotations

import sqlite3
from importlib.resources import files
from pathlib import Path

SCHEMA_VERSION = 1


def _read_schema_sql() -> str:
    return (files("fcbillar.db") / "schema.sql").read_text(encoding="utf-8")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def current_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def ensure_schema(db_path: Path) -> sqlite3.Connection:
    conn = connect(db_path)
    version = current_version(conn)
    if version < SCHEMA_VERSION:
        conn.executescript(_read_schema_sql())
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return conn
