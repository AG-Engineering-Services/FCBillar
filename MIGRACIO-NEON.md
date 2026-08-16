# FCBillar — migració a Neon (completa)

> Última actualització: **16/08/2026**. FCBillar està **sencer a Neon**: dades,
> web i ingesta. Supabase ja no hi pinta res. Llegeix això abans de tocar la base
> de dades o els workflows.

## On és cada cosa

| | Nom | Identificador |
|---|---|---|
| Repo | `AG-Engineering-Services/FCBillar` | branca `master` |
| Vercel | projecte `fcbillar` | serveix `seguiment-lliga-open.vercel.app` |
| Neon | projecte `fcbillar` | `restless-lab-78968832` |
| Data API | `https://ep-silent-resonance-b10v6qta.apirest.c-5.eu-central-1.aws.neon.tech/neondb` | esquemes `fcbillar` i `fcb_opens` |

El projecte de Vercel es diu `fcbillar` però **serveix el domini antic a
propòsit**. Una PWA instal·lada queda lligada al seu origen i no es pot migrar
amb una redirecció: canviar el domini obligaria tothom a reinstal·lar. Es farà el
dia que hi hagi domini propi, i llavors caldrà avisar.

## Què hi ha migrat

Comparat taula a taula entre origen i destí:

```
51 taules · 289.633 files · 0 discrepàncies
9 funcions · 0 triggers · 2 vistes · 56 polítiques RLS
```

## Com hi accedeix cadascú

| Qui | Com | Credencial |
|---|---|---|
| Web (navegador) | Data API amb `@neondatabase/postgrest-js` | JWT públic amb `role: anon` |
| Ingesta (Python) | Data API amb `supabase-py` | JWT amb `role: service_role` (BYPASSRLS) |
| Workflows de GitHub | igual que la ingesta | secrets del repo |

**El Data API de Neon és PostgREST, igual que el de Supabase.** Per això ni les
87 crides de la web ni les 4.796 línies de `.table().execute()` del Python no
s'han hagut de tocar: només canvien la URL base i la credencial. Les relacions
incrustades (`players(nom)`) també funcionen igual.

### El JWT substitueix l'anon key

Neon exigeix un JWT a cada petició i **no té equivalent de l'anon key**. Els dos
tokens que fem servir els signa una clau RSA pròpia i es verifiquen contra
`static/.well-known/jwks.json`, que serveix la mateixa web.

- `PUBLIC_NEON_ANON_TOKEN` — `role: anon`, viatja al navegador, RLS el limita.
- `NEON_SERVICE_ROLE_TOKEN` — `role: service_role`, **mai al navegador**.

Es revoquen publicant un JWKS nou i regenerant-los. No caduquen.

> El Data API d'aquest projecte funciona sense una sola errada (mesurat 15/15
> repetidament). A `BillarFoment` el mateix muntatge falla el 20-40% de les
> vegades i per això allà es va descartar. Si algun dia falla aquí, mireu la
> taula de mesures del runbook d'`ag-standards` abans de començar a investigar.

## Variables d'entorn

```
NEON_DATA_API_URL          base del Data API (sense /rest/v1: les llibreries l'afegeixen)
NEON_SERVICE_ROLE_TOKEN    JWT de servei, per a la ingesta
NEON_C3B_DATA_API_URL      Data API del projecte c3b — vegeu més avall
PUBLIC_NEON_DATA_API_URL   les mateixes dues, per a la web
PUBLIC_NEON_ANON_TOKEN
```

### Per què cal `NEON_C3B_DATA_API_URL`

`cloud_sync.get_public_client()` escriu el camp `computa` a les partides de
l'app **Estadístiques/c3b**. A Supabase compartien projecte i n'hi havia prou
amb canviar d'esquema; a Neon c3b viu en un projecte separat, així que cal una
connexió pròpia. **Aquesta dependència creuada és fàcil de trencar sense
adonar-se'n**: si es toca la configuració de c3b, comproveu que això segueix
funcionant.

## Qui llegeix les dades de FCBillar

`NouProjecte` (CBBanyoles) llegeix l'esquema `fcbillar` amb
`src/lib/fcbillarClient.ts`. Va apuntar a Supabase fins al 16/08 i **mostrava
dades congelades sense donar cap error** perquè la ingesta ja escrivia a Neon.
Si es torna a moure aquest projecte, cal actualitzar-lo també.

## Coses que van fallar i com es van resoldre

- **El primer migrador no movia funcions ni triggers.** Es va detectar tard: a
  `fcb_opens` faltaven 9 funcions. Si es migra res més, verifiqueu-ho
  explícitament; que la migració no doni errors no vol dir que estigui completa.
- **`pg` desplaça les dates.** Converteix `DATE` en `Date` de JS i en serialitzar
  a JSON hi aplica la zona horària: `2026-07-25` sortia com `2026-07-24T22:00Z`.
  Cal `types.setTypeParser`.
- **Límit de paràmetres de Postgres.** 65.535 per sentència, amb comptador de 16
  bits: passar-se no dona error clar, desborda. Cal partir les insercions per
  nombre de paràmetres, no de files.
- **Esborrar un esquema exposat a PostgREST tomba tot el servei.** Va passar amb
  `porra` i va caure c3b, la web i els automatismes. Vegeu el procediment al
  runbook abans de buidar cap esquema de Supabase.

## Còpies de seguretat

Neon Free no té *snapshots* programats. El workflow `neon-backup.yml` fa un
`pg_dump` complet setmanal a la branca `backups`. Necessita el secret
`DATABASE_URL`.
