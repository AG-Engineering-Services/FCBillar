-- FCBillar cloud schema — la Lliga Catalana de 4 Modalitats.
--
-- La base de dades és Neon (projecte `fcbillar`); el nom de la carpeta és
-- herència. No s'aplica automàticament: l'admin valida el SQL i l'executa amb
-- `psql` i la connexió sense pool.
--
-- La federació juga dues lligues per equips cada temporada: la de Tres Bandes
-- (lliga 34, 36, 38…) i la de 4 Modalitats (35, 37, 39…). Fins ara només es
-- publicava la primera, a `lliga_groups`, `lliga_standings`, `lliga_encontres`
-- i `lliga_partides`.
--
-- SÓN TAULES A PART, i s'hi han de quedar. Qui llegeix les de Tres Bandes
-- —l'app del club i /lliga— no filtra per lliga: una segona lliga a dins se'ls
-- barrejaria amb la primera. Aquí no es toca cap taula que ja existeixi.
--
-- Les quatre són un mirall de les de Tres Bandes, columna per columna, i les
-- omplen les mateixes funcions (`publish_lliga_4m` a cloud_sync.py). El que
-- canvia és el que hi ha a dins de `lliga4m_partides.modalitat_codi`: a Tres
-- Bandes sempre és 1, i aquí cada partida d'un encontre és d'una modalitat.
-- El nom surt de `fcbillar.modalitats` (codi_fcb → nom):
--
--   1 = Tres bandes · 2 = Lliure · 3 = Quadre 47/2 · 4 = Banda
--
-- Els punts són els mateixos que a Tres Bandes: quatre partides per encontre,
-- 2 punts parcials per partida guanyada i 1 per empatada (sumen 8), i de punts
-- de matx 3 per a qui guanya l'encontre o 1 per a cadascú si queden 4-4.
--
-- Mentre el Data API no vegi les taules (fins a mitja hora després d'aplicar
-- això), `publish-cloud` avisa i no hi publica res.

-- Els noms de les divisions i dels grups. `lliga_id` és el de la federació, que
-- canvia cada temporada; les files de les temporades anteriors s'hi queden.
create table if not exists fcbillar.lliga4m_groups (
    lliga_id     integer not null,
    divisio_id   integer not null,
    grup_id      integer not null,
    divisio_nom  text,                  -- 'HONOR', '1A DIVISIÓ', '2A DIVISIÓ'
    grup_nom     text,                  -- 'UNIC', 'GRUP A', 'PROMOCIONS'…
    primary key (lliga_id, divisio_id, grup_id)
);

-- La classificació de cada grup. Posició i punts són els oficials de la
-- federació; la resta es compta dels encontres.
create table if not exists fcbillar.lliga4m_standings (
    lliga_id     integer not null,
    divisio_id   integer not null,
    grup_id      integer not null,
    posicio      integer,
    equip        text not null,
    club_fcb_id  text,
    pj integer, g integer, e integer, p integer,
    punts        integer,               -- punts de matx (3 / 1 / 0 per encontre)
    pf integer, pc integer,             -- punts de matx a favor i en contra
    penalitzacio integer,               -- punts que la federació ha restat; NULL = cap
    ppf integer, ppc integer,           -- punts parcials a favor i en contra
    car_f integer, car_c integer,       -- caramboles fetes i rebudes (totes les modalitats)
    entrades     integer,
    primary key (lliga_id, divisio_id, grup_id, equip)
);
create index if not exists idx_fcbillar_lliga4m_standings_grup
    on fcbillar.lliga4m_standings (lliga_id, divisio_id, grup_id);

-- Els encontres, jugats o no. `encontre_id` és el de la federació quan
-- l'encontre s'ha jugat i 10.000.000 + jornada_id * 100 + lloc mentre no en té.
-- No porta `lliga_id`, igual que `lliga_encontres`: la lliga surt de
-- `lliga4m_groups` per `divisio_id`, que la federació no repeteix entre lligues.
create table if not exists fcbillar.lliga4m_encontres (
    encontre_id    bigint primary key,
    divisio_id     integer not null,
    grup_id        integer not null,
    jornada        integer,             -- 1, 2, 3… dins del grup, per data
    data           date,
    equip_local    text,
    equip_visitant text,
    gols_local     integer,             -- punts de matx; NULL = encara no jugat
    gols_visitant  integer
);
create index if not exists idx_fcbillar_lliga4m_encontres_grup
    on fcbillar.lliga4m_encontres (divisio_id, grup_id);

-- Les partides de cada encontre: quatre, una de cada modalitat.
create table if not exists fcbillar.lliga4m_partides (
    encontre_id         bigint not null
        references fcbillar.lliga4m_encontres (encontre_id) on delete cascade,
    ordre               integer not null,
    modalitat_codi      integer,        -- fcbillar.modalitats.codi_fcb
    jugador_local       text,
    caramboles_local    integer,
    jugador_visitant    text,
    caramboles_visitant integer,
    entrades            integer,
    primary key (encontre_id, ordre)
);

-- Lectura per a tothom i escriptura només per al rol de servei, que és qui
-- publica: el mateix repartiment que la resta de taules de competició. RLS diu
-- quines files es poden llegir; el GRANT, si el rol pot tocar la taula.
do $$
declare
    t text;
begin
    foreach t in array array[
        'lliga4m_groups', 'lliga4m_standings', 'lliga4m_encontres', 'lliga4m_partides'
    ] loop
        execute format('alter table fcbillar.%I enable row level security', t);
        execute format('drop policy if exists %I on fcbillar.%I', 'read ' || t, t);
        execute format(
            'create policy %I on fcbillar.%I for select to anon, authenticated using (true)',
            'read ' || t, t
        );
        execute format('grant select on fcbillar.%I to anon, authenticated', t);
        execute format('grant all on fcbillar.%I to service_role', t);
    end loop;
end $$;

notify pgrst, 'reload schema';
