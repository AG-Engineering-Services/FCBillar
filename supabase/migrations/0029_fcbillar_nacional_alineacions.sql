-- FCBillar cloud schema — qui té inscrit cada equip de la Lliga Nacional.
--
-- La base de dades és Neon (projecte `fcbillar`). No s'aplica automàticament:
-- l'admin valida el SQL i l'executa amb `psql` i la connexió sense pool.
--
-- La classificació de jugadors de la RFEB només porta qui ja ha jugat alguna
-- partida. Per ensenyar TOTS els jugadors d'un equip cal l'«orden de fuerza», el
-- document on cada club diu a qui té inscrit i en quin ordre.
--
-- D'aquell document només se'n desa això: grup, equip, número d'ordre i nom del
-- jugador. Hi ha també adreces, telèfons i correus de directius, que no es
-- llegeixen ni arriben mai aquí.
--
-- Com la resta de `nacional_*`, és a part de la federació catalana: cap columna
-- apunta a `players` ni a `clubs`.

create table if not exists fcbillar.nacional_alineacions (
    temporada   text not null,
    divisio     text not null,
    grup        text not null default '',
    equip       text not null,
    ordre       integer not null,           -- el número d'ordre de força
    jugador     text not null,
    primary key (temporada, divisio, equip, ordre)
);

alter table fcbillar.nacional_alineacions enable row level security;
drop policy if exists "read nacional_alineacions" on fcbillar.nacional_alineacions;
create policy "read nacional_alineacions" on fcbillar.nacional_alineacions
    for select to anon, authenticated using (true);
grant select on fcbillar.nacional_alineacions to anon, authenticated;
grant all on fcbillar.nacional_alineacions to service_role;

notify pgrst, 'reload schema';
