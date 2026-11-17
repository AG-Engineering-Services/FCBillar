-- FCBillar cloud schema — el resultat de cada set de les partides UMB a sets.
--
-- La base de dades és Neon (projecte `fcbillar`). No s'aplica automàticament:
-- l'admin valida el SQL i l'executa amb `psql` i la connexió sense pool.
--
-- Fins al 2011 la UMB jugava a sets de 15 i la partida la guanyava qui guanyava
-- més sets, no qui feia més caramboles. Fins ara, d'aquestes partides s'hi desava
-- el primer set com si fos el total. `sets_a` i `sets_b` porten «caramboles/
-- entrades» de cada set separats per comes («15/14,15/7»); NULL si no és a sets.
-- Després d'aplicar-la cal tornar a carregar i publicar la UMB.

alter table fcbillar.umb_partides add column if not exists sets_a text;
alter table fcbillar.umb_partides add column if not exists sets_b text;

-- La mateixa vista de la 0037, amb els sets de cada costat al final.
create or replace view fcbillar.umb_partides_fitxa
with (security_invoker = on) as
with costats as (
    select p.*, 'a' as costat, p.jugador_a as jugador, p.caramboles_a as caramboles, p.entrades_a as entrades,
           p.mitjana_a as mitjana, p.punts_a as punts, p.serie_a as serie, p.serie2_a as serie2,
           p.jugador_b as rival, p.caramboles_b as rival_caramboles, p.entrades_b as rival_entrades, p.mitjana_b as rival_mitjana,
           p.punts_b as rival_punts, p.sets_a as sets_propis, p.sets_b as sets_rival
    from fcbillar.umb_partides p
    union all
    select p.*, 'b', p.jugador_b, p.caramboles_b, p.entrades_b, p.mitjana_b, p.punts_b, p.serie_b, p.serie2_b,
           p.jugador_a, p.caramboles_a, p.entrades_a, p.mitjana_a, p.punts_a, p.sets_b, p.sets_a
    from fcbillar.umb_partides p
)
select f.fcb_id, c.esdeveniment_id, e.nom as esdeveniment, e.disciplina, e.lloc,
       e.data_inici, e.data_fi, c.fase, c.grup, c.ordre, c.jugador, c.caramboles, c.entrades,
       c.mitjana, c.punts, c.serie, c.serie2,
       c.rival, c.rival_caramboles, c.rival_entrades, c.rival_mitjana, c.rival_punts,
       rj.umb_id as rival_umb_id, rf.fcb_id as rival_fcb_id,
       c.sets_propis as sets, c.sets_rival as rival_sets
from costats c
join fcbillar.umb_esdeveniments e on e.id = c.esdeveniment_id
join fcbillar.umb_jugadors j on j.esdeveniment_id = c.esdeveniment_id and j.nom = c.jugador
join fcbillar.umb_fitxes f on f.umb_id = j.umb_id
left join fcbillar.umb_jugadors rj on rj.esdeveniment_id = c.esdeveniment_id and rj.nom = c.rival
left join fcbillar.umb_fitxes rf on rf.umb_id = rj.umb_id;

grant select on fcbillar.umb_partides_fitxa to anon, authenticated, service_role;

notify pgrst, 'reload schema';
