"""Path resolution helpers.

Centralizes how fcb-opens finds its default database location.

The resolution order is:
  1. $FCB_OPENS_DB environment variable (absolute path, explicit)
  2. <project_root>/data/fcb_opens.db, where project_root is the
     closest directory above the package source that contains a
     pyproject.toml file.
  3. $CWD/data/fcb_opens.db, as a last-resort fallback when the
     package is installed outside of any project (e.g. from PyPI).

This means the CLI and the API always agree on the same DB file
regardless of which directory you invoke them from, as long as you
are inside the checked-out project.
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path

_PROJECT_MARKER = "pyproject.toml"
_DB_RELATIVE = Path("data") / "fcb_opens.db"


@cache
def find_project_root() -> Path | None:
    """Walk upwards from this file looking for pyproject.toml.

    Cached because the answer never changes during a single process.
    Returns None if no marker is found (e.g. when installed as a wheel
    with no accompanying project tree).
    """
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / _PROJECT_MARKER).is_file():
            return candidate
    return None


def default_db_path() -> Path:
    """Return the default SQLite DB path, anchored to the project root.

    Falls back to `./data/fcb_opens.db` under the current working
    directory only if no project root can be located.
    """
    root = find_project_root()
    if root is not None:
        return root / _DB_RELATIVE
    return Path.cwd() / _DB_RELATIVE


def resolve_db_path(override: Path | str | None = None) -> Path:
    """Resolve the DB path honoring override > env var > project default.

    Args:
        override: explicit path passed from the CLI (--db flag). Wins
            over everything when provided.

    Returns:
        An absolute Path. Creation of the parent directory is the
        caller's responsibility (db.init_db does this).
    """
    if override is not None:
        return Path(override).expanduser().resolve()
    env = os.environ.get("FCB_OPENS_DB")
    if env:
        return Path(env).expanduser().resolve()
    return default_db_path().resolve()
