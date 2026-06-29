-- FCBillar cloud schema — estat de l'última reingesta al núvol (GitHub Actions).
--
-- La reingesta ja no corre al PC sinó a GitHub Actions (.github/workflows/reingest.yml).
-- El job escriu aquí l'estat resultant via `fcbillar state report` (service_role):
-- si la sessió de login encara és vàlida i quants passos han anat bé/malament.
-- El PWA llegeix aquesta fila (anon) per mostrar un banner quan cal re-login al PC.
--
-- És una taula d'UNA SOLA FILA (id=1). Seguretat: lectura anon/authenticated;
-- l'escriptura la fa només la service_role (salta RLS).

create table if not exists fcbillar.cloud_status (
    id          integer primary key default 1 check (id = 1),
    session_ok  boolean not null default true,    -- false => sessió caducada, cal re-login al PC
    last_run    timestamptz,                       -- fi de l'última execució del job
    last_error  text,                              -- resum del darrer error (si n'hi ha)
    n_ok        integer,                           -- passos correctes
    n_fail      integer,                           -- passos fallats
    updated_at  timestamptz not null default now()
);

-- Sembra la fila única perquè el primer `report` faci upsert sense soroll.
insert into fcbillar.cloud_status (id) values (1) on conflict (id) do nothing;

-- =========================================================================
-- RLS: lectura pública (per al banner); escriptura només service_role
-- =========================================================================
alter table fcbillar.cloud_status enable row level security;

create policy "read cloud_status"
    on fcbillar.cloud_status for select to anon, authenticated using (true);

grant select on fcbillar.cloud_status to anon, authenticated;
