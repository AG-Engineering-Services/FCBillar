"""Tests de la normalització de categories de lliga (fcbillar.categories)."""

from __future__ import annotations

import pytest

from fcbillar.categories import (
    norm_divisio,
    norm_grup,
    short_divisio_inline,
    unify_modalitat,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1a DIVISIÓ", "1a"),
        ("1a DIVISIÒ", "1a"),  # Ò en lloc de Ó
        ("1º DIVISIÓ", "1a"),  # ordinal masculí
        ("4ª DIVISIÓ", "4a"),  # ordinal femení
        ("4a DIVISIÓ", "4a"),
        ("HONOR", "Honor"),
        ("L'AMISTAT", "L'Amistat"),
        ("ÙNICA", "Única"),
        ("PROMOCIÓ A 1a", "Promoció a 1a"),
    ],
)
def test_norm_divisio(raw, expected):
    assert norm_divisio(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("GRUP A", "A"),
        ("Grup A", "A"),
        ("GRUP D", "D"),
        ("UNIC", "Únic"),
        ("ÙNIC", "Únic"),
        ("ÚNIC", "Únic"),
        ("Grup ùnic", "Únic"),
        ("FINAL 4a DIVISIÓ", "Final"),
        ("FINAL HONOR", "Final"),
        ("Final Four Grup A", "Final Four A"),
        ('SEMIFINALS "A"', "Semifinals A"),
        ("PROMOCIÓ-1", "Promoció 1"),
        ("PROMOCIÓ-2", "Promoció 2"),
        ("PROMOCIÓ HONOR", "Promoció Honor"),
        ("PROMOCIÓ PRIMERA", "Promoció Primera"),
    ],
)
def test_norm_grup(raw, expected):
    assert norm_grup(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("TRES BANDES - 1ª DIVISIÓ", "TRES BANDES - 1a"),
        ("TRES BANDES - 1A DIVISIÒ", "TRES BANDES - 1a"),
        ("LLIURE - 1º DIVISIÓ", "LLIURE - 1a"),
        ('LLIURE - 2A DIVISIÓ "A"', "LLIURE - 2a A"),
        ("LLIURE - 2ª DIVISIÓ B", "LLIURE - 2a B"),
        ("QUADRE 47/2 - 3A DIVISIÓ", "QUADRE 47/2 - 3a"),
        # Sense número (zones d'un open): es deixa intacte.
        ("OPEN ZONA 2 3 BANDES - DIVISIÓ A", "OPEN ZONA 2 3 BANDES - DIVISIÓ A"),
    ],
)
def test_short_divisio_inline(raw, expected):
    assert short_divisio_inline(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("TRES BANDES - 1a", "Tres Bandes - 1a"),
        ("3 BANDES - 1a", "Tres Bandes - 1a"),
        ("CAMPIONAT CATALUNYA 3 BANDES - 1a", "Tres Bandes - 1a"),
        ("TRES BANDES - HONOR", "Tres Bandes - HONOR"),
        ("QUADRE 47/2 - 2a A", "Quadre 47/2 - 2a A"),
        ("QUADRE 71/2 - HONOR", "Quadre 71/2 - HONOR"),
        ("LLIURE - FEMENÍ", "Lliure - FEMENÍ"),
        ("BANDA - 3a", "Banda - 3a"),
        (
            "CAMPIONAT CATALUNYA HISTÒRIC LLIURE - CATEGORIA NO PUBLICADA",
            "Lliure - CATEGORIA NO PUBLICADA",
        ),
        # "BANDES" no s'ha de confondre amb la modalitat "BANDA".
        ("3 BANDES - 2a", "Tres Bandes - 2a"),
    ],
)
def test_unify_modalitat(raw, expected):
    assert unify_modalitat(raw) == expected
