"""Test que la selecció de darrers 15 games amb desempat funciona correctament."""

import pytest
from datetime import date


def select_last_15_games(games):
    """Selecciona els últims 15 games, amb desempat per mitjana si empat de data en frontera 15/16.

    Args:
        games: llista de tuples (data, caramboles, entrades) ordenades per data desc.

    Returns:
        llista d'índex dels games seleccionats (fins a 15 games).
    """
    if len(games) <= 15:
        return list(range(len(games)))

    # Si tenim més de 15 i la 15ena (índex 14) i 16ena (índex 15) són del mateix dia,
    # mantenir la 15ena excepte si la 16ena té millor mitjana.
    selected_idxs = list(range(15))  # indices 0..14 (15 games)

    date_15 = games[14][0]
    date_16 = games[15][0]

    if date_15 == date_16:
        # Comparar mitjanes (caramboles/entrades)
        car_15, ent_15 = games[14][1], games[14][2]
        car_16, ent_16 = games[15][1], games[15][2]

        avg_15 = (car_15 / ent_15) if ent_15 else 0
        avg_16 = (car_16 / ent_16) if ent_16 else 0

        if avg_16 > avg_15:
            # Triar la 16ena en comptes de la 15ena
            selected_idxs[14] = 15

    return selected_idxs


def test_select_last_15_games_less_than_15():
    """Si hi ha menys de 15 games, selecciona tots."""
    games = [
        (date(2026, 5, 2), 32, 19),
        (date(2026, 4, 19), 5, 22),
    ]
    result = select_last_15_games(games)
    assert result == [0, 1]


def test_select_last_15_games_exactly_15():
    """Si hi ha exactament 15 games, selecciona tots."""
    games = [(date(2026, 1, 1 + i), 32, 19) for i in range(15)]
    result = select_last_15_games(games)
    assert result == list(range(15))


def test_select_last_15_games_more_than_15_no_tiebreak():
    """Si hi ha més de 15 games i no empat de data en frontera, selecciona els primers 15."""
    games = [(date(2026, 1, 1 + i), 32, 19) for i in range(20)]
    result = select_last_15_games(games)
    assert result == list(range(15))


def test_select_last_15_games_tiebreak_16_better():
    """Si 15ena i 16ena són del mateix dia i 16ena té millor mitjana, triar 16ena."""
    games = [
        (date(2026, 5, 2), 32, 19),  # 32/19 = 1.68
        (date(2026, 4, 19), 5, 22),
        (date(2026, 3, 15), 40, 21),
        (date(2026, 3, 14), 40, 20),
        (date(2026, 3, 13), 40, 20),
        (date(2026, 3, 12), 40, 20),
        (date(2026, 3, 11), 40, 20),
        (date(2026, 3, 10), 40, 20),
        (date(2026, 3, 9), 40, 20),
        (date(2026, 3, 8), 40, 20),
        (date(2026, 3, 7), 40, 20),
        (date(2026, 3, 6), 40, 20),
        (date(2026, 3, 5), 40, 20),
        (date(2026, 3, 4), 40, 20),
        (date(2026, 1, 10), 20, 10),  # 20/10 = 2.0 (15ena)
        (date(2026, 1, 10), 30, 10),  # 30/10 = 3.0 (16ena, millor mitjana)
        (date(2026, 1, 9), 40, 20),
    ]
    result = select_last_15_games(games)
    # Esperem que s'inclogui la 16ena (índex 15) en comptes de la 15ena (índex 14)
    assert 14 not in result or 15 in result
    assert result[14] == 15  # L'última selecció hauria de ser la 16ena (índex 15)


def test_select_last_15_games_tiebreak_15_better():
    """Si 15ena i 16ena són del mateix dia i 15ena té millor mitjana, mantenir 15ena."""
    games = [
        (date(2026, 5, 2), 32, 19),  # 32/19 = 1.68
        (date(2026, 4, 19), 5, 22),
        (date(2026, 3, 15), 40, 21),
        (date(2026, 3, 14), 40, 20),
        (date(2026, 3, 13), 40, 20),
        (date(2026, 3, 12), 40, 20),
        (date(2026, 3, 11), 40, 20),
        (date(2026, 3, 10), 40, 20),
        (date(2026, 3, 9), 40, 20),
        (date(2026, 3, 8), 40, 20),
        (date(2026, 3, 7), 40, 20),
        (date(2026, 3, 6), 40, 20),
        (date(2026, 3, 5), 40, 20),
        (date(2026, 3, 4), 40, 20),
        (date(2026, 1, 10), 30, 10),  # 30/10 = 3.0 (15ena, millor mitjana)
        (date(2026, 1, 10), 20, 10),  # 20/10 = 2.0 (16ena)
        (date(2026, 1, 9), 40, 20),
    ]
    result = select_last_15_games(games)
    # Esperem que es mantingui la 15ena (índex 14)
    assert result[14] == 14


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
