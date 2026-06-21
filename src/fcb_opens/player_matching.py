from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from difflib import SequenceMatcher

from .models import Player

_GREETING_PREFIXES = {
    "SR",
    "SRA",
    "SENYOR",
    "SENYORA",
    "MR",
    "MRS",
    "DR",
    "DRA",
    "DON",
    "DONA",
}

_ABBREVIATIONS = {
    "HDEZ": "HERNANDEZ",
}

# Given-name variants that refer to the same person across FCB sources: the
# monthly ranking may store the Catalan form while the live tournament page
# shows the Spanish one (or vice-versa). Canonicalised to a single form so
# surname-anchored matching links them. Extend as new cases surface.
_GIVEN_NAME_ALIASES = {
    "ARMANDO": "ARMAND",
}

# Single per-token rewrite table applied during matching normalization.
_TOKEN_ALIASES = {**_ABBREVIATIONS, **_GIVEN_NAME_ALIASES}


def _strip_accents(value: str) -> str:
    nfkd = unicodedata.normalize("NFD", value)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def normalize_for_matching(name: str) -> str:
    """Return an aggressive normalized name for fuzzy player matching."""
    text = _strip_accents(name.strip().upper())
    text = re.sub(r"[^A-Z0-9\s]", " ", text)
    tokens = [t for t in text.split() if t]
    while tokens and tokens[0] in _GREETING_PREFIXES:
        tokens.pop(0)
    expanded = [_TOKEN_ALIASES.get(tok, tok) for tok in tokens]
    return " ".join(expanded)


def name_tokens(name: str) -> tuple[str, ...]:
    """Split a player name into significant normalized tokens."""
    norm = normalize_for_matching(name)
    return tuple(tok for tok in norm.split() if tok)


def _name_parts(name: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    raw = _strip_accents(name.strip().upper())
    parts = raw.split(",", 1)
    left = normalize_for_matching(parts[0])
    right = normalize_for_matching(parts[1]) if len(parts) == 2 else ""
    return tuple(left.split()), tuple(right.split())


def match_player(
    target: str,
    candidates: list[str],
    threshold: float = 0.7,
) -> tuple[str, float] | None:
    """Return the best candidate and score for a target player name."""
    if not candidates:
        return None

    target_norm = normalize_for_matching(target)
    target_tokens = name_tokens(target)
    target_surnames, target_given = _name_parts(target)

    best_name: str | None = None
    best_score = -1.0

    for candidate in candidates:
        cand_norm = normalize_for_matching(candidate)
        cand_tokens = name_tokens(candidate)
        cand_surnames, cand_given = _name_parts(candidate)

        if cand_norm == target_norm:
            score = 1.0
        elif len(target_tokens) >= 2 and len(cand_tokens) >= 2 and target_tokens[:2] == cand_tokens[:2]:
            score = 0.9
        elif (
            target_surnames
            and cand_surnames
            and target_surnames[0] == cand_surnames[0]
            and target_given
            and cand_given
            and target_given[0][0] == cand_given[0][0]
        ):
            score = 0.8
        else:
            score = SequenceMatcher(None, target_norm, cand_norm).ratio()

        if score > best_score:
            best_name = candidate
            best_score = score

    if best_name is None or best_score < threshold:
        return None
    return best_name, best_score


def build_matcher(db_players: list[Player]) -> Callable[[str], Player | None]:
    """Build a reusable player matcher for repeated lookups against DB players."""
    by_exact: dict[str, Player] = {}
    by_name: dict[str, Player] = {}

    for player in db_players:
        norm = normalize_for_matching(player.display_name)
        by_exact.setdefault(norm, player)
        by_name.setdefault(player.display_name, player)

    candidate_names = list(by_name.keys())

    def _lookup(name: str) -> Player | None:
        norm = normalize_for_matching(name)
        exact = by_exact.get(norm)
        if exact is not None:
            return exact
        result = match_player(name, candidate_names)
        if result is None:
            return None
        matched_name, _ = result
        return by_name[matched_name]

    return _lookup
