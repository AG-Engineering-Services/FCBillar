"""Derivació del mes/any que representa un rànquing a partir de la seva data
de publicació real (la que dona `/ca/jugador/ranking/historial`).

L'historial és l'única font autoritativa que lliga `num_seq` ↔ data exacta.
Aquesta funció converteix aquella data en l'etiqueta (any, mes) del rànquing,
substituint la vella heurística monòtona ("un rànquing per mes, salta l'agost")
que derivava la primera vegada que la federació es desviava de la cadència.

Convenció (verificada contra l'historial real, 0 discrepàncies a la finestra
98–112): un rànquing publicat als ÚLTIMS ~5 dies del mes és el rànquing del mes
SEGÜENT; l'agost no té rànquing (es publica a finals de juliol i s'etiqueta com
a setembre).
"""

from __future__ import annotations

import calendar
from datetime import date

# Marge (dies abans de final de mes) a partir del qual la publicació es
# considera del mes vinent. Tots els casos reals observats publiquen o bé a
# principi de mes (dies 1–9) o bé els últims 0–2 dies; 5 és un coixí segur.
_END_OF_MONTH_MARGIN = 5


def month_for_publication_date(d: date) -> tuple[int, int]:
    """Retorna (any, mes) del rànquing publicat el dia `d`."""
    y, m = d.year, d.month
    last_day = calendar.monthrange(y, m)[1]
    if last_day - d.day <= _END_OF_MONTH_MARGIN:
        m += 1
        if m == 13:
            y, m = y + 1, 1
    if m == 8:  # no hi ha rànquing d'agost
        m = 9
    return y, m
