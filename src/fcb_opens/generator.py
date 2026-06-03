"""Tournament group generator.

Given an inscription count N (sorted via Art. XVIII.5), produces the
complete phase structure following Articles VIII-IX of the Reglament
Opens Tres Bandes.

Closed-form structure (derived from the federation's "fill-cascade"
rule with a hard cap of 16 groups per phase):

    G1 = 16                              # P always 16 groups
    overflow = (N - 64) // 2
    G2 = min(16, max(0, overflow))       # PP groups
    G3 = max(0, overflow - 16)           # PPP groups

Seed allocation by phase (positions are 1-indexed inscription ranks):

    1..16                       → KO direct
    17..48                      → P rows 1-2     (always 32)
    next (16 - G2)              → P row 3 directes
    next 2·G2                   → PP rows 1-2
    next (G2 - G3)              → PP row 3 directes
    next 3·G3                   → PPP (all directes)

The implicit "rescue" rule emerges naturally: every row-3 slot not
filled by a direct seed becomes a placeholder for a winner from the
phase below, so the cascading-fill the federation describes verbally
collapses into the placeholder count per phase.

Supported range: N in [64, 128], even. N=128 saturates the 16-group
cap on all three prèvies. Outside this range raises NotImplementedError
with a descriptive message.

The 120-player case (G2=16, G3=12) is verified verbatim against the
30è Memorial Joaquim Domingo PDFs in tests/test_generator.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .reglament.serp import serpentine_layout


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GroupSlot:
    """One seat in a group.

    Either refers to an inscription list position (1-indexed) via
    `inscription_position`, or to a placeholder for a future advancer
    from a lower phase via `placeholder_rank` + `placeholder_phase`
    (e.g. "1-PPP" means the best PPP winner by mitjana within PPP).
    """

    inscription_position: int | None = None
    placeholder_rank: int | None = None
    placeholder_phase: str | None = None

    @classmethod
    def direct(cls, position: int) -> "GroupSlot":
        return cls(inscription_position=position)

    @classmethod
    def from_phase(cls, phase: str, rank: int) -> "GroupSlot":
        return cls(placeholder_rank=rank, placeholder_phase=phase)

    @property
    def label(self) -> str:
        if self.inscription_position is not None:
            return str(self.inscription_position)
        return f"{self.placeholder_rank}-{self.placeholder_phase}"

    def __repr__(self) -> str:
        return self.label


@dataclass
class Group:
    """A single group in a phase, identified by its letter label."""

    label: str
    slots: list[GroupSlot] = field(default_factory=list)


@dataclass
class Phase:
    """A full phase of the competition (PPP, PP, or P)."""

    name: str
    groups: list[Group] = field(default_factory=list)


@dataclass
class Tournament:
    """The complete phase structure for an Open.

    `phases` is a dict keyed by phase name ("PPP", "PP", "P") that
    contains only the phases actually used for the given N. Phases
    with zero groups are omitted entirely.
    """

    num_inscriptions: int
    phases: dict[str, Phase] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Group label sequences
# --------------------------------------------------------------------------- #

# P phase: single letters A-P (16 labels)
_P_LABELS = ["A", "B", "C", "D", "E", "F", "G", "H",
             "I", "J", "K", "L", "M", "N", "O", "P"]

# PP phase: Q, R, S, T, U, V, W, X, Y, Z, AA-AF (16 labels)
_PP_LABELS = ["Q", "R", "S", "T", "U", "V", "W", "X",
              "Y", "Z", "AA", "AB", "AC", "AD", "AE", "AF"]

# PPP phase: AG-AV (16 labels — enough for the cap of 16 PPP groups at N=128)
_PPP_LABELS = ["AG", "AH", "AI", "AJ", "AK", "AL", "AM", "AN",
               "AO", "AP", "AQ", "AR", "AS", "AT", "AU", "AV"]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


_MIN_INSCRIPTIONS = 64
_MAX_INSCRIPTIONS = 128


def generate_tournament(num_inscriptions: int) -> Tournament:
    """Generate the full phase structure for an Open with `num_inscriptions` players.

    Supports any even N in [64, 128]. Outside this range raises
    NotImplementedError — the federation's behaviour for those edge
    cases hasn't been observed in real Opens and isn't pinned down
    in the reglament with the precision needed to encode it here.
    """
    if num_inscriptions < _MIN_INSCRIPTIONS:
        raise NotImplementedError(
            f"Phase structure for N={num_inscriptions} is not supported. "
            f"Minimum supported is N={_MIN_INSCRIPTIONS}; below that the "
            f"federation typically cancels the Open as unsustainable."
        )
    if num_inscriptions > _MAX_INSCRIPTIONS:
        raise NotImplementedError(
            f"Phase structure for N={num_inscriptions} is not supported. "
            f"Maximum is N={_MAX_INSCRIPTIONS} (3 prèvies × 16 groups); "
            f"a four-level cascade would be needed beyond that."
        )
    if num_inscriptions % 2 != 0:
        raise NotImplementedError(
            f"Odd N={num_inscriptions} is not supported. The 1-player "
            f"rescue rule (rescue from PP to complete a PPP group of 2, "
            f"with 2nds advancing) has not been verified against a real "
            f"published group draw."
        )

    overflow = (num_inscriptions - 64) // 2
    g2 = min(16, max(0, overflow))
    g3 = max(0, overflow - 16)

    # Cursor walks through inscription positions as we hand out directes.
    cursor = 17  # KO consumed positions 1-16

    p_rows_12 = _take(cursor, 32)
    cursor += 32

    n_p_row3_direct = 16 - g2
    p_row3_directs = _take(cursor, n_p_row3_direct)
    cursor += n_p_row3_direct

    pp_rows_12 = _take(cursor, 2 * g2)
    cursor += 2 * g2

    n_pp_row3_direct = g2 - g3
    pp_row3_directs = _take(cursor, n_pp_row3_direct)
    cursor += n_pp_row3_direct

    ppp_all_directs = _take(cursor, 3 * g3)
    cursor += 3 * g3

    assert cursor == num_inscriptions + 1, (
        f"Internal allocation error: cursor={cursor}, "
        f"expected={num_inscriptions + 1} for N={num_inscriptions}"
    )

    phases: dict[str, Phase] = {}

    p_seeds = (
        [GroupSlot.direct(p) for p in p_rows_12]
        + [GroupSlot.direct(p) for p in p_row3_directs]
        + [GroupSlot.from_phase("PP", k) for k in range(1, g2 + 1)]
    )
    p_layout = serpentine_layout(p_seeds, num_groups=16, rows_per_group=3)
    phases["P"] = Phase(
        name="P",
        groups=[Group(label=_P_LABELS[i], slots=p_layout[i]) for i in range(16)],
    )

    if g2 > 0:
        pp_seeds = (
            [GroupSlot.direct(p) for p in pp_rows_12]
            + [GroupSlot.direct(p) for p in pp_row3_directs]
            + [GroupSlot.from_phase("PPP", k) for k in range(1, g3 + 1)]
        )
        pp_layout = serpentine_layout(pp_seeds, num_groups=g2, rows_per_group=3)
        phases["PP"] = Phase(
            name="PP",
            groups=[Group(label=_PP_LABELS[i], slots=pp_layout[i]) for i in range(g2)],
        )

    if g3 > 0:
        ppp_seeds = [GroupSlot.direct(p) for p in ppp_all_directs]
        ppp_layout = serpentine_layout(ppp_seeds, num_groups=g3, rows_per_group=3)
        phases["PPP"] = Phase(
            name="PPP",
            groups=[Group(label=_PPP_LABELS[i], slots=ppp_layout[i]) for i in range(g3)],
        )

    return Tournament(num_inscriptions=num_inscriptions, phases=phases)


def _take(start: int, count: int) -> list[int]:
    return list(range(start, start + count))
