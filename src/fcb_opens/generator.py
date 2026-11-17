"""Tournament group generator.

Given an inscription count N (sorted via Art. XVIII.5), produces the
complete phase structure following Articles VIII-IX of the Reglament
Opens Tres Bandes.

The reglament fixes three things and leaves the rest to N: every prèvia
is played in groups of 3, group winners go through, and "d'entre els
subcampions ... la quantitat que podran accedir ... depenent del número
d'inscrits" (Art. IX.3). The federation's draws follow a cascade:

    Seeds 1..16 go straight to the Fase Final. The Prèvia (P) always has
    16 groups and sends its 16 winners to the setzens, so the remaining
    N - 16 players must be cut down to 48 before P: X = N - 64 players
    are eliminated in the phases below it.

    Going down a level at a time, a full phase (16 groups, winners only)
    eliminates 32. The deepest phase eliminates what is left, E: it plays
    ceil(E/2) groups and, when E is odd, the best second also goes
    through (6 groups for E=11, 7 qualifiers).

    Each phase is filled with direct seeds in order, and the seats left
    over are placeholders for the qualifiers of the phase below.

Verified group by group against eight published draws, from N=78 to
N=124, among them two with N=107 (XIII Open Mataró and X Open Sant
Adrià: six PPP groups, seven qualifiers). They live in
tests/fixtures/sorteig_opens/. The reglament caps an Open at 128
players (Art. X.1), which is three full prèvies; N below 64 would leave
P with fewer than 48 players and the reglament does not say how it is
drawn, so both ends raise NotImplementedError.
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
    def direct(cls, position: int) -> GroupSlot:
        return cls(inscription_position=position)

    @classmethod
    def from_phase(cls, phase: str, rank: int) -> GroupSlot:
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
    """A full phase of the competition (PPP, PP, or P).

    `qualifiers` is how many players go through to the next phase: one
    per group, plus the best second when the phase has to eliminate an
    odd number of players.
    """

    name: str
    groups: list[Group] = field(default_factory=list)
    qualifiers: int = 0

    @property
    def best_seconds(self) -> int:
        return self.qualifiers - len(self.groups)


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


def phase_plan(num_inscriptions: int) -> list[tuple[int, int]]:
    """(groups, qualifiers) per prèvia, from P downwards (see module docstring)."""
    if num_inscriptions < _MIN_INSCRIPTIONS:
        raise NotImplementedError(
            f"Phase structure for N={num_inscriptions} is not supported. "
            f"Minimum supported is N={_MIN_INSCRIPTIONS}: below that the "
            f"Prèvia cannot fill its 16 groups of 3 and the reglament does "
            f"not say how the draw is made."
        )
    if num_inscriptions > _MAX_INSCRIPTIONS:
        raise NotImplementedError(
            f"Phase structure for N={num_inscriptions} is not supported. "
            f"The reglament caps an Open at N={_MAX_INSCRIPTIONS} (Art. X.1)."
        )
    plan = [(16, 16)]
    to_eliminate = num_inscriptions - 64
    while to_eliminate > 0:
        if to_eliminate > 32:
            plan.append((16, 16))
            to_eliminate -= 32
            continue
        groups = -(-to_eliminate // 2)
        plan.append((groups, 3 * groups - to_eliminate))
        to_eliminate = 0
    return plan


_PHASE_NAMES = ("P", "PP", "PPP")
_PHASE_LABELS = {"P": _P_LABELS, "PP": _PP_LABELS, "PPP": _PPP_LABELS}


def generate_tournament(num_inscriptions: int) -> Tournament:
    """Generate the full phase structure for an Open with `num_inscriptions` players.

    Supports any N in [64, 128]; outside that range raises NotImplementedError.
    """
    plan = phase_plan(num_inscriptions)

    cursor = 17  # seeds 1-16 go straight to the Fase Final
    phases: dict[str, Phase] = {}
    for level, (n_groups, qualifiers) in enumerate(plan):
        name = _PHASE_NAMES[level]
        below = _PHASE_NAMES[level + 1] if level + 1 < len(plan) else None
        incoming = plan[level + 1][1] if below else 0
        n_direct = 3 * n_groups - incoming
        seeds = [GroupSlot.direct(p) for p in _take(cursor, n_direct)]
        cursor += n_direct
        if below:
            seeds += [GroupSlot.from_phase(below, k) for k in range(1, incoming + 1)]
        layout = serpentine_layout(seeds, num_groups=n_groups, rows_per_group=3)
        labels = _PHASE_LABELS[name]
        phases[name] = Phase(
            name=name,
            groups=[Group(label=labels[i], slots=layout[i]) for i in range(n_groups)],
            qualifiers=qualifiers,
        )

    assert cursor == num_inscriptions + 1, (
        f"Internal allocation error: cursor={cursor}, "
        f"expected={num_inscriptions + 1} for N={num_inscriptions}"
    )
    return Tournament(num_inscriptions=num_inscriptions, phases=phases)


def _take(start: int, count: int) -> list[int]:
    return list(range(start, start + count))
