-- FCBillar cloud schema — parcials, caramboles i entrades a la classificació de lliga.
--
-- Base de dades: **Neon** (vegeu 0018). No s'aplica sola: l'admin l'executa amb
-- `psql` i la connexió sense pool.
--
-- La classificació de cada grup només portava els punts de matx (pf/pc). Ara hi
-- van també:
--   ppf / ppc         punts parcials a favor i en contra (2 per partida guanyada,
--                     1 per empatada), que és el primer desempat de la federació;
--   car_f / car_c     caramboles fetes i rebudes, sumant totes les partides;
--   entrades          entrades jugades, sumant totes les partides (les d'una
--                     partida són les mateixes per als dos equips).
-- La mitjana general de l'equip és car_f / entrades, i la calcula qui la llegeix.
--
-- Mentre el Data API no vegi les columnes (fins a mitja hora), publish_lliga
-- publica la classificació sense aquests camps.

alter table fcbillar.lliga_standings
    add column if not exists ppf      integer,
    add column if not exists ppc      integer,
    add column if not exists car_f    integer,
    add column if not exists car_c    integer,
    add column if not exists entrades integer;
