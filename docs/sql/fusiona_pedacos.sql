-- Fusiona les fitxes de pedaç amb la fitxa de llicència de la mateixa persona.
--
-- Quan una llista d'opens porta el nom i no el número de llicència, es crea una
-- fitxa provisional identificada pel nom (`name:COGNOMS, NOM`) per no perdre el
-- resultat. Si aquella persona ja té fitxa amb llicència, en queden dues i surt
-- dos cops a la cerca.
--
-- En LOCAL això ja es resol sol: `Repository.upsert_player` promociona el pedaç
-- quan arriba la llicència, reanomenant-li l'identificador. El que no passa mai
-- és que el núvol se n'assabenti, perquè la publicació de jugadors només fa
-- upsert i no retira res: allà hi queden les dues fitxes.
--
-- Aquest guió arregla el núvol. És repetible: si no hi ha res a fusionar, no fa
-- res. El 5 de setembre de 2026 en va fusionar 28.
--
--   uv run python <guió de connexió> -f docs/sql/fusiona_pedacos.sql
--
-- Només es toca el que és la mateixa persona sense dubte raonable: mateix nom
-- I mateix club a les dues fitxes, i una sola fitxa amb llicència per a aquell
-- nom. Els pedaços de gent que NO té llicència no es toquen: són els únics que
-- en tenim i porten els seus resultats -667 el mateix dia.
BEGIN;

CREATE TEMP TABLE parelles ON COMMIT DROP AS
SELECT a.fcb_id AS pedac, b.fcb_id AS bo
  FROM fcbillar.players a
  JOIN fcbillar.players b
    ON b.nom = a.nom
   AND b.fcb_id NOT LIKE 'name:%'
   AND b.club_fcb_id IS NOT DISTINCT FROM a.club_fcb_id
 WHERE a.fcb_id LIKE 'name:%'
   -- Amb dues fitxes de llicència pel mateix nom no se sap a quina va: es deixa.
   AND (SELECT count(*) FROM fcbillar.players c
         WHERE c.nom = a.nom AND c.fcb_id NOT LIKE 'name:%') = 1;

SELECT 'parelles a fusionar: ' || count(*) FROM parelles;

-- Els resultats passen a la fitxa bona, menys els que ja hi són: aquells el
-- pedaç els duplicava.
UPDATE fcbillar.open_ranking o SET player_fcb_id = p.bo
  FROM parelles p
 WHERE o.player_fcb_id = p.pedac
   AND NOT EXISTS (SELECT 1 FROM fcbillar.open_ranking x
                    WHERE x.genere = o.genere AND x.ronda = o.ronda AND x.player_fcb_id = p.bo);
DELETE FROM fcbillar.open_ranking o USING parelles p WHERE o.player_fcb_id = p.pedac;

UPDATE fcbillar.open_classifications o SET player_fcb_id = p.bo
  FROM parelles p
 WHERE o.player_fcb_id = p.pedac
   AND NOT EXISTS (SELECT 1 FROM fcbillar.open_classifications x
                    WHERE x.open_id = o.open_id AND x.player_fcb_id = p.bo);
DELETE FROM fcbillar.open_classifications o USING parelles p WHERE o.player_fcb_id = p.pedac;

DELETE FROM fcbillar.players a USING parelles p WHERE a.fcb_id = p.pedac;

SELECT 'jugadors que queden: ' || count(*) FROM fcbillar.players;
SELECT 'pedacos amb homonim de llicencia: ' || count(*)
  FROM fcbillar.players a
 WHERE a.fcb_id LIKE 'name:%'
   AND EXISTS (SELECT 1 FROM fcbillar.players b WHERE b.nom = a.nom AND b.fcb_id NOT LIKE 'name:%');
SELECT 'files d opens orfes: ' || count(*) FROM fcbillar.open_ranking o
 WHERE NOT EXISTS (SELECT 1 FROM fcbillar.players p WHERE p.fcb_id = o.player_fcb_id);

COMMIT;
