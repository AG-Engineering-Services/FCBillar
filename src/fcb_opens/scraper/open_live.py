"""Live-tournament scraper for Opens currently being played.

Unlike `classificacio.py` which scrapes the final classification once the
Open is closed, this module walks the in-progress structure:

    divisions/{div}                  → top-level Open page
    fases/{div}/{phase}              → list of group-phases + KO rounds
    grups/{div}/{phase}/{subphase}   → list of groups in a phase
    partidesgrups/{div}/{phase}/{subphase}/{group_id}  → one group's standings + matches
    partideseliminatoria/{div}/{phase}/{elim_id}       → one KO round's matches

The page markup is consistent across Opens. We reuse the shared HTTP cache
from `scraper/http.py`, which means a full refresh is one HTTP round-trip
per unique page (no re-parsing after the first scrape within the 1h TTL).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from .http import fetch, fetch_binary

BASE = "https://www.fcbillar.cat/ca"
LLISTAT_URL = f"{BASE}/individuals/llistat"
# Docs listing for the "Opens" subcategory of Carambola. The trailing segment
# is the zero-based offset (20 per page). Season id 15 = 2025-26.
DOCS_OPENS_BASE = f"{BASE}/docs/s/1/Carambola/c/68/15"

# Live tournament data changes as matches are played. 60 s is a good trade-off
# between "fresh" and "not hammering the FCB on every client poll". Static
# metadata (division/fases layout, docs listings) keeps the default 1 h TTL.
LIVE_TTL_S = 60


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PhaseRef:
    """Reference to a group-phase (grups) or a KO round (partideseliminatoria)."""

    label: str                       # e.g. "PRÈVIA", "SETZENS"
    kind: str                        # "group" | "ko"
    url: str                         # path after BASE, e.g. "/individuals/grups/206/443/785"
    group_ids: tuple[int, ...] = ()  # populated for kind="group" after fetch_phase_detail


@dataclass(frozen=True)
class DocEntry:
    """One document from the FCB 'Competició Opens' documents section.

    Each entry has a title, publication date and a VIEW url (HTML page that
    links to the actual PDF). We don't follow through to the PDF by default —
    that's up to the frontend or a second-pass enrichment.
    """

    doc_id: int
    title: str
    date: str       # "DD/MM/YYYY" as printed by FCB
    view_url: str   # absolute URL of the view page


_DOC_VIEW_RE = re.compile(
    r"/docs/view/s/1/Carambola/d/(\d+)/([^/]+)/c/\d+/\d+/\d+"
)
_DOC_DATE_RE = re.compile(r"Data:\s*(\d{2}/\d{2}/\d{4})")


def parse_opens_docs(html: str) -> tuple[DocEntry, ...]:
    """Parse one page of the Opens documents listing."""
    soup = BeautifulSoup(html, "lxml")
    out: list[DocEntry] = []
    for block in soup.find_all("div", class_="row noticies"):
        link = block.find("a")
        if link is None:
            continue
        href = link.get("href") or ""
        m = _DOC_VIEW_RE.search(href)
        if not m:
            continue
        doc_id = int(m.group(1))
        title = link.get_text(strip=True)
        # Date is in a sibling <p><span class='meta'>Data: DD/MM/YYYY</span>...
        date_match = _DOC_DATE_RE.search(block.get_text())
        date = date_match.group(1) if date_match else ""
        out.append(DocEntry(
            doc_id=doc_id,
            title=title,
            date=date,
            view_url=_abs(href),
        ))
    return tuple(out)


_DOC_PDF_RE = re.compile(
    r"""href=['"]([^'"]*\.pdf)['"]""",
    re.IGNORECASE,
)


def doc_view_url(doc_id: int, slug: str = "x") -> str:
    """Build the canonical view URL for a document id. The slug in the URL
    is decorative — FCB ignores it as long as the doc id is correct."""
    return f"{BASE}/docs/view/s/1/Carambola/d/{doc_id}/{slug}/c/68/15/0"


def parse_doc_pdf_url(html: str) -> str | None:
    """Extract the underlying PDF URL from a document's view page.

    The view page has a link to `/media/.../<filename>.pdf`. There are many
    other PDF links on the layout (calendar banner, etc.) so we take the
    LAST one inside the main content area: the main PDF is rendered after
    the page title, and the header/footer links appear before it.
    """
    soup = BeautifulSoup(html, "lxml")
    # Search the main section; fall back to whole document if not found.
    section = soup.find("section", class_="three fourths padded") or soup
    candidates: list[str] = []
    for link in section.find_all("a"):
        href = link.get("href") or ""
        if href.lower().endswith(".pdf"):
            candidates.append(href)
    if not candidates:
        return None
    # FCB stores doc PDFs under /media/{season}/COMPETICIO/OPENS/...
    # Prefer any PDF under /COMPETICIO/OPENS/; otherwise take the last link
    # (main content PDF, not header banners).
    for url in candidates:
        if "/COMPETICIO/OPENS/" in url.upper():
            return url
    return candidates[-1]


def fetch_doc_pdf(doc_id: int, *, force: bool = False) -> tuple[bytes, str]:
    """Fetch a document's PDF as bytes + filename.

    Two-step fetch: first the view page (cached), then the PDF itself
    (cached separately as a .pdf file).
    """
    from urllib.parse import unquote

    html = fetch(doc_view_url(doc_id), force=force)
    pdf_url = parse_doc_pdf_url(html)
    if pdf_url is None:
        raise ValueError(f"No PDF link found in view page for doc {doc_id}")
    # Derive a clean filename from the URL
    filename = unquote(pdf_url.rsplit("/", 1)[-1])
    pdf_bytes = fetch_binary(pdf_url, force=force, suffix=".pdf")
    return pdf_bytes, filename


def fetch_opens_docs(*, pages: int = 3, force: bool = False) -> tuple[DocEntry, ...]:
    """Fetch all pages of the Opens docs listing. `pages=3` covers up to 60
    docs (current season tops at ~35). Each page is cached individually."""
    collected: list[DocEntry] = []
    seen_ids: set[int] = set()
    for page in range(pages):
        offset = page * 20
        url = f"{DOCS_OPENS_BASE}/{offset}"
        try:
            html = fetch(url, force=force)
        except Exception:  # noqa: BLE001
            break
        batch = parse_opens_docs(html)
        if not batch:
            break
        new_this_page = 0
        for doc in batch:
            if doc.doc_id in seen_ids:
                continue
            seen_ids.add(doc.doc_id)
            collected.append(doc)
            new_this_page += 1
        # If this page returned zero new entries, we've reached the end.
        if new_this_page == 0:
            break
    return tuple(collected)


# --------------------------------------------------------------------------- #
# Doc linking: associate docs to Open divisions via title keywords
# --------------------------------------------------------------------------- #

# Alias tokens that identify a specific Open in doc titles. The official
# "OPEN TRES BANDES X" name doesn't always appear — some Opens use memorial /
# sponsor names (e.g. Sants 2026 = "30e Memorial Joaquim Domingo"). We match
# case-insensitively using `token in title.upper()`.
OPEN_TITLE_ALIASES: dict[int, tuple[str, ...]] = {
    206: ("SANTS", "JOAQUIM DOMINGO"),
    204: ("MANRESA", "JAUME ARNAU"),
    196: ("SANT ADRIA", "SANT ADRIÀ"),
    189: ("LLINARS", "XAVI MARTINEZ"),
    187: ("MATARO", "MATARÓ", "LES SANTES"),
    186: ("COSTA DAURADA",),
}


def filter_docs_for_division(
    docs: Iterable[DocEntry],
    division_id: int,
    division_name: str,
) -> tuple[DocEntry, ...]:
    """Return the subset of docs whose title matches the given Open.

    Matching is a case-insensitive substring check against either an entry in
    OPEN_TITLE_ALIASES[division_id] or a key token of the division's name
    (stripped of generic prefixes like 'OPEN TRES BANDES').
    """
    aliases = set(OPEN_TITLE_ALIASES.get(division_id, ()))
    # Derive a fallback alias from the division name.
    cleaned = (
        division_name.upper()
        .replace("OPEN", "")
        .replace("TRES BANDES", "")
        .replace("FEMENI", "")
        .strip()
    )
    if cleaned:
        aliases.add(cleaned)

    upper_aliases = {a.upper() for a in aliases if a}
    matched: list[DocEntry] = []
    for d in docs:
        title_upper = d.title.upper()
        if any(alias in title_upper for alias in upper_aliases):
            matched.append(d)
    return tuple(matched)


@dataclass(frozen=True)
class CompetitionIndexEntry:
    """Entry from the /individuals/llistat index page.

    The FCB lists current-season competitions in reverse-chronological order
    (most recent first). Not all are Tres Bandes Opens — includes other
    disciplines (QUADRE, SNOOKER, etc.) and modalities (FEMENI, JUNIOR).
    """

    division_id: int
    name: str
    index: int  # position in the list, 0 = most recent


_DIVISION_LINK_RE = re.compile(r"/individuals/divisions/(\d+)")


def parse_individuals_llistat(html: str) -> tuple[CompetitionIndexEntry, ...]:
    """Parse the /individuals/llistat page into an ordered list of competitions."""
    soup = BeautifulSoup(html, "lxml")
    out: list[CompetitionIndexEntry] = []
    seen: set[int] = set()

    for link in soup.find_all("a", class_="button"):
        href = link.get("href") or ""
        m = _DIVISION_LINK_RE.search(href)
        if not m:
            continue
        div_id = int(m.group(1))
        if div_id in seen:
            continue
        seen.add(div_id)
        name = link.get_text(strip=True)
        out.append(CompetitionIndexEntry(
            division_id=div_id,
            name=name,
            index=len(out),
        ))
    return tuple(out)


def fetch_individuals_llistat(*, force: bool = False) -> tuple[CompetitionIndexEntry, ...]:
    html = fetch(LLISTAT_URL, force=force)
    return parse_individuals_llistat(html)


@dataclass(frozen=True)
class OpenStructure:
    """Top-level layout of a single Open competition."""

    division_id: int
    name: str
    phase_id: int | None     # e.g. 443 for Sants — the "fases" id, if any
    phases: tuple[PhaseRef, ...]


@dataclass(frozen=True)
class GroupStanding:
    """One row in a group's standings table."""

    player_name: str
    club: str
    punts: int       # match points (2 per win)
    mitjana: float   # group-level average


@dataclass(frozen=True)
class ProvisionalQualifier:
    """A player we COMPUTE to be advancing from a group, based on current
    standings. This is an internal projection, not FCB-official data —
    the UI must visually distinguish it from data fetched from the FCB site.
    """

    group_label: str
    position_in_group: int   # 1 = group winner, 2 = runner-up, ...
    player_name: str
    club: str
    punts: int
    mitjana: float
    serie_major: int = 0     # max SM across the player's group matches


@dataclass(frozen=True)
class MatchResult:
    """One match within a group or KO round."""

    player_a: str
    player_b: str
    punts_a: int
    punts_b: int
    caramboles_a: int
    caramboles_b: int
    serie_major_a: int
    serie_major_b: int
    entrades: int | None
    arbitre: str | None
    # Free-text "Observacions" cell — typically used by FCB to record
    # tie-break results in KO matches when the scoreboard ends 1-1.
    observations: str | None = None

    @property
    def is_played(self) -> bool:
        return self.entrades is not None and self.entrades > 0


@dataclass(frozen=True)
class Group:
    """One group: standings + matches."""

    label: str                               # e.g. "Grup A"
    url: str
    venue: str | None = None
    standings: tuple[GroupStanding, ...] = ()
    matches: tuple[MatchResult, ...] = ()


@dataclass(frozen=True)
class AdvancingPlayer:
    """A player advancing INTO a KO round, with the seeding stats used to
    sort them. Surfaced on PhaseDetail.provisional_players so the UI can
    list expected participants even when we can't compute the bracket yet
    (e.g. unresolved ties in the previous round)."""

    name: str
    club: str = ""
    mitjana: float = 0.0
    serie_major: int = 0
    source: str = "winner"  # "winner" | "reservat" | "previous_winner"


@dataclass(frozen=True)
class PhaseDetail:
    """A phase with its resolved content."""

    ref: PhaseRef
    groups: tuple[Group, ...] = ()     # for kind="group"
    ko_matches: tuple[MatchResult, ...] = ()  # for kind="ko"
    provisional_qualifiers: tuple[ProvisionalQualifier, ...] = ()  # computed
    provisional_matches: tuple[MatchResult, ...] = ()  # computed KO pairings
    provisional_players: tuple[AdvancingPlayer, ...] = ()  # advancers list


@dataclass
class OpenLiveState:
    """Full snapshot of an ongoing Open."""

    structure: OpenStructure
    phases: list[PhaseDetail] = field(default_factory=list)
    # `{nom normalitzat → posició al Rànquing Català d'Opens}` (1 = millor), el
    # mateix seeding que ordena els grups no jugats. L'usa la classificació per
    # ordenar el bloc de jugadors encara vius (els 16 primers llocs del quadre).
    seeding: dict[str, int] = field(default_factory=dict)
    # Caps de sèrie (grup "JUGADORS RESERVATS"): entren directament al primer KO
    # sense jugar la prèvia. Es guarden a part dels grups regulars perquè no
    # comptin com a jugadors de la prèvia; ocupen els llocs 1..N de dalt del
    # quadre, ordenats pel `seeding`.
    reservats: tuple[GroupStanding, ...] = ()


# --------------------------------------------------------------------------- #
# URL helpers
# --------------------------------------------------------------------------- #


def division_url(division_id: int) -> str:
    return f"{BASE}/individuals/divisions/{division_id}"


def _abs(path: str) -> str:
    """Turn a relative FCB path (e.g. 'ca/individuals/...') into an absolute URL."""
    path = path.lstrip("/")
    if path.startswith("http"):
        return path
    if path.startswith("ca/"):
        return f"https://www.fcbillar.cat/{path}"
    return f"{BASE}/{path}"


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #


_PHASE_ID_RE = re.compile(r"/individuals/fases/\d+/(\d+)")
_KO_LABELS = {
    "SETZENS", "VUITENS", "QUARTS", "SEMIFINALS", "FINAL",
    "32ENS", "16ENS",
}


def parse_division_page(html: str, division_id: int) -> OpenStructure:
    """Parse the Open's landing page to extract name and the `fases` phase id."""
    soup = BeautifulSoup(html, "lxml")

    # The first h2 is the submenu label ("Competicions"). The real Open name
    # is the first h2 WITHOUT class attributes, inside the main content section.
    name = "UNKNOWN"
    for h2 in soup.find_all("h2"):
        if not h2.get("class"):
            text = h2.get_text(strip=True)
            if text:
                name = text
                break

    phase_id: int | None = None
    for link in soup.find_all("a"):
        href = link.get("href") or ""
        m = _PHASE_ID_RE.search(href)
        if m:
            phase_id = int(m.group(1))
            break

    return OpenStructure(
        division_id=division_id,
        name=name,
        phase_id=phase_id,
        phases=(),
    )


def parse_has_final_classification(html: str) -> bool:
    """Check whether the division's landing page exposes a 'Classificació final'
    link. The FCB adds this link only once the tournament has been completed
    and a final ranking has been published. Detecting its presence is the
    lightest possible signal for 'completed vs ongoing'."""
    return "/individuals/classificaciofinal/" in html


_FINAL_CLF_ID_RE = re.compile(r"/individuals/classificaciofinal/\d+/(\d+)")


def parse_final_classification_id(html: str) -> int | None:
    """Extract the FCB classification id from the division's landing
    page when a final ranking is published. Returns None if the link
    isn't there yet."""
    m = _FINAL_CLF_ID_RE.search(html)
    return int(m.group(1)) if m else None


def fetch_has_final_classification(division_id: int, *, force: bool = False) -> bool:
    html = fetch(division_url(division_id), force=force)
    return parse_has_final_classification(html)


def fetch_final_classification_id(
    division_id: int, *, force: bool = False
) -> int | None:
    html = fetch(division_url(division_id), force=force)
    return parse_final_classification_id(html)


def parse_fases_page(html: str) -> tuple[PhaseRef, ...]:
    """Parse the fases page to extract the ordered list of group and KO phases."""
    soup = BeautifulSoup(html, "lxml")
    phases: list[PhaseRef] = []

    for link in soup.find_all("a", class_="button"):
        href = link.get("href") or ""
        label = link.get_text(strip=True)
        if not href or not label:
            continue
        if "/individuals/grups/" in href:
            phases.append(PhaseRef(label=label, kind="group", url=_abs(href)))
        elif "/individuals/partideseliminatoria/" in href:
            phases.append(PhaseRef(label=label, kind="ko", url=_abs(href)))

    return tuple(phases)


_GROUP_LINK_RE = re.compile(
    r"/individuals/partidesgrups/\d+/\d+/\d+/(\d+)"
)
# El grup de caps de sèrie (jugadors reservats directament al primer KO) surt
# etiquetat "JUGADORS RESERVATS" o, en altres opens, només "RESERVATS". Capturem
# les dues formes i normalitzem l'etiqueta a "RESERVATS" (la resta del codi hi
# compta amb `label.upper() == "RESERVATS"`).
_GROUP_VENUE_RE = re.compile(
    r"(Grup [A-Z]+|(?:JUGADORS\s+)?RESERVATS)(?:\s*\|\s*Es juga a:\s*(.+))?", re.I
)


def parse_grups_page(html: str) -> tuple[Group, ...]:
    """Parse a /grups/{div}/{phase}/{subphase} page to extract group links + venues.
    Returns Group objects with url + label + venue only (standings/matches empty).
    """
    soup = BeautifulSoup(html, "lxml")
    groups: list[Group] = []

    for link in soup.find_all("a", class_="button"):
        href = link.get("href") or ""
        if not _GROUP_LINK_RE.search(href):
            continue
        text = link.get_text(strip=True)
        m = _GROUP_VENUE_RE.match(text)
        if not m:
            continue
        label = m.group(1)
        if "RESERVAT" in label.upper():
            label = "RESERVATS"  # normalitza "JUGADORS RESERVATS" → "RESERVATS"
        venue = m.group(2).strip() if m.group(2) else None
        groups.append(Group(label=label, url=_abs(href), venue=venue))

    return tuple(groups)


def parse_group_page(html: str, label: str, url: str, venue: str | None = None) -> Group:
    """Parse a /partidesgrups page: standings + match results."""
    soup = BeautifulSoup(html, "lxml")

    standings = _parse_group_standings(soup)
    matches = _parse_group_matches(soup)

    return Group(
        label=label,
        url=url,
        venue=venue,
        standings=standings,
        matches=matches,
    )


def _parse_group_standings(soup: BeautifulSoup) -> tuple[GroupStanding, ...]:
    """The standings are inside <div id="classificacio">, in 4 cells per row:
    jugador | club | punts | mitjana."""
    block = soup.find("div", id="classificacio")
    if block is None:
        return ()

    cells = [d.get_text(strip=True) for d in block.find_all("div")]
    # Skip the header row (JUGADOR, CLUB, PUNTS, MITJANA)
    rows: list[GroupStanding] = []
    # Find the start by locating "JUGADOR" then advance past header cells
    start = 0
    for i, c in enumerate(cells):
        if c.upper() == "JUGADOR":
            start = i + 4
            break

    for i in range(start, len(cells) - 3, 4):
        name = cells[i]
        club = cells[i + 1]
        punts_raw = cells[i + 2]
        mitjana_raw = cells[i + 3]
        if not name:
            continue
        try:
            punts = int(punts_raw) if punts_raw else 0
        except ValueError:
            punts = 0
        try:
            mitjana = float(mitjana_raw) if mitjana_raw else 0.0
        except ValueError:
            mitjana = 0.0
        rows.append(GroupStanding(
            player_name=name,
            club=club,
            punts=punts,
            mitjana=mitjana,
        ))
    return tuple(rows)


_HEADER_COLS = ("PUNTS", "SÈRIE MAJOR", "CARAMBOLES")


def _parse_group_matches(soup: BeautifulSoup) -> tuple[MatchResult, ...]:
    """Parse the match rows of a group/KO page.

    The FCB renders each match as a sequence of `<div class='row padded'>`
    blocks under a `<div class='row box black'>` header:

        [HEADER]    PUNTS  SÈRIE MAJOR  CARAMBOLES
        [PADDED 1]  PLAYER_A_NAME  PUNTS  SM  CARAMBOLES         (4 cells)
        [PADDED 2]  PLAYER_B_NAME  PUNTS  SM  CARAMBOLES         (4 cells)
        [PADDED 3]  Àrbitre:NAME   Entrades:N                    (2 cells)

    Older Opens shipped with a single fat `row padded` containing both
    players (≥ 8 cells); we still accept that shape as a fallback so we
    don't regress on cached pages.
    """
    matches: list[MatchResult] = []
    paddeds = soup.find_all("div", class_="row padded")
    cell_lists: list[list[str]] = [
        [d.get_text(strip=True) for d in p.find_all("div")] for p in paddeds
    ]

    i = 0
    while i < len(cell_lists):
        cells = cell_lists[i]

        # Single-block layout (legacy): all 8 player cells in one row.
        if len(cells) >= 8 and not _looks_like_meta_row(cells):
            try:
                name_a = cells[0]
                punts_a = int(cells[1]) if cells[1] else 0
                sm_a = int(cells[2]) if cells[2] else 0
                car_a = int(cells[3]) if cells[3] else 0
                name_b = cells[4]
                punts_b = int(cells[5]) if cells[5] else 0
                sm_b = int(cells[6]) if cells[6] else 0
                car_b = int(cells[7]) if cells[7] else 0
            except (ValueError, IndexError):
                i += 1
                continue
            arbitre, entrades, observations = _extract_meta(cells[8:])
            if name_a and name_b:
                matches.append(MatchResult(
                    player_a=name_a, player_b=name_b,
                    punts_a=punts_a, punts_b=punts_b,
                    caramboles_a=car_a, caramboles_b=car_b,
                    serie_major_a=sm_a, serie_major_b=sm_b,
                    entrades=entrades, arbitre=arbitre,
                    observations=observations,
                ))
            i += 1
            continue

        # Per-player layout (current): one row per player, 4 cells each.
        if len(cells) == 4 and not _looks_like_meta_row(cells) and i + 1 < len(cell_lists):
            next_cells = cell_lists[i + 1]
            if len(next_cells) == 4 and not _looks_like_meta_row(next_cells):
                try:
                    name_a = cells[0]
                    punts_a = int(cells[1]) if cells[1] else 0
                    sm_a = int(cells[2]) if cells[2] else 0
                    car_a = int(cells[3]) if cells[3] else 0
                    name_b = next_cells[0]
                    punts_b = int(next_cells[1]) if next_cells[1] else 0
                    sm_b = int(next_cells[2]) if next_cells[2] else 0
                    car_b = int(next_cells[3]) if next_cells[3] else 0
                except (ValueError, IndexError):
                    i += 1
                    continue
                # Optional third row with arbitre/entrades/observacions meta.
                arbitre: str | None = None
                entrades: int | None = None
                observations: str | None = None
                if i + 2 < len(cell_lists):
                    third = cell_lists[i + 2]
                    if _looks_like_meta_row(third):
                        arbitre, entrades, observations = _extract_meta(third)
                        i += 3
                    else:
                        i += 2
                else:
                    i += 2
                if name_a and name_b:
                    matches.append(MatchResult(
                        player_a=name_a, player_b=name_b,
                        punts_a=punts_a, punts_b=punts_b,
                        caramboles_a=car_a, caramboles_b=car_b,
                        serie_major_a=sm_a, serie_major_b=sm_b,
                        entrades=entrades, arbitre=arbitre,
                        observations=observations,
                    ))
                continue

        i += 1

    return tuple(matches)


def _looks_like_meta_row(cells: list[str]) -> bool:
    """A "meta" row is one that holds only Àrbitre / Entrades / Observacions
    labels — i.e. its FIRST cell is one of those labels. The legacy single-
    block layout has metadata cells appended after the 8 player cells; those
    rows shouldn't be classified as meta because cells[0] is a name."""
    if not cells:
        return False
    first = cells[0]
    return (
        "Àrbitre" in first
        or "Arbitre" in first
        or "Entrades" in first
        or "Observacions" in first
    )


def _extract_meta(cells: list[str]) -> tuple[str | None, int | None, str | None]:
    """Pull arbitre + entrades + observacions out of the metadata cells."""
    arbitre: str | None = None
    entrades: int | None = None
    observations: str | None = None
    for c in cells:
        if "Àrbitre" in c or "Arbitre" in c:
            if ":" in c:
                arbitre = c.split(":", 1)[1].strip() or None
        elif "Entrades" in c:
            if ":" in c:
                try:
                    entrades = int(c.split(":", 1)[1].strip())
                except ValueError:
                    entrades = None
        elif "Observacions" in c:
            if ":" in c:
                observations = c.split(":", 1)[1].strip() or None
    return arbitre, entrades, observations


_KO_LABEL_TO_MATCHES = {
    "TRENTADOSENS": 32,
    "SETZENS": 16,
    "VUITENS": 8,
    "QUARTS": 4,
    "SEMIFINALS": 2,
    "FINAL": 1,
}


def _is_round_fully_scheduled(phase: "PhaseDetail") -> bool:
    """A round is "fully scheduled" when FCB has published the expected
    number of pairings for its label (8 for vuitens, 4 for quarts, …).
    Used to decide whether we can safely chain projections to the next
    round: if prev's schedule is partial, we don't yet know all winners."""
    expected = _KO_LABEL_TO_MATCHES.get(phase.ref.label.upper())
    if expected is None:
        return True  # unknown label, assume complete
    return len(phase.ko_matches) >= expected


def _expected_ko_slots(ref: PhaseRef, played_count: int) -> int:
    """Expected number of player slots going INTO a KO round.

    Uses the round label when known (setzens → 32, vuitens → 16, ...).
    Falls back to 2× the number of matches already scraped.
    """
    n_matches = _KO_LABEL_TO_MATCHES.get(ref.label.upper())
    if n_matches is None:
        n_matches = played_count
    return n_matches * 2 if n_matches else 0


def _norm_name(name: str) -> str:
    """Collapse whitespace + upper-case, to match a player across phases
    regardless of incidental spacing/case differences in the source HTML."""
    return " ".join(name.split()).upper()


def _phase_player_names(phase: PhaseDetail) -> frozenset[str]:
    """Normalised set of every player named in a phase — group standings or
    KO pairings. Used to detect who advanced INTO the phase."""
    names: set[str] = set()
    for g in phase.groups:
        for s in g.standings:
            if s.player_name:
                names.add(_norm_name(s.player_name))
    for m in phase.ko_matches:
        for nm in (m.player_a, m.player_b):
            if nm:
                names.add(_norm_name(nm))
    for p in phase.provisional_players:
        if p.name:
            names.add(_norm_name(p.name))
    return frozenset(names)


def _seed_unplayed_groups(
    groups: tuple[Group, ...],
    earlier_names: frozenset[str],
    rank_by_name: dict[str, int] | None = None,
) -> tuple[Group, ...]:
    """Ordena els jugadors dels grups encara NO jugats segons l'ordre de sorteig.

    Mentre no s'hagi jugat cap partida d'un grup, l'ordre dels jugadors és
    informatiu (tots van 0-0), així que el fixem nosaltres:

      • Per RÀNQUING D'OPENS: `rank_by_name` mapeja nom normalitzat → posició al
        Rànquing Català d'Opens (1 = millor). Els jugadors sense rànquing
        conserven l'ordre relatiu de la federació, darrere dels classificats.
      • EXCEPCIÓ — advancers de fase anterior: els qui vénen d'una fase prèvia
        (p.ex. els qualificats de la pre-prèvia) són SEMPRE l'últim cap de sèrie
        del seu grup (el 3r en un grup de 3), passi el que passi al rànquing.

    Sense `rank_by_name` mantenim l'ordre de la federació i només recol·loquem
    els advancers al final (comportament anterior). Els grups ja començats es
    deixen tal qual: l'ordre ja reflecteix els resultats."""
    if not rank_by_name and not earlier_names:
        return groups
    big = 10**9

    def _rank(s: GroupStanding) -> int:
        return (rank_by_name or {}).get(_norm_name(s.player_name), big)

    out: list[Group] = []
    for g in groups:
        if not g.standings or any(m.is_played for m in g.matches):
            out.append(g)
            continue
        direct = [s for s in g.standings if _norm_name(s.player_name) not in earlier_names]
        adv = [s for s in g.standings if _norm_name(s.player_name) in earlier_names]
        if rank_by_name:
            # `sorted` és estable: els jugadors sense rànquing (clau `big`)
            # queden al final conservant l'ordre original de la federació.
            direct = sorted(direct, key=_rank)
            adv = sorted(adv, key=_rank)
        new_standings = tuple(direct + adv)
        if new_standings == g.standings:
            out.append(g)
            continue
        out.append(Group(
            label=g.label, url=g.url, venue=g.venue,
            standings=new_standings, matches=g.matches,
        ))
    return tuple(out)


def _group_sm_by_player(group: Group) -> dict[str, int]:
    """Max sèrie-major per player across a group's matches. The standings
    table doesn't carry SM, so we derive it from the match results."""
    sm: dict[str, int] = {}
    for m in group.matches:
        if m.player_a:
            sm[m.player_a] = max(sm.get(m.player_a, 0), m.serie_major_a)
        if m.player_b:
            sm[m.player_b] = max(sm.get(m.player_b, 0), m.serie_major_b)
    return sm


def _is_regular_group(label: str) -> bool:
    """A 'regular' group label is 'Grup X' where X is one or more uppercase
    letters. RESERVATS and lowercase ad-hoc groups (like 'Grup ww') are not
    counted for qualifier arithmetic."""
    import re as _re
    return bool(_re.fullmatch(r"Grup [A-Z]+", label.strip()))


def compute_provisional_qualifiers(
    current: PhaseDetail,
    next_phase_names: frozenset[str] | None = None,
) -> tuple[ProvisionalQualifier, ...]:
    """Compute who advances from a group phase.

    FCB opens rule (per the user): the 1st of EVERY group advances, and then
    — to fill the next round's groups — the BEST runners-up advance too, as
    many 2nds as there are free seats ("es classifiquen tots els primers i
    tants 2ns com calgui per omplir tots els grups").

    We don't guess the seat count: the federation publishes the NEXT round's
    draw with the actual advancing players, so the players of THIS phase that
    already appear in the next phase (`next_phase_names`) ARE the qualifiers.
    We therefore mark:
      • every group winner (a sure qualifier), plus
      • anyone the federation has already placed in the next round (the best
        2nds), tagged with their real standings position.
    When the next round isn't drawn yet (`next_phase_names` empty) we only
    surface the sure qualifiers (the group winners).

    Group order is the federation's official standings order (it already
    applies their tie-breaks and the no-show convention); we never re-sort.
    Returns an empty tuple if the phase has no groups or no standings.
    """
    out: list[ProvisionalQualifier] = []
    for group in current.groups:
        # Only regular groups (Grup A..P) feed the next phase. RESERVATS and
        # ad-hoc lowercase groups (like 'Grup ww') are excluded.
        if not _is_regular_group(group.label):
            continue
        if not group.standings:
            continue
        # Si encara no s'ha jugat cap partida del grup, no hi ha base per dir
        # qui passa (tothom va 0-0): no marquem cap classificat provisional.
        if not any(m.is_played for m in group.matches):
            continue
        sm = _group_sm_by_player(group)
        for idx, s in enumerate(group.standings):
            is_winner = idx == 0
            advanced = bool(next_phase_names) and (
                _norm_name(s.player_name) in next_phase_names
            )
            if not (is_winner or advanced):
                continue
            out.append(
                ProvisionalQualifier(
                    group_label=group.label,
                    position_in_group=idx + 1,
                    player_name=s.player_name,
                    club=s.club,
                    punts=s.punts,
                    mitjana=s.mitjana,
                    serie_major=sm.get(s.player_name, 0),
                )
            )
    return tuple(out)


@dataclass
class _PlayerStats:
    """Cumulative caramboles / entrades / best-serie across every played
    match a player has appeared in. Used to seed deeper KO rounds."""

    name: str
    caramboles: int = 0
    entrades: int = 0
    serie_major: int = 0  # max across the player's matches

    @property
    def mitjana(self) -> float:
        return (self.caramboles / self.entrades) if self.entrades else 0.0


def _accumulate_match(
    stats: dict[str, _PlayerStats],
    name: str,
    caramboles: int,
    entrades: int | None,
    serie_major: int,
) -> None:
    if not name:
        return
    s = stats.get(name) or _PlayerStats(name=name)
    s.caramboles += int(caramboles or 0)
    s.entrades += int(entrades or 0)
    s.serie_major = max(s.serie_major, int(serie_major or 0))
    stats[name] = s


def _collect_player_stats_in_phase(phase: "PhaseDetail") -> dict[str, _PlayerStats]:
    """Aggregate per-player stats from the played matches of a SINGLE phase.

    This is the seeding key for the next KO round: per FCB practice the
    qualifiers of a KO round are re-seeded by the mitjana they made IN THAT
    ROUND ONLY (not the cumulative one across the whole Open). Since a player
    plays exactly one match per KO round, this is effectively that match's
    caramboles/entrades and its sèrie major."""
    stats: dict[str, _PlayerStats] = {}
    for g in phase.groups:
        for m in g.matches:
            if not m.is_played:
                continue
            _accumulate_match(stats, m.player_a, m.caramboles_a, m.entrades, m.serie_major_a)
            _accumulate_match(stats, m.player_b, m.caramboles_b, m.entrades, m.serie_major_b)
    for m in phase.ko_matches:
        if not m.is_played:
            continue
        _accumulate_match(stats, m.player_a, m.caramboles_a, m.entrades, m.serie_major_a)
        _accumulate_match(stats, m.player_b, m.caramboles_b, m.entrades, m.serie_major_b)
    return stats


def _strip_diacritics(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def _winner_from_observations(
    obs: str | None, name_a: str, name_b: str
) -> str | None:
    """When a KO match ends 1-1, FCB writes the tie-break winner in the
    Observacions cell (e.g. 'GANA JIMÉNEZ POR 1-0…'). Heuristic: count how
    many tokens of each player's normalized name appear in the (also
    normalized) observations text. Whichever player has more matches wins.
    Returns None when the heuristic can't decide.
    """
    if not obs:
        return None
    norm = _strip_diacritics(obs.upper())

    def hits(name: str) -> int:
        tokens = [t for t in _strip_diacritics(name.upper()).split() if len(t) > 2]
        return sum(1 for t in tokens if t in norm)

    a_hits = hits(name_a)
    b_hits = hits(name_b)
    if a_hits > b_hits:
        return name_a
    if b_hits > a_hits:
        return name_b
    return None


def _ko_winner(m: "MatchResult") -> str | None:
    """Winner of a single KO match, or None if it can't be decided.

    FCB isn't consistent about the PUNTS column in KO rounds (sometimes a
    1-0 / 2-0 win marker, sometimes left at 0-0 with only the CARAMBOLES
    filled). We therefore decide in this order, each step strictly safer
    than the previous one:
      1. more PUNTS wins (when FCB fills the win marker);
      2. else more CARAMBOLES wins (a three-cushion match is won by
         scoring more caramboles, so this never picks the loser);
      3. else fall back to the Observacions tie-break text (1-1 endings).
    Returns None for an unplayed match or a genuine, unresolvable tie."""
    if not m.is_played:
        return None
    if m.punts_a != m.punts_b:
        return m.player_a if m.punts_a > m.punts_b else m.player_b
    if m.caramboles_a != m.caramboles_b:
        return m.player_a if m.caramboles_a > m.caramboles_b else m.player_b
    return _winner_from_observations(m.observations, m.player_a, m.player_b)


def _winners_of(matches: tuple["MatchResult", ...]) -> list[str] | None:
    """Return the list of winners of a played KO round, or None if any
    match is unplayed or has an unresolvable tie."""
    winners: list[str] = []
    for m in matches:
        if not m.is_played:
            return None
        w = _ko_winner(m)
        if w is None:
            return None
        winners.append(w)
    return winners


def compute_next_ko_round(
    phases: list["PhaseDetail"], idx: int
) -> tuple["MatchResult", ...]:
    """Provisional bracket for KO phase `phases[idx]` derived from the
    immediately preceding KO phase's winners.

    Re-seeding rule (per FCB practice): the qualifiers are sorted by the
    mitjana they made IN THE PREVIOUS ROUND DESC, then sèrie major DESC,
    then name. They then play 1st-vs-Nth, 2nd-vs-(N-1)th, … 1-vs-N pyramid.

    Returns () if the previous round can't be resolved (any match
    unplayed or tied) or if the index doesn't fit (no previous KO).
    """
    if idx <= 0 or idx >= len(phases):
        return ()
    prev = phases[idx - 1]
    if prev.ref.kind != "ko":
        return ()
    winners = _winners_of(prev.ko_matches)
    if winners is None or len(winners) < 2:
        return ()
    stats = _collect_player_stats_in_phase(prev)

    def sort_key(name: str) -> tuple[float, int, str]:
        s = stats.get(name) or _PlayerStats(name=name)
        return (-s.mitjana, -s.serie_major, name)

    seeded = sorted(winners, key=sort_key)
    return _pair_pyramid(seeded)


def compute_advancing_players(
    phases: list["PhaseDetail"],
    idx: int,
    last_group_idx: int,
) -> tuple[AdvancingPlayer, ...]:
    """Return the players advancing INTO `phases[idx]` (a KO round),
    sorted by mitjana DESC, sèrie major DESC, name.

    Used for display when we CAN'T form the pairings (e.g. the previous
    round has unresolved ties). When we CAN form pairings, this list is
    still populated so the UI can render both the bracket and the seeded
    participants list.

    Sources:
      • First KO after the last group phase → group winners + RESERVATS.
      • Any subsequent KO → winners of the previous KO (real or computed),
        seeded by the mitjana they made in that previous round only.
    """
    if idx <= last_group_idx or idx >= len(phases):
        return ()

    # First KO right after the group phase.
    if idx == last_group_idx + 1:
        last_group = phases[last_group_idx]
        out: list[AdvancingPlayer] = []
        # Winners come with their PRÈVIA group mitjana + sèrie major.
        for q in last_group.provisional_qualifiers:
            if q.position_in_group != 1:
                continue
            out.append(AdvancingPlayer(
                name=q.player_name,
                club=q.club,
                mitjana=q.mitjana,
                serie_major=q.serie_major,
                source="winner",
            ))
        # Reservats: pull their mitjana from the RESERVATS standings, and
        # their sèrie major from any RESERVATS-group matches if available.
        reservats_group = next(
            (g for g in last_group.groups if g.label.upper() == "RESERVATS"),
            None,
        )
        if reservats_group is not None:
            sm_by_player: dict[str, int] = {}
            for m in reservats_group.matches:
                if m.player_a:
                    sm_by_player[m.player_a] = max(
                        sm_by_player.get(m.player_a, 0), m.serie_major_a
                    )
                if m.player_b:
                    sm_by_player[m.player_b] = max(
                        sm_by_player.get(m.player_b, 0), m.serie_major_b
                    )
            for s in reservats_group.standings:
                out.append(AdvancingPlayer(
                    name=s.player_name,
                    club=s.club,
                    mitjana=s.mitjana,
                    serie_major=sm_by_player.get(s.player_name, 0),
                    source="reservat",
                ))
        out.sort(key=lambda p: (-p.mitjana, -p.serie_major, p.name))
        return tuple(out)

    # Subsequent KO: collect every known winner from the previous round,
    # even if that round is partial / incomplete. A "known winner" is one
    # whose match has been played and has a clear (or tie-break-resolved)
    # result. The third pass uses pool-size to decide whether to actually
    # form pairings or just expose the list of qualifiers.
    prev = phases[idx - 1]
    if prev.ref.kind != "ko":
        return ()
    source_matches = prev.ko_matches if prev.ko_matches else prev.provisional_matches
    winners: list[str] = []
    for m in source_matches:
        if not m.is_played:
            continue
        w = _ko_winner(m)
        if w is not None:
            winners.append(w)
    if not winners:
        return ()
    stats = _collect_player_stats_in_phase(prev)
    out = []
    for name in winners:
        s = stats.get(name)
        out.append(AdvancingPlayer(
            name=name,
            mitjana=s.mitjana if s else 0.0,
            serie_major=s.serie_major if s else 0,
            source="previous_winner",
        ))
    out.sort(key=lambda p: (-p.mitjana, -p.serie_major, p.name))
    return tuple(out)


def _seeded_first_ko_pool(
    last_group_phase: PhaseDetail,
    reservats: tuple[GroupStanding, ...],
    seeding: dict[str, int],
) -> tuple[AdvancingPlayer, ...]:
    """Pool del PRIMER KO en ordre de SEEDING (1..N), pensat per a l'aparellament
    piràmide 1-N, 2-(N-1), … de `_pair_pyramid`:

      • PRIMER els RESERVATS (caps de sèrie que no juguen la prèvia), pel
        RÀNQUING D'OPENS (`seeding`; 1 = millor, sense rànquing al final);
      • DESPRÉS els classificats de la prèvia, per ORDRE DE CLASSIFICACIÓ a la
        següent fase (1rs abans que 2ns; després punts/mitjana).

    Reservats al davant (millors seeds, llocs 1..16) i classificats al darrere
    (17..32): la piràmide empara així el millor reservat amb el pitjor classificat.
    Sense reservats publicats recau només en els classificats de la prèvia."""
    big = 10**9
    out: list[AdvancingPlayer] = []
    seen: set[str] = set()
    for s in sorted(
        reservats,
        key=lambda r: (seeding.get(_norm_name(r.player_name), big), r.player_name),
    ):
        k = _norm_name(s.player_name)
        if not s.player_name or k in seen:
            continue
        seen.add(k)
        out.append(AdvancingPlayer(
            name=s.player_name, club=s.club, mitjana=s.mitjana,
            serie_major=0, source="reservat",
        ))
    for q in sorted(
        last_group_phase.provisional_qualifiers,
        key=lambda q: (q.position_in_group, -q.punts, -q.mitjana, q.player_name),
    ):
        k = _norm_name(q.player_name)
        if not q.player_name or k in seen:
            continue
        seen.add(k)
        out.append(AdvancingPlayer(
            name=q.player_name, club=q.club, mitjana=q.mitjana,
            serie_major=q.serie_major, source="winner",
        ))
    return tuple(out)


def _pair_pyramid(names: list[str]) -> tuple[MatchResult, ...]:
    """Pyramid pairing: 1st vs Nth, 2nd vs (N-1)th, … Returns () if the
    pool has fewer than 2 names."""
    n = len(names)
    if n < 2:
        return ()
    pairs = n // 2
    return tuple(
        MatchResult(
            player_a=names[i],
            player_b=names[n - 1 - i],
            punts_a=0, punts_b=0,
            caramboles_a=0, caramboles_b=0,
            serie_major_a=0, serie_major_b=0,
            entrades=None, arbitre=None,
        )
        for i in range(pairs)
    )


def compute_provisional_ko_matches(
    last_group_phase: PhaseDetail,
) -> tuple[MatchResult, ...]:
    """Generate the provisional first-KO-round pairings from the last group
    phase's winners and the RESERVATS group.

    Unified pyramid pairing: pool group winners + reservats, sort by
    (mitjana DESC, sèrie major DESC, name ASC), then pair 1st-vs-Nth,
    2nd-vs-(N-1)th, …  Returns () if the pool has fewer than 2 players.
    """
    pool: list[tuple[float, int, str]] = []  # (mitjana, sm, name)
    for q in last_group_phase.provisional_qualifiers:
        if q.position_in_group != 1:
            continue
        pool.append((q.mitjana, q.serie_major, q.player_name))

    reservats_group = next(
        (g for g in last_group_phase.groups if g.label.upper() == "RESERVATS"),
        None,
    )
    if reservats_group is not None:
        sm_by_player: dict[str, int] = {}
        for m in reservats_group.matches:
            if m.player_a:
                sm_by_player[m.player_a] = max(
                    sm_by_player.get(m.player_a, 0), m.serie_major_a
                )
            if m.player_b:
                sm_by_player[m.player_b] = max(
                    sm_by_player.get(m.player_b, 0), m.serie_major_b
                )
        for s in reservats_group.standings:
            pool.append((
                s.mitjana,
                sm_by_player.get(s.player_name, 0),
                s.player_name,
            ))

    if len(pool) < 2:
        return ()
    pool.sort(key=lambda t: (-t[0], -t[1], t[2]))
    return _pair_pyramid([t[2] for t in pool])


# --------------------------------------------------------------------------- #
# Open classification (eliminated-players ranking with Art. XVII points)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class OpenClassificationRow:
    """One row of the Open's eliminated-players classification.

    `position` follows FCB convention: the deeper a player progressed, the
    lower their position number. Within an elimination round, players are
    ordered by (mitjana DESC, sèrie major DESC). Points come from Art. XVII
    via `reglament.puntuacio.points_for_position`.

    `is_provisional_position` flags rows whose position is doubly tentative
    — projected finalists for instance: the final hasn't been played yet,
    so we don't know who will be 1st vs 2nd. We display them tied at 1-2
    but mark them so the UI can render a "provisional" badge per row.
    """

    position: int
    player_name: str
    club: str
    round_label: str
    mitjana: float
    serie_major: int
    open_points: int
    is_provisional_position: bool = False


def _phase_player_stats(
    phase: PhaseDetail,
) -> dict[str, tuple[float, int, str]]:
    """Per-player (mitjana, sèrie major, club) for a single phase.

    For groups: mitjana from standings (caramboles/entrades summed over
    the round's matches), sèrie major = max across the player's group
    matches, club from standings.

    For KO rounds: mitjana = caramboles/entrades for the match, sèrie
    major = the player's SM in that match, club is unknown at this layer
    (resolved later via cross-phase lookup). Only PLAYED matches
    contribute; pending pairings don't count.
    """
    out: dict[str, tuple[float, int, str]] = {}
    if phase.ref.kind == "group":
        for g in phase.groups:
            sm_by_name: dict[str, int] = {}
            for m in g.matches:
                if m.player_a:
                    sm_by_name[m.player_a] = max(
                        sm_by_name.get(m.player_a, 0), m.serie_major_a
                    )
                if m.player_b:
                    sm_by_name[m.player_b] = max(
                        sm_by_name.get(m.player_b, 0), m.serie_major_b
                    )
            for s in g.standings:
                out[s.player_name] = (
                    s.mitjana,
                    sm_by_name.get(s.player_name, 0),
                    s.club,
                )
    else:  # ko
        for m in phase.ko_matches:
            if not m.is_played or not m.entrades:
                continue
            avg_a = m.caramboles_a / m.entrades
            avg_b = m.caramboles_b / m.entrades
            if m.player_a:
                out[m.player_a] = (avg_a, m.serie_major_a, "")
            if m.player_b:
                out[m.player_b] = (avg_b, m.serie_major_b, "")
    return out


def _phase_punts_lookup(phase: PhaseDetail) -> dict[str, int]:
    """Per-player match-points within a group phase (used for sorting
    eliminated group players)."""
    if phase.ref.kind != "group":
        return {}
    out: dict[str, int] = {}
    for g in phase.groups:
        for s in g.standings:
            out[s.player_name] = s.punts
    return out


def _phase_position_in_group_lookup(phase: PhaseDetail) -> dict[str, int]:
    """Per-player position WITHIN their FCB group standings (1-based).

    The standings table at FCB is already ordered by the round's tiebreak
    rules — including special-case handling for no-shows in 3-player
    groups (the no-show is placed 2nd, the other non-winner 3rd). Trust
    that order when ranking eliminated players: 2nds first, then 3rds,
    then 4ths, …
    """
    if phase.ref.kind != "group":
        return {}
    out: dict[str, int] = {}
    for g in phase.groups:
        for idx, s in enumerate(g.standings, start=1):
            out[s.player_name] = idx
    return out


def _phase_capacity(phase: PhaseDetail) -> int:
    """Number of player slots a phase has (or is expected to have).

    KO rounds use the round-label's expected match count when known,
    falling back to the actual number of pairings. Group phases sum
    standings sizes across all groups.
    """
    if phase.ref.kind == "ko":
        n = _KO_LABEL_TO_MATCHES.get(phase.ref.label.upper())
        if n is not None:
            return n * 2
        return len(phase.ko_matches) * 2
    return sum(len(g.standings) for g in phase.groups)


def _confirmed_advancers(
    phase: PhaseDetail,
    later_known: set[str],
) -> set[str]:
    """Players who DEFINITELY advanced past `phase`.

    For KO phases: winners of every played match (with tie-break-resolved
    ties counted as wins for the named player). For group phases:
    1st-of-each-group from `provisional_qualifiers`, plus anyone whose
    name shows up in a later phase's data (handles pre-prèvia → prèvia
    where multiple players advance per group)."""
    if phase.ref.kind == "ko":
        winners: set[str] = set()
        for m in phase.ko_matches:
            if not m.is_played:
                continue
            if m.punts_a > m.punts_b:
                winners.add(m.player_a)
            elif m.punts_b > m.punts_a:
                winners.add(m.player_b)
            else:
                tw = _winner_from_observations(
                    m.observations, m.player_a, m.player_b
                )
                if tw is not None:
                    winners.add(tw)
        return winners
    # group
    adv: set[str] = set()
    for q in phase.provisional_qualifiers:
        if q.position_in_group == 1:
            adv.add(q.player_name)
    # Cross-reference with later phases (catches multi-advance group phases).
    return adv | later_known


def _group_closed(group: Group) -> bool:
    """El grup té les places DECIDIDES: o bé totes les partides estan jugades,
    o bé —grup de 3 amb un jugador que NO es presenta— les partides jugades són
    totes del MATEIX parell (els 2 presents juguen dos cops i el grup es tanca amb
    2 partides, encara que el calendari en previa 3)."""
    played = [m for m in group.matches if m.is_played and m.player_a and m.player_b]
    total = len(group.matches)
    if total > 0 and len(played) == total:
        return True
    if len(played) >= 2 and len({frozenset((m.player_a, m.player_b)) for m in played}) == 1:
        return True
    return False


# Inici del tram de classificació de cada fase de GRUPS (esquema estàndard FCB):
# prèvia 33-64, pre-prèvia 65-94, pre-pre-prèvia 95+. Permet situar els eliminats
# d'una fase de grups encara que la ronda KO següent no estigui sortejada (i per
# tant no en sapiguem la capacitat per la via de _phase_capacity).
_GROUP_ROUND_BAND_START: dict[str, int] = {
    "PREVIA": 33,
    "PREVIES": 33,
    "PREPREVIA": 65,
    "PREPREPREVIA": 95,
}


def _group_band_start(label: str) -> int | None:
    key = "".join(
        c for c in unicodedata.normalize("NFD", label.upper())
        if unicodedata.category(c) != "Mn"
    ).replace("-", "").replace(" ", "")
    return _GROUP_ROUND_BAND_START.get(key)


def compute_open_classification(
    state: "OpenLiveState",
) -> tuple[OpenClassificationRow, ...]:
    """Build the eliminated-players classification of an in-progress Open.

    Always provisional — FCB publishes the canonical PDF only when the
    Open has finished. While running, we identify confirmed advancers
    (KO match winners + group 1st / cross-referenced) and confirmed
    eliminated (everyone else in that phase whose name doesn't appear in
    any later phase). Players in still-pending matches contribute to
    neither set yet.

    Position numbering is structural: each round occupies a fixed band
    (final loser = 2nd, semis = 3-4, quarts = 5-8, vuitens = 9-16, …),
    which means a partial round can be "closed" for its known losers
    even if some matches are still pending.

    Sort within a band:
      • Group phases (PRÈVIA and earlier): (punts DESC, mitjana DESC,
        sèrie major DESC, name).
      • KO phases: (mitjana DESC, sèrie major DESC, name) — only one
        match per player, so punts is always 0.

    Club: groups carry it explicitly; KO rows resolve it from the most
    recent group phase where the player appears. Points come from Art.
    XVII via `points_for_position`.
    """
    from ..reglament.puntuacio import points_for_position

    phases = state.phases
    if not phases:
        return ()

    phase_stats: list[dict[str, tuple[float, int, str]]] = [
        _phase_player_stats(p) for p in phases
    ]

    # Cross-phase club lookup: for KO players we don't have a club in the
    # match data, so reach back to the deepest group phase where the
    # player has standings.
    club_by_player: dict[str, str] = {}
    for phase in phases:
        if phase.ref.kind != "group":
            continue
        for g in phase.groups:
            for s in g.standings:
                if s.club:
                    club_by_player[s.player_name] = s.club

    # Pre-compute eliminated + sorted name list per phase. Sort key differs
    # for KO (mitjana/SM only — single match) vs group (punts first).
    eliminated_per_phase: list[list[str]] = []
    noshow_names: set[str] = set()  # no-presentats: punts d'open = 0 (de moment)
    for i, phase in enumerate(phases):
        later_known: set[str] = set()
        for j in range(i + 1, len(phases)):
            later_known.update(phase_stats[j].keys())
        advancers = _confirmed_advancers(phase, later_known)
        if phase.ref.kind == "group":
            # NOMÉS eliminats CONFIRMATS: cal que el grup estigui TANCAT (places
            # decidides). Així no llistem jugadors de grups encara pendents.
            closed_players: set[str] = set()
            played_count: dict[str, int] = {}
            for g in phase.groups:
                if _group_closed(g):
                    closed_players.update(s.player_name for s in g.standings)
                for m in g.matches:
                    if not m.is_played:
                        continue
                    for nm in (m.player_a, m.player_b):
                        if nm:
                            played_count[nm] = played_count.get(nm, 0) + 1
            # No-presentat: jugador d'un grup tancat que no ha jugat cap partida.
            def _noshow(n: str) -> bool:
                return n in closed_players and played_count.get(n, 0) == 0
            position_lookup = _phase_position_in_group_lookup(phase)
            if later_known:
                # La ronda següent ja està sortejada → els avançats són definitius.
                # Eliminats = jugadors de grups tancats que no avancen ni hi apareixen.
                elim = [
                    n for n in phase_stats[i]
                    if n in closed_players and n not in advancers and n not in later_known
                ]
            else:
                # Fase FRONTERA (KO encara no sortejat): TOTS els no-avançats d'un
                # grup TANCAT estan eliminats. A la darrera fase de grups només
                # avancen els 1rs (els altres llocs del KO els ocupen reservats), de
                # manera que 2ns i 3rs queden tots fora. `advancers` aquí són els 1rs.
                elim = [
                    n for n in phase_stats[i]
                    if n in closed_players and n not in advancers
                ]
            punts_lookup = _phase_punts_lookup(phase)
            # Ordena: els NO-PRESENTATS van SEMPRE al final del seu tram (0 punts,
            # mantenen plaça però darrers); després per posició al grup, punts i
            # mitjana (criteri de l'usuari).
            elim.sort(
                key=lambda n: (
                    1 if _noshow(n) else 0,
                    position_lookup.get(n, 999),
                    -punts_lookup.get(n, 0),
                    -phase_stats[i][n][0],
                    -phase_stats[i][n][1],
                    n,
                )
            )
            noshow_names.update(n for n in elim if _noshow(n))
        else:
            elim = [
                n for n in phase_stats[i]
                if n not in advancers and n not in later_known
            ]
            elim.sort(
                key=lambda n: (
                    -phase_stats[i][n][0],
                    -phase_stats[i][n][1],
                    n,
                )
            )
        eliminated_per_phase.append(elim)

    rows: list[OpenClassificationRow] = []

    # KO bands keep their structural depth-based positions: a final loser
    # is always 2nd, semis losers 3-4, quarts 5-8, vuitens 9-16, setzens
    # 17-32, regardless of how many group phases came before.
    for i, phase in enumerate(phases):
        if phase.ref.kind != "ko":
            continue
        n_above = (
            _phase_capacity(phases[i + 1]) if i + 1 < len(phases) else 1
        )
        for rank, name in enumerate(eliminated_per_phase[i], start=1):
            mg, sm, club = phase_stats[i][name]
            if not club:
                club = club_by_player.get(name, "")
            position = n_above + rank
            rows.append(
                OpenClassificationRow(
                    position=position,
                    player_name=name,
                    club=club,
                    round_label=phase.ref.label,
                    mitjana=mg,
                    serie_major=sm,
                    open_points=points_for_position(position),
                )
            )

    # Trams de GRUP, sota el KO. El primer lloc de cada tram = posicions ja ocupades
    # (KO + trams de grup més profunds) + 1. S'ADAPTA A LA MODALITAT: el KO de 3
    # bandes entra a SETZENS (32 jugadors) i el de QUADRE a VUITENS (16), de manera
    # que la prèvia comença a 33 o a 17 respectivament.
    group_idxs = [k for k, p in enumerate(phases) if p.ref.kind == "group"]
    ko_idxs = [k for k, p in enumerate(phases) if p.ref.kind == "ko"]
    deepest_group = max(group_idxs) if group_idxs else None
    if ko_idxs:
        ko_size = _phase_capacity(phases[min(ko_idxs)])   # capacitat del primer KO
    elif deepest_group is not None:
        # Frontera (KO no sortejat): 1rs de cada grup + igual nombre de reservats.
        ko_size = 2 * len(phases[deepest_group].groups)
    else:
        ko_size = 1
    running = ko_size  # llocs 1..ko_size ocupats pel quadre KO
    for i in range(len(phases) - 1, -1, -1):
        phase = phases[i]
        if phase.ref.kind != "group":
            continue
        band = running + 1
        # Els classificats d'una fase TANCADA (tots els grups decidits) són
        # DEFINITIUS; si encara hi ha grups oberts, la posició és provisional.
        phase_closed = bool(phase.groups) and all(_group_closed(g) for g in phase.groups)
        pos = band
        for name in eliminated_per_phase[i]:
            mg, sm, club = phase_stats[i][name]
            if not club:
                club = club_by_player.get(name, "")
            # No-presentat: 0 punts (de moment; el reglament en preveu possible -20).
            pts = 0 if name in noshow_names else points_for_position(pos)
            rows.append(
                OpenClassificationRow(
                    position=pos,
                    player_name=name,
                    club=club,
                    round_label=phase.ref.label,
                    mitjana=mg,
                    serie_major=sm,
                    open_points=pts,
                    is_provisional_position=not phase_closed,
                )
            )
            pos += 1
        # Avança pel TOTAL d'eliminats de la fase (no només els confirmats fins ara),
        # perquè el tram de la fase superior quedi ben col·locat. Avançats: a la
        # darrera fase de grups només els 1rs (els altres llocs del KO són reservats);
        # a les fases anteriors, els que apareixen en fases posteriors.
        if i == deepest_group:
            advancers_total = len(phase.groups)
        else:
            later: set[str] = set()
            for j in range(i + 1, len(phases)):
                later |= set(phase_stats[j].keys())
            advancers_total = len(set(phase_stats[i].keys()) & later)
        elim_total = max(len(phase_stats[i]) - advancers_total, len(eliminated_per_phase[i]))
        running = band - 1 + elim_total

    # Final-phase head: position 1 (and 2) get filled by, in priority order:
    #   1. Champion if the final has been played.
    #   2. Confirmed semi-winners going to the final (1 or 2 of them) marked
    #      as provisional. This covers the in-progress case where the final
    #      pairing isn't fully known yet but at least one finalist is.
    last = phases[-1]
    if last.ref.kind == "ko" and last.ref.label.upper() == "FINAL":
        if last.ko_matches and last.ko_matches[0].is_played:
            fm = last.ko_matches[0]
            winner_name = _ko_winner(fm)
            if winner_name:
                if fm.entrades:
                    won_by_a = winner_name == fm.player_a
                    car = fm.caramboles_a if won_by_a else fm.caramboles_b
                    sm_w = fm.serie_major_a if won_by_a else fm.serie_major_b
                    mg_w = car / fm.entrades
                else:
                    mg_w = 0.0
                    sm_w = 0
                rows.append(
                    OpenClassificationRow(
                        position=1,
                        player_name=winner_name,
                        club=club_by_player.get(winner_name, ""),
                        round_label="CAMPIÓ",
                        mitjana=mg_w,
                        serie_major=sm_w,
                        open_points=points_for_position(1),
                    )
                )

    # --- Jugadors encara VIUS (capçalera provisional del quadre) --------------
    # Tots els qui han entrat al quadre KO i encara NO han estat eliminats ocupen,
    # PROVISIONALMENT, els llocs de dalt (1..K) fins que la federació publiqui la
    # classificació definitiva. Per petició de l'usuari l'ordre del bloc és:
    #   • PRIMER els RESERVATS (caps de sèrie que no juguen la prèvia), pel
    #     RÀNQUING INICIAL d'opens → ocupen els 16 primers llocs;
    #   • DESPRÉS els classificats de la prèvia, per l'ORDRE DE CLASSIFICACIÓ a la
    #     següent fase (1rs abans que 2ns; després punts/mitjana) → llocs 17..32.
    # Substitueix l'antiga capçalera que només col·locava els finalistes coneguts.
    if ko_idxs:
        rows.extend(
            _alive_classification_rows(
                phases=phases,
                group_idxs=group_idxs,
                phase_stats=phase_stats,
                club_by_player=club_by_player,
                ko_size=ko_size,
                placed_names={_norm_name(r.player_name) for r in rows},
                used_positions={r.position for r in rows},
                seeding=getattr(state, "seeding", None) or {},
                reservats=getattr(state, "reservats", ()) or (),
            )
        )

    rows.sort(key=lambda r: r.position)
    return tuple(rows)


def _alive_classification_rows(
    *,
    phases: list[PhaseDetail],
    group_idxs: list[int],
    phase_stats: list[dict[str, tuple[float, int, str]]],
    club_by_player: dict[str, str],
    ko_size: int,
    placed_names: set[str],
    used_positions: set[int],
    seeding: dict[str, int],
    reservats: tuple[GroupStanding, ...] = (),
) -> list[OpenClassificationRow]:
    """Files provisionals dels jugadors encara VIUS (vegeu el bloc que crida).

    Viu = ha entrat al quadre KO (cap de sèrie RESERVAT, classificat d'una fase de
    grups, o present en una ronda KO) i encara no té lloc assignat (ni eliminat ni
    campió). Els RESERVATS van primer, ordenats pel `seeding` (rànquing d'opens);
    després els classificats de la prèvia, per l'ordre de classificació a la
    següent fase. Tot marcat `is_provisional_position`."""
    from ..reglament.puntuacio import points_for_position

    BIG = 10**9

    # Caps de sèrie reservats: nom + club (no juguen la prèvia → mitjana/SM 0).
    reservat_info: dict[str, tuple[str, str]] = {}
    for s in reservats:
        if s.player_name:
            reservat_info.setdefault(_norm_name(s.player_name), (s.player_name, s.club))
    reservat_norms = set(reservat_info)

    # Estadístiques (mitjana, SM, club) de la fase més profunda on apareix cadascú.
    latest_stats: dict[str, tuple[float, int, str]] = {}
    for ps in phase_stats:
        for nm, val in ps.items():
            latest_stats[_norm_name(nm)] = val
    club_by_norm = {_norm_name(k): v for k, v in club_by_player.items()}

    # Ordre de classificació a la següent fase, de la fase de grups més profunda
    # que en tingui: clau menor = millor (1rs abans que 2ns; després punts/mitjana).
    qual_key: dict[str, tuple[int, int, float]] = {}
    for gi in reversed(group_idxs):
        if phases[gi].provisional_qualifiers:
            for q in phases[gi].provisional_qualifiers:
                qual_key[_norm_name(q.player_name)] = (
                    q.position_in_group, -q.punts, -q.mitjana
                )
            break

    # Pool del quadre KO: reservats + classificats de grups + noms a una ronda KO.
    alive: dict[str, str] = {}  # norm → nom a mostrar
    for norm, (name, _club) in reservat_info.items():
        alive[norm] = name
    for gi in group_idxs:
        for q in phases[gi].provisional_qualifiers:
            if q.player_name:
                alive.setdefault(_norm_name(q.player_name), q.player_name)
    for phase in phases:
        if phase.ref.kind != "ko":
            continue
        for m in (*phase.ko_matches, *phase.provisional_matches):
            for nm in (m.player_a, m.player_b):
                if nm:
                    alive.setdefault(_norm_name(nm), nm)
        for p in phase.provisional_players:
            if p.name:
                alive.setdefault(_norm_name(p.name), p.name)
    # Treu els que ja tenen lloc (eliminats confirmats o campió).
    alive = {k: v for k, v in alive.items() if k not in placed_names}
    if not alive:
        return []

    def _qkey(norm: str) -> tuple[int, int, float, str]:
        pg, npunts, nmitj = qual_key.get(norm, (9, 0, 0.0))
        return (pg, npunts, nmitj, alive[norm])

    # RESERVATS primer (per seeding); després la resta (per ordre de classificació).
    res_alive = sorted(
        (k for k in alive if k in reservat_norms),
        key=lambda k: (seeding.get(k, BIG), alive[k]),
    )
    oth_alive = sorted((k for k in alive if k not in reservat_norms), key=_qkey)
    ordered = res_alive + oth_alive

    free = [p for p in range(1, ko_size + 1) if p not in used_positions]
    out: list[OpenClassificationRow] = []
    for norm, pos in zip(ordered, free):
        name = alive[norm]
        if norm in reservat_info:
            mg, sm, club = 0.0, 0, reservat_info[norm][1]
        else:
            mg, sm, club = latest_stats.get(norm, (0.0, 0, ""))
            if not club:
                club = club_by_norm.get(norm, "")
        out.append(
            OpenClassificationRow(
                position=pos,
                player_name=name,
                club=club,
                round_label="EN JOC",
                mitjana=mg,
                serie_major=sm,
                open_points=points_for_position(pos),
                is_provisional_position=True,
            )
        )
    return out


_PDF_MATCH_LINE_A = re.compile(
    r"^Billar\s+(\d+)\s+#+\s+(\S+)\s+(.+?)\s*$",
    re.IGNORECASE,
)
_PDF_MATCH_LINE_B = re.compile(
    r"^(\d{1,2}:\d{2})\s*h\.?\s+#+\s+(\S+)\s+(.+?)\s*$",
    re.IGNORECASE,
)


def parse_ko_pdf(pdf_bytes: bytes) -> tuple[MatchResult, ...]:
    """Parse an Opens KO-round PDF (SETZENS, VUITENS, …) into matches.

    FCB publishes the bracket as a PDF some time before match day. Each
    match is rendered as two consecutive lines:

        Billar 8 ##### 16 GARCIA ALARCÓN, RICARDO
        10:00 h. ##### 1-P MAS CANADELL, JOSEP Mª

    where the seed on the first line is the reservat number and the seed on
    the second is the prèvia classification position suffixed with 'P'. We
    don't need the seeds downstream — just the two player names.
    """
    import io

    import pdfplumber

    matches: list[MatchResult] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            raw = page.extract_text() or ""
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            i = 0
            while i < len(lines) - 1:
                m_a = _PDF_MATCH_LINE_A.match(lines[i])
                m_b = _PDF_MATCH_LINE_B.match(lines[i + 1]) if m_a else None
                if m_a and m_b:
                    # Strip trailing commas/whitespace from names; names come
                    # as "SURNAME, GIVEN" and the regex captures the trailing
                    # whitespace up to end-of-line cleanly.
                    name_a = m_a.group(3).strip().rstrip(",").strip()
                    name_b = m_b.group(3).strip().rstrip(",").strip()
                    matches.append(MatchResult(
                        player_a=name_a,
                        player_b=name_b,
                        punts_a=0,
                        punts_b=0,
                        caramboles_a=0,
                        caramboles_b=0,
                        serie_major_a=0,
                        serie_major_b=0,
                        entrades=None,
                        arbitre=None,
                    ))
                    i += 2
                else:
                    i += 1
    return tuple(matches)


# Terms that signal a NARROWER round label and must be absent from the title
# for a looser round to match. Example: "SETZENS DE FINAL" contains "FINAL",
# so when we're looking for the final round we must exclude setzens/vuitens/etc.
_ROUND_EXCLUSIONS: dict[str, tuple[str, ...]] = {
    "FINAL": ("SETZENS", "VUITENS", "QUARTS", "SEMIFINALS", "DE FINAL"),
    "SEMIFINALS": ("SETZENS", "VUITENS", "QUARTS"),
    "QUARTS": ("SETZENS", "VUITENS"),
    "VUITENS": ("SETZENS",),
}


def _find_ko_doc_for_round(
    docs: Iterable[DocEntry],
    aliases: set[str],
    round_label: str,
) -> int | None:
    """Return the doc id of a published KO-round PDF for this Open.

    Title conventions seen on FCB:
        "SETZENS DE FINAL <OPEN NAME>"
        "VUITENS DE FINAL <OPEN NAME>"
        "QUARTS DE FINAL <OPEN NAME>"
        "SEMIFINALS <OPEN NAME>"
        "FINAL <OPEN NAME>"

    Because narrower round labels include the token "FINAL", matching must
    exclude narrower labels when looking for a looser one.
    """
    label_upper = round_label.upper()
    exclusions = _ROUND_EXCLUSIONS.get(label_upper, ())
    alias_upper = {a.upper() for a in aliases if a}
    for d in docs:
        title_upper = d.title.upper()
        if label_upper not in title_upper:
            continue
        if any(excl in title_upper for excl in exclusions):
            continue
        if not any(alias in title_upper for alias in alias_upper):
            continue
        return d.doc_id
    return None


def _dedupe_ko_matches(matches: tuple[MatchResult, ...]) -> tuple[MatchResult, ...]:
    """Drop duplicate KO pairings. FCB occasionally enters the same match
    twice (mirrored A/B, e.g. once per arbitre), which would otherwise yield
    duplicate winners and a garbled next round. In a single-elimination round
    each player plays at most once, so any repeated unordered {A, B} pairing is
    a duplicate: keep the first occurrence, upgrading to a played row if the
    first copy was still unplayed."""
    best: dict[frozenset[str], MatchResult] = {}
    order: list[frozenset[str]] = []
    for m in matches:
        if not m.player_a or not m.player_b:
            continue
        key = frozenset({_norm_name(m.player_a), _norm_name(m.player_b)})
        prev = best.get(key)
        if prev is None:
            best[key] = m
            order.append(key)
        elif m.is_played and not prev.is_played:
            best[key] = m
    return tuple(best[k] for k in order)


def parse_ko_page(html: str) -> tuple[MatchResult, ...]:
    """Parse a KO round page. Same match-row structure as groups, without a
    group-level standings block. Returns () if 'No hi ha registres disponibles'."""
    if "No hi ha registres disponibles" in html:
        return ()
    soup = BeautifulSoup(html, "lxml")
    return _dedupe_ko_matches(_parse_group_matches(soup))


def _attach_ko_provisional_players(
    phases: list[PhaseDetail],
    reservats: tuple[GroupStanding, ...],
    seeding: dict[str, int],
) -> list[PhaseDetail]:
    """Deriva els quadres KO PROVISIONALS quan la FCB encara no els ha penjat —
    inclosa la publicació PARCIAL (uns emparellaments llistats, d'altres no). Per
    cada ronda KO:
      • calcula el pool d'avançats esperat (guanyadors de grup + RESERVATS al primer
        KO; guanyadors de la ronda anterior després);
      • treu els ja emparellats a `ko_matches` oficials;
      • empara en piràmide els restants (1r-vs-Nè per sembra mitjana/SM).
    `provisional_matches` només conté els emparellaments que falten, perquè la UI els
    pinti al costat dels oficials amb marca "calculat". Idempotent: recalculable amb
    un `reservats` ampliat (p.ex. completant els que la FCB encara no ha llistat)."""
    final = list(phases)
    last_group_idx = next(
        (i for i in range(len(final) - 1, -1, -1) if final[i].ref.kind == "group"),
        None,
    )
    if last_group_idx is None:
        return final
    for i in range(last_group_idx + 1, len(final)):
        d = final[i]
        if d.ref.kind != "ko":
            continue

        # Primer KO: pool sembrat reservats(rànquing) + classificats(classif.),
        # perquè la piràmide doni l'aparellament 1-N, 2-(N-1), … demanat (caps
        # de sèrie contra els pitjors classificats). La resta de rondes: guanyadors
        # de la ronda anterior.
        if i == last_group_idx + 1:
            advancing = _seeded_first_ko_pool(final[last_group_idx], reservats, seeding)
        else:
            advancing = compute_advancing_players(final, i, last_group_idx)
        paired: set[str] = set()
        for m in d.ko_matches:
            if m.player_a:
                paired.add(m.player_a)
            if m.player_b:
                paired.add(m.player_b)

        # Only form pairings when the full expected pool is known;
        # for partial pools we keep `advancing` (so the UI shows the
        # already-qualified players) but skip pairing.
        expected_n_matches = _KO_LABEL_TO_MATCHES.get(d.ref.label.upper())
        expected_pool_size = expected_n_matches * 2 if expected_n_matches else None
        pool_complete = (
            expected_pool_size is None or len(advancing) >= expected_pool_size
        )
        if advancing and pool_complete:
            leftover_names = [p.name for p in advancing if p.name not in paired]
            prov = _pair_pyramid(leftover_names)
        else:
            prov = ()

        if prov or advancing:
            final[i] = PhaseDetail(
                ref=d.ref,
                groups=d.groups,
                ko_matches=d.ko_matches,
                provisional_qualifiers=d.provisional_qualifiers,
                provisional_matches=prov,
                provisional_players=advancing,
            )
    return final


def augment_state_reservats(
    state: "OpenLiveState", extra: list[GroupStanding]
) -> None:
    """Afegeix caps de sèrie RESERVATS extres a l'estat en viu i recalcula el pool
    del primer KO, in-place. Pensat per COMPLETAR els reservats que la federació
    encara no ha llistat al grup "RESERVATS" en viu (sovint en falta algun fins que
    penja el sorteig del primer KO) a partir de la projecció (RÀNQUING INICIAL).

    No afegeix res si `extra` és buit. Els noms extres es normalitzen amb l'espai
    després de la coma perquè casin amb el `seeding` (rànquing d'Opens) i el reservat
    quedi ben ordenat entre els altres caps de sèrie."""
    if not extra:
        return
    state.reservats = tuple(state.reservats) + tuple(extra)
    state.phases = _attach_ko_provisional_players(
        state.phases, state.reservats, state.seeding or {}
    )


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #


def fetch_live_state(
    division_id: int,
    *,
    force: bool = False,
    rank_by_name: dict[str, int] | None = None,
) -> OpenLiveState:
    """Fetch the complete live state of an ongoing Open.

    Args:
        division_id: FCB division id, e.g. 206 for Sants.
        force: bypass the HTTP cache for every page.
        rank_by_name: optional `{normalised name → Opens-ranking position}`
            (1 = top). When provided, the players of every NOT-yet-played group
            are ordered by that ranking (advancers from a previous phase always
            last; see `_seed_unplayed_groups`). When omitted, the federation's
            draw order is kept and only advancers are pushed to the end.

    Returns:
        OpenLiveState with phases fully populated. KO rounds that haven't
        been played yet will have empty ko_matches.
    """
    # 1) Landing page → name + phase_id
    div_html = fetch(division_url(division_id), force=force)
    structure = parse_division_page(div_html, division_id)
    if structure.phase_id is None:
        return OpenLiveState(structure=structure, phases=[])

    # 2) Fases page → list of phase refs
    fases_url = f"{BASE}/individuals/fases/{division_id}/{structure.phase_id}"
    fases_html = fetch(fases_url, force=force)
    phase_refs = parse_fases_page(fases_html)
    structure_full = OpenStructure(
        division_id=division_id,
        name=structure.name,
        phase_id=structure.phase_id,
        phases=phase_refs,
    )

    # 3) For each phase ref, fetch details. Use a short TTL for the match-
    #    level pages (group standings, KO pairings) since those change as
    #    matches are played. The phase list itself is stable during a day.
    # KO rounds have TWO potential sources: the /partideseliminatoria HTML
    # (filled in once matches are PLAYED) and a published PDF bracket
    # (available days before match day). We prefer HTML; fall back to PDF.
    ko_docs_cache: tuple[DocEntry, ...] | None = None
    details: list[PhaseDetail] = []
    reservats_standings: tuple[GroupStanding, ...] = ()
    for ref in phase_refs:
        if ref.kind == "group":
            grups_html = fetch(ref.url, force=force)
            group_stubs = parse_grups_page(grups_html)
            groups: list[Group] = []
            for stub in group_stubs:
                group_html = fetch(stub.url, force=force, cache_ttl_s=LIVE_TTL_S)
                group = parse_group_page(
                    group_html, label=stub.label, url=stub.url, venue=stub.venue
                )
                if group.label.upper() == "RESERVATS":
                    # Caps de sèrie: es guarden a part. NO entren als grups
                    # regulars perquè no contin com a jugadors de la prèvia
                    # (afectaria el càlcul de trams d'eliminats de la classif.).
                    if group.standings:
                        reservats_standings = group.standings
                    continue
                groups.append(group)
            details.append(PhaseDetail(ref=ref, groups=tuple(groups)))
        else:  # ko
            ko_html = fetch(ref.url, force=force, cache_ttl_s=LIVE_TTL_S)
            matches = parse_ko_page(ko_html)
            if not matches:
                # Try to find and parse a published PDF bracket for this round.
                # Docs list is fetched once and reused across all KO rounds.
                if ko_docs_cache is None:
                    try:
                        ko_docs_cache = fetch_opens_docs(force=force)
                    except Exception:  # noqa: BLE001
                        ko_docs_cache = ()
                aliases = set(OPEN_TITLE_ALIASES.get(division_id, ()))
                # Also accept tokens from the division's own name (sans
                # generic prefixes like 'OPEN TRES BANDES').
                cleaned = (
                    structure.name.upper()
                    .replace("OPEN", "")
                    .replace("TRES BANDES", "")
                    .replace("FEMENI", "")
                    .strip()
                )
                if cleaned:
                    aliases.add(cleaned)
                doc_id = _find_ko_doc_for_round(ko_docs_cache, aliases, ref.label)
                if doc_id is not None:
                    try:
                        pdf_bytes, _ = fetch_doc_pdf(doc_id, force=force)
                        matches = parse_ko_pdf(pdf_bytes)
                    except Exception:  # noqa: BLE001
                        matches = ()
            details.append(PhaseDetail(ref=ref, ko_matches=matches))

    # 4) Second pass: compute provisional qualifiers per group phase.
    #    Rule (per the user): the 1st of every regular group advances, plus
    #    the best runners-up needed to fill the next round's groups. We read
    #    that seat count straight from the next round's published draw — the
    #    players of this phase that already appear in the next phase ARE the
    #    advancers (group winners + best 2nds). When the next round isn't
    #    drawn yet we only surface the sure qualifiers (the group winners).
    enriched: list[PhaseDetail] = []
    earlier_names: frozenset[str] = frozenset()  # jugadors de fases anteriors
    for i, d in enumerate(details):
        if d.ref.kind != "group":
            enriched.append(d)
            earlier_names = earlier_names | _phase_player_names(d)
            continue
        # The next round's published draw tells us who advanced from this
        # phase: all group winners + the best 2nds the federation placed
        # there to fill the next round's groups.
        next_names = (
            _phase_player_names(details[i + 1]) if i + 1 < len(details) else None
        )
        qualifiers = compute_provisional_qualifiers(d, next_names)
        # Ordre de sorteig dels grups encara no jugats: per rànquing d'Opens
        # (si el tenim) i amb els advancers de fase anterior sempre al final (3r
        # en grups de 3). No afecta els classificats: els grups no jugats no en tenen.
        groups = _seed_unplayed_groups(d.groups, earlier_names, rank_by_name)
        enriched.append(
            PhaseDetail(
                ref=d.ref,
                groups=groups,
                ko_matches=d.ko_matches,
                provisional_qualifiers=qualifiers,
            )
        )
        earlier_names = earlier_names | _phase_player_names(d)

    # 5) Third pass: derive provisional KO brackets when the FCB hasn't
    #    published them yet — including PARTIAL publication (some pairings
    #    listed, others missing).  See `_attach_ko_provisional_players`.
    final = _attach_ko_provisional_players(
        enriched, reservats_standings, rank_by_name or {}
    )

    return OpenLiveState(
        structure=structure_full,
        phases=final,
        seeding=dict(rank_by_name or {}),
        reservats=reservats_standings,
    )
