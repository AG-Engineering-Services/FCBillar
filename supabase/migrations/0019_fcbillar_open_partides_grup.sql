-- FCBillar cloud schema — de quin GRUP és cada partida d'un torneig individual.
--
-- Es guarda a `supabase/migrations/` perquè és on són les altres divuit, però la
-- base de dades és **Neon** (projecte `fcbillar`, esquemes `fcbillar` i
-- `fcb_opens`): Supabase va quedar congelat el 16/08/2026 i ja no hi pinta res.
-- El nom de la carpeta és herència. Vegeu `MIGRACIO-NEON.md`.
--
-- No s'aplica automàticament: l'admin valida el SQL i l'executa amb `psql` i la
-- connexió sense pool del projecte de Neon.
--
-- `open_partides` deia de quina FASE era cada partida però no de quin grup, i per
-- tant les partides d'una fase de grups eren un sac: es podia dir que eren de la
-- pre-prèvia, no quines eren del Grup A i quines del Grup K.
--
-- Fa falta per als CAMPIONATS DE CATALUNYA, que es llegeixen grup a grup: la
-- classificació del grup i, al costat, les partides que l'expliquen. Un campionat
-- de 2a divisió té catorze grups de tres jugadors, i sense el grup les 42
-- partides no es poden repartir.
--
-- `null` a les eliminatòries, que no tenen grup.

alter table fcbillar.open_partides add column if not exists grup_nom text;
create index if not exists idx_fcbillar_open_partides_grup
    on fcbillar.open_partides(open_id, fase_id, grup_nom);
