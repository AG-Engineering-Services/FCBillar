-- FCBillar cloud schema — l'admin pot eliminar vídeos del traductor.
--
-- Base de dades: **Neon** (vegeu 0018). No s'aplica sola: l'admin l'executa amb
-- `psql` i la connexió sense pool.
--
-- La PWA no té login: l'«admin» és una marca al localStorage, i això no pot
-- decidir qui esborra. Per això l'anon no té DELETE sobre la taula i l'esborrat
-- passa per aquesta funció, que demana una clau i la compara amb el hash bcrypt
-- de `traductor_admin`. La clau no és a la PWA ni al repositori: és al `.env`
-- local de l'admin (TRADUCTOR_ADMIN_CLAU) i ell l'entra el primer cop.
--
-- La fila s'esborra a l'acte; l'mp3 del release el treu el workflow traductor.yml
-- al proper tret (esborra els assets que ja no tenen fila).
--
-- La funció es pot cridar sense límit, però bcrypt fa cada intent lent i la clau
-- és aleatòria de 32 caràcters: no s'endevina a cops.

create extension if not exists pgcrypto;

create table if not exists fcbillar.traductor_admin (
    id        smallint primary key default 1 check (id = 1),
    clau_hash text not null
);
alter table fcbillar.traductor_admin enable row level security;
-- Sense polítiques: ningú la pot llegir pel Data API.
revoke all on fcbillar.traductor_admin from anon, authenticated;

create or replace function fcbillar.elimina_video_traduccio(p_id bigint, p_clau text)
returns boolean
language plpgsql
security definer
set search_path = fcbillar, public
as $$
declare
    ok boolean;
begin
    select clau_hash = crypt(p_clau, clau_hash) into ok
      from fcbillar.traductor_admin where id = 1;
    if not coalesce(ok, false) then
        raise exception 'Clau incorrecta' using errcode = '42501';
    end if;
    -- Amb un id que no existeix (p. ex. 0) només comprova la clau.
    delete from fcbillar.video_traduccio where id = p_id;
    return found;
end $$;

revoke all on function fcbillar.elimina_video_traduccio(bigint, text) from public;
grant execute on function fcbillar.elimina_video_traduccio(bigint, text) to anon, authenticated;
