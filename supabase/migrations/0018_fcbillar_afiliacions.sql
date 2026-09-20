-- FCBillar cloud schema — amb quin club juga cadascú CADA competició.
--
-- Es guarda a `supabase/migrations/` perquè és on són les altres setze, però la
-- base de dades és **Neon** (projecte `fcbillar`, esquemes `fcbillar` i
-- `fcb_opens`): Supabase va quedar congelat el 16/08/2026 i ja no hi pinta res.
-- El nom de la carpeta és herència. Vegeu `MIGRACIO-NEON.md`.
--
-- No s'aplica automàticament: l'admin valida el SQL i l'executa amb `psql` i la
-- connexió sense pool del projecte de Neon.
--
-- `player_clubs` ja diu el club d'un jugador per temporada, i per a l'històric fa
-- el fet. Per a la temporada en curs no, perquè un jugador no en té un: en té un
-- per competició, i la federació ho publica així.
--
-- Passa de debò a la 2026-27: quatre jugadors van fitxats a la lliga de 4
-- Modalitats per un club i a la de tres bandes per un altre, i dos juguen el
-- campionat individual per un club diferent del de la lliga. Amb una fila per
-- jugador i temporada, una de les dues respostes ha de ser falsa.
--
-- D'on surt cada fila:
--   font = 'lliga_inscrits'  → `lligues/participants/{lliga}/{club}`, la llista
--                              oficial de cada club, que marca els fitxatges.
--   font = 'sorteig_fase'    → el PDF del sorteig d'una ronda del campionat
--                              individual. És l'ÚNICA font que diu el club de
--                              l'individual: cap pàgina del portal no el publica.
--
-- ATENCIÓ QUI LA LLEGEIXI: la 2026-27 ja en són **1.086 files**, i el Data API
-- torna **mil files i prou** sense dir-ho. Un `select('*')` sense `range()` en
-- perd 86 en silenci, i no es veu: la resposta arriba bé, només que curta. Cal
-- `range()` explícit o filtrar per (temporada, competicio, modalitat).
--
-- El jugador va pel nom perquè cap de les dues fonts no en dona l'identificador.
-- `player_fcb_id` s'omple quan el nom casa amb una fitxa nostra, i queda null
-- per a qui s'acaba de federar i encara no ha jugat res.

create table if not exists fcbillar.afiliacions (
    temporada     text not null,                 -- '2026/2027'
    competicio    text not null,                 -- 'LLIGA' | 'INDIVIDUAL'
    modalitat     text not null,                 -- 'Tres bandes' | '4 Modalitats' | …
    jugador       text not null,                 -- 'COGNOMS, NOM'
    player_fcb_id text,
    club          text not null,                 -- nom del cens, ja canonicalitzat
    -- 1 = hi ve fitxat d'un altre club. A la lliga la federació ho marca; al
    -- sorteig de l'individual no, i llavors és 0 perquè no ho sabem.
    fitxatge      boolean not null default false,
    font          text not null,
    primary key (temporada, competicio, modalitat, jugador)
);
create index if not exists idx_fcbillar_afiliacions_jugador
    on fcbillar.afiliacions(temporada, jugador);
create index if not exists idx_fcbillar_afiliacions_club
    on fcbillar.afiliacions(temporada, club);
create index if not exists idx_fcbillar_afiliacions_player
    on fcbillar.afiliacions(player_fcb_id);

alter table fcbillar.afiliacions enable row level security;
create policy "read afiliacions" on fcbillar.afiliacions
    for select to anon, authenticated using (true);
