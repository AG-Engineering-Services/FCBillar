-- La PWA no podia encuar reingestes: «permission denied for table
-- reingest_requests». La política d'inserció de la 0010 va arribar a Neon, però
-- el GRANT INSERT a anon no, i sense el grant la política no arriba a avaluar-se.
-- Detectat el 07/11/2026; l'última petició que hi havia entrat era del 27/07.
--
-- Només les columnes que omple la fitxa, com a video_traduccio (0022): l'estat,
-- les dates i els comptadors els escriu el workflow amb la service_role.

grant insert (requested_email, source) on fcbillar.reingest_requests to anon, authenticated;
