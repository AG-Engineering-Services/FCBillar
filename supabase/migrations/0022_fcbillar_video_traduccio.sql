-- FCBillar cloud schema — el traductor de vídeos (secció «Aprèn» de la PWA).
--
-- Base de dades: **Neon** (vegeu 0018 i `MIGRACIO-NEON.md`). No s'aplica sola:
-- l'admin valida el SQL i l'executa amb `psql` i la connexió sense pool.
--
-- Qualsevol usuari de la PWA enganxa un enllaç de YouTube, Instagram o Facebook i
-- queda una fila 'pendent'. El workflow `traductor.yml` (GitHub Actions, cada
-- quart d'hora) la recull amb la service_role, transcriu amb el Whisper de NVIDIA,
-- tradueix al català amb el Llama de NVIDIA, genera la veu en off amb Piper i
-- penja l'àudio com a asset del release `traduccions` del repositori (públic i
-- gratuït). Tothom veu tots els vídeos traduïts.
--
-- NO es guarda el vídeo: la PWA incrusta l'original silenciat i hi posa a sobre
-- la pista catalana. Tornar a publicar el vídeo d'algú altre és un problema de
-- drets; una pista d'àudio sincronitzada sobre el reproductor oficial, no.
--
-- L'anon només pot INSERIR, i només `url`, `plataforma`, `video_id` i `idioma`: l'estat i
-- la resta de columnes surten dels valors per defecte. No pot tocar res més. Com
-- que no hi ha login, el fre contra abusos és el trigger: quan ja hi ha massa
-- feina a la cua, la petició es rebutja.

create table if not exists fcbillar.video_traduccio (
    id          bigint generated always as identity primary key,
    url         text not null check (length(url) between 10 and 500),
    plataforma  text not null check (plataforma in ('youtube', 'instagram', 'facebook')),
    video_id    text not null check (length(video_id) between 3 and 64),
    -- L'idioma el tria qui demana la traducció. La detecció automàtica del
    -- Whisper de NVIDIA ('multi') es va provar amb un vídeo coreà i el va
    -- transcriure en una altra escriptura: no s'hi pot confiar.
    idioma      text not null default 'ko' check (idioma in ('ko', 'vi', 'tr')),
    estat       text not null default 'pendent'
                check (estat in ('pendent', 'processant', 'fet', 'error')),
    titol       text,
    canal       text,
    durada      real,                        -- segons
    -- [{"t0": 1.2, "t1": 4.8, "orig": "…", "ca": "…"}, …], ordenats per t0.
    segments    jsonb,
    audio_url   text,                        -- mp3 de la veu en off, al release
    missatge    text,                        -- l'error, si n'hi ha
    intents     smallint not null default 0,
    creat       timestamptz not null default now(),
    processat   timestamptz
);
-- Un vídeo es tradueix una vegada i serveix per a tothom.
create unique index if not exists uq_fcbillar_video_traduccio_video
    on fcbillar.video_traduccio(plataforma, video_id);
create index if not exists idx_fcbillar_video_traduccio_estat
    on fcbillar.video_traduccio(estat, creat);

create or replace function fcbillar.video_traduccio_limit_cua()
returns trigger language plpgsql as $$
begin
    if (select count(*) from fcbillar.video_traduccio where estat = 'pendent') >= 20 then
        raise exception 'La cua del traductor és plena; torna-ho a provar més tard.';
    end if;
    return new;
end $$;
drop trigger if exists trg_video_traduccio_limit_cua on fcbillar.video_traduccio;
create trigger trg_video_traduccio_limit_cua
    before insert on fcbillar.video_traduccio
    for each row execute function fcbillar.video_traduccio_limit_cua();

alter table fcbillar.video_traduccio enable row level security;

drop policy if exists "read video_traduccio" on fcbillar.video_traduccio;
create policy "read video_traduccio" on fcbillar.video_traduccio
    for select to anon, authenticated using (true);

drop policy if exists "demana video_traduccio" on fcbillar.video_traduccio;
create policy "demana video_traduccio" on fcbillar.video_traduccio
    for insert to anon, authenticated with check (estat = 'pendent');

grant select on fcbillar.video_traduccio to anon, authenticated;
grant insert (url, plataforma, video_id, idioma) on fcbillar.video_traduccio to anon, authenticated;
grant select, insert, update, delete on fcbillar.video_traduccio to service_role;
