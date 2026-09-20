-- FCBillar cloud schema — la ronda següent d'un campionat, projectada.
--
-- Es guarda a `supabase/migrations/` perquè és on són les altres vint, però la
-- base de dades és **Neon** (projecte `fcbillar`): Supabase va quedar congelat el
-- 16/08/2026. El nom de la carpeta és herència. Vegeu `MIGRACIO-NEON.md`.
--
-- No s'aplica automàticament: l'admin valida el SQL i l'executa amb `psql`.
--
-- Quan s'acaba una pre-prèvia ja se sap QUI passa —la regla és al PDF del sorteig
-- i l'ordre entre grups es calcula— però la federació tarda dies a publicar COM
-- queden repartits. Això es projecta, com el rànquing provisional, i la publicació
-- oficial el substitueix.
--
-- QUÈ ÉS EXACTE I QUÈ NO, que qui llegeixi la taula ho ha de saber:
--
--   jugador, posicio  -> la regla del PDF + la classificació publicada.  EXACTE
--   bombo             -> del nombre de places i la mida de grup.         EXACTE
--   grup_projectat    -> el repartiment que fa FCBillar.                 PROJECCIÓ
--
-- L'última no es pot encertar: el sorteig de la federació és GEOGRÀFIC. Al PDF de
-- la prèvia d'Honor de 2026-27 la seu de cada grup té sempre jugadors de casa i
-- els clubs no se separen —tres del Granollers al mateix grup—, i les seus no es
-- publiquen fins que surt el sorteig.
--
-- O sigui que d'aquesta taula el que val de debò és el BOMBO: qui et pot tocar és
-- algú de cada un dels altres, i això no canviarà. El grup concret sí.
--
-- Es buida sola: quan la federació publica els grups de la ronda, la projecció es
-- retira de la base local i la publicació se l'endú d'aquí.

create table if not exists fcbillar.open_ronda_projectada (
    open_id        integer not null references fcbillar.opens(open_id) on delete cascade,
    ronda          text not null,              -- 'PRÈVIA', la ronda projectada
    jugador        text not null,
    player_fcb_id  text,
    -- L'ordre al rànquing de la ronda que s'acaba de jugar.
    posicio        integer not null,
    bombo          integer not null,
    grup_projectat text not null,
    mida_grup      integer not null,
    club           text,
    primary key (open_id, ronda, jugador)
);
create index if not exists idx_fcbillar_ronda_proj_open
    on fcbillar.open_ronda_projectada(open_id, ronda);
create index if not exists idx_fcbillar_ronda_proj_player
    on fcbillar.open_ronda_projectada(player_fcb_id);

alter table fcbillar.open_ronda_projectada enable row level security;
drop policy if exists "read open_ronda_projectada" on fcbillar.open_ronda_projectada;
create policy "read open_ronda_projectada" on fcbillar.open_ronda_projectada
    for select to anon, authenticated using (true);

-- RLS diu quines files es poden llegir; el GRANT diu si el rol pot tocar la taula
-- per començar. Sense ell la publicació peta amb «permission denied for table», i
-- no es veu: crear la taula i la política sembla que ja estigui.
grant select on fcbillar.open_ronda_projectada to anon, authenticated;
grant all on fcbillar.open_ronda_projectada to service_role;
