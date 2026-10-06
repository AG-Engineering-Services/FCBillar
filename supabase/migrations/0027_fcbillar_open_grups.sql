-- FCBillar cloud schema — els grups de cada fase d'un torneig individual.
--
-- La base de dades és Neon (projecte `fcbillar`); el nom de la carpeta és
-- herència. No s'aplica automàticament: l'admin valida el SQL i l'executa amb
-- `psql` i la connexió sense pool.
--
-- Fa falta per dir «quan jugues, on i contra qui» la ronda que ve. La federació
-- publica els grups d'una fase amb el sorteig, abans que es jugui cap partida:
-- quin dia, a quin club i qui hi ha. `open_fase_ranquing` no ho pot dir, perquè
-- només porta qui ja té classificació, i el dia i el club no eren enlloc.
--
-- Els jugadors van dins de la fila del grup (`jugadors`, una llista d'objectes
-- {jugador, player_fcb_id, club}): sempre es llegeixen junts i així no cal una
-- segona taula. Hi surten tots, hagin jugat o no.
--
-- L'hora no hi és: la federació només l'escriu al PDF del sorteig.

create table if not exists fcbillar.open_grups (
    open_id           integer not null,
    fase_id           integer not null,           -- id de la fase al portal de la FCB
    grup_nom          text not null,              -- 'Grup A'
    club_organitzador text,                       -- 'C.B.BANYOLES', on es juga
    data              date,                       -- el dia que es juga el grup
    jugadors          jsonb not null default '[]'::jsonb,
    primary key (open_id, fase_id, grup_nom),
    foreign key (open_id, fase_id) references fcbillar.open_fases(open_id, fase_id) on delete cascade
);
create index if not exists idx_fcbillar_open_grups_data on fcbillar.open_grups(data);

alter table fcbillar.open_grups enable row level security;
drop policy if exists "read open_grups" on fcbillar.open_grups;
create policy "read open_grups" on fcbillar.open_grups for select to anon, authenticated using (true);

-- RLS diu quines files es poden llegir; el GRANT, si el rol pot tocar la taula.
grant select on fcbillar.open_grups to anon, authenticated;
grant all on fcbillar.open_grups to service_role;

-- Qui passa de ronda. La regla és al PDF del sorteig («el primer de cada grup i
-- els quatre millors segons») i les places es calculen amb els grups que té la
-- fase. Amb `open_fase_ranquing.posicio` n'hi ha prou per dir qui ha passat:
-- els que queden dins de les places.
--
-- Són `null` quan no se sap: la final no té ronda següent, i una regla que no
-- encaixa amb cap patró conegut no es converteix en un nombre inventat.
alter table fcbillar.open_fases add column if not exists regla  text;
alter table fcbillar.open_fases add column if not exists places integer;

notify pgrst, 'reload schema';
