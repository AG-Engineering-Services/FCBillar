-- FCBillar cloud schema — cua per GENERAR un open en curs PROJECTAT des del PWA.
--
-- El botó "Genera open des del rànquing inicial" (web/PWA, admin-gated) llegeix
-- el PDF oficial 'RÀNQUING INICIAL' d'un open, el codifica en base64 i insereix
-- una fila aquí amb la clau anon. Un watcher al PC de casa
-- (scripts/open_projection_watcher.ps1) consulta les peticions pendents amb la
-- service_role, desa el base64 a un .pdf temporal i executa
-- `fcbillar project-open-ranking` (que parseja, genera els grups de totes les
-- fases i publica l'open projectat a fcbillar.open_live amb un id sintètic
-- negatiu). La generació ha de córrer en local perquè reusa el motor Python i
-- resol els fcb_id contra la BD.
--
-- El PDF viatja DINS la fila (base64, ~0,4 MB) per no haver de muntar un bucket
-- de Supabase Storage ni les seves polítiques: són càrregues puntuals d'admin.
--
-- Seguretat: mateixa postura (soft-gate) que reingest_requests — l'anon només
-- pot inserir amb email = algoam@gmail.com i estat 'pending'. Lectura anon per
-- mostrar l'estat. L'escriptura d'estat (running/done/error) i el buidat del
-- base64 en acabar els fa només la service_role (salta RLS).

create table if not exists fcbillar.open_projection_requests (
    id              uuid primary key default gen_random_uuid(),
    requested_at    timestamptz not null default now(),
    requested_email text not null,
    source          text,                              -- p.ex. 'opens/upload'
    season          text,                              -- temporada, ex '2025-2026'
    file_name       text,                              -- nom original del PDF
    pdf_base64      text not null,                     -- PDF 'RÀNQUING INICIAL' en base64
    status          text not null default 'pending',   -- pending|running|done|error
    started_at      timestamptz,
    finished_at     timestamptz,
    division_id     integer,                           -- id sintètic negatiu assignat
    open_name       text,                              -- nom d'open llegit del PDF
    n_players       integer,                           -- inscrits llegits
    message         text
);
create index if not exists idx_fcbillar_open_projection_status
    on fcbillar.open_projection_requests(status, requested_at desc);

-- =========================================================================
-- RLS: lectura pública; inserció anon només amb el correu autoritzat
-- =========================================================================
alter table fcbillar.open_projection_requests enable row level security;

create policy "read open_projection_requests"
    on fcbillar.open_projection_requests for select to anon, authenticated using (true);

create policy "insert open_projection_requests (gated)"
    on fcbillar.open_projection_requests for insert to anon, authenticated
    with check (requested_email = 'algoam@gmail.com' and status = 'pending');

grant select, insert on fcbillar.open_projection_requests to anon, authenticated;
