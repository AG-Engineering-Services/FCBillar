-- FCBillar cloud schema — el nom del rival com l'escriu la federació catalana.
--
-- La base de dades és Neon (projecte `fcbillar`). No s'aplica automàticament:
-- l'admin valida el SQL i l'executa amb `psql` i la connexió sense pool.
--
-- La vista `nacional_partides_fitxa` (0034) donava el rival amb el nom de la
-- RFEB («Luis Ametller Congost»). Si el rival té fitxa al cens, `rival_nom_fcb`
-- porta el nom com el té la FCB («AMETLLER CONGOST, LLUIS»), que és com surt a
-- la llista de partides catalanes de la mateixa fitxa.

create or replace view fcbillar.nacional_partides_fitxa
with (security_invoker = on) as
select f.fcb_id,
       p.temporada, p.divisio, p.grup, p.jornada, e.data,
       p.ordre_encontre, p.ordre,
       p.jugador_local       as jugador,
       p.caramboles_local    as caramboles,
       p.jugador_visitant    as rival,
       p.caramboles_visitant as caramboles_rival,
       fr.fcb_id             as rival_fcb_id,
       p.entrades,
       e.local               as equip,
       e.visitant            as equip_rival,
       e.punts_local         as punts_equip,
       e.punts_visitant      as punts_rival,
       true                  as a_casa,
       pr.nom                as rival_nom_fcb
from fcbillar.nacional_partides p
join fcbillar.nacional_encontres e
  on e.temporada = p.temporada and e.divisio = p.divisio and e.grup = p.grup
 and e.jornada = p.jornada and e.ordre = p.ordre_encontre
join fcbillar.nacional_fitxes f on f.jugador = p.jugador_local
left join fcbillar.nacional_fitxes fr on fr.jugador = p.jugador_visitant
left join fcbillar.players pr on pr.fcb_id = fr.fcb_id
union all
select f.fcb_id,
       p.temporada, p.divisio, p.grup, p.jornada, e.data,
       p.ordre_encontre, p.ordre,
       p.jugador_visitant, p.caramboles_visitant,
       p.jugador_local, p.caramboles_local,
       fr.fcb_id,
       p.entrades,
       e.visitant, e.local,
       e.punts_visitant, e.punts_local,
       false,
       pr.nom
from fcbillar.nacional_partides p
join fcbillar.nacional_encontres e
  on e.temporada = p.temporada and e.divisio = p.divisio and e.grup = p.grup
 and e.jornada = p.jornada and e.ordre = p.ordre_encontre
join fcbillar.nacional_fitxes f on f.jugador = p.jugador_visitant
left join fcbillar.nacional_fitxes fr on fr.jugador = p.jugador_local
left join fcbillar.players pr on pr.fcb_id = fr.fcb_id;

grant select on fcbillar.nacional_partides_fitxa to anon, authenticated, service_role;

notify pgrst, 'reload schema';
