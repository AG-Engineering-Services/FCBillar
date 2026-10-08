"""Derivació del mes/any que representa un rànquing a partir de la seva data
de publicació real: la de la seva fila a l'índex públic de rànquings
(`intranet.fcbillar.cat/frontend/rankings/llistat`; abans de l'agost de 2026,
`/ca/jugador/ranking/historial`).

L'índex és l'única font autoritativa que lliga `num_seq` ↔ data exacta.
`num_seq` és l'`idranking` de la federació tal qual i pot fer salts: el 125 no
s'ha publicat mai, i després del 124 (27-07-2026, agost) ve el 126 (02-10-2026,
octubre). No s'han de renumerar ni omplir: qui llegeix ordena per `num_seq` i
per `data_pub`, i tots dos segueixen creixent alhora.
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

# Etiquetes fixades a mà, quan la derivada de la data no és la que fa servir la
# federació. Manen sobre el càlcul i sobreviuen a les reingestes (que si no
# tornarien a derivar el mes i desfarien la correcció).
#
#   124 → AGOST 2026 (decisió de l'usuari, 27-07-2026). Publicat el 27 de juliol,
#   la regla el faria de setembre, com tots els de finals de juliol des del 2015
#   (3, 14, 25, 36, 47, 58, 69, 80, 91, 102, 113: cap any no ha tingut rànquing
#   d'agost). Aquest sí.
_MONTH_OVERRIDES: dict[int, tuple[int, int]] = {
    124: (2026, 8),
}


def month_for_publication_date(d: date, num_seq: int | None = None) -> tuple[int, int]:
    """Retorna (any, mes) del rànquing publicat el dia `d`.

    Amb `num_seq`, una etiqueta fixada a `_MONTH_OVERRIDES` mana sobre el càlcul.
    """
    if num_seq is not None and num_seq in _MONTH_OVERRIDES:
        return _MONTH_OVERRIDES[num_seq]
    y, m = d.year, d.month
    last_day = calendar.monthrange(y, m)[1]
    if last_day - d.day <= _END_OF_MONTH_MARGIN:
        m += 1
        if m == 13:
            y, m = y + 1, 1
    if m == 8:  # no hi ha rànquing d'agost
        m = 9
    return y, m
