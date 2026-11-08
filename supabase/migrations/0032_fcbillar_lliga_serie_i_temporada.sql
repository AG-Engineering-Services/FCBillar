-- FCBillar cloud schema — la sèrie major a les partides de lliga, i la temporada
-- a cada grup.
--
-- La base de dades és Neon (projecte `fcbillar`). No s'aplica automàticament:
-- l'admin valida el SQL i l'executa amb `psql` i la connexió sense pool.
--
-- 1. SÈRIE MAJOR. `games` la porta de pràcticament totes les partides de lliga
--    (en falten 32 de 30.000), però `lliga_partides` no la tenia i el web no la
--    podia ensenyar. NULL vol dir que no la sabem, no que hagi estat zero.
--
-- 2. TEMPORADA DEL GRUP. Amb les lligues passades publicades, les taules en viu
--    porten quinze temporades. Per llegir-ne una sola cal saber de quina és
--    cada `lliga_id`, i fins ara només es podia deduir de les dates dels
--    encontres, baixant-los tots. Es repeteix a cada grup perquè `lliga_groups`
--    ja és el diccionari que tothom llegeix primer. Format '2025-2026'.
--
-- Només s'afegeixen columnes que admeten NULL: les funcions de publicació
-- d'abans continuen funcionant, i les d'ara publiquen sense aquests camps
-- mentre el Data API no els vegi (`esquema_encara_no_hi_es`).

alter table fcbillar.lliga_partides
    add column if not exists serie_local     integer,
    add column if not exists serie_visitant  integer;

alter table fcbillar.lliga4m_partides
    add column if not exists serie_local     integer,
    add column if not exists serie_visitant  integer;

alter table fcbillar.lliga_groups
    add column if not exists temporada  text;

alter table fcbillar.lliga4m_groups
    add column if not exists temporada  text;

notify pgrst, 'reload schema';
