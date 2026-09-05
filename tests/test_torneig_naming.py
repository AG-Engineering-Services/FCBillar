"""Tests del nom/tipus canònic dels torneigs (fcbillar.torneig_naming)."""

from __future__ import annotations

import pytest

from fcbillar.torneig_naming import clean_torneig_nom, torneig_tipus


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('VI OPEN MATARÓ "LES SANTES" - OPEN MATARÓ', 'VI OPEN MATARÓ "LES SANTES"'),
        ("I OPEN CIUTAT DE VIC - OPEN VIC", "I OPEN CIUTAT DE VIC"),
        ("OPEN LLIURE MANRESA - OPEN LLIURE MANRESA", "OPEN LLIURE MANRESA"),
        ("OPEN BANDA LLEIDA - OPEN LLEIDA", "OPEN BANDA LLEIDA"),
        ("3 BANDES FEMENÍ - FEMENÍ", "3 BANDES FEMENÍ"),
        ("MEMORIAL MIQUEL ESPONA - DIVISIÓ ÚNICA", "MEMORIAL MIQUEL ESPONA"),
        ("OPEN 3 BANDES LLINARS - I OPEN 3 BANDES", "OPEN 3 BANDES LLINARS"),
    ],
)
def test_clean_removes_redundant_suffix(raw, expected):
    assert clean_torneig_nom(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "TRES BANDES - 1A DIVISIÓ",
        "BANDA - HONOR",
        "LLIURE - 2A DIVISIÓ A",
        "XVI CIUTAT DE MANRESA - MEMORIAL JAUME ARNAU",  # sufix aporta info real
        "QUADRE 47/2 - HONOR",
    ],
)
def test_clean_keeps_meaningful_suffix(raw):
    assert clean_torneig_nom(raw) == raw


@pytest.mark.parametrize(
    "nom",
    [
        # El cas de l'usuari: Memorial Jaume Arnau, amb i sense la paraula OPEN.
        "XVI CIUTAT DE MANRESA - MEMORIAL JAUME ARNAU",
        "XV OPEN CIUTAT DE MANRESA - MEMORIAL JAUME ARNAU",
        "OPEN 3 BANDES MANRESA - MEMORIAL JAUME ARNAU",
        "MEMORIAL MIQUEL ESPONA - DIVISIÓ ÚNICA",
        "II MEMORIAL MIQUEL ESPONA - OPEN VIC",
        'VI OPEN MATARÓ "LES SANTES"',
        "I OPEN C.B. MONFORTE",
    ],
)
def test_tipus_open_for_named_trophies(nom):
    assert torneig_tipus(nom) == "open"


@pytest.mark.parametrize(
    "nom",
    [
        "TRES BANDES - 1A DIVISIÓ",
        "BANDA - HONOR",
        "LLIURE - FEMENÍ",
        "CAMPIONAT CATALUNYA BANDA - 1ª DIVISIÓ",
        "TRES BANDES - FEMENÍ SANT BOI",  # borderline → campionat (decisió usuari)
        "TRES BANDES - GP JUNIOR LA UNIÓ CORAL",  # borderline → campionat
        "5 QUILLES",
        "ARTISTIC",
        "SNOOKER",
    ],
)
def test_tipus_campionat_for_modality_divisions_and_borderline(nom):
    assert torneig_tipus(nom) == "campionat"


def test_tipus_is_stable_across_seasons_for_same_event():
    # El mateix esdeveniment, escrit diferent cada any, sempre dona el mateix tipus.
    variants = [
        "XVI CIUTAT DE MANRESA - MEMORIAL JAUME ARNAU",
        "XV OPEN CIUTAT DE MANRESA - MEMORIAL JAUME ARNAU",
        "OPEN 3 BANDES MANRESA - MEMORIAL JAUME ARNAU",
    ]
    assert {torneig_tipus(v) for v in variants} == {"open"}
