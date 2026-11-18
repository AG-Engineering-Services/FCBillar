-- FCBillar cloud schema — les partides una a una de les proves de la RFEB.
--
-- La base de dades és Neon (projecte `fcbillar`). No s'aplica automàticament:
-- l'admin valida el SQL i l'executa amb la connexió sense pool.
--
-- Fins ara de les proves de la RFEB només hi havia la classificació final
-- (`rfeb_classificacions`). Aquí van les partides de les que en publiquen el
-- detall: els fulls de Google de desenvolupament (play-offs de la Lliga
-- Nacional, seleccions autonòmiques, sub-15, GPE de la web nova…) i les
-- eliminatòries dels PDF antics. Com la resta de la RFEB, a part de la
-- federació catalana: no compten per a cap rànquing ni mitjana catalana.

create table if not exists fcbillar.rfeb_partides (
    prova_id      text not null references fcbillar.rfeb_proves (id) on delete cascade,
    fase          text not null,
    grup          text not null default '',
    ordre         integer not null,
    data          date,
    modalitat     text,                     -- només si la prova en barreja
    jugador_a     text not null,
    equip_a       text,
    caramboles_a  integer not null,
    serie_a       integer,
    punts_a       integer,
    jugador_b     text not null,
    equip_b       text,
    caramboles_b  integer not null,
    serie_b       integer,
    punts_b       integer,
    entrades      integer not null,         -- les mateixes per als dos
    primary key (prova_id, fase, grup, ordre)
);

alter table fcbillar.rfeb_partides enable row level security;
drop policy if exists "read rfeb_partides" on fcbillar.rfeb_partides;
create policy "read rfeb_partides" on fcbillar.rfeb_partides
    for select to anon, authenticated using (true);
grant select on fcbillar.rfeb_partides to anon, authenticated;
grant all on fcbillar.rfeb_partides to service_role;

-- Una fila per partida i jugador amb fitxa, des del seu costat.
create or replace view fcbillar.rfeb_partides_fitxa
with (security_invoker = on) as
with costats as (
    select p.prova_id, p.fase, p.grup, p.ordre, p.data, p.modalitat as modalitat_partida,
           p.jugador_a as jugador, p.equip_a as equip, p.caramboles_a as caramboles,
           p.serie_a as serie, p.punts_a as punts,
           p.jugador_b as rival, p.equip_b as equip_rival, p.caramboles_b as rival_caramboles,
           p.serie_b as rival_serie, p.punts_b as rival_punts, p.entrades
    from fcbillar.rfeb_partides p
    union all
    select p.prova_id, p.fase, p.grup, p.ordre, p.data, p.modalitat,
           p.jugador_b, p.equip_b, p.caramboles_b, p.serie_b, p.punts_b,
           p.jugador_a, p.equip_a, p.caramboles_a, p.serie_a, p.punts_a, p.entrades
    from fcbillar.rfeb_partides p
)
select f.fcb_id, c.*, coalesce(c.modalitat_partida, pr.modalitat) as modalitat,
       pr.temporada, pr.categoria, pr.tipus, pr.titol, pr.lloc, pr.data_inici, pr.data_fi,
       pr.font, rf.fcb_id as rival_fcb_id
from costats c
join fcbillar.rfeb_proves pr on pr.id = c.prova_id
join fcbillar.nacional_fitxes f on f.jugador = c.jugador
left join fcbillar.nacional_fitxes rf on rf.jugador = c.rival;

grant select on fcbillar.rfeb_partides_fitxa to anon, authenticated, service_role;

notify pgrst, 'reload schema';
