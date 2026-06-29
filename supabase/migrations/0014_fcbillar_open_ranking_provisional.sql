-- FCBillar — marca PROVISIONAL a la ronda vigent del Rànquing Català d'Opens 3B.
--
-- La FCB publica la CLASSIFICACIÓ final d'un open abans de refrescar el PDF del
-- RÀNQUING oficial. En aquesta finestra de temps `publish_open_ranking` ja calcula
-- la ronda vigent amb els punts de la classificació final, però com que el rànquing
-- oficial encara no l'inclou, la ronda es marca provisional=true (i el desglossament
-- de l'open més recent porta `prov: true`). Quan el PDF oficial s'actualitza i casa
-- amb la finestra vigent, s'apliquen les penalitzacions i provisional torna a false.
--
-- Additiva i segura: columna nova amb default. Les files existents queden a false.

alter table fcbillar.open_ranking
    add column if not exists provisional boolean not null default false;
