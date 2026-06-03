"""Scraping orchestration for the Lliga (league) feature.

Walks the FCB pages from the top (competition) down to per-encontre
partides, persisting through the parser functions in `parser.py`.

Network access is shared with the Opens scraper via `scraper.http.fetch`,
which means responses are cached for 1h by default and `force=True`
bypasses the cache.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..scraper.http import fetch
from .models import (
    DivisionSnapshot,
    GroupSnapshot,
    JornadaSnapshot,
    LeagueSnapshot,
)
from .parser import (
    parse_competition_divisions,
    parse_division_groups,
    parse_encontre_partides,
    parse_group_jornades,
    parse_group_standings,
    parse_jornada_encontres,
)
from .persistence import (
    is_jornada_complete,
    load_jornada_from_db,
    save_league_snapshot,
)

BASE = "https://www.fcbillar.cat"


# --------------------------------------------------------------------------- #
# URL builders
# --------------------------------------------------------------------------- #


def url_divisions(competition_id: int) -> str:
    return f"{BASE}/ca/lligues/divisions/{competition_id}"


def url_groups(competition_id: int, division_id: int) -> str:
    return f"{BASE}/ca/lligues/grups/{competition_id}/{division_id}"


def url_classificacio(competition_id: int, division_id: int, group_id: int) -> str:
    return f"{BASE}/ca/lligues/classificacio/{competition_id}/{division_id}/{group_id}"


def url_jornades(competition_id: int, division_id: int, group_id: int) -> str:
    return f"{BASE}/ca/lligues/jornades/{competition_id}/{division_id}/{group_id}"


def url_encontres(
    competition_id: int, division_id: int, group_id: int, jornada_id: int
) -> str:
    return (
        f"{BASE}/ca/lligues/encontres/{competition_id}/{division_id}/{group_id}/{jornada_id}"
    )


def url_partides(
    competition_id: int,
    division_id: int,
    group_id: int,
    jornada_id: int,
    encontre_id: int,
) -> str:
    return (
        f"{BASE}/ca/lligues/partides/"
        f"{competition_id}/{division_id}/{group_id}/{jornada_id}/{encontre_id}"
    )


# --------------------------------------------------------------------------- #
# Scrape orchestration
# --------------------------------------------------------------------------- #


@dataclass
class ScrapeProgress:
    """Counters yielded by `scrape_competition` for CLI feedback."""

    divisions: int = 0
    groups: int = 0
    jornades: int = 0
    encontres: int = 0
    partides: int = 0
    jornades_skipped: int = 0  # incremental: complete in DB → no refetch


def scrape_competition(
    competition_id: int,
    *,
    season: str = "",
    force: bool = False,
    on_progress=None,
) -> tuple[LeagueSnapshot, ScrapeProgress]:
    """Walk a full competition tree and return a snapshot + progress.

    `on_progress(level, message)` is called as significant URLs are
    fetched, so a CLI can stream a log without coupling the scraper to
    `print`. `level` is one of: "division", "group", "jornada", "encontre".
    """
    progress = ScrapeProgress()
    if on_progress is None:
        on_progress = lambda *_a, **_kw: None  # noqa: E731

    on_progress("competition", url_divisions(competition_id))
    div_html = fetch(url_divisions(competition_id), force=force)
    comp = parse_competition_divisions(div_html, competition_id)

    snapshot = LeagueSnapshot(
        competition_id=competition_id,
        season=season,
        name=comp.name,
        divisions=[],
    )

    for division in comp.divisions:
        on_progress("division", division.name)
        progress.divisions += 1
        groups_html = fetch(
            url_groups(competition_id, division.fcb_division_id),
            force=force,
        )
        groups_summary = parse_division_groups(
            groups_html, competition_id, division.fcb_division_id
        )
        # The division name from the parent /divisions/ page is authoritative
        # (anchor text "1a DIVISIÓ", "HONOR", …). The groups page breadcrumb
        # only carries the league-level pointer, so we don't try to re-derive
        # the division label from there.
        div_snap = DivisionSnapshot(
            division=division,
            groups=[],
        )

        for group in groups_summary.groups:
            on_progress("group", group.name)
            progress.groups += 1
            clf_html = fetch(
                url_classificacio(
                    competition_id, division.fcb_division_id, group.fcb_group_id
                ),
                force=force,
            )
            standings = parse_group_standings(clf_html)

            jornades_html = fetch(
                url_jornades(
                    competition_id, division.fcb_division_id, group.fcb_group_id
                ),
                force=force,
            )
            jornades = parse_group_jornades(jornades_html, group.fcb_group_id)

            grp_snap = GroupSnapshot(
                group=group, standings=standings, jornades=[]
            )

            for jornada in jornades:
                progress.jornades += 1
                on_progress(
                    "jornada",
                    f"{group.name} J{jornada.number:02d} ({jornada.played_on})",
                )
                enc_html = fetch(
                    url_encontres(
                        competition_id,
                        division.fcb_division_id,
                        group.fcb_group_id,
                        jornada.fcb_jornada_id,
                    ),
                    force=force,
                )
                encontres = parse_jornada_encontres(enc_html, jornada.fcb_jornada_id)

                jor_snap = JornadaSnapshot(jornada=jornada, encontres=[])
                for encontre in encontres:
                    progress.encontres += 1
                    if encontre.fcb_encontre_id < 0:
                        # Pending encontre (synthetic id) — the FCB hasn't
                        # published the partides URL yet, so don't try to
                        # fetch it. Leave partides empty.
                        encontre.partides = []
                        jor_snap.encontres.append(encontre)
                        continue
                    par_html = fetch(
                        url_partides(
                            competition_id,
                            division.fcb_division_id,
                            group.fcb_group_id,
                            jornada.fcb_jornada_id,
                            encontre.fcb_encontre_id,
                        ),
                        force=force,
                    )
                    encontre.partides = parse_encontre_partides(par_html)
                    progress.partides += len(encontre.partides)
                    jor_snap.encontres.append(encontre)

                grp_snap.jornades.append(jor_snap)
            div_snap.groups.append(grp_snap)
        snapshot.divisions.append(div_snap)

    return snapshot, progress


# --------------------------------------------------------------------------- #
# Incremental refresh
# --------------------------------------------------------------------------- #


def incremental_refresh(
    conn: sqlite3.Connection,
    competition_id: int,
    *,
    season: str = "",
    force: bool = False,
    on_progress=None,
) -> ScrapeProgress:
    """Refresh a competition tree, reusing jornades that are 100% played.

    Strategy: always refetch the cheap top-of-tree pages (divisions, groups,
    standings, jornades index), since the FCB updates standings as soon as
    a jornada is locked. For each jornada in the index, ask the DB if it's
    already complete (every saved partida `is_played = 1`). If yes — reuse
    the saved data verbatim. If no — refetch encontres + partides.

    On a fresh DB this falls through to a regular full scrape.

    Args:
        conn: open SQLite connection. The function commits at the end.
        competition_id: FCB competition id (36 for Tres Bandes).
        season: optional season label to store on the leagues row.
        force: bypass the HTTP cache for refetched pages.
        on_progress: callback `(level, message)`; same shape as scrape_competition.

    Returns the progress counters.
    """
    progress = ScrapeProgress()
    if on_progress is None:
        on_progress = lambda *_a, **_kw: None  # noqa: E731

    on_progress("competition", url_divisions(competition_id))
    div_html = fetch(url_divisions(competition_id), force=force)
    comp = parse_competition_divisions(div_html, competition_id)

    snapshot = LeagueSnapshot(
        competition_id=competition_id,
        season=season,
        name=comp.name,
        divisions=[],
    )

    for division in comp.divisions:
        on_progress("division", division.name)
        progress.divisions += 1
        groups_html = fetch(
            url_groups(competition_id, division.fcb_division_id),
            force=force,
        )
        groups_summary = parse_division_groups(
            groups_html, competition_id, division.fcb_division_id
        )
        # See note in scrape_competition: the /divisions/ page's anchor text
        # is the source of truth for the division label.
        div_snap = DivisionSnapshot(
            division=division,
            groups=[],
        )

        for group in groups_summary.groups:
            on_progress("group", group.name)
            progress.groups += 1
            clf_html = fetch(
                url_classificacio(
                    competition_id, division.fcb_division_id, group.fcb_group_id
                ),
                force=force,
            )
            standings = parse_group_standings(clf_html)

            jornades_html = fetch(
                url_jornades(
                    competition_id, division.fcb_division_id, group.fcb_group_id
                ),
                force=force,
            )
            jornades = parse_group_jornades(jornades_html, group.fcb_group_id)

            grp_snap = GroupSnapshot(
                group=group, standings=standings, jornades=[]
            )

            for jornada in jornades:
                progress.jornades += 1
                if is_jornada_complete(
                    conn,
                    fcb_group_id=group.fcb_group_id,
                    fcb_jornada_id=jornada.fcb_jornada_id,
                ):
                    cached = load_jornada_from_db(
                        conn,
                        fcb_group_id=group.fcb_group_id,
                        fcb_jornada_id=jornada.fcb_jornada_id,
                    )
                    if cached is not None:
                        # Always overlay the freshly-parsed jornada metadata
                        # (number, played_on) on top of the cached partides
                        # — the FCB occasionally rescheduling published dates.
                        cached.jornada = jornada
                        grp_snap.jornades.append(cached)
                        progress.jornades_skipped += 1
                        continue

                on_progress(
                    "jornada",
                    f"{group.name} J{jornada.number:02d} ({jornada.played_on})",
                )
                enc_html = fetch(
                    url_encontres(
                        competition_id,
                        division.fcb_division_id,
                        group.fcb_group_id,
                        jornada.fcb_jornada_id,
                    ),
                    force=force,
                )
                encontres = parse_jornada_encontres(enc_html, jornada.fcb_jornada_id)
                jor_snap = JornadaSnapshot(jornada=jornada, encontres=[])
                for encontre in encontres:
                    progress.encontres += 1
                    if encontre.fcb_encontre_id < 0:
                        # Pending encontre — no partides URL yet.
                        encontre.partides = []
                        jor_snap.encontres.append(encontre)
                        continue
                    par_html = fetch(
                        url_partides(
                            competition_id,
                            division.fcb_division_id,
                            group.fcb_group_id,
                            jornada.fcb_jornada_id,
                            encontre.fcb_encontre_id,
                        ),
                        force=force,
                    )
                    encontre.partides = parse_encontre_partides(par_html)
                    progress.partides += len(encontre.partides)
                    jor_snap.encontres.append(encontre)
                grp_snap.jornades.append(jor_snap)

            div_snap.groups.append(grp_snap)
        snapshot.divisions.append(div_snap)

    save_league_snapshot(conn, snapshot)
    conn.commit()
    return progress
