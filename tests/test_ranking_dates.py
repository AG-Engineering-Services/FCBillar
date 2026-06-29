"""Tests de la derivació num_seq → mes a partir de la data real de l'historial."""

from __future__ import annotations

from datetime import date

import pytest

from fcbillar.config import Settings
from fcbillar.db.migrations import ensure_schema
from fcbillar.models import Ranking
from fcbillar.pipeline import reconcile_ranking_dates
from fcbillar.ranking_dates import month_for_publication_date
from fcbillar.scraper.parsers import HistorialEntry


@pytest.mark.parametrize(
    "d, expected",
    [
        (date(2024, 4, 2), (2024, 4)),   # principi de mes -> mateix mes
        (date(2024, 7, 8), (2024, 7)),
        (date(2024, 7, 29), (2024, 9)),  # finals de mes + salt d'agost -> setembre
        (date(2024, 9, 30), (2024, 10)),  # finals de mes -> mes vinent
        (date(2025, 3, 31), (2025, 4)),
        (date(2025, 5, 5), (2025, 5)),
        (date(2024, 12, 9), (2024, 12)),
        (date(2025, 7, 1), (2025, 7)),
        (date(2025, 12, 30), (2026, 1)),  # canvi d'any
    ],
)
def test_month_for_publication_date(d: date, expected: tuple[int, int]) -> None:
    assert month_for_publication_date(d) == expected


def test_reconcile_corrects_wrong_month_and_stores_data_pub(tmp_path) -> None:
    settings = Settings(db_path=tmp_path / "t.db")
    conn = ensure_schema(settings.db_path)
    from fcbillar.db.repository import Repository

    repo = Repository(conn)
    # Sembrem el num_seq 102 amb un mes EQUIVOCAT (juliol) i sense data_pub.
    repo.upsert_ranking(
        Ranking(num_seq=102, modalitat_codi_fcb=1, url="x", format_url="data",
                any_pub=2024, mes_pub=7)
    )
    conn.commit()

    # L'historial diu que el 102 es va publicar el 2024-07-29 -> setembre.
    entries = [HistorialEntry(data=date(2024, 7, 29), rankings={1: ("data", 102)})]
    result = reconcile_ranking_dates(entries, settings=settings)

    assert result.dated == 1
    assert len(result.changed) == 1
    chg = result.changed[0]
    assert chg.num_seq == 102
    assert chg.old == (2024, 7)
    assert chg.new == (2024, 9)

    row = conn.execute(
        "SELECT any_pub, mes_pub, data_pub FROM rankings WHERE num_seq=102"
    ).fetchone()
    assert (row["any_pub"], row["mes_pub"], row["data_pub"]) == (2024, 9, "2024-07-29")


def test_reconcile_reports_num_seq_not_in_db(tmp_path) -> None:
    settings = Settings(db_path=tmp_path / "t.db")
    ensure_schema(settings.db_path)
    entries = [HistorialEntry(data=date(2025, 7, 1), rankings={1: ("data", 999)})]
    result = reconcile_ranking_dates(entries, settings=settings)
    assert result.not_in_db == [999]
    assert result.dated == 0
