-- FCBillar cloud schema — còpia del vídeo per als que no es poden incrustar.
--
-- Base de dades: **Neon** (vegeu 0018). No s'aplica sola: l'admin l'executa amb
-- `psql` i la connexió sense pool.
--
-- Instagram i Facebook no deixen controlar el reproductor incrustat: no s'hi pot
-- sincronitzar la veu catalana ni posar-hi subtítols. Per a aquests vídeos, el
-- workflow en desa una còpia a 480p al release `traduccions` i la PWA la reprodueix
-- amb el seu reproductor. YouTube continua sense còpia: es fa servir l'oficial.
--
-- Decisió de l'admin del 24/09/2026. La còpia és pública (el repositori ho és):
-- és el vídeo d'algú altre, i si l'autor ho demana s'ha d'eliminar.

alter table fcbillar.video_traduccio add column if not exists video_url text;
