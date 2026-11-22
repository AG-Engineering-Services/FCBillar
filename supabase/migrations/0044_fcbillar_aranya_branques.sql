-- FCBillar cloud schema: el detall de cada branca de l'aranya de la fitxa.
--
-- En tocar una branca, la fitxa ensenya les partides d'aquella franja i la
-- mitjana que tenia el rival quan es van jugar. Per saber-ho calen:
--   * a cada partida, la mitjana de rànquing de cada jugador en aquell moment
--     (la del snapshot on la partida entra a la finestra; NULL si no en tenia:
--     llavors la web hi posa la mitjana de la partida, com el càlcul de franges);
--   * a cada franja, els límits [rating_min, rating_max) (NULL = oberta).
-- Ho omplen cloud_sync.publish_games i publish_rating_buckets.

alter table fcbillar.games
    add column if not exists mitjana_rank1 double precision,
    add column if not exists mitjana_rank2 double precision;

alter table fcbillar.player_rating_buckets
    add column if not exists rating_min double precision,
    add column if not exists rating_max double precision;
