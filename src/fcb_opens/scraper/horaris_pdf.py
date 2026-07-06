"""Parser for the official "HORARIS" PDF of an Open.

The federation publishes, alongside the groups, a schedule grid: for every
group of every previa phase it fixes the **day**, the **billar** (table 1-4)
and the time of each of its three matches. The match types follow the group
play order (Art.):

    (2-3) = seed2 vs seed3        (first match of the group)
    (1-P) = seed1 vs the *loser*  of (2-3)
    (1-G) = seed1 vs the *winner* of (2-3)

This lets us pin a real calendar slot (and, via the billar, the club's YouTube
table channel) to each projected group — see ``projection_to_live_payload``.

Layout — several stacked phase blocks per page. Each block has a date cell
(``DD-MM-YY``), a HORA column and four BILLAR columns; each grid cell reads
``"<GROUP> (<type>)"`` e.g. ``"AG (2-3)"``. The Fase Final blocks use numeric
re-seed pairings (``"13 - 20"``) instead, so they never match the group-cell
pattern and are skipped naturally.

Parsed spatially with pdfplumber: we pair every match-type token with the group
label to its left, read the time from the HORA column of its row, assign the
billar by clustering cell x-positions into the four table columns, and inherit
the date from the nearest date cell above.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ..generator import _P_LABELS, _PP_LABELS, _PPP_LABELS

# Every valid previa group label (PPP + PP + P). KO cells ("13 - 20") aren't here.
_GROUP_LABELS = frozenset(_P_LABELS) | frozenset(_PP_LABELS) | frozenset(_PPP_LABELS)

_DATE_RE = re.compile(r"^(\d{2})-(\d{2})-(\d{2})$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_MATCH_RE = re.compile(r"^\((2-3|1-P|1-G)\)$")

_Y_TOL = 3.0  # words within this many points vertically share a row


@dataclass
class GroupSchedule:
    """When and where a single group plays its three matches."""

    group: str  # bare label, e.g. "AG", "Q", "B"
    date: str | None  # ISO "YYYY-MM-DD"
    billar: int | None  # table number 1..4
    # match type -> "HH:MM" (e.g. {"2-3": "09:30", "1-P": "11:00", "1-G": "12:30"})
    times: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        # Ordered by play order, not by clock (O group is known to swap 1-P/1-G).
        matches = [
            {"type": t, "time": self.times[t]}
            for t in ("2-3", "1-P", "1-G")
            if t in self.times
        ]
        return {"date": self.date, "billar": self.billar, "matches": matches}


def _iso_date(text: str) -> str | None:
    m = _DATE_RE.match(text)
    if not m:
        return None
    dd, mm, yy = m.groups()
    return f"20{yy}-{mm}-{dd}"


def _cluster_columns(xs: list[float], *, gap: float = 30.0) -> list[float]:
    """Return sorted column centers from cell x-positions (gap-based 1-D clustering).

    The four billar columns are ~100pt apart and cells within a column share an
    x0 (±a couple of points), so splitting the sorted x list wherever a gap
    exceeds ``gap`` recovers the column centers even when some rows (e.g. the
    lone PPP group) only populate the first column.
    """
    if not xs:
        return []
    xs = sorted(xs)
    clusters: list[list[float]] = [[xs[0]]]
    for x in xs[1:]:
        if x - clusters[-1][-1] > gap:
            clusters.append([x])
        else:
            clusters[-1].append(x)
    return [sum(c) / len(c) for c in clusters]


def _cluster_rows(words: list[dict]) -> list[list[dict]]:
    buckets: dict[int, list[dict]] = defaultdict(list)
    for w in words:
        buckets[round(w["top"] / _Y_TOL)].append(w)
    return [sorted(ws, key=lambda w: w["x0"]) for _, ws in sorted(buckets.items())]


def parse_horaris_pdf(path: str | Path) -> dict[str, dict]:
    """Parse the HORARIS PDF into ``{group_label: {date, billar, matches[]}}``.

    Group labels are bare (``"AG"``, ``"Q"``, ``"B"``) to match the generator's
    ``Group.label``. Fase Final blocks are ignored (numeric pairings).
    """
    import pdfplumber

    # First pass: collect raw cells with absolute (page, y) so dates/times/billars
    # can be resolved per page. We key everything by a global (page_index, top).
    @dataclass
    class _Cell:
        page: int
        top: float
        x0: float
        group: str
        mtype: str

    cells: list[_Cell] = []
    # Per page: sorted (top, iso_date) date anchors and (top, x0, "HH:MM") times.
    dates_by_page: dict[int, list[tuple[float, str]]] = defaultdict(list)
    times_by_page: dict[int, list[tuple[float, float, str]]] = defaultdict(list)

    with pdfplumber.open(str(path)) as pdf:
        for pi, page in enumerate(pdf.pages):
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            for row in _cluster_rows(words):
                for w in row:
                    iso = _iso_date(w["text"])
                    if iso:
                        dates_by_page[pi].append((w["top"], iso))
                    tm = _TIME_RE.match(w["text"])
                    if tm:
                        hhmm = f"{int(tm.group(1)):02d}:{tm.group(2)}"
                        times_by_page[pi].append((w["top"], w["x0"], hhmm))
                # Pair each "(type)" token with the group label immediately left.
                for i, w in enumerate(row):
                    mt = _MATCH_RE.match(w["text"])
                    if not mt:
                        continue
                    for prev in reversed(row[:i]):
                        if prev["text"] in _GROUP_LABELS:
                            cells.append(_Cell(pi, w["top"], prev["x0"], prev["text"], mt.group(1)))
                            break

    # Billar columns from all cell x-positions across the document (aligned grid).
    centers = _cluster_columns([c.x0 for c in cells])

    def _billar(x0: float) -> int | None:
        if not centers:
            return None
        idx = min(range(len(centers)), key=lambda i: abs(centers[i] - x0))
        return idx + 1

    def _date_for(page: int, top: float) -> str | None:
        # Nearest date anchor above this row on the same page.
        anchors = [(t, d) for (t, d) in dates_by_page[page] if t <= top + _Y_TOL]
        return max(anchors, key=lambda td: td[0])[1] if anchors else None

    def _time_for(page: int, top: float) -> str | None:
        # The HORA-column time on this row (leftmost time within y-tolerance).
        same = [(x0, hhmm) for (t, x0, hhmm) in times_by_page[page] if abs(t - top) <= _Y_TOL]
        return min(same, key=lambda xh: xh[0])[1] if same else None

    schedules: dict[str, GroupSchedule] = {}
    for c in cells:
        sched = schedules.setdefault(c.group, GroupSchedule(group=c.group, date=None, billar=None))
        if sched.date is None:
            sched.date = _date_for(c.page, c.top)
        if sched.billar is None:
            sched.billar = _billar(c.x0)
        tm = _time_for(c.page, c.top)
        if tm:
            sched.times[c.mtype] = tm

    return {g: s.as_dict() for g, s in schedules.items()}
