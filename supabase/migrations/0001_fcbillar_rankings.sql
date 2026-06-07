-- FCBillar cloud schema (Supabase / Postgres) — FASE 1: rànquings.
--
-- Totes les taules viuen en un schema dedicat `fcbillar` per no barrejar-se
-- amb `public` ni amb `fcb_opens`. DESPRÉS d'aplicar aquesta migració has
-- d'exposar el schema: Supabase Dashboard → Project Settings → API →
-- Exposed schemas → afegeix `fcbillar` a la llista.
--
-- Patró (mirall de fcb-opens):
--   • claus naturals (fcb_id / codi) perquè el sync des de SQLite sigui
--     idempotent via upsert, sense haver de mapejar ids interns;
--   • RLS activat a totes les taules; anon + authenticated només SELECT;
--   • només service_role (que salta RLS) escriu.

-- =========================================================================
-- Schema + grants
-- =========================================================================
create schema if not exists fcbillar;

grant usage on schema fcbillar to anon, authenticated;
alter default privileges in schema fcbillar grant select on tables to anon, authenticated;
alter default privileges in schema fcbillar grant execute on functions to anon, authenticated;

grant usage on schema fcbillar to service_role;
alter default privileges in schema fcbillar grant all privileges on tables to service_role;
alter default privileges in schema fcbillar grant all privileges on sequences to service_role;
alter default privileges in schema fcbillar grant execute on functions to service_role;

-- =========================================================================
-- Taules (claus naturals)
-- =========================================================================
create table if not exists fcbillar.modalitats (
    codi_fcb integer primary key,
    nom      text not null
);

create table if not exists fcbillar.clubs (
    fcb_id text primary key,
    nom    text not null
);

create table if not exists fcbillar.players (
    fcb_id      text primary key,
    nom         text not null,
    club_fcb_id text references fcbillar.clubs(fcb_id),
    seguiment   boolean not null default false
);
create index if not exists idx_fcbillar_players_club on fcbillar.players(club_fcb_id);

create table if not exists fcbillar.rankings (
    modalitat_codi integer not null references fcbillar.modalitats(codi_fcb),
    num_seq        integer not null,
    any_pub        integer,
    mes_pub        integer,
    primary key (modalitat_codi, num_seq)
);

create table if not exists fcbillar.ranking_entries (
    modalitat_codi     integer not null,
    num_seq            integer not null,
    player_fcb_id      text not null references fcbillar.players(fcb_id),
    posicio            integer,
    mitjana_general    double precision,
    mitjana_particular double precision,
    partides           integer,
    primary key (modalitat_codi, num_seq, player_fcb_id),
    foreign key (modalitat_codi, num_seq)
        references fcbillar.rankings(modalitat_codi, num_seq) on delete cascade
);
create index if not exists idx_fcbillar_re_rank on fcbillar.ranking_entries(modalitat_codi, num_seq);
create index if not exists idx_fcbillar_re_player on fcbillar.ranking_entries(player_fcb_id);

-- Vista de conveniència: classificació amb nom de jugador i club resolts.
create or replace view fcbillar.ranking_full as
    select re.modalitat_codi,
           re.num_seq,
           re.posicio,
           re.player_fcb_id,
           p.nom        as jugador,
           c.nom        as club,
           re.mitjana_general,
           re.mitjana_particular,
           re.partides
    from fcbillar.ranking_entries re
    join fcbillar.players p on p.fcb_id = re.player_fcb_id
    left join fcbillar.clubs c on c.fcb_id = p.club_fcb_id;

-- =========================================================================
-- RLS: lectura pública (anon + authenticated); escriptura només service_role
-- =========================================================================
alter table fcbillar.modalitats      enable row level security;
alter table fcbillar.clubs           enable row level security;
alter table fcbillar.players         enable row level security;
alter table fcbillar.rankings        enable row level security;
alter table fcbillar.ranking_entries enable row level security;

create policy "read modalitats"      on fcbillar.modalitats      for select to anon, authenticated using (true);
create policy "read clubs"           on fcbillar.clubs           for select to anon, authenticated using (true);
create policy "read players"         on fcbillar.players         for select to anon, authenticated using (true);
create policy "read rankings"        on fcbillar.rankings        for select to anon, authenticated using (true);
create policy "read ranking_entries" on fcbillar.ranking_entries for select to anon, authenticated using (true);

grant select on fcbillar.ranking_full to anon, authenticated;
