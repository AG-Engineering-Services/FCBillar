"""Parser for the official "LLISTAT D'INSCRITS PER CLUBS" PDF.

This is the per-club entry list the FCB publishes for each Open *before* the
groups are drawn. It is a different document from the season Opens ranking PDF
(see ``official_pdf.py``): here each row is a registered player, grouped under
their club, with the player's position in the Catalan Opens ranking
("POSSIC. RANQ. OPEN"), their average and their ranking status.

The layout is a fixed-column table. We parse it spatially with pdfplumber,
bucketing each word into a column by its x-coordinate, because the textual
reading order is unreliable (club headers and the first player share a row).

Column x-bands (observed, points from page left):

    club name      x0 < 160
    Nº (count)     195 < x0 < 220       -> players declared for this club
    player name    235 < x0 < 365       -> "SURNAME, GIVEN"
    seed position  385 < x0 < 435       -> POSSIC. RANQ. OPEN (may be blank)
    mitjana        440 < x0 < 475       -> general average (comma decimal)
    ranquing       x0 > 490             -> OPENS | Definitiva | Provisional

A row is a *player* row iff it has name tokens and a parseable average; this
cleanly skips the title/header rows. A row sets the *current club* iff it has
tokens in the club band plus a count in the count band.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InscritEntry:
    """One registered player on the inscrits list."""

    club: str
    player_name: str
    seed_position: int | None  # POSSIC. RANQ. OPEN (Catalan Opens ranking pos)
    mitjana: float
    ranquing_estat: str  # "OPENS" | "Definitiva" | "Provisional" | ...


@dataclass(frozen=True)
class InscritsList:
    """Parsed inscrits PDF: the open name, declared total and the entries."""

    open_name: str | None
    declared_total: int | None
    entries: tuple[InscritEntry, ...]


# Column bands (x0 in PDF points).
_CLUB_MAX = 160.0
_COUNT_MIN, _COUNT_MAX = 195.0, 220.0
_NAME_MIN, _NAME_MAX = 235.0, 365.0
_SEED_MIN, _SEED_MAX = 385.0, 435.0
_MITJANA_MIN, _MITJANA_MAX = 440.0, 475.0
_STATUS_MIN = 490.0

_Y_TOL = 3.0  # words within this many points vertically share a row

_INT_RE = re.compile(r"^\d+$")
_FLOAT_RE = re.compile(r"^\d+[.,]\d+$")
_TOTAL_RE = re.compile(r"(\d+)\s*Jugadors", re.IGNORECASE)


def _to_float(text: str) -> float | None:
    if not _FLOAT_RE.match(text):
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual rows using a y-tolerance.

    pdfplumber tops can wobble by ~1px on the same line, and a club header may
    sit a point or two above the first player on the same row, so we cluster
    rather than round.
    """
    buckets: dict[int, list[dict]] = defaultdict(list)
    for w in words:
        buckets[round(w["top"] / _Y_TOL)].append(w)
    rows = [sorted(ws, key=lambda w: w["x0"]) for _, ws in sorted(buckets.items())]
    return rows


def parse_inscrits_pdf(path: str | Path) -> InscritsList:
    """Parse the inscrits-per-clubs PDF into structured entries."""
    import pdfplumber

    open_name: str | None = None
    declared_total: int | None = None
    current_club: str | None = None
    entries: list[InscritEntry] = []

    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            for row in _cluster_rows(words):
                row_text = " ".join(w["text"] for w in row)

                if declared_total is None:
                    m = _TOTAL_RE.search(row_text)
                    if m:
                        declared_total = int(m.group(1))

                club_tokens = [w for w in row if w["x0"] < _CLUB_MAX]
                count_tokens = [
                    w for w in row if _COUNT_MIN < w["x0"] < _COUNT_MAX and _INT_RE.match(w["text"])
                ]
                name_tokens = [w for w in row if _NAME_MIN < w["x0"] < _NAME_MAX]
                seed_tokens = [
                    w for w in row if _SEED_MIN < w["x0"] < _SEED_MAX and _INT_RE.match(w["text"])
                ]
                mitjana_tokens = [
                    w for w in row if _MITJANA_MIN < w["x0"] < _MITJANA_MAX and _to_float(w["text"]) is not None
                ]
                status_tokens = [w for w in row if w["x0"] >= _STATUS_MIN]

                # Capture the open title: a row whose text contains "OPEN" and
                # has no tabular columns (no count/name/mitjana).
                if (
                    open_name is None
                    and "OPEN" in row_text.upper()
                    and not count_tokens
                    and not mitjana_tokens
                    and not club_tokens
                ):
                    open_name = row_text.strip()

                # Club header: club-band tokens + a count in the count band.
                if club_tokens and count_tokens:
                    current_club = " ".join(w["text"] for w in club_tokens).strip()

                # Player row: needs a name and a parseable average.
                if name_tokens and mitjana_tokens and current_club:
                    player_name = " ".join(w["text"] for w in name_tokens).strip()
                    seed = int(seed_tokens[0]["text"]) if seed_tokens else None
                    mitjana = _to_float(mitjana_tokens[0]["text"]) or 0.0
                    estat = status_tokens[0]["text"].strip() if status_tokens else ""
                    entries.append(
                        InscritEntry(
                            club=current_club,
                            player_name=player_name,
                            seed_position=seed,
                            mitjana=mitjana,
                            ranquing_estat=estat,
                        )
                    )

    return InscritsList(
        open_name=open_name,
        declared_total=declared_total,
        entries=tuple(entries),
    )
