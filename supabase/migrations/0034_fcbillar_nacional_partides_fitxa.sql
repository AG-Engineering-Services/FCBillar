-- FCBillar cloud schema — les partides de la Lliga Nacional de cada fitxa del cens.
--
-- La base de dades és Neon (projecte `fcbillar`). No s'aplica automàticament:
-- l'admin valida el SQL i l'executa amb `psql` i la connexió sense pool.
--
-- Una fila per partida i jugador amb fitxa, vista des del seu costat: el seu
-- equip, el rival, el marcador de la partida i el resultat de l'encontre. És el
-- que la fitxa ensenya com la llista de partides de la federació catalana, a
-- part: res d'aquí compta per a cap rànquing ni mitjana catalana.

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
       true                  as a_casa
from fcbillar.nacional_partides p
join fcbillar.nacional_encontres e
  on e.temporada = p.temporada and e.divisio = p.divisio and e.grup = p.grup
 and e.jornada = p.jornada and e.ordre = p.ordre_encontre
join fcbillar.nacional_fitxes f on f.jugador = p.jugador_local
left join fcbillar.nacional_fitxes fr on fr.jugador = p.jugador_visitant
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
       false
from fcbillar.nacional_partides p
join fcbillar.nacional_encontres e
  on e.temporada = p.temporada and e.divisio = p.divisio and e.grup = p.grup
 and e.jornada = p.jornada and e.ordre = p.ordre_encontre
join fcbillar.nacional_fitxes f on f.jugador = p.jugador_visitant
left join fcbillar.nacional_fitxes fr on fr.jugador = p.jugador_local;

grant select on fcbillar.nacional_partides_fitxa to anon, authenticated, service_role;

notify pgrst, 'reload schema';
