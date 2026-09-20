-- FCBillar cloud schema — les fases d'un torneig individual i el rànquing de cada fase.
--
-- Es guarda a `supabase/migrations/` perquè és on són les altres setze, però la
-- base de dades és **Neon** (projecte `fcbillar`, esquemes `fcbillar` i
-- `fcb_opens`): Supabase va quedar congelat el 16/08/2026 i ja no hi pinta res.
-- El nom de la carpeta és herència. Vegeu `MIGRACIO-NEON.md`.
--
-- No s'aplica automàticament: l'admin valida el SQL i l'executa amb `psql` i la
-- connexió sense pool del projecte de Neon.
--
-- Fa falta per als CAMPIONATS DE CATALUNYA, que es juguen per rondes: pre-prèvia,
-- prèvia, vuitens, i després el quadre. La federació publica la classificació de
-- cada grup («Grup I - CLASSIFICACIÓ»: jugador, punts, mitjana) però cap ordre
-- ENTRE grups, i sense aquell ordre no es pot dir qui s'ha classificat: quan
-- passen «els dos primers de cada grup» n'hi ha prou amb la posició, però quan
-- passen els millors segons —o uns quants tercers— cal comparar-los.
--
-- L'ordre és el que aplica la federació: primer la posició dins del grup, després
-- els punts de la ronda, i a igualtat de tots dos la mitjana. El calcula
-- `fcbillar.individuals.ranquing_fase` i el puja `publish_open_fases`.
--
-- `open_fase_ranquing` no és la classificació final del torneig —això és
-- `open_classifications`— sinó la foto d'una ronda: qui hi ha jugat i en quin
-- ordre ha quedat. Un jugador hi surt un cop per fase que hagi disputat.

create table if not exists fcbillar.open_fases (
    open_id  integer not null references fcbillar.opens(open_id) on delete cascade,
    fase_id  integer not null,              -- id de la fase al portal de la FCB
    nom      text not null,                 -- 'PRE-PRÈVIA', 'PRÈVIA', 'QUARTS'…
    tipus    text not null default '',      -- 'grups' | 'ko'
    ordre    integer,                       -- 1 = la primera que es juga
    data     date,                          -- el dia que es juga, si el portal el diu
    primary key (open_id, fase_id)
);
create index if not exists idx_fcbillar_open_fases_open on fcbillar.open_fases(open_id);

create table if not exists fcbillar.open_fase_ranquing (
    open_id       integer not null,
    fase_id       integer not null,
    posicio       integer not null,          -- l'ordre entre TOTS els grups de la fase
    jugador       text not null,
    player_fcb_id text,
    grup_nom      text,
    posicio_grup  integer,                   -- com ha quedat dins del seu grup
    punts         integer,                   -- punts de la ronda (2 per victòria, 1 per empat)
    mitjana       double precision,          -- null = no ha jugat cap partida
    -- El club amb què juga AQUEST campionat, que no és necessàriament el de la
    -- lliga: ve de `fcbillar.afiliacions` (competicio = 'INDIVIDUAL').
    --
    -- No entra a l'ordre del rànquing i no hi ha d'entrar: la federació ordena
    -- per posició al grup, punts de la ronda i mitjana, i el club no hi juga cap
    -- paper. Hi és per poder llegir la llista, que és una altra cosa.
    club          text
    primary key (open_id, fase_id, jugador),
    foreign key (open_id, fase_id) references fcbillar.open_fases(open_id, fase_id) on delete cascade
);
create index if not exists idx_fcbillar_ofr_fase on fcbillar.open_fase_ranquing(open_id, fase_id);
create index if not exists idx_fcbillar_ofr_player on fcbillar.open_fase_ranquing(player_fcb_id);

alter table fcbillar.open_fases         enable row level security;
alter table fcbillar.open_fase_ranquing enable row level security;
create policy "read open_fases"         on fcbillar.open_fases         for select to anon, authenticated using (true);
create policy "read open_fase_ranquing" on fcbillar.open_fase_ranquing for select to anon, authenticated using (true);

-- Si la taula ja existia d'una execució anterior d'aquest fitxer, la columna del
-- club s'hi afegeix aquí. Les dues formes deixen el mateix resultat.
alter table fcbillar.open_fase_ranquing add column if not exists club text;
