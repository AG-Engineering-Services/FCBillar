-- FCBillar cloud schema — calendari esportiu federatiu (pestanya «Calendari»).
--
-- Origen: dos PDF per temporada, tots dos parsejats per `fcbillar.calendari_fed` i
-- pujats per `publish_calendari`. El de la RFEB (`cal_rfeb_2627.pdf`) hi entra amb
-- `font = 'RFEB'` i el de la FCB, que la federació catalana publica més tard, amb
-- `font = 'FCB'`; d'aquest últim només se n'agafa la meitat catalana (`ambit =
-- 'catala'`), perquè la resta és una còpia del calendari estatal.
--
-- Una fila per cel·la de la graella del PDF: setmana × (disciplina, àmbit, tipus).
-- El PDF només concreta el CAP DE SETMANA, no el dia i hora exactes; `data_inici`
-- i `data_fi` són el rang de dies que la cel·la ocupa a la graella.
--
-- No s'hi puja la columna `raw` de la BD local (les línies crues del PDF): serveix
-- per auditar el parser al PC i no aporta res al frontend.

create table if not exists fcbillar.calendari_events (
    font        text not null,                 -- 'RFEB' | 'FCB'
    temporada   text not null,                 -- '2026/2027'
    setmana     date not null,                 -- dilluns de la setmana
    disciplina  text not null,                 -- carambola | pool | snooker
    ambit       text not null,                 -- nacional | internacional | mixt | tot
    grup        text not null default '',       -- 'Tres bandes' | 'Jocs de sèrie…' | ''
    tipus       text not null default '',       -- equips | individual | ''
    data_inici  date not null,
    data_fi     date not null,
    titol       text not null,
    seu         text,                          -- null = sense seu al PDF (o «?»)
    dissabte    text,                          -- què es juga el ds (patró LIGA NACIONAL)
    diumenge    text,
    col_span    integer not null default 1,     -- >1 = cel·la fusionada (Nadal, S. Santa)
    primary key (font, temporada, setmana, disciplina, ambit, grup, tipus)
);

create index if not exists ix_calendari_events_setmana
    on fcbillar.calendari_events (setmana);

-- Revisions del PDF. La RFEB en va publicant de noves sobre la MATEIXA URL
-- («CALENDARIO V.1 actualizado a 28/07/2026»), per això la clau és el sha256 del
-- contingut i no la versió que hi diu. `last_checked_at` es refresca a cada
-- comprovació encara que no hi hagi canvis: així la web pot dir «comprovat avui».
create table if not exists fcbillar.calendari_revisions (
    font            text not null,
    temporada       text not null,
    sha256          text not null,
    versio          text,                       -- 'V.1' tal com ho escriu el PDF
    data_versio     date,                       -- del "actualizado a dd/mm/aaaa"
    url             text,
    n_events        integer not null default 0,
    n_canvis        integer not null default 0,
    ingested_at     timestamptz,                -- quan va entrar aquest contingut
    last_checked_at timestamptz,                -- última comprovació (amb o sense canvis)
    primary key (font, temporada, sha256)
);

-- Què ha mogut la RFEB d'una revisió a l'altra. És el que fa útil revisar el PDF
-- periòdicament: no només estar al dia, sinó veure els canvis.
create table if not exists fcbillar.calendari_canvis (
    font        text not null,
    temporada   text not null,
    sha256      text not null,                  -- revisió que introdueix el canvi
    ord         integer not null,               -- ordre dins la revisió
    tipus_canvi text not null,                  -- alta | baixa | modificacio
    setmana     date not null,
    disciplina  text not null,
    ambit       text not null,
    grup        text,
    tipus       text,
    abans       text,
    despres     text,
    primary key (font, temporada, sha256, ord)
);

create index if not exists ix_calendari_canvis_rev
    on fcbillar.calendari_canvis (font, temporada, sha256);

-- =========================================================================
-- RLS: lectura pública (la PWA hi entra amb anon); escriptura només service_role
-- =========================================================================
alter table fcbillar.calendari_events    enable row level security;
alter table fcbillar.calendari_revisions enable row level security;
alter table fcbillar.calendari_canvis    enable row level security;

create policy "read calendari_events"
    on fcbillar.calendari_events for select to anon, authenticated using (true);
create policy "read calendari_revisions"
    on fcbillar.calendari_revisions for select to anon, authenticated using (true);
create policy "read calendari_canvis"
    on fcbillar.calendari_canvis for select to anon, authenticated using (true);

grant select on fcbillar.calendari_events    to anon, authenticated;
grant select on fcbillar.calendari_revisions to anon, authenticated;
grant select on fcbillar.calendari_canvis    to anon, authenticated;
