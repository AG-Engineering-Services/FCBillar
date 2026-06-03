"""Data models for FCB rankings and Open classifications.

Everything is a plain dataclass: we don't need Pydantic at this stage.
Name normalization lives here because every cross-source match
(ranking ↔ open classification ↔ inscriptions list) goes through it.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

# Trailing FCB team suffix: a quoted short token at the end of a name,
# e.g. `B.C. GRANOLLERS "A"`, `SBPE. CENTELLES "B"`. The base club is
# the same across all team variants, so for club identity we drop the
# suffix and keep the rest.
_TEAM_SUFFIX_RE = re.compile(r'\s*"[^"]+"\s*$')

# Strip the generic Catalan billiard-club prefix (C.B. / B.C.) when
# computing canonical keys — Lliga sometimes drops it (e.g.
# `SANT ADRIÀ "A"`) while Opens always keeps it (`C.B.SANT ADRIÀ`).
# Both should resolve to the same club. We only strip these two
# common prefixes; SB / SBPE / etc. are real club roots.
_CANONICAL_PREFIX_RE = re.compile(r"^(CB|BC)(?=[A-Z])")

# Manual aliases for known typos / synonyms that the punctuation/case
# normalizer can't catch (e.g. "SANTA ADRIÀ" is a typo for "SANT ADRIÀ"
# in some Lliga rosters — there is no female saint Adrià).
_CANONICAL_ALIASES = {
    "SANTAADRIA": "SANTADRIA",
}


def normalize_name(name: str) -> str:
    """Return a canonical form of a player name for cross-source matching.

    The FCB publishes names in "SURNAME SURNAME, GIVEN" format but with
    occasional variations: accents, extra spaces, case differences, and
    abbreviations like "Mª" vs "MARIA". This function strips diacritics,
    uppercases, and collapses whitespace.

    It does NOT attempt to resolve abbreviations — if a player appears as
    "JOSEP Mª" in one source and "JOSEP MARIA" in another, the caller must
    handle that with an alias table.
    """
    nfkd = unicodedata.normalize("NFD", name)
    without_accents = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    return " ".join(without_accents.upper().split())


def normalize_club(value: str | None) -> str | None:
    """Return None for empty/missing club values, else the trimmed string."""
    if value is None:
        return None
    v = value.strip()
    if v == "" or v.lower() == "cap":
        return None
    return v


def extract_club_name(value: str | None) -> str | None:
    """Return the canonical club name without team suffix.

    `B.C. GRANOLLERS "A"` → `B.C. GRANOLLERS`
    `SB FOMENT MOLINS "C"` → `SB FOMENT MOLINS`
    `B.C. GRANOLLERS` → `B.C. GRANOLLERS` (idempotent)
    `Cap` / `""` / None → None

    Used wherever we want club *identity* (the institution) rather than
    *team identity* (which squad of that club a player appeared with).
    """
    normalized = normalize_club(value)
    if normalized is None:
        return None
    stripped = _TEAM_SUFFIX_RE.sub("", normalized).strip()
    return stripped or normalized


def canonical_club_key(value: str | None) -> str | None:
    """Aggressive identity key for club deduplication.

    Strips team suffix, diacritics, all whitespace, dots, commas,
    apostrophes and dashes; uppercases; strips the generic
    `CB`/`BC` Catalan-billiard prefix; applies known aliases. Two
    strings collide on this key if they refer to the same club
    regardless of formatting variants in the FCB sources.

    `C.B.Vilanova`, `C.B. Vilanova`, `C.B. VILANOVA` → `VILANOVA`
    `B.C. GRANOLLERS "A"`, `BC GRANOLLERS` → `GRANOLLERS`
    `C.B.SANT ADRIÀ`, `SANT ADRIÀ "A"`, `SANTA ADRIÀ "D"` → `SANTADRIA`
    `S.B.F.MOLINS`, `S.B.F. MOLINS` → `SBFMOLINS`
    None / empty / "Cap" → None

    The original display form is preserved separately by the caller —
    this function returns ONLY the matching key, never a display value.
    """
    base = extract_club_name(value)
    if base is None:
        return None
    nfkd = unicodedata.normalize("NFD", base)
    no_accents = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    key = re.sub(r"[\s.,'\-]+", "", no_accents.upper())
    key = _CANONICAL_PREFIX_RE.sub("", key)
    return _CANONICAL_ALIASES.get(key, key)


@dataclass(frozen=True)
class Player:
    """Minimal player identity. Club is tracked separately because a player
    may change club across seasons."""

    display_name: str
    club: str | None = None

    @property
    def normalized(self) -> str:
        return normalize_name(self.display_name)


@dataclass
class RankingEntry:
    """One row of the monthly FCB Carambola ranking.

    FCB columns are: #, Jugador, MJ, Punts*, Definitiu**
    - MJ: mitjana general (decimal)
    - Punts* (format "aconseguits/possibles"): partides puntuables
      jugades vs màxim comptabilitzat
    - Definitiu**: "Definitiva" si s'han jugat les partides mínimes,
      altrament "Provisional"
    """

    position: int
    player_name: str
    average: float
    matches_scored: int
    matches_max: int
    is_definitive: bool
    club: str | None = None


@dataclass
class MonthlyRanking:
    """A full monthly ranking snapshot."""

    month_id: int  # FCB increments this monthly; 120 = March 2026
    fetched_at: date
    entries: list[RankingEntry] = field(default_factory=list)

    def by_normalized_name(self, name: str) -> RankingEntry | None:
        key = normalize_name(name)
        for e in self.entries:
            if normalize_name(e.player_name) == key:
                return e
        return None


@dataclass
class OpenClassificationEntry:
    """One row of an individual Open final classification.

    FCB columns: #, Jugador, Club, PJ, Punts, CAR, ENT, MG, MP, SM
    """

    position: int
    player_name: str
    club: str | None
    matches_played: int  # PJ
    match_points: int  # Punts (2 per win, 1 per draw, 0 per loss)
    caramboles: int  # CAR
    entries: int  # ENT
    general_average: float  # MG
    particular_average: float  # MP
    best_series: int  # SM


@dataclass
class Open:
    """An Open tournament with its final classification."""

    fcb_division_id: int  # e.g. 204 for Manresa
    fcb_classification_id: int  # e.g. 439
    name: str  # "XXIII CIUTAT DE MANRESA"
    season: str  # "2025-26"
    classification: list[OpenClassificationEntry] = field(default_factory=list)
