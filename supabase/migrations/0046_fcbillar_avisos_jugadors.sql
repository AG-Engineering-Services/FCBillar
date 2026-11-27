-- Avisos dels jugadors seguits (★ Seguits de la PWA), a més dels tipus de la 0045.
--
-- No s'aplica automàticament: l'admin valida el SQL i l'executa amb `psql` i la
-- connexió sense pool. El Data API pot trigar ~30 min a veure la funció nova.

alter table fcbillar.push_subscripcions
    add column if not exists jugadors text[] not null default '{}';

-- Fora la de cinc paràmetres: amb totes dues, una crida sense `p_jugadors` seria
-- ambigua per al Data API.
drop function if exists fcbillar.desa_subscripcio(text, text, text, text[], text);

create or replace function fcbillar.desa_subscripcio(
    p_endpoint text,
    p_p256dh text,
    p_auth text,
    p_tipus text[],
    p_dispositiu text default null,
    p_jugadors text[] default '{}'
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
        'opens_3b', 'banyoles_lliga', 'banyoles_opens', 'banyoles_copa_camp', 'jugadors_seguits'
    ]::text[]) then
        raise exception 'tipus d''avís desconegut';
    end if;
    if coalesce(cardinality(p_jugadors), 0) > 300 then
        raise exception 'massa jugadors';
    end if;
    insert into fcbillar.push_subscripcions (endpoint, p256dh, auth, tipus, dispositiu, jugadors)
    values (p_endpoint, p_p256dh, p_auth, p_tipus, left(p_dispositiu, 200), coalesce(p_jugadors, '{}'))
    on conflict (endpoint) do update
        set p256dh = excluded.p256dh,
            auth = excluded.auth,
            tipus = excluded.tipus,
            dispositiu = excluded.dispositiu,
            jugadors = excluded.jugadors,
            actualitzat = now();
end;
$$;

revoke all on function fcbillar.desa_subscripcio(text, text, text, text[], text, text[]) from public;
grant execute on function fcbillar.desa_subscripcio(text, text, text, text[], text, text[])
    to anon, authenticated, service_role;

notify pgrst, 'reload schema';
