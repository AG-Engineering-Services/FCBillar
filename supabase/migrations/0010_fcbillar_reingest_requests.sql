-- FCBillar cloud schema — cua de reingesta disparada des del PWA.
--
-- El botó de la fitxa de l'Albert Gómez (fcb_id 278) insereix una fila aquí amb
-- la clau anon. Un watcher al PC de casa (scripts/reingest_watcher.ps1) consulta
-- les peticions pendents amb la service_role i executa scripts/weekly_reingest.ps1
-- (la reingesta ha de córrer en local: necessita les BD SQLite i la sessió de
-- login amb captcha, que no viuen al núvol).
--
-- Seguretat: l'anon NOMÉS pot inserir files amb email = algoam@gmail.com i estat
-- inicial 'pending' (gate de servidor a més del prompt del client). Lectura anon
-- permesa per mostrar l'estat de l'última petició a la fitxa. L'escriptura
-- d'estat (running/done/error) la fa només la service_role (salta RLS).

create table if not exists fcbillar.reingest_requests (
    id              uuid primary key default gen_random_uuid(),
    requested_at    timestamptz not null default now(),
    requested_email text not null,
    source          text,                              -- p.ex. 'fitxa/278'
    status          text not null default 'pending',   -- pending|running|done|error
    started_at      timestamptz,
    finished_at     timestamptz,
    n_ok            integer,
    n_fail          integer,
    message         text
);
create index if not exists idx_fcbillar_reingest_status
    on fcbillar.reingest_requests(status, requested_at desc);

-- =========================================================================
-- RLS: lectura pública; inserció anon només amb el correu autoritzat
-- =========================================================================
alter table fcbillar.reingest_requests enable row level security;

create policy "read reingest_requests"
    on fcbillar.reingest_requests for select to anon, authenticated using (true);

create policy "insert reingest_requests (gated)"
    on fcbillar.reingest_requests for insert to anon, authenticated
    with check (requested_email = 'algoam@gmail.com' and status = 'pending');

grant select, insert on fcbillar.reingest_requests to anon, authenticated;
