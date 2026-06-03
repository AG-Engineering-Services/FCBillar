from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from .player_matching import match_player
from .reglament.ranquing_opens import OpensRankingEntry
from .scraper.official_pdf import OfficialRanking, OfficialRankingEntry


@dataclass(frozen=True)
class PlayerRef:
    display_name: str
    club: str | None
    player_id: int | None


@dataclass(frozen=True)
class Discrepancy:
    kind: str
    player: PlayerRef
    official_position: int | None
    computed_position: int | None
    official_total: int | None
    computed_total: int | None
    details: str
    n_penalties: int | None = None


@dataclass(frozen=True)
class DiffReport:
    official_source: str
    official_size: int
    computed_size: int
    matched_count: int
    discrepancies: tuple[Discrepancy, ...]
    penalty_adjusted_count: int = 0
    penalty_cascade_count: int = 0
    source_mismatch_count: int = 0
    position_cascade_count: int = 0

    @property
    def is_clean(self) -> bool:
        return len(self.discrepancies) == 0


@dataclass(frozen=True)
class MatchPair:
    official: OfficialRankingEntry
    computed: OpensRankingEntry


_KIND_ORDER = {
    "position_only": 0,
    "total_points": 1,
    "per_open": 2,
    "penalty_expected": 3,
    "penalty_cascade": 4,
    "position_cascade": 5,
    "source_mismatch": 6,
    "missing_in_official": 7,
    "missing_in_computed": 8,
}

_DISPLACED_KINDS = frozenset({
    "source_mismatch",
    "penalty_cascade",
    "penalty_expected",
    "total_points",
    "per_open",
    "missing_in_official",
})

_PENALTY_POINTS = -20
_PENALTY_TOLERANCE = 2


def _negative_points_summary(off: OfficialRankingEntry) -> tuple[int, int]:
    """Return (count, abs_sum) of negative points_per_open values (e.g. -20 no-show)."""
    negatives = [p for p in off.points_per_open if p is not None and p < 0]
    return len(negatives), -sum(negatives)


def _is_explained_by_penalties(off: OfficialRankingEntry, comp: OpensRankingEntry) -> bool:
    """Return True if the total_points gap can be fully attributed to -20
    penalties that the PDF has but the DB does not store.

    The DB omits no-show rows entirely, so `comp.total_points` misses the
    penalty delta. If `official_total + |sum_of_negatives| ≈ computed_total`
    (within ±_PENALTY_TOLERANCE), the discrepancy is structural, not a bug.
    """
    count, abs_sum = _negative_points_summary(off)
    if count == 0:
        return False
    expected = off.total_points + abs_sum
    return abs(expected - comp.total_points) <= _PENALTY_TOLERANCE


def _is_source_mismatch(off: OfficialRankingEntry, comp: OpensRankingEntry) -> bool:
    """Return True if PDF and HTML disagree about WHICH Opens the player
    participated in. The official PDF and the individual-Open HTML pages
    come from the same FCB backend but are generated at different times,
    and occasionally attribute a player's participations to different
    Open columns. This is a source-side inconsistency we can't resolve
    from our side.

    Signature: the set of Open columns with a non-None, non-penalty value
    in the PDF differs from the set with a non-None value in the calc.
    We exclude negative PDF values (-20 penalties) since those are a
    separate signal handled by `_is_explained_by_penalties`.
    """
    off_cols = {
        i for i, v in enumerate(off.points_per_open)
        if v is not None and v > 0
    }
    calc_cols = {
        i for i, b in enumerate(comp.breakdown)
        if b.points is not None and b.points > 0
    }
    return off_cols != calc_cols


def _is_penalty_cascade(
    discrepancy: Discrepancy,
    n_opens_in_window: int,
) -> bool:
    """Return True if a TOTAL_POINTS discrepancy is likely explained by
    the penalty cascade effect.

    When a player gets a -20 at Open X, the PDF still counts them as
    occupying a position in that Open's ranking. Every player below them
    in the PDF ends up 1 position lower than in our HTML-scraped BD
    (which omits no-show rows entirely), worth ~1 point less at their
    band. Across a window of N Opens, a single player can accumulate up
    to N such -1 shifts.

    Heuristic: diff = off - calc is in [-2*N, 0]. The sign must be
    non-positive because the cascade ALWAYS makes the PDF total lower
    than the calc total (positions in the PDF are worse). The tolerance
    is 2*N to also cover the rare case of two penalized players above
    in the same Open.
    """
    if discrepancy.kind != "total_points":
        return False
    if discrepancy.official_total is None or discrepancy.computed_total is None:
        return False
    diff = discrepancy.official_total - discrepancy.computed_total
    lower_bound = -2 * n_opens_in_window
    return lower_bound <= diff <= 0


def _pair_rankings(
    official: OfficialRanking,
    computed: Sequence[OpensRankingEntry],
) -> tuple[list[MatchPair], list[OfficialRankingEntry], list[OpensRankingEntry]]:
    by_computed_name = {entry.display_name: entry for entry in computed}
    unmatched_computed = set(by_computed_name.keys())

    pairs: list[MatchPair] = []
    missing_in_computed: list[OfficialRankingEntry] = []

    for off in official.entries:
        candidates = sorted(unmatched_computed)
        best = match_player(off.display_name, candidates)
        if best is None:
            missing_in_computed.append(off)
            continue
        name, _ = best
        comp = by_computed_name[name]
        unmatched_computed.remove(name)
        pairs.append(MatchPair(official=off, computed=comp))

    missing_in_official = [by_computed_name[name] for name in sorted(unmatched_computed)]
    return pairs, missing_in_computed, missing_in_official


def _short_open_name(idx: int, open_names: list[str] | None) -> str:
    """Return a compact, human-readable Open label for diff messages."""
    if open_names and idx < len(open_names):
        # Strip the noisy ordinal/`OPEN` prefixes so the venue stands out.
        name = open_names[idx]
        for prefix in ("OPEN TRES BANDES ", "OPEN ", "TRES BANDES "):
            if name.upper().startswith(prefix):
                name = name[len(prefix):]
                break
        return name.strip() or f"Open #{idx + 1}"
    return f"Open #{idx + 1}"


def _open_mismatches(
    off: OfficialRankingEntry,
    comp: OpensRankingEntry,
    open_names: list[str] | None = None,
) -> list[str]:
    """Return a per-Open list of cells where PDF and calc differ.

    Each element looks like `"MATARO: oficial=165 calculat=—"`. When
    open_names is None we fall back to numeric column labels. The
    cell value `None` (no row) renders as `—` so the message reads
    naturally regardless of which side is missing.
    """
    mismatches: list[str] = []
    comp_points = [b.points for b in comp.breakdown]
    max_len = max(len(off.points_per_open), len(comp_points))
    fmt = lambda v: "—" if v is None else str(v)
    for idx in range(max_len):
        o = off.points_per_open[idx] if idx < len(off.points_per_open) else None
        c = comp_points[idx] if idx < len(comp_points) else None
        if o != c:
            label = _short_open_name(idx, open_names)
            mismatches.append(f"{label}: oficial={fmt(o)} calculat={fmt(c)}")
    return mismatches


def collect_clean_matches(
    official: OfficialRanking,
    computed: Sequence[OpensRankingEntry],
) -> tuple[MatchPair, ...]:
    """Return matched pairs without any discrepancy."""
    pairs, _, _ = _pair_rankings(official, computed)
    computed_position = {entry.display_name: idx + 1 for idx, entry in enumerate(computed)}
    clean: list[MatchPair] = []
    for pair in pairs:
        off = pair.official
        comp = pair.computed
        if off.total_points != comp.total_points:
            continue
        if off.position != computed_position.get(comp.display_name):
            continue
        if _open_mismatches(off, comp):
            continue
        clean.append(pair)
    return tuple(clean)


def pair_rankings(
    official: OfficialRanking,
    computed: Sequence[OpensRankingEntry],
) -> tuple[MatchPair, ...]:
    """Return official/computed match pairs used by the diff algorithm."""
    pairs, _, _ = _pair_rankings(official, computed)
    return tuple(pairs)


def diff_rankings(
    official: OfficialRanking,
    computed: Sequence[OpensRankingEntry],
    matcher_player_lookup: Callable[[str], int | None],
) -> DiffReport:
    """Compare official vs computed Open rankings and return discrepancies."""
    discrepancies: list[Discrepancy] = []

    # Use the PDF's own Open titles for diff details so users see e.g.
    # "MATARO: oficial=165 calculat=—" instead of "Open #1: ...".
    open_names = [o.full_name for o in official.opens]

    computed_position = {entry.display_name: idx + 1 for idx, entry in enumerate(computed)}
    pairs, missing_in_computed, missing_in_official = _pair_rankings(official, computed)

    matched_count = 0

    for pair in pairs:
        off = pair.official
        comp = pair.computed
        player = PlayerRef(
            display_name=off.display_name,
            club=off.club or comp.club,
            player_id=matcher_player_lookup(comp.display_name),
        )
        off_pos = off.position
        comp_pos = computed_position.get(comp.display_name)

        if off.total_points == comp.total_points and off_pos != comp_pos:
            discrepancies.append(
                Discrepancy(
                    kind="position_only",
                    player=player,
                    official_position=off_pos,
                    computed_position=comp_pos,
                    official_total=off.total_points,
                    computed_total=comp.total_points,
                    details="probable diferència de tiebreak",
                )
            )
            continue

        if off.total_points != comp.total_points:
            if _is_explained_by_penalties(off, comp):
                n_penalties, _ = _negative_points_summary(off)
                negative_opens = [
                    _short_open_name(i, open_names)
                    for i, p in enumerate(off.points_per_open)
                    if p is not None and p < 0
                ]
                discrepancies.append(
                    Discrepancy(
                        kind="penalty_expected",
                        player=player,
                        official_position=off_pos,
                        computed_position=comp_pos,
                        official_total=off.total_points,
                        computed_total=comp.total_points,
                        details=(
                            f"oficial={off.total_points} calculat={comp.total_points}"
                            f" — {n_penalties} × {_PENALTY_POINTS} a "
                            f"{', '.join(negative_opens) if negative_opens else 'desconegut'}"
                            f" (no emmagatzemat a la BD)"
                        ),
                        n_penalties=n_penalties,
                    )
                )
                continue
            # For real total_points discrepancies, list every Open that
            # contributes to the gap so the user knows where to look.
            mismatches = _open_mismatches(off, comp, open_names)
            details = f"oficial={off.total_points} calculat={comp.total_points}"
            if mismatches:
                details += f" — diferències per Open: {'; '.join(mismatches)}"
            discrepancies.append(
                Discrepancy(
                    kind="total_points",
                    player=player,
                    official_position=off_pos,
                    computed_position=comp_pos,
                    official_total=off.total_points,
                    computed_total=comp.total_points,
                    details=details,
                )
            )
            continue

        mismatches = _open_mismatches(off, comp, open_names)
        if mismatches:
            discrepancies.append(
                Discrepancy(
                    kind="per_open",
                    player=player,
                    official_position=off_pos,
                    computed_position=comp_pos,
                    official_total=off.total_points,
                    computed_total=comp.total_points,
                    details="; ".join(mismatches),
                )
            )
            continue

        matched_count += 1

    for off in missing_in_computed:
        discrepancies.append(
            Discrepancy(
                kind="missing_in_computed",
                player=PlayerRef(
                    display_name=off.display_name,
                    club=off.club,
                    player_id=matcher_player_lookup(off.display_name),
                ),
                official_position=off.position,
                computed_position=None,
                official_total=off.total_points,
                computed_total=None,
                details="No s'ha trobat cap match a la BD",
            )
        )

    for comp in missing_in_official:
        discrepancies.append(
            Discrepancy(
                kind="missing_in_official",
                player=PlayerRef(
                    display_name=comp.display_name,
                    club=comp.club,
                    player_id=matcher_player_lookup(comp.display_name),
                ),
                official_position=None,
                computed_position=computed_position.get(comp.display_name),
                official_total=None,
                computed_total=comp.total_points,
                details="Jugador present al càlcul però absent al PDF oficial",
            )
        )

    # Source-mismatch reclassification must run before penalty_cascade so that
    # small-diff entries with mismatched Open attribution aren't absorbed by the
    # cascade heuristic (which only looks at diff magnitude).
    pair_by_name = {p.official.display_name: p for p in pairs}
    for i, d in enumerate(discrepancies):
        if d.kind not in ("total_points", "per_open"):
            continue
        pair = pair_by_name.get(d.player.display_name)
        if pair is None:
            continue
        if _is_source_mismatch(pair.official, pair.computed):
            diff = (d.official_total or 0) - (d.computed_total or 0)
            discrepancies[i] = replace(
                d,
                kind="source_mismatch",
                details=(
                    f"oficial={d.official_total} calculat={d.computed_total} "
                    f"diff={diff:+d} "
                    "(PDF i HTML atribueixen participacions a Opens diferents)"
                ),
            )

    n_opens = len(official.opens)
    for i, d in enumerate(discrepancies):
        if _is_penalty_cascade(d, n_opens):
            diff = (d.official_total or 0) - (d.computed_total or 0)
            discrepancies[i] = replace(
                d,
                kind="penalty_cascade",
                details=(
                    f"oficial={d.official_total} calculat={d.computed_total} "
                    f"diff={diff:+d} "
                    "(desplaçament de posicions per penalitzacions -20 al PDF)"
                ),
            )

    # Position-cascade reclassification: a POSITION_ONLY entry is just a side
    # effect of upstream displaced entries. For player P at PDF pos N, calc pos M:
    #   delta = M - N
    #   intruders = entries above P in calc that should be below P in PDF
    #   extruders = entries below P in calc that should be above P in PDF
    #   net_displacement = intruders - extruders
    # If net_displacement == delta, the cascade fully explains the position diff
    # and our tiebreak logic is correct on the underlying data.
    # Must run after source_mismatch / penalty_cascade so kinds are final.
    displaced: list[tuple[int, int | None]] = []  # (calc_pos, pdf_pos)
    for d in discrepancies:
        if d.kind in _DISPLACED_KINDS and d.computed_position is not None:
            displaced.append((d.computed_position, d.official_position))
    for i, d in enumerate(discrepancies):
        if d.kind != "position_only":
            continue
        if d.official_position is None or d.computed_position is None:
            continue
        pdf_pos = d.official_position
        calc_pos = d.computed_position
        delta = calc_pos - pdf_pos
        intruders = sum(
            1 for cp, pp in displaced
            if cp < calc_pos and (pp is None or pp > pdf_pos)
        )
        extruders = sum(
            1 for cp, pp in displaced
            if cp > calc_pos and pp is not None and pp < pdf_pos
        )
        if intruders - extruders == delta:
            discrepancies[i] = replace(
                d,
                kind="position_cascade",
                details=(
                    f"oficial={pdf_pos} calculat={calc_pos} "
                    f"(desplaçat {delta:+d} per intruders={intruders} extruders={extruders})"
                ),
            )

    discrepancies.sort(
        key=lambda d: (
            _KIND_ORDER.get(d.kind, 999),
            d.official_position if d.official_position is not None else (d.computed_position or 99999),
        )
    )

    counts: dict[str, int] = {}
    for d in discrepancies:
        counts[d.kind] = counts.get(d.kind, 0) + 1

    return DiffReport(
        official_source=official.source_url,
        official_size=len(official.entries),
        computed_size=len(computed),
        matched_count=matched_count,
        discrepancies=tuple(discrepancies),
        penalty_adjusted_count=counts.get("penalty_expected", 0),
        penalty_cascade_count=counts.get("penalty_cascade", 0),
        source_mismatch_count=counts.get("source_mismatch", 0),
        position_cascade_count=counts.get("position_cascade", 0),
    )
