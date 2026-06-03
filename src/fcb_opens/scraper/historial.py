"""Historical Opens scraper for fcbillar.cat/ca/historial.

Walks four URL levels to discover and catalogue all past 3-cushion
Opens from the FCB history section:

    Level 0: /ca/historial
        Section index. We find the INDIVIDUALS season links here:
        /ca/historial/llistatIndividual/{season}

    Level 1: /ca/historial/llistatIndividual/{season}
        Season page listing all individual competitions. Each
        competition is a link like:
        /ca/historial/divisionsIndividual/{division_id}
        Competitions are listed in reverse chronological order —
        the highest division_id is the most recent.

    Level 2: /ca/historial/divisionsIndividual/{division_id}
        Competition page with phase links. We extract the
        classification_id from the "Classificació final" link:
        /ca/historial/classificaciofinalIndividual/{div_id}/{clf_id}

    Level 3: /ca/historial/classificaciofinalIndividual/{div_id}/{clf_id}
        Final classification HTML table. Reuses the existing parser
        from scraper.classificacio because the table structure is
        identical to the current-season version.

The filtering strategy is name-based (the FCB has no structured
modality tag on the historical pages). See `DEFAULT_EXCLUDE_PATTERNS`.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Iterator

from bs4 import BeautifulSoup

from ..models import normalize_name
from .http import fetch

HISTORIAL_URL = "https://www.fcbillar.cat/ca/historial"
SEASON_LISTING_URL = "https://www.fcbillar.cat/ca/historial/llistatIndividual/{season}"
DIVISION_URL = "https://www.fcbillar.cat/ca/historial/divisionsIndividual/{division_id}"

# Default patterns (case/accent-insensitive) that mark a competition
# as non-3-bandes. A competition is considered a 3-bandes Open if
# its name contains "OPEN" AND none of these exclude patterns.
DEFAULT_EXCLUDE_PATTERNS: tuple[str, ...] = (
    "QUADRE",     # 47/2, 71/2 etc.
    "LLIURE",     # lliure modality
    "QUILLES",    # 5 quilles
    "ARTISTIC",   # billiard artistic
    "BIATHLO",    # biatló (normalized form of "BIATHLÓ")
    "JUNIOR",
    "FEMENI",
    "600",        # OPEN 600 LLINARS (not 3-bandes per user decision)
    "47/2",       # just in case
    "71/2",
)


@dataclass(frozen=True)
class SeasonLink:
    """One season from the historial index page."""

    season: str  # e.g. "2024-2025"
    url: str


@dataclass(frozen=True)
class CompetitionLink:
    """One competition from a season listing page."""

    name: str
    division_id: int
    season: str
    url: str


@dataclass(frozen=True)
class HistoricalOpen:
    """A historical Open fully resolved: ready to fetch its classification."""

    name: str
    division_id: int
    classification_id: int
    season: str


# --------------------------------------------------------------------------- #
# Parsers (pure HTML → structured data, unit-testable)
# --------------------------------------------------------------------------- #


def parse_historial_index(html: str) -> list[SeasonLink]:
    """Extract INDIVIDUALS season links from the /ca/historial page.

    The page has three sections (LLIGUES, INDIVIDUALS, COPA). We
    only want INDIVIDUALS, identified by the URL prefix
    /ca/historial/llistatIndividual/.
    """
    soup = BeautifulSoup(html, "lxml")
    seasons: list[SeasonLink] = []
    seen: set[str] = set()
    for link in soup.find_all("a"):
        href = link.get("href", "")
        m = re.search(r"/?ca/historial/llistatIndividual/([\w\-]+)", href)
        if not m:
            continue
        season = m.group(1)
        if season in seen:
            continue
        seen.add(season)
        seasons.append(
            SeasonLink(
                season=season,
                url=SEASON_LISTING_URL.format(season=season),
            )
        )
    return seasons


def parse_season_listing(html: str, season: str) -> list[CompetitionLink]:
    """Extract all competition links from a season listing page.

    Returns every competition in the page (no filtering). The caller
    applies name filters. The FCB orders competitions in reverse
    chronological order on this page; we preserve that order.
    """
    soup = BeautifulSoup(html, "lxml")
    comps: list[CompetitionLink] = []
    seen_ids: set[int] = set()
    for link in soup.find_all("a"):
        href = link.get("href", "")
        m = re.search(r"/?ca/historial/divisionsIndividual/(\d+)", href)
        if not m:
            continue
        division_id = int(m.group(1))
        if division_id in seen_ids:
            continue
        seen_ids.add(division_id)
        name = link.get_text(strip=True)
        if not name:
            continue
        comps.append(
            CompetitionLink(
                name=name,
                division_id=division_id,
                season=season,
                url=DIVISION_URL.format(division_id=division_id),
            )
        )
    return comps


def parse_division_page(html: str) -> int | None:
    """Extract the classification_id from a competition's division page.

    The page contains a link like:
        <a href="/ca/historial/classificaciofinalIndividual/187/404">Classificació final</a>
    We only care about the numeric classification_id at the end.
    Returns None if the page has no Classificació final link (some
    competitions in progress or very old ones).
    """
    soup = BeautifulSoup(html, "lxml")
    for link in soup.find_all("a"):
        href = link.get("href", "")
        m = re.search(
            r"/?ca/historial/classificaciofinalIndividual/\d+/(\d+)", href
        )
        if m:
            return int(m.group(1))
    return None


# --------------------------------------------------------------------------- #
# Filtering
# --------------------------------------------------------------------------- #


def is_three_bandes_open(
    name: str,
    *,
    exclude_patterns: tuple[str, ...] = DEFAULT_EXCLUDE_PATTERNS,
    include_ids: set[int] | None = None,
    division_id: int | None = None,
) -> bool:
    """Return True if the competition name suggests a 3-bandes Open.

    Rules:
      1. If `include_ids` is given and `division_id` is in it, always True.
      2. Must contain "OPEN" (accent-insensitive).
      3. Must NOT contain any of `exclude_patterns` (accent-insensitive).
      4. "BANDA" alone (without "BANDES") excludes the single-band
         modality while allowing "TRES BANDES".
    """
    if include_ids and division_id is not None and division_id in include_ids:
        return True

    norm = normalize_name(name)
    if "OPEN" not in norm:
        return False

    for pattern in exclude_patterns:
        if normalize_name(pattern) in norm:
            return False

    # Special case: "BANDA" without "BANDES" or "TRES BANDES"
    if re.search(r"\bBANDA\b", norm) and "BANDES" not in norm:
        return False

    return True


def filter_competitions(
    competitions: list[CompetitionLink],
    *,
    exclude_patterns: tuple[str, ...] = DEFAULT_EXCLUDE_PATTERNS,
    include_ids: set[int] | None = None,
    only_name_substring: str | None = None,
) -> list[CompetitionLink]:
    """Apply the 3-bandes Open filter and optional name substring filter."""
    result: list[CompetitionLink] = []
    for comp in competitions:
        if not is_three_bandes_open(
            comp.name,
            exclude_patterns=exclude_patterns,
            include_ids=include_ids,
            division_id=comp.division_id,
        ):
            continue
        if only_name_substring:
            if normalize_name(only_name_substring) not in normalize_name(comp.name):
                continue
        result.append(comp)
    return result


# --------------------------------------------------------------------------- #
# High-level walker
# --------------------------------------------------------------------------- #


def list_seasons(*, force: bool = False) -> list[SeasonLink]:
    """Fetch the /ca/historial index and return all individual seasons."""
    html = fetch(HISTORIAL_URL, force=force)
    return parse_historial_index(html)


def list_competitions(season: str, *, force: bool = False) -> list[CompetitionLink]:
    """Fetch a single season listing and return all its competitions."""
    html = fetch(SEASON_LISTING_URL.format(season=season), force=force)
    return parse_season_listing(html, season)


def resolve_classification_id(
    competition: CompetitionLink,
    *,
    force: bool = False,
) -> int | None:
    """Fetch a division page and extract its classification_id."""
    html = fetch(competition.url, force=force)
    return parse_division_page(html)


def discover_historical_opens(
    *,
    seasons: list[str] | None = None,
    exclude_patterns: tuple[str, ...] = DEFAULT_EXCLUDE_PATTERNS,
    include_ids: set[int] | None = None,
    only_name_substring: str | None = None,
    rate_limit_s: float = 0.3,
    force: bool = False,
) -> Iterator[HistoricalOpen | tuple[str, str]]:
    """Walk levels 0 → 1 → 2 and yield every 3-bandes Open found.

    Yields either a `HistoricalOpen` (ready to fetch classification)
    or a `("error", message)` tuple for problems that should be
    reported but not stop the walk (e.g. a division page without a
    classification link).

    Args:
        seasons: if None, all seasons from the historial index.
            Otherwise restrict to these season strings (e.g. "2024-2025").
        exclude_patterns: patterns that mark a competition as non-3-bandes.
        include_ids: division ids to always include regardless of name.
        only_name_substring: if given, only keep competitions whose name
            (normalized) contains this substring.
        rate_limit_s: sleep between level-2 requests to be polite.
        force: bypass the HTTP cache.
    """
    if seasons is None:
        season_links = list_seasons(force=force)
        seasons_to_walk = [s.season for s in season_links]
    else:
        seasons_to_walk = seasons

    for season in seasons_to_walk:
        try:
            competitions = list_competitions(season, force=force)
        except Exception as e:
            yield ("error", f"season {season}: {e}")
            continue

        filtered = filter_competitions(
            competitions,
            exclude_patterns=exclude_patterns,
            include_ids=include_ids,
            only_name_substring=only_name_substring,
        )

        for comp in filtered:
            try:
                clf_id = resolve_classification_id(comp, force=force)
            except Exception as e:
                yield ("error", f"{comp.name} (div {comp.division_id}): {e}")
                continue

            if clf_id is None:
                yield ("error", f"{comp.name} (div {comp.division_id}): no classification final link")
                continue

            yield HistoricalOpen(
                name=comp.name,
                division_id=comp.division_id,
                classification_id=clf_id,
                season=comp.season,
            )

            if rate_limit_s > 0:
                time.sleep(rate_limit_s)
