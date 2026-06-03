"""Article IX: serpentine (snake) group layout for fase prèvies.

The FCB uses a specific variant of the snake draw: the first row of
seeds goes FORWARD (group A gets seed 1, group B gets seed 2, ...), and
ALL subsequent rows go REVERSED. This is NOT the classic boustrophedon
pattern (forward/reversed/forward/reversed).

Example — 12 players in 4 groups of 3:

    Row 1 (seeds 1-4) forward:   A=1,  B=2,  C=3,  D=4
    Row 2 (seeds 5-8) reversed:  D=5,  C=6,  B=7,  A=8
    Row 3 (seeds 9-12) reversed: D=9,  C=10, B=11, A=12

Result groups:
    A: [1, 8, 12]
    B: [2, 7, 11]
    C: [3, 6, 10]
    D: [4, 5, 9]

This balances strength: group A has the best top seed but the weakest
mid- and bottom-tier seeds, while group D has the weakest top seed but
the strongest mid- and bottom-tier seeds.

Verified against the 30è Memorial Joaquim Domingo PPP groups published
by CB Sants (36 players in 12 groups of 3).
"""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


def serpentine_layout(
    ordered_items: list[T],
    num_groups: int,
    rows_per_group: int = 3,
) -> list[list[T]]:
    """Distribute ordered_items across num_groups using the FCB serp pattern.

    Args:
        ordered_items: items sorted from strongest (index 0) to weakest.
            Can be shorter than num_groups * rows_per_group; trailing
            groups simply receive fewer items.
        num_groups: number of groups to create.
        rows_per_group: items per group (default 3, matching the FCB's
            3-player group format for fase prèvies).

    Returns:
        List of `num_groups` lists. Each inner list has up to
        `rows_per_group` items, ordered from strongest (seed 1) to
        weakest (seed `rows_per_group`).

    Raises:
        ValueError: if there are more items than capacity or if
            arguments are non-positive.
    """
    if num_groups <= 0:
        raise ValueError(f"num_groups must be positive, got {num_groups}")
    if rows_per_group <= 0:
        raise ValueError(f"rows_per_group must be positive, got {rows_per_group}")

    capacity = num_groups * rows_per_group
    if len(ordered_items) > capacity:
        raise ValueError(
            f"{len(ordered_items)} items exceed capacity {capacity} "
            f"({num_groups} groups × {rows_per_group} rows)"
        )

    groups: list[list[T]] = [[] for _ in range(num_groups)]
    for idx, item in enumerate(ordered_items):
        row = idx // num_groups
        col = idx % num_groups
        target = col if row == 0 else num_groups - 1 - col
        groups[target].append(item)
    return groups
