-- FCBillar cloud schema — els resultats internacionals oficials de la UMB.
--
-- La base de dades és Neon (projecte `fcbillar`). No s'aplica automàticament:
-- l'admin valida el SQL i l'executa amb `psql` i la connexió sense pool.
--
-- Mundials i Copes del Món de carambola, llegits dels PDF de resultats que la
-- UMB publica a umb-carom.org. Com la Lliga Nacional i els campionats de la
-- RFEB, és a part de la federació catalana: res d'aquí compta per a cap rànquing
-- ni mitjana catalana.
--
-- Es desen TOTS els jugadors de cada prova, no només els espanyols: calen per
-- posar nom als rivals. El lligam amb la fitxa del cens va per l'identificador
-- que la UMB dóna a cada jugador (`umb_id`), validat a mà a
-- `fonts/internacional/fitxes.csv`.

create table if not exists fcbillar.umb_esdeveniments (
    id          integer primary key,        -- l'id de umb-carom.org/events/{id}
    nom         text not null,
    disciplina  text,                       -- 3 bandes, quadre, 5 quilles, 1 banda, lliure, artistic
    lloc        text,
    data_inici  date,
    data_fi     date,
    font        text not null
);

create table if not exists fcbillar.umb_jugadors (
    esdeveniment_id integer not null references fcbillar.umb_esdeveniments (id) on delete cascade,
    nom             text not null,          -- «COGNOM Nom», com a la llista de jugadors
    umb_id          text,                   -- «0106»; pot faltar als PDF antics
    nacionalitat    text,                   -- ES, NL, KR…
    primary key (esdeveniment_id, nom)
);

create table if not exists fcbillar.umb_classificacions (
    esdeveniment_id integer not null references fcbillar.umb_esdeveniments (id) on delete cascade,
    posicio         integer not null,
    jugador         text not null,
    nacionalitat    text,
    ronda           text,                   -- MT, R16, Q…: fins on va arribar
    punts           integer,                -- punts de partida acumulats
    mitjana         numeric,
    mitjana_particular numeric,             -- la millor mitjana d'una partida
    serie1          integer,
    serie2          integer,
    caramboles      integer,
    entrades        integer,
    primary key (esdeveniment_id, posicio, jugador)
);

create table if not exists fcbillar.umb_partides (
    esdeveniment_id integer not null references fcbillar.umb_esdeveniments (id) on delete cascade,
    fase            text not null,          -- «Main Tournament - Final», «Pre-Qualification»…
    grup            text not null default '',
    ordre           integer not null,       -- ordre dins del PDF
    jugador_a       text not null,
    caramboles_a    integer,
    entrades_a      integer,                -- qui comença juga una entrada més
    mitjana_a       numeric,
    punts_a         integer,                -- punts de partida (0, 1 o 2)
    serie_a         integer,                -- millor sèrie; la UMB en dóna una o dues
    serie2_a        integer,
    jugador_b       text not null,
    caramboles_b    integer,
    entrades_b      integer,
    mitjana_b       numeric,
    punts_b         integer,
    serie_b         integer,
    serie2_b        integer
    primary key (esdeveniment_id, fase, grup, ordre)
);

-- Qui és cada jugador de la UMB a la fitxa del cens (`fcb_id`). Només els validats.
create table if not exists fcbillar.umb_fitxes (
    umb_id text primary key,
    fcb_id text not null
);

do $$
declare t text;
begin
  foreach t in array array['umb_esdeveniments', 'umb_jugadors', 'umb_classificacions',
                           'umb_partides', 'umb_fitxes'] loop
    execute format('alter table fcbillar.%I enable row level security', t);
    execute format('drop policy if exists "read %s" on fcbillar.%I', t, t);
    execute format('create policy "read %s" on fcbillar.%I for select to anon, authenticated using (true)', t, t);
    execute format('grant select on fcbillar.%I to anon, authenticated', t);
    execute format('grant all on fcbillar.%I to service_role', t);
  end loop;
end $$;

create index if not exists idx_umb_jugadors_umb_id on fcbillar.umb_jugadors (umb_id);

-- Una fila per partida i jugador amb fitxa: el que ensenya la fitxa. El rival hi
-- surt amb el nom i, si també té fitxa, amb el seu `rival_fcb_id`.
create or replace view fcbillar.umb_partides_fitxa
with (security_invoker = on) as
with costats as (
    select p.*, 'a' as costat, p.jugador_a as jugador, p.caramboles_a as caramboles, p.entrades_a as entrades,
           p.mitjana_a as mitjana, p.punts_a as punts, p.serie_a as serie, p.serie2_a as serie2,
           p.jugador_b as rival, p.caramboles_b as rival_caramboles, p.entrades_b as rival_entrades, p.mitjana_b as rival_mitjana,
           p.punts_b as rival_punts
    from fcbillar.umb_partides p
    union all
    select p.*, 'b', p.jugador_b, p.caramboles_b, p.entrades_b, p.mitjana_b, p.punts_b, p.serie_b, p.serie2_b,
           p.jugador_a, p.caramboles_a, p.entrades_a, p.mitjana_a, p.punts_a
    from fcbillar.umb_partides p
)
select f.fcb_id, c.esdeveniment_id, e.nom as esdeveniment, e.disciplina, e.lloc,
       e.data_inici, e.data_fi, c.fase, c.grup, c.ordre, c.jugador, c.caramboles, c.entrades,
       c.mitjana, c.punts, c.serie, c.serie2,
       c.rival, c.rival_caramboles, c.rival_entrades, c.rival_mitjana, c.rival_punts,
       rj.umb_id as rival_umb_id, rf.fcb_id as rival_fcb_id
from costats c
join fcbillar.umb_esdeveniments e on e.id = c.esdeveniment_id
join fcbillar.umb_jugadors j on j.esdeveniment_id = c.esdeveniment_id and j.nom = c.jugador
join fcbillar.umb_fitxes f on f.umb_id = j.umb_id
left join fcbillar.umb_jugadors rj on rj.esdeveniment_id = c.esdeveniment_id and rj.nom = c.rival
left join fcbillar.umb_fitxes rf on rf.umb_id = rj.umb_id;

grant select on fcbillar.umb_partides_fitxa to anon, authenticated, service_role;

-- La posició final de cada jugador amb fitxa en cada prova.
create or replace view fcbillar.umb_classificacions_fitxa
with (security_invoker = on) as
select f.fcb_id, c.*, e.nom as esdeveniment, e.disciplina, e.lloc, e.data_inici, e.data_fi,
       (select count(*) from fcbillar.umb_classificacions t
         where t.esdeveniment_id = c.esdeveniment_id) as participants
from fcbillar.umb_classificacions c
join fcbillar.umb_esdeveniments e on e.id = c.esdeveniment_id
join fcbillar.umb_jugadors j on j.esdeveniment_id = c.esdeveniment_id and j.nom = c.jugador
join fcbillar.umb_fitxes f on f.umb_id = j.umb_id;

grant select on fcbillar.umb_classificacions_fitxa to anon, authenticated, service_role;

notify pgrst, 'reload schema';
