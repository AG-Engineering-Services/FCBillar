-- El palmarès de la fitxa també porta el Quadre d'Honor de la FCB (font 'fcb':
-- campions i subcampions de Catalunya des del 1961-62).
create or replace view fcbillar.palmares_fitxa
with (security_invoker = on) as
select f.fcb_id, m.*
from fcbillar.palmares_medalles m
join fcbillar.nacional_fitxes f on f.jugador = m.jugador
where m.font in ('rfeb', 'fcb') or m.pais = 'ES';

grant select on fcbillar.palmares_fitxa to anon, authenticated, service_role;

notify pgrst, 'reload schema';
