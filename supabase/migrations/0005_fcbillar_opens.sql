-- FCBillar cloud schema — FASE 5: Opens (torneigs individuals) + classificacions.
--
-- opens: torneig (id del portal, nom). open_classifications: classificació final
-- (posició, jugador, club, partides, punts, mitjana, sèrie). RLS lectura pública.

create table if not exists fcbillar.opens (
    open_id      integer primary key,   -- torneig_id_extern (id del portal)
    nom          text not null,
    temporada_id integer
);

create table if not exists fcbillar.open_classifications (
    open_id            integer not null references fcbillar.opens(open_id) on delete cascade,
    posicio            integer,
    player_fcb_id      text,
    jugador            text,
    club               text,
    partides           integer,
    punts              integer,
    caramboles         integer,
    entrades           integer,
    mitjana_general    double precision,
    mitjana_particular double precision,
    serie_max          integer,
    primary key (open_id, player_fcb_id)
);
create index if not exists idx_fcbillar_openclass_open on fcbillar.open_classifications(open_id);
create index if not exists idx_fcbillar_openclass_player on fcbillar.open_classifications(player_fcb_id);

alter table fcbillar.opens                enable row level security;
alter table fcbillar.open_classifications enable row level security;
create policy "read opens"                on fcbillar.opens                for select to anon, authenticated using (true);
create policy "read open_classifications" on fcbillar.open_classifications for select to anon, authenticated using (true);
