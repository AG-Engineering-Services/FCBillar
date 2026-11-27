-- Avisos push de resultats (campana de la PWA, només als dispositius d'admin).
--
-- No s'aplica automàticament: l'admin valida el SQL i l'executa amb `psql` i la
-- connexió sense pool. El Data API pot trigar ~30 min a veure les taules i la
-- funció noves; mentrestant `fcbillar avisa` avisa i no envia res.

-- Una fila per dispositiu. `tipus` són els identificadors de web/src/lib/avisos.ts
-- (i de src/fcbillar/avisos.py); buit vol dir que el dispositiu s'ha donat de baixa.
create table if not exists fcbillar.push_subscripcions (
    endpoint    text primary key,
    p256dh      text not null,
    auth        text not null,
    tipus       text[] not null default '{}',
    dispositiu  text,
    creat       timestamptz not null default now(),
    actualitzat timestamptz not null default now()
);

-- Resultats ja avisats, per no repetir-los a la passada següent.
create table if not exists fcbillar.avisos_enviats (
    clau   text primary key,
    enviat timestamptz not null default now()
);

alter table fcbillar.push_subscripcions enable row level security;
alter table fcbillar.avisos_enviats enable row level security;

-- Ningú de fora no llegeix cap de les dues: un endpoint permet enviar avisos a
-- aquell dispositiu. El navegador només hi escriu a través de la funció.
grant all on fcbillar.push_subscripcions to service_role;
grant all on fcbillar.avisos_enviats to service_role;

-- Alta, canvi de tipus o baixa (tipus buit) d'un dispositiu. SECURITY DEFINER
-- perquè l'anon no necessiti cap permís sobre la taula: un upsert directe hauria
-- de poder-la llegir.
create or replace function fcbillar.desa_subscripcio(
    p_endpoint text,
    p_p256dh text,
    p_auth text,
    p_tipus text[],
    p_dispositiu text default null
) returns void
language plpgsql
security definer
set search_path = fcbillar, pg_temp
as $$
begin
    if p_endpoint is null or p_endpoint !~ '^https://' or length(p_endpoint) > 1000 then
        raise exception 'endpoint no vàlid';
    end if;
    if p_tipus is null or not (p_tipus <@ array[
        'opens_3b', 'banyoles_lliga', 'banyoles_opens', 'banyoles_copa_camp'
    ]::text[]) then
        raise exception 'tipus d''avís desconegut';
    end if;
    insert into fcbillar.push_subscripcions (endpoint, p256dh, auth, tipus, dispositiu)
    values (p_endpoint, p_p256dh, p_auth, p_tipus, left(p_dispositiu, 200))
    on conflict (endpoint) do update
        set p256dh = excluded.p256dh,
            auth = excluded.auth,
            tipus = excluded.tipus,
            dispositiu = excluded.dispositiu,
            actualitzat = now();
end;
$$;

revoke all on function fcbillar.desa_subscripcio(text, text, text, text[], text) from public;
grant execute on function fcbillar.desa_subscripcio(text, text, text, text[], text)
    to anon, authenticated, service_role;

notify pgrst, 'reload schema';
