"""Parser for the official "RÀNQUING INICIAL" PDF of an Open.

This is the seeded start list the FCB publishes for each Open *before* the
groups are drawn — and it is the input that lets us project the whole bracket
ahead of the federation (see ``projection.build_projection_from_seeded``).

It differs from the inscrits-per-clubs PDF (``inscrits_pdf.py``): here the
players are already **sorted into final seed order** by the federation (the
``Posició`` column, 1..N, with Art. XVIII fully applied — opens points → tier →
fcb position → mitjana). So we don't re-seed: we trust ``Posició`` verbatim.

Layout — a fixed-column grid. Parsed spatially with pdfplumber, bucketing each
word into a column by its x-coordinate (name and club are multi-word and
adjacent, so textual reading order can't split them reliably).

Column x-bands (x0 in PDF points, observed on the Mataró PDF):

    posició        x0 < 70            -> seed order (1..N)
    jugador        70  <= x0 < 210    -> "SURNAME, GIVEN"
    club           210 <= x0 < 318
    rànquing       318 <= x0 < 365    -> Catalan Opens ranking pos (blank if none)
    tipus          365 <= x0 < 445    -> OPENS | Definitiva | Provisional
    punts          445 <= x0 < 500    -> ranking points (may be 0 or negative)
    mitjana        x0 >= 500          -> general average (comma decimal)

A row is a *player* row iff it has a leading integer in the posició band, name
tokens, and a parseable average — cleanly skipping title/header/footer rows.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RankingInicialEntry:
    """One seeded player on the initial ranking list."""

    posicio: int  # seed order (1 = top seed); Art. XVIII already applied
    player_name: str
    club: str
    ranking_position: int | None  # "Rànquing" = Catalan Opens ranking pos (may be None)
    ranquing_estat: str  # "OPENS" | "Definitiva" | "Provisional" | ...
    punts: int
    mitjana: float


@dataclass(frozen=True)
class RankingInicialList:
    """Parsed RÀNQUING INICIAL PDF: the open name and the seeded entries."""

    open_name: str | None
    entries: tuple[RankingInicialEntry, ...]

    @property
    def num_players(self) -> int:
        return len(self.entries)


# Column bands (x0 in PDF points).
_POS_MAX = 70.0
_NAME_MIN, _NAME_MAX = 70.0, 210.0
_CLUB_MIN, _CLUB_MAX = 210.0, 318.0
_RANK_MIN, _RANK_MAX = 318.0, 365.0
_ESTAT_MIN, _ESTAT_MAX = 365.0, 445.0
_PUNTS_MIN, _PUNTS_MAX = 445.0, 500.0
_MITJANA_MIN = 500.0

_Y_TOL = 3.0  # words within this many points vertically share a row

_INT_RE = re.compile(r"^\d+$")
_SIGNED_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+[.,]\d+$")

# Non-title rows that also contain "OPEN": footer, org banner, notices.
_TITLE_STOPWORDS = ("PÀG", "PAG.", "ORGANITZACIÓ", "ORGANITZACIO", "VESTIMENTA", "RECORDA")


def _to_float(text: str) -> float | None:
    if not _FLOAT_RE.match(text):
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    """Group words into visual rows using a y-tolerance (tops wobble ~1px)."""
    buckets: dict[int, list[dict]] = defaultdict(list)
    for w in words:
        buckets[round(w["top"] / _Y_TOL)].append(w)
    return [sorted(ws, key=lambda w: w["x0"]) for _, ws in sorted(buckets.items())]


def parse_ranking_inicial_pdf(path: str | Path) -> RankingInicialList:
    """Parse the RÀNQUING INICIAL PDF into seeded entries (ordered by Posició)."""
    import pdfplumber

    open_name: str | None = None
    entries: list[RankingInicialEntry] = []

    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            for row in _cluster_rows(words):
                row_text = " ".join(w["text"] for w in row)

                pos_tokens = [
                    w for w in row if w["x0"] < _POS_MAX and _INT_RE.match(w["text"])
                ]
                name_tokens = [w for w in row if _NAME_MIN <= w["x0"] < _NAME_MAX]
                club_tokens = [w for w in row if _CLUB_MIN <= w["x0"] < _CLUB_MAX]
                rank_tokens = [
                    w for w in row if _RANK_MIN <= w["x0"] < _RANK_MAX and _INT_RE.match(w["text"])
                ]
                estat_tokens = [w for w in row if _ESTAT_MIN <= w["x0"] < _ESTAT_MAX]
                punts_tokens = [
                    w for w in row
                    if _PUNTS_MIN <= w["x0"] < _PUNTS_MAX and _SIGNED_INT_RE.match(w["text"])
                ]
                mitjana_tokens = [
                    w for w in row if w["x0"] >= _MITJANA_MIN and _to_float(w["text"]) is not None
                ]

                # Player row: leading posició int + name + a parseable average.
                if pos_tokens and name_tokens and mitjana_tokens:
                    entries.append(
                        RankingInicialEntry(
                            posicio=int(pos_tokens[0]["text"]),
                            player_name=" ".join(w["text"] for w in name_tokens).strip(),
                            club=" ".join(w["text"] for w in club_tokens).strip(),
                            ranking_position=int(rank_tokens[0]["text"]) if rank_tokens else None,
                            ranquing_estat=" ".join(w["text"] for w in estat_tokens).strip(),
                            punts=int(punts_tokens[0]["text"]) if punts_tokens else 0,
                            mitjana=_to_float(mitjana_tokens[0]["text"]) or 0.0,
                        )
                    )
                    continue

                # Open title: the longest "OPEN" row that isn't a footer/banner/notice.
                up = row_text.upper()
                if "OPEN" in up and not any(sw in up for sw in _TITLE_STOPWORDS):
                    cand = row_text.strip()
                    if open_name is None or len(cand) > len(open_name):
                        open_name = cand

    # Trust Posició, but sort defensively (pages are already in order).
    entries.sort(key=lambda e: e.posicio)
    return RankingInicialList(open_name=open_name, entries=tuple(entries))
