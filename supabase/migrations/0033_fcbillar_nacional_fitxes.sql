-- FCBillar cloud schema — quin nom de la Lliga Nacional és quina fitxa del cens.
--
-- La base de dades és Neon (projecte `fcbillar`). No s'aplica automàticament:
-- l'admin valida el SQL i l'executa amb `psql` i la connexió sense pool.
--
-- La RFEB i la FCB no comparteixen cap identificador. Cada fila és un lligam
-- validat a mà a `fonts/nacional/fitxes.csv`: el nom tal com l'escriu la RFEB
-- (un mateix jugador pot tenir-ne uns quants, d'anys diferents) i el `fcb_id` de
-- la fitxa. Només serveix perquè la fitxa del jugador ensenyi el seu apartat de
-- Lliga Nacional: no fa comptar res per a cap rànquing ni mitjana catalana.

create table if not exists fcbillar.nacional_fitxes (
    jugador     text primary key,           -- el nom a la RFEB
    fcb_id      text not null
);
create index if not exists nacional_fitxes_fcb_id on fcbillar.nacional_fitxes (fcb_id);

alter table fcbillar.nacional_fitxes enable row level security;
drop policy if exists "read nacional_fitxes" on fcbillar.nacional_fitxes;
create policy "read nacional_fitxes" on fcbillar.nacional_fitxes
    for select to anon, authenticated using (true);
grant select on fcbillar.nacional_fitxes to anon, authenticated;
grant all on fcbillar.nacional_fitxes to service_role;

notify pgrst, 'reload schema';
