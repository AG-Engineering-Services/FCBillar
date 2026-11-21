-- FCBillar cloud schema — el palmarès: les medalles dels campionats d'Espanya i d'Europa.
--
-- La base de dades és Neon (projecte `fcbillar`). No s'aplica automàticament:
-- l'admin valida el SQL i l'executa amb la connexió sense pool.
--
-- Campió, subcampió i tercer de cada edició, llegits del «medallero» de la RFEB
-- (campionats d'Espanya, des de 1926) i dels «Rolls of Honors» del CEB
-- (campionats i Grand Prix d'Europa). Són a part de tot el que ve de la
-- federació catalana: no compten per a cap rànquing ni cap mitjana catalana.
--
-- Els noms són els que escriu la font («Joaquín Domingo», «A. Trapé»; al CEB,
-- «Ivan Mayor» amb el país a banda) i no hi ha cap identificador. El lligam amb
-- la fitxa és el de `nacional_fitxes`: el nom tal com el va escriure la font
-- -de la RFEB, o del CEB amb país ES- i el `fcb_id` que algú ha validat a mà
-- (`fonts/nacional/fitxes.csv`, amb `divisio` «palmares» o «palmares-ceb»). Un
-- nom que no hi és, no té fitxa i no surt a la vista. El CEB només es lliga si
-- el país és ES: un jugador d'un altre país no és al cens. No es fa servir
-- `umb_fitxes`: aquell lligam és per l'`umb_id` que dóna la UMB, i el CEB no en
-- dóna cap.

create table if not exists fcbillar.palmares_medalles (
    font         text not null,              -- 'rfeb' o 'ceb'
    competicio   text not null,              -- «Tres bandes», «Campionat d'Europa lliure»…
    categoria    text not null,              -- absolut, femení, sub-21, júnior…
    edicio       text not null,              -- xifra romana (RFEB) o número (CEB)
    any_edicio   integer,                    -- null si el PDF no el porta llegible
    lloc         text,
    posicio      integer not null check (posicio between 1 and 3),
    jugador      text not null,              -- tal com ho escriu la font
    pais         text,                       -- només el CEB
    mitjana      double precision,           -- a l'artístic és un percentatge
    primary key (font, competicio, categoria, edicio, posicio, jugador)
);

create index if not exists palmares_medalles_jugador on fcbillar.palmares_medalles (jugador);

alter table fcbillar.palmares_medalles enable row level security;
drop policy if exists "read palmares_medalles" on fcbillar.palmares_medalles;
create policy "read palmares_medalles" on fcbillar.palmares_medalles
    for select to anon, authenticated using (true);
grant select on fcbillar.palmares_medalles to anon, authenticated;
grant all on fcbillar.palmares_medalles to service_role;

-- Les medalles dels jugadors amb fitxa, amb el `fcb_id`. Una fila per medalla.
create or replace view fcbillar.palmares_fitxa
with (security_invoker = on) as
select f.fcb_id, m.*
from fcbillar.palmares_medalles m
join fcbillar.nacional_fitxes f on f.jugador = m.jugador
where m.font = 'rfeb' or m.pais = 'ES';

grant select on fcbillar.palmares_fitxa to anon, authenticated, service_role;

notify pgrst, 'reload schema';
