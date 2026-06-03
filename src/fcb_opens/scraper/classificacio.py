"""Scraper for an individual Open final classification.

URL pattern:
    https://www.fcbillar.cat/ca/individuals/classificaciofinal/{division_id}/{classification_id}

Examples:
    204/439 — XXIII Ciutat de Manresa (2025-26)
    196/431 — IX Ciutat de Sant Adrià (2025-26)
    189/405 — VI Vila de Llinars (2025-26)

The page exposes a single HTML table with columns:
    #, Jugador, Club, PJ, Punts, CAR, ENT, MG, MP, SM
"""

from __future__ import annotations

from bs4 import BeautifulSoup
from bs4.element import Tag

from ..models import Open, OpenClassificationEntry, normalize_club
from .http import fetch

BASE_URL = "https://www.fcbillar.cat/ca/individuals/classificaciofinal/{division_id}/{classification_id}"
HISTORICAL_URL = "https://www.fcbillar.cat/ca/historial/classificaciofinalIndividual/{division_id}/{classification_id}"


def classification_url(division_id: int, classification_id: int) -> str:
    return BASE_URL.format(
        division_id=division_id,
        classification_id=classification_id,
    )


def classification_url_historical(division_id: int, classification_id: int) -> str:
    """URL for the historical Open classification page.

    Note: the FCB currently serves a placeholder page here ("No hi ha
    temporades disponibles") instead of the real classification table.
    Callers should prefer `classification_url()` for both current and
    historical Opens unless the site changes its behavior in the future.
    """
    return HISTORICAL_URL.format(
        division_id=division_id,
        classification_id=classification_id,
    )


def fetch_classification(
    division_id: int,
    classification_id: int,
    *,
    historical: bool = False,
    force: bool = False,
) -> Open:
    """Fetch and parse an Open's final classification.

    Args:
        division_id: FCB division id.
        classification_id: FCB classification id.
        historical: if True, use the /historial/ URL variant. This mode
            is kept only for backwards compatibility and is effectively
            obsolete; the FCB serves the real table from the /individuals/
            URL for both current and historical Opens.
        force: bypass the HTTP cache.
    """
    url = (
        classification_url_historical(division_id, classification_id)
        if historical
        else classification_url(division_id, classification_id)
    )
    html = fetch(url, force=force)
    return parse_classification_html(html, division_id, classification_id)


def parse_classification_html(
    html: str,
    division_id: int,
    classification_id: int,
) -> Open:
    """Parse a pre-fetched classification HTML page."""
    soup = BeautifulSoup(html, "lxml")
    name = _extract_open_name(soup, division_id)

    table = _find_classification_table(soup)
    if table is None:
        raise ValueError("Classification table not found in HTML")

    entries: list[OpenClassificationEntry] = []
    for row in table.find_all("tr"):
        parsed = _parse_classification_row(row)
        if parsed is not None:
            entries.append(parsed)

    if not entries:
        raise ValueError("Classification table was found but contained no parseable rows")

    return Open(
        fcb_division_id=division_id,
        fcb_classification_id=classification_id,
        name=name,
        season="",  # set by the caller (e.g. from the overall Opens index)
        classification=entries,
    )


def _extract_open_name(soup: BeautifulSoup, division_id: int) -> str:
    """Try to extract the Open's display name from the breadcrumb link
    that points to /individuals/divisions/{division_id}."""
    target_href = f"/individuals/divisions/{division_id}"
    for link in soup.find_all("a"):
        href = link.get("href", "")
        if target_href in href:
            text = link.get_text(strip=True)
            if text:
                return text
    return "UNKNOWN"


def _find_classification_table(soup: BeautifulSoup) -> Tag | None:
    """Locate the classification table by its header signature.

    Signature headers: 'Jugador', 'CAR', 'MG', 'SM' — the combination is
    specific enough to avoid other tables on the page.
    """
    for table in soup.find_all("table"):
        headers = {th.get_text(strip=True) for th in table.find_all("th")}
        if {"Jugador", "CAR", "MG", "SM"}.issubset(headers):
            return table
    return None


def _parse_classification_row(row: Tag) -> OpenClassificationEntry | None:
    cells = row.find_all("td")
    if len(cells) < 10:
        return None

    try:
        position = int(cells[0].get_text(strip=True))
    except ValueError:
        return None

    return OpenClassificationEntry(
        position=position,
        player_name=cells[1].get_text(strip=True),
        club=normalize_club(cells[2].get_text(strip=True)),
        matches_played=_safe_int(cells[3]),
        match_points=_safe_int(cells[4]),
        caramboles=_safe_int(cells[5]),
        entries=_safe_int(cells[6]),
        general_average=_safe_float(cells[7]),
        particular_average=_safe_float(cells[8]),
        best_series=_safe_int(cells[9]),
    )


def _safe_int(cell: Tag) -> int:
    text = cell.get_text(strip=True)
    try:
        return int(text)
    except ValueError:
        return 0


def _safe_float(cell: Tag) -> float:
    text = cell.get_text(strip=True)
    try:
        return float(text)
    except ValueError:
        return 0.0
