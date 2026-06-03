"""Article XVII of the Reglament Opens Tres Bandes FCB (14-Juny-2025).

Implements the points-per-position table used to compute the Rànquing
Català d'Opens (Article XVIII: sum of the last 5 Opens).
"""

from __future__ import annotations

# Positions 1 to 80 have explicit values. After 80 the points are piecewise
# constant bands. Values transcribed verbatim from the PDF reglament.
_EXPLICIT_POINTS: dict[int, int] = {
    1: 180, 2: 165, 3: 155, 4: 155, 5: 146, 6: 144, 7: 142, 8: 140,
    9: 132, 10: 131, 11: 130, 12: 129, 13: 128, 14: 127, 15: 126, 16: 125,
    17: 118, 18: 117, 19: 116, 20: 115, 21: 114, 22: 113, 23: 112, 24: 111,
    25: 110, 26: 109, 27: 108, 28: 107, 29: 106, 30: 105, 31: 104, 32: 103,
    33: 95, 34: 94, 35: 93, 36: 92, 37: 91, 38: 90, 39: 89, 40: 88,
    41: 87, 42: 86, 43: 85, 44: 84, 45: 83, 46: 82, 47: 81, 48: 80,
    49: 72, 50: 71, 51: 70, 52: 69, 53: 68, 54: 67, 55: 66, 56: 65,
    57: 64, 58: 63, 59: 62, 60: 61, 61: 60, 62: 59, 63: 58, 64: 57,
    65: 49, 66: 48, 67: 47, 68: 46, 69: 45, 70: 44, 71: 43, 72: 42,
    73: 41, 74: 40, 75: 39, 76: 38, 77: 37, 78: 36, 79: 35, 80: 34,
}

# Sentinel values used elsewhere in the reglament
INCOMPAREIXENCA_INJUSTIFICADA_PENALTY = -20  # Article IV.3
FORCA_MAJOR_POINTS = 0  # Article IV.4 (with supporting documentation)


def points_for_position(position: int) -> int:
    """Return the open points a player gets for finishing at the given position.

    Implements Article XVII.1 of the Reglament Opens Tres Bandes FCB.

    >>> points_for_position(1)
    180
    >>> points_for_position(3)  # podium ties
    155
    >>> points_for_position(4)
    155
    >>> points_for_position(80)
    34
    >>> points_for_position(96)  # last of the 25-point band
    25
    >>> points_for_position(500)  # well into the 12-point tail
    12
    """
    if position < 1:
        raise ValueError(f"Position must be >= 1, got {position}")

    if position <= 80:
        return _EXPLICIT_POINTS[position]
    if position <= 96:  # del 81è al 96è
        return 25
    if position <= 112:  # del 97è al 112è
        return 18
    if position <= 128:  # del 113è al 128è
        return 15
    return 12  # del 129è al final
