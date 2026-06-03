"""Scraper for the monthly FCB Carambola ranking.

URL pattern:
    https://www.fcbillar.cat/ca/rankings/s/1/Carambola/m/{month_id}/1/

The `month_id` is a monotonically increasing integer that the FCB updates
approximately on the first of each month. 120 corresponds to March 2026.

The page returns a single server-rendered HTML table with columns:
    #, Jugador, MJ, Punts*, Definitiu**
where Punts is formatted as "aconseguits/possibles" (e.g. "30/30") and
Definitiu is the literal text "Definitiva" or "Provisional".
"""

from __future__ import annotations

from datetime import date

from bs4 import BeautifulSoup
from bs4.element import Tag

from ..models import MonthlyRanking, RankingEntry, normalize_club
from .http import fetch

BASE_URL = "https://www.fcbillar.cat/ca/rankings/s/1/Carambola/m/{month_id}/1/"


def ranking_url(month_id: int) -> str:
    return BASE_URL.format(month_id=month_id)


def fetch_ranking(month_id: int, *, force: bool = False) -> MonthlyRanking:
    """Fetch and parse the monthly ranking for the given month_id."""
    html = fetch(ranking_url(month_id), force=force)
    return parse_ranking_html(html, month_id)


def parse_ranking_html(html: str, month_id: int) -> MonthlyRanking:
    """Parse a pre-fetched ranking HTML page."""
    soup = BeautifulSoup(html, "lxml")
    table = _find_ranking_table(soup)
    if table is None:
        raise ValueError("Ranking table not found in HTML")

    entries: list[RankingEntry] = []
    for row in table.find_all("tr"):
        parsed = _parse_ranking_row(row)
        if parsed is not None:
            entries.append(parsed)

    if not entries:
        raise ValueError("Ranking table was found but contained no parseable rows")

    return MonthlyRanking(
        month_id=month_id,
        fetched_at=date.today(),
        entries=entries,
    )


def _find_ranking_table(soup: BeautifulSoup) -> Tag | None:
    """Locate the ranking table by its header signature.

    Tables in the FCB page have no stable id or class, so we sniff for
    the combination of headers: 'Jugador', 'MJ', 'Definitiu'.
    """
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        header_joined = " ".join(headers)
        if "Jugador" in header_joined and "MJ" in header_joined and "Definitiu" in header_joined:
            return table
    return None


def _parse_ranking_row(row: Tag) -> RankingEntry | None:
    cells = row.find_all("td")
    if len(cells) < 5:
        return None

    position_text = cells[0].get_text(strip=True)
    try:
        position = int(position_text)
    except ValueError:
        return None

    player_name = cells[1].get_text(strip=True)

    # The FCB ranking table appears in two variants:
    # - 5 columns: #, Jugador, MJ, Punts, Definitiu
    # - 6 columns: #, Jugador, Club, MJ, Punts, Definitiu
    if "/" in cells[3].get_text(strip=True):
        club = None
        average_text = cells[2].get_text(strip=True)
        points_text = cells[3].get_text(strip=True)  # e.g. "30/30"
        definitive_text = cells[4].get_text(strip=True)
    elif len(cells) >= 6 and "/" in cells[4].get_text(strip=True):
        club = normalize_club(cells[2].get_text(strip=True))
        average_text = cells[3].get_text(strip=True)
        points_text = cells[4].get_text(strip=True)
        definitive_text = cells[5].get_text(strip=True)
    else:
        return None

    try:
        average = float(average_text)
    except ValueError:
        return None

    try:
        scored_text, max_text = points_text.split("/", 1)
        matches_scored = int(scored_text.strip())
        matches_max = int(max_text.strip())
    except (ValueError, IndexError):
        return None

    is_definitive = definitive_text.lower().startswith("defin")

    return RankingEntry(
        position=position,
        player_name=player_name,
        average=average,
        matches_scored=matches_scored,
        matches_max=matches_max,
        is_definitive=is_definitive,
        club=club,
    )
