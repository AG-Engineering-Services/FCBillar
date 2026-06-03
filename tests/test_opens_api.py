"""Smoke tests for the FCBillar opens API surface (main app + mounted sub-app).

Deterministic: they assert shapes and the absent/404 paths rather than relying
on specific player data, so they pass regardless of DB contents (as long as the
databases exist).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# `api` and `desktop` live at the repo root (not under src/), so make them
# importable when pytest's rootdir isn't already on sys.path.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytestmark = pytest.mark.skipif(
    not (ROOT / "data" / "fcbillar.db").exists()
    or not (ROOT / "data" / "fcb_opens.db").exists(),
    reason="databases not present",
)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from api.app import app

    return TestClient(app)


def test_resolve_players_absent_name_is_null(client):
    r = client.post("/api/opens/resolve-players", json={"names": ["___NO_EXISTEIX___, NINGU"]})
    assert r.status_code == 200
    assert r.json()["___NO_EXISTEIX___, NINGU"] is None


def test_followed_players_returns_list(client):
    r = client.get("/api/opens/followed-players")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    if body:
        assert {"fcb_id", "nom"} <= set(body[0])


def test_player_opens_404_for_unknown(client):
    r = client.get("/api/players/__no_such_fcb_id__/opens")
    assert r.status_code == 404


def test_projections_list_and_detail(client):
    r = client.get("/opens-backend/api/opens/projections")
    assert r.status_code == 200
    projections = r.json()
    assert isinstance(projections, list)
    if projections:
        pid = projections[0]["id"]
        d = client.get(f"/opens-backend/api/opens/projections/{pid}").json()
        assert {"name", "num_inscriptions", "structure", "seeds", "phases", "fase_final"} <= set(d)


def test_compare_unlinked_projection_is_unpublished(client):
    r = client.get("/opens-backend/api/opens/projections")
    projections = r.json()
    if not projections:
        pytest.skip("no projections to compare")
    pid = projections[0]["id"]
    # A projection with no linked division reports published=false (no network hit).
    detail = client.get(f"/opens-backend/api/opens/projections/{pid}").json()
    if detail.get("fcb_division_id"):
        pytest.skip("projection already linked to a division")
    c = client.get(f"/opens-backend/api/opens/projections/{pid}/compare").json()
    assert c["published"] is False
