-- FCBillar cloud schema — partides de fora de Catalunya: Campionats d'Espanya
-- (RFEB), Europeus (CEB), Mundials i Copes del Món (UMB).
--
-- La base de dades és Neon (projecte `fcbillar`). No s'aplica automàticament:
-- l'admin valida el SQL i l'executa amb `psql` i la connexió sense pool.
--
-- `fcbillar ingest-externes` llegeix les tres fonts i `publish_externes` les puja
-- aquí. Com les `nacional_*`, SÓN TAULES A PART: cap columna apunta a `players`
-- ni a `clubs`, i res d'aquí compta per a cap rànquing ni mitjana catalana. Els
-- noms són text, tal com els escriu cada font; quina fitxa del cens és cadascú
-- ho diu `ext_fitxes`, que surt dels lligams validats a mà.
--
-- La CEB i la UMB publiquen les partides. La RFEB no: d'un Campionat d'Espanya
-- només hi ha la classificació final, amb els totals de cada jugador
-- (`ext_totals`).

create table if not exists fcbillar.ext_esdeveniments (
    font        text not null,              -- ceb | umb | rfeb
    id          text not null,
    nom         text not null,
    modalitat   text not null,              -- 3B | LLIURE | 47/2 | BANDA | 71/2 | 47/1
    ambit       text not null,              -- espanya | internacional
    tipus       text not null,              -- campionat_espanya | gp_espanya | europeu | mundial | copa_mon
    temporada   text not null default '',   -- '2024-2025'
    data_inici  date,
    data_fi     date,
    lloc        text not null default '',
    url         text not null default '',
    primary key (font, id)
);

create table if not exists fcbillar.ext_partides (
    font          text not null,
    esdeveniment  text not null,
    ordre         integer not null,
    data          date,
    fase          text not null default '',
    grup          text not null default '',
    jugador1      text not null,
    nacio1        text not null default '',
    caramboles1   integer,
    entrades1     integer,
    serie1        integer,
    punts1        integer,
    jugador2      text not null,
    nacio2        text not null default '',
    caramboles2   integer,
    entrades2     integer,
    serie2        integer,
    punts2        integer,
    primary key (font, esdeveniment, ordre),
    foreign key (font, esdeveniment) references fcbillar.ext_esdeveniments (font, id) on delete cascade
);

create table if not exists fcbillar.ext_totals (
    font          text not null,
    esdeveniment  text not null,
    jugador       text not null,
    federacio     text not null default '',
    posicio       integer,
    jugades       integer,
    guanyades     integer,
    empatades     integer,
    perdudes      integer,
    caramboles    integer,
    entrades      integer,
    serie         integer,
    primary key (font, esdeveniment, jugador),
    foreign key (font, esdeveniment) references fcbillar.ext_esdeveniments (font, id) on delete cascade
);

-- Quin nom de cada font és quina fitxa del cens. Els noms de la RFEB validats
-- per a la Lliga Nacional també hi són: és la mateixa federació.
create table if not exists fcbillar.ext_fitxes (
    font        text not null,
    jugador     text not null,
    fcb_id      text not null,
    primary key (font, jugador)
);
create index if not exists ext_fitxes_fcb_id on fcbillar.ext_fitxes (fcb_id);

do $$
declare t text;
begin
    foreach t in array array['ext_esdeveniments', 'ext_partides', 'ext_totals', 'ext_fitxes'] loop
        execute format('alter table fcbillar.%I enable row level security', t);
        execute format('drop policy if exists "read %s" on fcbillar.%I', t, t);
        execute format(
            'create policy "read %s" on fcbillar.%I for select to anon, authenticated using (true)', t, t
        );
        execute format('grant select on fcbillar.%I to anon, authenticated', t);
        execute format('grant all on fcbillar.%I to service_role', t);
    end loop;
end $$;

-- Les partides de cada fitxa del cens, vistes des del seu costat: el jugador,
-- el rival i el marcador. Una partida entre dos jugadors amb fitxa surt dues
-- vegades, una per a cadascun.
create or replace view fcbillar.ext_partides_fitxa
with (security_invoker = on) as
select f.fcb_id,
       e.font, e.id as esdeveniment, e.nom as competicio, e.modalitat, e.ambit, e.tipus,
       e.temporada, coalesce(p.data, e.data_inici) as data, p.fase, p.grup, p.ordre,
       p.jugador1 as jugador, p.caramboles1 as caramboles, p.entrades1 as entrades,
       p.serie1 as serie, p.punts1 as punts,
       p.jugador2 as rival, p.nacio2 as nacio_rival, fr.fcb_id as rival_fcb_id,
       p.caramboles2 as caramboles_rival, p.entrades2 as entrades_rival,
       p.serie2 as serie_rival, p.punts2 as punts_rival
from fcbillar.ext_partides p
join fcbillar.ext_esdeveniments e on e.font = p.font and e.id = p.esdeveniment
join fcbillar.ext_fitxes f on f.font = p.font and f.jugador = p.jugador1
left join fcbillar.ext_fitxes fr on fr.font = p.font and fr.jugador = p.jugador2
union all
select f.fcb_id,
       e.font, e.id, e.nom, e.modalitat, e.ambit, e.tipus,
       e.temporada, coalesce(p.data, e.data_inici), p.fase, p.grup, p.ordre,
       p.jugador2, p.caramboles2, p.entrades2, p.serie2, p.punts2,
       p.jugador1, p.nacio1, fr.fcb_id,
       p.caramboles1, p.entrades1, p.serie1, p.punts1
from fcbillar.ext_partides p
join fcbillar.ext_esdeveniments e on e.font = p.font and e.id = p.esdeveniment
join fcbillar.ext_fitxes f on f.font = p.font and f.jugador = p.jugador2
left join fcbillar.ext_fitxes fr on fr.font = p.font and fr.jugador = p.jugador1;

-- Els totals de cada fitxa del cens als campionats dels quals no hi ha partides.
create or replace view fcbillar.ext_totals_fitxa
with (security_invoker = on) as
select f.fcb_id,
       e.font, e.id as esdeveniment, e.nom as competicio, e.modalitat, e.ambit, e.tipus,
       e.temporada, e.data_inici as data,
       t.jugador, t.federacio, t.posicio, t.jugades, t.guanyades, t.empatades, t.perdudes,
       t.caramboles, t.entrades, t.serie
from fcbillar.ext_totals t
join fcbillar.ext_esdeveniments e on e.font = t.font and e.id = t.esdeveniment
join fcbillar.ext_fitxes f on f.font = t.font and f.jugador = t.jugador;

grant select on fcbillar.ext_partides_fitxa to anon, authenticated, service_role;
grant select on fcbillar.ext_totals_fitxa to anon, authenticated, service_role;

notify pgrst, 'reload schema';
