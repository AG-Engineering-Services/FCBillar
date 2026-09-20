-- FCBillar cloud schema — la data d'una partida pendent.
--
-- Es guarda a `supabase/migrations/` perquè és on són les altres dinou, però la
-- base de dades és **Neon** (projecte `fcbillar`): Supabase va quedar congelat el
-- 16/08/2026. El nom de la carpeta és herència. Vegeu `MIGRACIO-NEON.md`.
--
-- No s'aplica automàticament: l'admin valida el SQL i l'executa amb `psql`.
--
-- `pending_games` són les partides jugades que el rànquing encara no ha publicat
-- —i el rànquing surt un cop al mes—. No portaven data, i per a la fitxa no feia
-- falta: allà surten com a pendents i prou.
--
-- Però `public.partides` de l'app d'Estadístiques (c3b) creua les partides
-- federatives amb les del jugador **per data**: signatura del marcador, primer
-- cognom del rival, i la data més propera dins d'una finestra de seixanta dies.
-- Una fila sense data no casa amb res i tampoc no s'hi pot inserir, o sigui que
-- desapareixia en silenci: es veia a la fitxa i no a c3b.
--
-- Avís sobre què vol dir aquesta data a la LLIGA: és la data de la **jornada**,
-- no el dia exacte. El web nou no publica cap data per partida —el vell sí— i un
-- encontre avançat es juga dies abans del que diu el calendari. És el que tenim.

alter table fcbillar.pending_games add column if not exists data date;
create index if not exists idx_fcbillar_pending_games_data
    on fcbillar.pending_games(data);
