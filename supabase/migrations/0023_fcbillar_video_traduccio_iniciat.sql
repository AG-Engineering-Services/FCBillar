-- FCBillar cloud schema — quan comença cada traducció, per estimar-ne el temps.
--
-- Base de dades: **Neon** (vegeu 0018). No s'aplica sola: l'admin l'executa amb
-- `psql` i la connexió sense pool.
--
-- `processat` es reescriu en acabar, així que no diu quant ha trigat. Amb
-- `iniciat` (quan el workflow agafa la fila) i `durada` (el vídeo), la PWA treu
-- el ritme real de traducció dels vídeos ja fets i estima quan estarà llest el
-- que s'està traduint i els que esperen a la cua.

alter table fcbillar.video_traduccio add column if not exists iniciat timestamptz;
