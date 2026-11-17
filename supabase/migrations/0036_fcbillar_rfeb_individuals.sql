-- FCBillar cloud schema — els campionats individuals de la RFEB.
--
-- La base de dades és Neon (projecte `fcbillar`). No s'aplica automàticament:
-- l'admin valida el SQL i l'executa amb `psql` i la connexió sense pool.
--
-- Les classificacions finals dels Campionats d'Espanya, els Grans Premis i
-- altres proves de totes les modalitats de carambola, llegides dels PDF de la
-- RFEB. Com la Lliga Nacional, és a part de la federació catalana: res d'aquí
-- compta per a cap rànquing ni mitjana catalana.
--
-- Els noms es lliguen amb la fitxa del cens amb la mateixa taula de lligams
-- validats a mà que la Lliga Nacional (`nacional_fitxes`): la RFEB escriu el
-- nom de cada jugador igual a totes les seves competicions.

create table if not exists fcbillar.rfeb_proves (
    id          text primary key,           -- `noticias2015/res_ce_3b_2015`
    temporada   text not null,              -- `2015-2016`
    modalitat   text not null,              -- 3b, banda, lliure, 47_2, 71_2, artistic, 5q
    categoria   text not null,              -- absolut, femeni, sub15, sub17, sub21, sub25, senior, infantil, junior
    tipus       text not null,              -- ce, gpe, altres
    titol       text not null,
    lloc        text,
    data_inici  date,
    data_fi     date,
    font        text
);

create table if not exists fcbillar.rfeb_classificacions (
    prova_id     text not null references fcbillar.rfeb_proves (id) on delete cascade,
    posicio      integer not null,
    jugador      text not null,             -- el nom a la RFEB
    fed          text,                      -- federació autonòmica: CAT, MAD…
    ronda        text,                      -- FF, Q, PQ-2º… fins on va arribar
    posicio_empat integer,                  -- la posició compartida («4 3 FF»: 4t, empatat al 3r)
    jugades      integer,
    guanyades    integer,
    empatades    integer,
    perdudes     integer,
    caramboles   integer,
    entrades     integer,
    mitjana      numeric,
    serie_major  integer,
    punts        integer,
    primary key (prova_id, posicio, jugador)
);

do $$
declare t text;
begin
  foreach t in array array['rfeb_proves', 'rfeb_classificacions'] loop
    execute format('alter table fcbillar.%I enable row level security', t);
    execute format('drop policy if exists "read %s" on fcbillar.%I', t, t);
    execute format('create policy "read %s" on fcbillar.%I for select to anon, authenticated using (true)', t, t);
    execute format('grant select on fcbillar.%I to anon, authenticated', t);
    execute format('grant all on fcbillar.%I to service_role', t);
  end loop;
end $$;

-- Una fila per prova i jugador amb fitxa: el que ensenya la fitxa.
create or replace view fcbillar.rfeb_individuals_fitxa
with (security_invoker = on) as
select f.fcb_id, c.*, p.temporada, p.modalitat, p.categoria, p.tipus, p.titol, p.lloc,
       p.data_inici, p.data_fi, p.font,
       (select count(*) from fcbillar.rfeb_classificacions t where t.prova_id = c.prova_id) as participants
from fcbillar.rfeb_classificacions c
join fcbillar.rfeb_proves p on p.id = c.prova_id
join fcbillar.nacional_fitxes f on f.jugador = c.jugador;

grant select on fcbillar.rfeb_individuals_fitxa to anon, authenticated, service_role;

notify pgrst, 'reload schema';
