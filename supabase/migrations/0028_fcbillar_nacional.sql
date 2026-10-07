-- FCBillar cloud schema — la Lliga Nacional de tres bandes de la RFEB.
--
-- La base de dades és Neon (projecte `fcbillar`); el nom de la carpeta és
-- herència. No s'aplica automàticament: l'admin valida el SQL i l'executa amb
-- `psql` i la connexió sense pool.
--
-- La federació espanyola no té web de competició: de cada jornada de cada divisió
-- en penja un PDF, i a part la classificació de jugadors. `fcbillar
-- ingest-nacional` els llegeix i `publish_nacional` els puja aquí.
--
-- SÓN TAULES A PART, i s'hi han de quedar. Cap columna apunta a `players`,
-- `clubs` ni a cap altra taula de l'esquema:
--
--   · La llicència espanyola i la catalana són independents. Es pot jugar la
--     lliga catalana amb un club i la nacional amb un altre, i les dues coses són
--     veritat alhora. Els noms de jugadors i d'equips són text, tal com els
--     escriu la RFEB.
--   · Les partides d'aquí no compten per al rànquing de la federació catalana.
--     No entren a `games`, ni a `pending_games`, ni a cap mitjana.
--
-- `divisio` és 'honor', '1' o '2'. `grup` és la lletra, o '' a les divisions d'un
-- sol grup. `temporada` va amb guió: '2026-2027'.

-- Com queda cada equip després de cada jornada. Es guarden totes: l'última és la
-- classificació vigent, i les anteriors, com hi ha arribat.
create table if not exists fcbillar.nacional_classificacio (
    temporada   text not null,
    divisio     text not null,
    grup        text not null default '',
    jornada     integer not null,
    posicio     integer not null,
    equip       text not null,
    jugats      integer,
    guanyats    integer,
    empatats    integer,
    perduts     integer,
    caramboles  integer,
    entrades    integer,
    mitjana     double precision,
    parcials    integer,                    -- partides guanyades, sumades
    punts       integer,
    primary key (temporada, divisio, grup, jornada, equip)
);

create table if not exists fcbillar.nacional_encontres (
    temporada           text not null,
    divisio             text not null,
    grup                text not null default '',
    jornada             integer not null,
    ordre               integer not null,   -- l'ordre dins del PDF
    data                date,               -- el dia de la jornada
    local               text not null,
    visitant            text not null,
    punts_local         integer,            -- 6-2, 4-4, 8-0
    punts_visitant      integer,
    caramboles_local    integer,
    caramboles_visitant integer,
    entrades            integer,
    mitjana_local       double precision,
    mitjana_visitant    double precision,
    primary key (temporada, divisio, grup, jornada, ordre)
);

create table if not exists fcbillar.nacional_partides (
    temporada           text not null,
    divisio             text not null,
    grup                text not null default '',
    jornada             integer not null,
    ordre_encontre      integer not null,
    ordre               integer not null,
    jugador_local       text not null,
    caramboles_local    integer,
    jugador_visitant    text not null,
    caramboles_visitant integer,
    entrades            integer,
    primary key (temporada, divisio, grup, jornada, ordre_encontre, ordre),
    foreign key (temporada, divisio, grup, jornada, ordre_encontre)
        references fcbillar.nacional_encontres (temporada, divisio, grup, jornada, ordre)
        on delete cascade
);
-- Per trobar les partides d'un jugador, que és el que demana la seva fitxa.
create index if not exists idx_fcbillar_nacional_partides_local
    on fcbillar.nacional_partides (jugador_local);
create index if not exists idx_fcbillar_nacional_partides_visitant
    on fcbillar.nacional_partides (jugador_visitant);

-- La classificació individual d'una divisió. La RFEB la publica ja sumada: es
-- desa tal com ve, no es recalcula.
create table if not exists fcbillar.nacional_jugadors (
    temporada   text not null,
    divisio     text not null,
    posicio     integer not null,
    jugador     text not null,
    equip       text not null,
    jugades     integer,
    guanyades   integer,
    empatades   integer,
    perdudes    integer,
    caramboles  integer,
    entrades    integer,
    mitjana     double precision,
    punts       integer,
    primary key (temporada, divisio, jugador, equip)
);

create table if not exists fcbillar.nacional_millors_series (
    temporada   text not null,
    divisio     text not null,
    jornada     integer not null,
    ordre       integer not null,
    jugador     text not null,
    equip       text not null,
    serie       integer not null,
    primary key (temporada, divisio, jornada, ordre)
);

-- Lectura per a tothom i escriptura només per al rol de servei, que és qui
-- publica: el mateix repartiment que la resta de taules de competició. RLS diu
-- quines files es poden llegir; el GRANT, si el rol pot tocar la taula.
do $$
declare
    t text;
begin
    foreach t in array array[
        'nacional_classificacio', 'nacional_encontres', 'nacional_partides',
        'nacional_jugadors', 'nacional_millors_series'
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
