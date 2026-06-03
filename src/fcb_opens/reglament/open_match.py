"""Open-name matching across data sources.

The FCB publishes Open titles in two flavours: terse names in the HTML
(`OPEN MATARO`, `OPEN TRES BANDES SANTS`) and verbose, ordinal-stuffed
names in the official PDF (`21È OPEN XIII OPEN CIUTAT DE MATARO LES
SANTES`, `25È OPEN XXX MEMORIAL JOAQUIN DOMINGO`).

Substring matching either way fails for these — neither is contained
in the other. Instead we extract a small set of well-known *venue
keywords* from each name and compare those sets. Two Open names refer
to the same Open iff their keyword sets intersect.

A small alias map handles the only naming oddity in the catalogue:
the Memorial Joaquin/Joaquim Domingo is the Sants Open's PDF title.

Used by:
  * `api/app.py` — to decide if the diff against the official PDF is
    comparing the same set of Opens.
  * `reglament/ranquing_opens.py` — to map PDF columns onto the DB
    window when applying -20 penalties to the computed ranking.
"""

from __future__ import annotations

import unicodedata


# Known FCB Open venue tokens. Add more here if the FCB adds new
# venues. Stored without diacritics, uppercase.
VENUE_KEYWORDS: tuple[str, ...] = (
    "MATARO",
    "LLINARS",
    "MANRESA",
    "SANT ADRIA",
    "COSTA DAURADA",
    "MOLINS",
    "VIC",
    "TORREDEMBARRA",
    "SANTS",
)

# Aliases: substrings that should also count as a particular venue.
# `MEMORIAL JOAQUIN DOMINGO` is the official PDF name for the Sants
# Open; "JOAQUIM" is the Catalan spelling that occasionally appears.
NAME_ALIASES: dict[str, str] = {
    "JOAQUIN DOMINGO": "SANTS",
    "JOAQUIM DOMINGO": "SANTS",
}


def open_match_keys(name: str | None) -> set[str]:
    """Return the set of venue keywords contained in `name`.

    Strips diacritics and uppercases; checks against `VENUE_KEYWORDS`
    and `NAME_ALIASES`. Empty / None inputs return an empty set.
    """
    if not name:
        return set()
    nfkd = unicodedata.normalize("NFD", name)
    no_accents = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    upper = no_accents.upper()
    keys: set[str] = set()
    for kw in VENUE_KEYWORDS:
        if kw in upper:
            keys.add(kw)
    for alias, target in NAME_ALIASES.items():
        if alias in upper:
            keys.add(target)
    return keys


def map_pdf_columns_to_window(
    pdf_open_names: list[str],
    window_open_names: list[str],
) -> dict[int, int]:
    """Bipartite-match each PDF column index to a window-Open index.

    Returns `{pdf_index: window_index}`. A PDF column is matched to
    the FIRST not-yet-claimed window Open whose keyword set intersects.
    A column with no match is omitted. The function is symmetric:
    `len(returned) == len(pdf_open_names)` only if every PDF column
    found a unique partner.
    """
    pdf_keys = [open_match_keys(n) for n in pdf_open_names]
    win_keys = [open_match_keys(n) for n in window_open_names]
    result: dict[int, int] = {}
    used: set[int] = set()
    for pi, p in enumerate(pdf_keys):
        if not p:
            continue
        for wi, w in enumerate(win_keys):
            if wi in used:
                continue
            if p & w:
                result[pi] = wi
                used.add(wi)
                break
    return result
