-- fcbillar.rankings.data_pub — data ISO exacta de publicació del rànquing.
--
-- Prové de l'historial del jugador (/ca/jugador/ranking/historial), l'única
-- font autoritativa que lliga num_seq ↔ data de publicació. És la font de
-- any_pub/mes_pub (substitueix la vella heurística monòtona "1 rànquing/mes,
-- salta l'agost"). Additiva i nul·lable: el sync l'omple progressivament.

alter table fcbillar.rankings
    add column if not exists data_pub date;
