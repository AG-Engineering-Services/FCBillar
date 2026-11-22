-- Lligams propis del palmarès del Quadre d'Honor de la FCB.
--
-- Fins ara el palmarès es lligava a la fitxa per nom amb `nacional_fitxes`, que
-- porta els lligams validats de totes les fonts. Un nom validat per a un jugador
-- d'ara a les partides de la RFEB («Antonio Gómez») acabava lligant també el
-- campió homònim de fa cinquanta anys. Les medalles de la FCB ara només es
-- lliguen amb els lligams validats per al Quadre d'Honor (`fonts/nacional/
-- fitxes.csv`, divisió «palmares-fcb»).

create table if not exists fcbillar.palmares_fitxes (
    font     text not null,             -- 'fcb'
    jugador  text not null,             -- tal com l'escriu el Quadre d'Honor
    fcb_id   text not null,
    primary key (font, jugador)
);
create index if not exists palmares_fitxes_fcb_id on fcbillar.palmares_fitxes (fcb_id);

alter table fcbillar.palmares_fitxes enable row level security;
drop policy if exists "read palmares_fitxes" on fcbillar.palmares_fitxes;
create policy "read palmares_fitxes" on fcbillar.palmares_fitxes
    for select to anon, authenticated using (true);
grant select on fcbillar.palmares_fitxes to anon, authenticated;
grant all on fcbillar.palmares_fitxes to service_role;

create or replace view fcbillar.palmares_fitxa
with (security_invoker = on) as
select f.fcb_id, m.*
from fcbillar.palmares_medalles m
join fcbillar.nacional_fitxes f on f.jugador = m.jugador
where m.font = 'rfeb' or m.pais = 'ES'
union all
select pf.fcb_id, m.*
from fcbillar.palmares_medalles m
join fcbillar.palmares_fitxes pf on pf.font = m.font and pf.jugador = m.jugador
where m.font = 'fcb';

grant select on fcbillar.palmares_fitxa to anon, authenticated, service_role;

notify pgrst, 'reload schema';
