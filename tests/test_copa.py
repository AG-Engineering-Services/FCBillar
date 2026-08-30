"""Tests de la copa: parsers i pipeline d'ingesta.

Fixtures del web nou (edició 7, capturades el 2026-08-30). El test d'ingesta
recorre la jerarquia sencera —jornades → grups → encontres → partides— amb un
client fals que serveix la fixture de cada nivell, contra una BD d'usar i
llençar.

Amb el web d'agost de 2026 totes les subrutes de copa s'han renombrat
(`faseGrups` → `fase-grups`, `encontresGrup` → `encontres-grup`…), i el
resultat d'un encontre ha passat de «(3) - (0)» a «3 - 0».
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from fcbillar.db.migrations import ensure_schema
from fcbillar.pipeline import ingest_copa_edicio
from fcbillar.scraper.parsers import (
    parse_copa_encontresgrup,
    parse_copa_grups,
    parse_copa_jornades,
    parse_copa_partides,
)

FX = Path(__file__).resolve().parent / "fixtures" / "nou"


def _rd(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8", errors="ignore")


pytestmark = pytest.mark.skipif(
    not (FX / "copa_fase_grups_7.html").exists(), reason="falten les fixtures de copa"
)


def test_parse_copa_jornades():
    jors = parse_copa_jornades(_rd("copa_fase_grups_7.html"))
    assert len(jors) == 4
    assert jors[0].edicio_id == 7
    assert any(j.jornada == 26 for j in jors)


def test_parse_copa_grups():
    grups = parse_copa_grups(_rd("copa_grups_7_26.html"))
    assert len(grups) == 8
    assert grups[0].grup_id == 150
    assert grups[0].nom == "GRUP A"


def test_parse_copa_encontresgrup():
    data = parse_copa_encontresgrup(_rd("copa_encontres_grup_7_26_150.html"))
    assert data.grup_nom == "GRUP A"
    assert len(data.classificacio) == 3
    assert len(data.encontres) == 3
    e = data.encontres[0]
    assert (e.enc_id_extern, e.team_a_extern, e.team_b_extern) == (472, 245, 238)
    assert e.p_match_local == 3 and e.p_match_visitant == 0


def test_parse_copa_partides():
    rows = parse_copa_partides(_rd("copa_partides_grup_7_26_150_472_245_238.html"))
    assert len(rows) == 3
    assert rows[0].local_caramboles == 30
    assert rows[0].entrades == 49


class _FakeClient:
    """Maps each copa URL level to its fixture."""

    def __init__(self, settings):
        self.settings = settings

    def fetch_html(self, url: str, use_cache: bool = True) -> str:
        # L'ordre importa: "partides-grup" i "encontres-grup" també contenen
        # "grup", o sigui que es miren abans que la ruta de grups.
        if "/fase-grups/" in url:
            return _rd("copa_fase_grups_7.html")
        if "/partides-grup/" in url:
            return _rd("copa_partides_grup_7_26_150_472_245_238.html")
        if "/encontres-grup/" in url:
            return _rd("copa_encontres_grup_7_26_150.html")
        if "/grups/" in url:
            return _rd("copa_grups_7_26.html")
        raise AssertionError(f"URL de copa no prevista al test: {url}")


def test_ingest_copa_edicio(tmp_path):
    db = tmp_path / "copa.db"
    settings = types.SimpleNamespace(base_url="https://example.test", db_path=db)
    client = _FakeClient(settings)

    res = ingest_copa_edicio(client, 7, jornada=26, settings=settings)
    # 1 jornada · 8 groups · 8×3 encontres · 8×3×3 partides
    assert (res.jornades, res.grups, res.encontres, res.partides) == (1, 8, 24, 72)

    conn = ensure_schema(db)
    assert conn.execute("SELECT COUNT(*) FROM copa_encontres").fetchone()[0] == 24
    assert conn.execute("SELECT COUNT(*) FROM copa_classificacio").fetchone()[0] == 24
    assert conn.execute("SELECT COUNT(*) FROM copa_partides").fetchone()[0] == 72

    # Idempotent: a second run must not duplicate rows.
    ingest_copa_edicio(client, 7, jornada=26, settings=settings)
    conn2 = ensure_schema(db)
    assert conn2.execute("SELECT COUNT(*) FROM copa_encontres").fetchone()[0] == 24
    assert conn2.execute("SELECT COUNT(*) FROM copa_partides").fetchone()[0] == 72
