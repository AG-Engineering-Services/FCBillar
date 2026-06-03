from __future__ import annotations

import io
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .http import DEFAULT_CACHE_DIR, DEFAULT_TIMEOUT_S, DEFAULT_TTL_S, USER_AGENT

OFFICIAL_RANKING_URL = "https://www.fcbillar.cat/media/2025-2026/COMPETICIO/OPENS/FcBillar-RanquingOpens3Bandes-25-26.pdf"

_OPEN_LABEL_RE = re.compile(r"(\d+\s*[EeÈèºo]?\s*OPEN)", re.IGNORECASE)
_OPEN_LEGEND_LINE_RE = re.compile(
    r"^\s*(\d+\s*[EeÈèºo]?\s*OPEN)\s+(.*?)\s+TEMP\.?\s*(\d{4}[/-]\d{2,4})\s*$",
    re.IGNORECASE,
)
_OPEN_NAME_SEASON_RE = re.compile(
    r"((?:[IVXLCDM]+)\s+OPEN\s+[^\n]*?)\s+TEMP\.?\s*(\d{4}[/-]\d{2,4})",
    re.IGNORECASE,
)
_DATA_LINE_RE = re.compile(r"^\s*(\d{1,3})\s+")
_INT_RE = re.compile(r"^-?\d+$")

_CLUB_PREFIXES = (
    "C.B",
    "B.C",
    "S.B",
    "S.B.F",
    "S.E",
)


@dataclass(frozen=True)
class OfficialOpen:
    index: int
    label: str
    full_name: str
    season: str


@dataclass(frozen=True)
class OfficialRankingEntry:
    position: int
    display_name: str
    club: str | None
    total_points: int
    points_per_open: tuple[int | None, ...]


@dataclass(frozen=True)
class OfficialRanking:
    source_url: str
    opens: tuple[OfficialOpen, ...]
    entries: tuple[OfficialRankingEntry, ...]


def _cache_path_for_pdf(url: str, cache_dir: Path) -> Path:
    import hashlib

    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return cache_dir / f"{digest}.pdf"


def fetch_official_ranking_pdf(
    url: str = OFFICIAL_RANKING_URL,
    force: bool = False,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    cache_ttl_s: int = DEFAULT_TTL_S,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    use_cache_only: bool = False,
) -> bytes:
    """Fetch the official Open ranking PDF using a local binary cache."""
    import httpx

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = _cache_path_for_pdf(url, cache_dir)

    if cache_file.exists():
        age_s = time.time() - cache_file.stat().st_mtime
        if use_cache_only or (not force and age_s < cache_ttl_s):
            return cache_file.read_bytes()

    if use_cache_only:
        raise FileNotFoundError(f"Cached PDF not found for URL: {url}")

    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout_s,
        follow_redirects=True,
    )
    response.raise_for_status()
    body = response.content
    cache_file.write_bytes(body)
    return body


def _clean_space(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _season_to_short(season: str) -> str:
    s = season.strip().replace("/", "-")
    m = re.match(r"^(\d{4})-(\d{2,4})$", s)
    if not m:
        return s
    left, right = m.group(1), m.group(2)
    return f"{left}-{right[-2:]}"


def _normalize_ascii_upper(value: str) -> str:
    nfkd = unicodedata.normalize("NFD", value)
    without_accents = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    return without_accents.upper()


def _extract_table_lines(page) -> list[str]:
    lines: list[str] = []
    tables = page.extract_tables() or []
    for table in tables:
        for row in table:
            if not row:
                continue
            text = _clean_space(" ".join((cell or "") for cell in row))
            if text:
                lines.append(text)
    return lines


def _extract_text_lines(page) -> list[str]:
    text = page.extract_text() or ""
    return [_clean_space(raw) for raw in text.splitlines() if _clean_space(raw)]


def _find_open_labels(lines: list[str]) -> tuple[str, ...]:
    for line in lines:
        upper = _normalize_ascii_upper(line)
        if "JUGADOR" in upper and "TOTAL" in upper:
            labels = []
            for m in _OPEN_LABEL_RE.finditer(line):
                labels.append(_clean_space(m.group(1).upper()))
            if labels:
                return tuple(labels)
    raise ValueError("Could not detect official ranking header with OPEN labels")


def _find_open_legend(lines: list[str], labels: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    by_label: dict[str, tuple[str, str]] = {}

    for line in lines:
        m = _OPEN_LEGEND_LINE_RE.match(line)
        if not m:
            continue
        label = _clean_space(m.group(1).upper())
        full_name = _clean_space(m.group(2).upper())
        season = _season_to_short(m.group(3))
        by_label[label] = (full_name, season)

    if not by_label:
        text = "\n".join(lines)
        seq = []
        for m in _OPEN_NAME_SEASON_RE.finditer(text):
            seq.append((_clean_space(m.group(1).upper()), _season_to_short(m.group(2))))
        if seq:
            seq = seq[: len(labels)]
            while len(seq) < len(labels):
                seq.append(("", ""))
            return tuple(seq)

    result: list[tuple[str, str]] = []
    for label in labels:
        result.append(by_label.get(label, (label, "")))
    return tuple(result)


def _detect_total_and_points(nums: list[int], opens_count: int) -> tuple[int, tuple[int | None, ...]]:
    if not nums:
        raise ValueError("No numeric values found in row")

    total = nums[0]
    raw_points = nums[1:]
    for i in range(len(nums)):
        maybe_total = nums[i]
        tail = nums[i + 1 :]
        if len(tail) <= opens_count and sum(tail) == maybe_total:
            total = maybe_total
            raw_points = tail
            break

    points: list[int | None] = [int(v) for v in raw_points]
    if len(points) < opens_count:
        points = [None] * (opens_count - len(points)) + points
    if len(points) > opens_count:
        points = points[-opens_count:]
    return total, tuple(points)


def _is_club_token(token: str) -> bool:
    if not token:
        return False
    upper = _normalize_ascii_upper(token)
    upper = upper.replace("'", "").replace('"', "")
    return any(upper.startswith(prefix) for prefix in _CLUB_PREFIXES)


def _split_name_and_club(text: str) -> tuple[str, str | None]:
    if "," not in text:
        return _clean_space(text), None

    left, right = text.split(",", 1)
    right_tokens = right.strip().split()

    club_idx = None
    for idx, tok in enumerate(right_tokens):
        if _is_club_token(tok):
            club_idx = idx
            break

    if club_idx is None:
        given = " ".join(right_tokens)
        club = None
    else:
        given = " ".join(right_tokens[:club_idx])
        club = _clean_space(" ".join(right_tokens[club_idx:])) or None

    display_name = _clean_space(f"{left.strip()}, {given.strip()}")
    return display_name, club


def _parse_data_line(line: str, opens_count: int) -> OfficialRankingEntry | None:
    if not _DATA_LINE_RE.match(line):
        return None
    tokens = line.split()
    if not tokens or not tokens[0].isdigit():
        return None

    position = int(tokens[0])
    tail = tokens[1:]

    numeric_tail: list[int] = []
    while tail and _INT_RE.match(tail[-1]):
        numeric_tail.append(int(tail.pop()))
    numeric_tail.reverse()
    if not numeric_tail:
        return None

    total_points, points = _detect_total_and_points(numeric_tail, opens_count)
    left_text = " ".join(tail)
    display_name, club = _split_name_and_club(left_text)

    return OfficialRankingEntry(
        position=position,
        display_name=display_name,
        club=club,
        total_points=total_points,
        points_per_open=points,
    )


# --------------------------------------------------------------------------- #
# Spatial (X-coord) row parser
# --------------------------------------------------------------------------- #
#
# The text-line parser above (`_parse_data_line`) loses column position
# info: empty cells disappear from the extracted line, so a row like
# `[--] 165 -20 [--] 180 118` collapses to `165 -20 180 118` and the
# parser can only guess which Open each value belongs to. The default
# guess (left-pad with None) is wrong whenever the missing column is
# in the middle of the row.
#
# The spatial parser uses pdfplumber's `page.extract_words()` to keep
# X coordinates around. From the header row we read the X-bounds of
# TOTAL and each `NNè OPEN` column; for each data row we then bucket
# numeric tokens into the column whose X range they fall in. Empty
# cells stay None — they're identified by "no token landed in this
# column" rather than by counting tokens.
#
# This is the correct fix for the real FCB PDF layout. The text-line
# parser is kept as a fallback for older synthetic test fixtures.


def _group_words_by_y(words, tolerance: float = 3.0) -> list[list[dict]]:
    """Group `pdfplumber.extract_words()` output into rows by Y coord.

    Rows in the FCB PDF sometimes split across two Y values (the
    position number sits on a baseline 1-2px different from the rest
    of the row). A small tolerance merges them.
    """
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    groups: list[list[dict]] = [[sorted_words[0]]]
    for w in sorted_words[1:]:
        last = groups[-1][-1]
        if abs(w["top"] - last["top"]) <= tolerance:
            groups[-1].append(w)
        else:
            groups.append([w])
    return groups


_OPEN_HEADER_RE = re.compile(r"^(\d+)\s*[èeE]?$")


def _detect_column_bounds(
    rows: list[list[dict]], opens_count: int
) -> tuple[tuple[float, float], tuple[tuple[float, float], ...]] | None:
    """Find the X bounds of TOTAL and each Open column from the header row.

    Returns `(total_bounds, open_bounds_tuple)` where each bounds is
    `(x0, x1)`. Returns None if no recognizable header is present.
    """
    for row in rows:
        words_by_x = sorted(row, key=lambda w: w["x0"])
        upper_texts = [w["text"].upper() for w in words_by_x]
        if "JUGADOR" not in " ".join(upper_texts) or "TOTAL" not in upper_texts:
            continue
        total_w = next(
            (w for w in words_by_x if w["text"].upper() == "TOTAL"), None
        )
        if total_w is None:
            continue
        # Each Open column shows up as a "NN" token followed by "OPEN".
        open_bounds: list[tuple[float, float]] = []
        for i, w in enumerate(words_by_x):
            if not _OPEN_HEADER_RE.match(w["text"]):
                continue
            if i + 1 >= len(words_by_x):
                continue
            next_w = words_by_x[i + 1]
            if next_w["text"].upper() != "OPEN":
                continue
            open_bounds.append((w["x0"], next_w["x1"]))
        if len(open_bounds) >= opens_count:
            return (total_w["x0"], total_w["x1"]), tuple(open_bounds[:opens_count])
    return None


def _bucket_into_column(
    word: dict,
    total_bounds: tuple[float, float],
    open_bounds: tuple[tuple[float, float], ...],
    slack: float = 12.0,
) -> tuple[str, int]:
    """Return ("total", -1), ("open", i), or ("none", -1) for `word`.

    Numeric tokens are right-aligned in their cells, so we accept the
    word if its X range overlaps the column bounds with a small slack.
    """
    wx0, wx1 = word["x0"], word["x1"]
    # TOTAL
    if wx0 >= total_bounds[0] - slack and wx1 <= total_bounds[1] + slack:
        return ("total", -1)
    for i, (cx0, cx1) in enumerate(open_bounds):
        if wx0 >= cx0 - slack and wx1 <= cx1 + slack:
            return ("open", i)
    return ("none", -1)


def _parse_spatial_row(
    row: list[dict],
    total_bounds: tuple[float, float],
    open_bounds: tuple[tuple[float, float], ...],
) -> OfficialRankingEntry | None:
    """Parse one data row using column X-coordinates."""
    sorted_row = sorted(row, key=lambda w: w["x0"])
    # First word should be the position number (leftmost integer).
    position: int | None = None
    name_words: list[str] = []
    total_value: int | None = None
    points: list[int | None] = [None] * len(open_bounds)

    # Position is the leftmost numeric word; everything to the right of
    # it but before TOTAL's column is the player name + club.
    for w in sorted_row:
        text = w["text"]
        # Skip everything left of the JUGADOR column area until we find
        # an integer (the position).
        if position is None:
            if text.isdigit():
                position = int(text)
            continue
        # Try to bucket this token. If it's a number that lands in a
        # column, store it there. Otherwise treat it as a name/club word.
        if _INT_RE.match(text):
            bucket, idx = _bucket_into_column(w, total_bounds, open_bounds)
            if bucket == "total":
                total_value = int(text)
                continue
            if bucket == "open":
                points[idx] = int(text)
                continue
            # Numeric word that didn't land in any column — treat as part
            # of the name (rare; e.g. a club ending in a digit).
            name_words.append(text)
        else:
            name_words.append(text)

    if position is None or total_value is None:
        return None

    name_club_text = _clean_space(" ".join(name_words))
    display_name, club = _split_name_and_club(name_club_text)

    return OfficialRankingEntry(
        position=position,
        display_name=display_name,
        club=club,
        total_points=total_value,
        points_per_open=tuple(points),
    )


def _parse_table_row(row: list[str | None], opens_count: int) -> OfficialRankingEntry | None:
    cells = [_clean_space((c or "")) for c in row]
    if not cells or not cells[0].isdigit():
        return None

    # In real FCB PDF, table extraction for data rows is unreliable (often split or merged),
    # so this path is mainly a fallback for synthetic/simple tables.
    if len(cells) < 4:
        return None

    position = int(cells[0])
    name = cells[1]
    club = cells[2] or None

    if not _INT_RE.match(cells[3]):
        return None
    total_points = int(cells[3])

    raw_points = cells[4 : 4 + opens_count]
    points: list[int | None] = []
    for cell in raw_points:
        if cell == "":
            points.append(None)
        elif _INT_RE.match(cell):
            points.append(int(cell))
        else:
            points.append(None)
    if len(points) < opens_count:
        points.extend([None] * (opens_count - len(points)))

    return OfficialRankingEntry(
        position=position,
        display_name=_clean_space(name),
        club=club,
        total_points=total_points,
        points_per_open=tuple(points),
    )


def _validate_entry(entry: OfficialRankingEntry) -> None:
    summed = sum(p for p in entry.points_per_open if p is not None)
    if summed != entry.total_points:
        logging.warning(
            "Official PDF total mismatch for %s (pos %s): total=%s, summed=%s, points=%s",
            entry.display_name,
            entry.position,
            entry.total_points,
            summed,
            entry.points_per_open,
        )


def parse_official_ranking(pdf_bytes: bytes, source_url: str) -> OfficialRanking:
    """Parse an official FCB Opens ranking PDF into structured rows.

    Strategy:
      1. Spatial parsing using `extract_words()` X coordinates — the
         only correct way to handle empty cells (justified absences),
         which collapse to nothing in the text-line stream.
      2. Text-line parsing as fallback for synthetic test fixtures
         and degenerate PDFs where header detection fails.
      3. Table extraction is kept as a last-resort fallback.
    """
    import pdfplumber

    table_lines: list[str] = []
    text_lines: list[str] = []
    table_rows: list[list[str | None]] = []
    spatial_pages: list[list[list[dict]]] = []  # per page: list of word-rows

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            # Spatial extraction is the primary path on the real FCB PDF
            # but can be absent in synthetic test fixtures, so we degrade
            # gracefully when `extract_words` isn't implemented.
            try:
                words = page.extract_words() or []
            except AttributeError:
                words = []
            spatial_pages.append(_group_words_by_y(words))

            # Requirement: try table extraction first on each page.
            lines_from_tables = _extract_table_lines(page)
            if lines_from_tables:
                table_lines.extend(lines_from_tables)
            else:
                # Requirement fallback: parse text line-by-line when no tables.
                text_lines.extend(_extract_text_lines(page))

            # Also collect text lines always, because data rows are more reliable there.
            text_lines.extend(_extract_text_lines(page))

            for table in (page.extract_tables() or []):
                for row in table:
                    if row:
                        table_rows.append(row)

    header_source = text_lines if text_lines else table_lines
    labels = _find_open_labels(header_source)
    legend = _find_open_legend(header_source, labels)

    opens = tuple(
        OfficialOpen(
            index=i + 1,
            label=labels[i],
            full_name=legend[i][0] or labels[i],
            season=legend[i][1],
        )
        for i in range(len(labels))
    )

    entries_by_position: dict[int, OfficialRankingEntry] = {}

    # 1) Spatial parser — primary path for the real FCB PDF.
    # Detect column bounds once from the first page that exposes a
    # recognizable header, then parse every data row across all pages.
    column_bounds: tuple[tuple[float, float], tuple[tuple[float, float], ...]] | None = None
    for page_rows in spatial_pages:
        if column_bounds is None:
            column_bounds = _detect_column_bounds(page_rows, len(opens))
        if column_bounds is None:
            continue
        total_bounds, open_bounds = column_bounds
        for row in page_rows:
            entry = _parse_spatial_row(row, total_bounds, open_bounds)
            if entry is None:
                continue
            entries_by_position.setdefault(entry.position, entry)

    # 2) Text-line fallback for tests / PDFs without recognizable header.
    if not entries_by_position:
        for line in text_lines:
            entry = _parse_data_line(line, len(opens))
            if entry is None:
                continue
            entries_by_position[entry.position] = entry

    # 3) Last-resort: table extraction.
    if not entries_by_position:
        for row in table_rows:
            entry = _parse_table_row(row, len(opens))
            if entry is None:
                continue
            entries_by_position[entry.position] = entry

    if not entries_by_position:
        raise ValueError("No ranking rows could be parsed from official PDF")

    entries = tuple(entries_by_position[pos] for pos in sorted(entries_by_position.keys()))
    for entry in entries:
        _validate_entry(entry)

    return OfficialRanking(source_url=source_url, opens=opens, entries=entries)
