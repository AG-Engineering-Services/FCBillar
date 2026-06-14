-- FCBillar cloud schema — penalitzacions federatives a la classificació de lliga.
--
-- La federació de vegades resta punts a un equip (sanció) sense publicar-ho com
-- a fet separat: només es veu com a menys PM dels que tocarien per les victòries.
-- publish_lliga ara pren posició i punts de la classificació OFICIAL i, quan els
-- punts oficials són inferiors als esperats (3·G + 1·E), desa la diferència aquí
-- perquè el frontend pugui marcar la sanció. NULL = sense sanció.

alter table fcbillar.lliga_standings
    add column if not exists penalitzacio integer;
