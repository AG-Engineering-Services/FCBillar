"""HTML parsers for the FCB league pages.

Each FCB page type has its own parser. They are pure functions: they
take an HTML string (already fetched and cached upstream) and return
dataclasses. They never hit the network or the database.

Page types and URL patterns:
    /ca/lligues/divisions/{competition}                         → list of divisions
    /ca/lligues/grups/{competition}/{division}                  → list of groups
    /ca/lligues/classificacio/{competition}/{division}/{group}  → team standings
    /ca/lligues/jornades/{competition}/{division}/{group}       → list of jornades
    /ca/lligues/encontres/{competition}/{division}/{group}/{jornada}                → list of encontres
    /ca/lligues/partides/{competition}/{division}/{group}/{jornada}/{encontre}      → individual partides
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup
from bs4.element import Tag

from .models import (
    Division,
    Encontre,
    Group,
    Jornada,
    Partida,
    TeamStanding,
)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _link_id(href: str, segment: str) -> int | None:
    """Extract the trailing integer following /{segment}/ in the href.

    `_link_id("ca/lligues/encontres/36/149/318/2621", "encontres")` → 2621.
    Used to pluck FCB ids from anchor URLs without committing to absolute vs
    relative URL prefixes.
    """
    parts = [p for p in href.split("/") if p]
    if segment not in parts:
        return None
    idx = parts.index(segment)
    nums = [int(p) for p in parts[idx + 1 :] if p.isdigit()]
    return nums[-1] if nums else None


def _all_link_ids(soup: BeautifulSoup, segment: str) -> list[int]:
    """All trailing ids for anchors whose href contains `/{segment}/`."""
    ids: list[int] = []
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if f"/{segment}/" in href:
            i = _link_id(href, segment)
            if i is not None:
                ids.append(i)
    return ids


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------- #
# /ca/lligues/divisions/{competition}
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CompetitionSummary:
    """Header info parsed from the divisions page."""

    competition_id: int
    name: str
    divisions: list[Division]


def parse_competition_divisions(html: str, competition_id: int) -> CompetitionSummary:
    """Parse the list of divisions inside a competition.

    The page has anchor links of the form
        ca/lligues/grups/{competition}/{division_id}
    each with the division name as anchor text.
    """
    soup = BeautifulSoup(html, "lxml")
    divisions: list[Division] = []
    seen: set[int] = set()
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if f"/lligues/grups/{competition_id}/" not in f"/{href}":
            continue
        div_id = _link_id(href, "grups")
        if div_id is None or div_id in seen:
            continue
        seen.add(div_id)
        name = _clean(a.get_text())
        if not name:
            continue
        divisions.append(Division(fcb_division_id=div_id, name=name))

    name = _extract_h2_or_breadcrumb(soup, fallback="LLIGA")
    return CompetitionSummary(
        competition_id=competition_id,
        name=name,
        divisions=divisions,
    )


def _extract_h2_or_breadcrumb(soup: BeautifulSoup, *, fallback: str) -> str:
    h2 = soup.find("h2")
    if h2 and h2.get_text(strip=True):
        return _clean(h2.get_text())
    title = soup.find("title")
    if title and title.get_text(strip=True):
        return _clean(title.get_text())
    return fallback


# --------------------------------------------------------------------------- #
# /ca/lligues/grups/{competition}/{division}
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DivisionGroupsSummary:
    division_id: int
    groups: list[Group]


def parse_division_groups(
    html: str,
    competition_id: int,
    division_id: int,
) -> DivisionGroupsSummary:
    """Parse the list of groups inside a division.

    The page links each group twice — once via the jornades URL and
    once via the classificacio URL — both share the same `{group_id}`
    suffix and the anchor text is the group label (e.g. "GRUP A").
    Only the *jornades* anchor reliably carries the group label, so we
    use that path as the source of truth.

    Note: we deliberately do NOT try to extract the division *label*
    from this page. The breadcrumb only points to the parent league,
    not to the current division — so any naive scrape would yield
    "LLIGA CATALANA TRES BANDES" five times. The authoritative source
    for the division label is the parent /divisions/ page (anchor text).
    """
    soup = BeautifulSoup(html, "lxml")
    groups: list[Group] = []
    seen: set[int] = set()
    for a in soup.find_all("a"):
        href = a.get("href", "")
        prefix = f"/lligues/jornades/{competition_id}/{division_id}/"
        if prefix not in f"/{href}":
            continue
        gid = _link_id(href, "jornades")
        if gid is None or gid in seen:
            continue
        label = _clean(a.get_text())
        if not label:
            continue
        seen.add(gid)
        groups.append(
            Group(fcb_group_id=gid, fcb_division_id=division_id, name=label)
        )
    return DivisionGroupsSummary(division_id=division_id, groups=groups)


# --------------------------------------------------------------------------- #
# /ca/lligues/classificacio/{competition}/{division}/{group}
# --------------------------------------------------------------------------- #


def parse_group_standings(html: str) -> list[TeamStanding]:
    """Parse the team-standings table for a group.

    The FCB page renders the standings as a sequence of `<div class='row box ...'>`
    rows where the first column is "PM PP J" header and subsequent rows contain:

        position | team name | PM value | PP value | J value

    Some pages use a real `<table>`. We try both shapes.
    """
    soup = BeautifulSoup(html, "lxml")

    # Try a real table first.
    for table in soup.find_all("table"):
        headers = {th.get_text(strip=True).upper() for th in table.find_all("th")}
        if {"PM", "PP", "J"}.issubset(headers):
            return _standings_from_table(table)

    # Fallback: parse the row-box layout used by the FCB Tres Bandes pages.
    return _standings_from_rows(soup)


def _standings_from_table(table: Tag) -> list[TeamStanding]:
    rows: list[TeamStanding] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue
        try:
            position = int(_clean(cells[0].get_text()))
        except ValueError:
            continue
        team_name = _clean(cells[1].get_text())
        pm = _safe_int(cells[2].get_text())
        pp = _safe_int(cells[3].get_text())
        j = _safe_int(cells[4].get_text())
        rows.append(
            TeamStanding(
                position=position,
                team_name=team_name,
                match_points=pm,
                set_points=pp,
                matches_played=j,
            )
        )
    return rows


_RE_STANDING_ROW = re.compile(
    r"^\s*(\d+)\.\s*(.+?)\s*\|\s*PM\s+(\d+)\s+PP\s+(\d+)\s+J\s+(\d+)",
    re.IGNORECASE,
)


def _standings_from_rows(soup: BeautifulSoup) -> list[TeamStanding]:
    """Parse standings from `row box`-style div blocks.

    The page renders one row per team like:
        <div class='row box info'>
          <div>1</div>
          <div>C.B. MONFORTE "B"</div>
          <div>27</div>
          <div>63</div>
          <div>14</div>
        </div>

    Header rows say "POSICIÓ EQUIP PM PP J" and are skipped.
    """
    out: list[TeamStanding] = []
    for row in soup.select("div.row.box"):
        cells = row.find_all("div", recursive=False)
        # Drop empty wrapper rows.
        if len(cells) < 5:
            continue
        first = _clean(cells[0].get_text())
        if not first.isdigit():
            continue
        try:
            position = int(first)
        except ValueError:
            continue
        team_name = _clean(cells[1].get_text())
        if not team_name:
            continue
        # Find the trailing PM PP J integers from the remaining cells.
        nums = [
            _safe_int(_clean(c.get_text())) for c in cells[2:] if _clean(c.get_text()).isdigit()
        ]
        if len(nums) < 3:
            continue
        out.append(
            TeamStanding(
                position=position,
                team_name=team_name,
                match_points=nums[0],
                set_points=nums[1],
                matches_played=nums[2],
            )
        )
    return out


# --------------------------------------------------------------------------- #
# /ca/lligues/jornades/{competition}/{division}/{group}
# --------------------------------------------------------------------------- #


def parse_group_jornades(html: str, group_id: int) -> list[Jornada]:
    """Parse the list of jornades for a group.

    Each jornada is rendered as a row containing:
      - an anchor `<a href='ca/lligues/encontres/{c}/{d}/{g}/{jornada_id}'>Jornada NN</a>`
      - a date in **2025-09-27** ISO format (sometimes inside a `<b>` tag)
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[Jornada] = []
    for row in soup.select("div.row.box"):
        link = row.find("a", href=re.compile(r"/lligues/encontres/"))
        if link is None:
            continue
        jid = _link_id(link.get("href", ""), "encontres")
        if jid is None:
            continue
        text = _clean(link.get_text())
        m = re.search(r"(\d+)", text)
        number = int(m.group(1)) if m else len(out) + 1

        # Date heuristic: the row also contains an ISO date like 2025-09-27.
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", row.get_text())
        played_on = date_match.group(0) if date_match else ""

        out.append(
            Jornada(
                fcb_jornada_id=jid,
                fcb_group_id=group_id,
                number=number,
                played_on=played_on,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# /ca/lligues/encontres/{competition}/{division}/{group}/{jornada}
# --------------------------------------------------------------------------- #


def parse_jornada_encontres(html: str, jornada_id: int) -> list[Encontre]:
    """Parse the team encounters for a single jornada.

    Two layouts are supported:
      • Played encontre — has an anchor `<a href='.../partides/.../{enc_id}'>
        Seguiment partides</a>` and 4 bold integers for PP/PM per side.
      • Pending encontre (the FCB publishes the calendar weeks in advance
        without scoreboards) — only the two bold team names plus a
        "Pendent de jugar" / "Descansa" label. We synthesise a stable
        negative `fcb_encontre_id` so the row can be persisted; once the
        FCB fills the partides page in, the next scrape replaces this
        placeholder with the real encontre id.
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[Encontre] = []
    pending_seq = 0  # bumps for each pending encontre in this jornada
    for row in soup.select("div.row.box"):
        # Skip header rows like `<div class='row box black'>JORNADES DADES</div>`
        # (no <b> tags inside).
        bold_texts = [_clean(b.get_text()) for b in row.find_all("b")]
        names = [t for t in bold_texts if not t.isdigit()]
        if len(names) < 2:
            continue

        link = row.find("a", href=re.compile(r"/lligues/partides/"))
        if link is not None:
            # Played encontre — reuse existing logic.
            enc_id = _link_id(link.get("href", ""), "partides")
            if enc_id is None:
                continue
            nums = [_safe_int(t) for t in bold_texts if t.isdigit()]
            if len(nums) < 4:
                continue
            home_name, away_name = names[0], names[1]
            home_pp, home_pm, away_pp, away_pm = nums[0], nums[1], nums[2], nums[3]
            out.append(
                Encontre(
                    fcb_encontre_id=enc_id,
                    fcb_jornada_id=jornada_id,
                    home_team_name=home_name,
                    away_team_name=away_name,
                    home_match_points=home_pm,
                    away_match_points=away_pm,
                    home_set_points=home_pp,
                    away_set_points=away_pp,
                )
            )
            continue

        # Pending — synthesise a negative id keyed off the jornada to
        # avoid clashes with real (always-positive) FCB ids and to stay
        # idempotent across re-scrapes.
        pending_seq += 1
        synthetic_id = -((jornada_id * 100) + pending_seq)
        home_name, away_name = names[0], names[1]
        out.append(
            Encontre(
                fcb_encontre_id=synthetic_id,
                fcb_jornada_id=jornada_id,
                home_team_name=home_name,
                away_team_name=away_name,
                home_match_points=0,
                away_match_points=0,
                home_set_points=0,
                away_set_points=0,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# /ca/lligues/partides/{competition}/{division}/{group}/{jornada}/{encontre}
# --------------------------------------------------------------------------- #


def parse_encontre_partides(html: str) -> list[Partida]:
    """Parse the four (or however many) partides inside a single encontre.

    Each partida is rendered as a `div.row.box.info.padded` block containing 12
    inner `<div>` cells in a deterministic order:

        0: home_player_name (bold)
        1: "Caramboles N"
        2: "Sèrie major N"
        3: "Punts N"
        4: away_player_name (bold)
        5: "Caramboles N"
        6: "Sèrie major N"
        7: "Punts N"
        8: "Entrades N"
        9: "Àrbitre TEXT"
       10: "Assistència TEXT"
       11: "Modalitat TEXT"
    """
    soup = BeautifulSoup(html, "lxml")
    out: list[Partida] = []
    for slot, block in enumerate(soup.select("div.row.box.info.padded"), start=1):
        cells = block.find_all("div", recursive=False)
        if len(cells) < 9:
            continue
        try:
            home_name = _clean(cells[0].get_text())
            home_car = _label_value_int(cells[1])
            home_serie = _label_value_int(cells[2])
            home_punts = _label_value_int(cells[3])
            away_name = _clean(cells[4].get_text())
            away_car = _label_value_int(cells[5])
            away_serie = _label_value_int(cells[6])
            away_punts = _label_value_int(cells[7])
            entrades = _label_value_int(cells[8])
            arbitre = _label_value_text(cells[9]) if len(cells) > 9 else None
            attendance = _label_value_text(cells[10]) if len(cells) > 10 else None
            modalitat = _label_value_text(cells[11]) if len(cells) > 11 else None
        except (IndexError, ValueError):
            continue

        played = (
            home_car > 0 or away_car > 0 or entrades > 0
            or (attendance or "").lower().startswith("partit disputat")
        )
        out.append(
            Partida(
                slot=slot,
                home_player_name=home_name,
                home_caramboles=home_car,
                home_serie_major=home_serie,
                home_punts=home_punts,
                away_player_name=away_name,
                away_caramboles=away_car,
                away_serie_major=away_serie,
                away_punts=away_punts,
                entrades=entrades,
                arbitre=arbitre,
                attendance=attendance,
                modalitat=modalitat,
                is_played=played,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _label_value_int(cell: Tag) -> int:
    """Cell text is "Caramboles 35" — the integer is the trailing token."""
    text = _clean(cell.get_text())
    m = re.search(r"(-?\d+)\s*$", text)
    return int(m.group(1)) if m else 0


def _label_value_text(cell: Tag) -> str | None:
    """Cell text is "Àrbitre Jordi Clapes" — return the value half (after the bold label)."""
    bold = cell.find("b")
    if bold is None:
        return _clean(cell.get_text()) or None
    label_text = _clean(bold.get_text())
    full = _clean(cell.get_text())
    if full.startswith(label_text):
        rest = full[len(label_text) :]
        return rest.strip() or None
    return full or None


def _safe_int(text: str) -> int:
    text = _clean(text)
    try:
        return int(text)
    except ValueError:
        return 0
