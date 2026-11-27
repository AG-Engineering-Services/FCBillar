-- Avisos per seguiments: clubs (lliga i Copa), jugadors (competicions
-- individuals) i opens sencers. Substitueix els tipus del Banyoles de la 0045.
--
-- No s'aplica automàticament: l'admin valida el SQL i l'executa amb `psql` i la
-- connexió sense pool. El Data API pot trigar ~30 min a veure la funció nova.

-- Una sola llista amb prefix: «j:278» (jugador), «c:C.B.BANYOLES» (club),
-- «e:C.B.BANYOLES A» (equip), «o:223» (open en directe, per `fcb_division_id`).
-- La columna `jugadors` de la
-- 0046 queda sense ús.
alter table fcbillar.push_subscripcions
    add column if not exists seguiments text[] not null default '{}';

-- Fora la de la 0046: canvia el nom de l'últim paràmetre i, amb totes dues, la
-- crida seria ambigua per al Data API.
drop function if exists fcbillar.desa_subscripcio(text, text, text, text[], text, text[]);

create or replace function fcbillar.desa_subscripcio(
    p_endpoint text,
    p_p256dh text,
    p_auth text,
    p_tipus text[],
    p_dispositiu text default null,
    p_seguiments text[] default '{}'
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
        'opens_3b', 'opens_seguits', 'clubs_seguits', 'jugadors_seguits'
    ]::text[]) then
        raise exception 'tipus d''avís desconegut';
    end if;
    if coalesce(cardinality(p_seguiments), 0) > 500 then
        raise exception 'massa seguiments';
    end if;
    if exists (
        select 1 from unnest(coalesce(p_seguiments, '{}')) s
        where s !~ '^[jceo]:.{1,80}$'
    ) then
        raise exception 'seguiment no vàlid';
    end if;
    insert into fcbillar.push_subscripcions (endpoint, p256dh, auth, tipus, dispositiu, seguiments)
    values (p_endpoint, p_p256dh, p_auth, p_tipus, left(p_dispositiu, 200), coalesce(p_seguiments, '{}'))
    on conflict (endpoint) do update
        set p256dh = excluded.p256dh,
            auth = excluded.auth,
            tipus = excluded.tipus,
            dispositiu = excluded.dispositiu,
            seguiments = excluded.seguiments,
            actualitzat = now();
end;
$$;

revoke all on function fcbillar.desa_subscripcio(text, text, text, text[], text, text[]) from public;
grant execute on function fcbillar.desa_subscripcio(text, text, text, text[], text, text[])
    to anon, authenticated, service_role;

notify pgrst, 'reload schema';
