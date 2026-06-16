# Contracte de lectura — Rànquing provisional (`fcbillar`)

Informació mínima perquè una **altra aplicació** llegeixi la projecció del proper
rànquing i les partides pendents des de Supabase. Tot és **només lectura** (RLS,
clau pública `anon`); l'escriptura la fa el desktop via `fcbillar publish-cloud`.

## Connexió

| | |
|---|---|
| Project URL | `https://unocmdvjuncqnzscrypg.supabase.co` |
| Schema | `fcbillar` |
| Clau (anon, pública) | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVub2NtZHZqdW5jcW56c2NyeXBnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjA1Mjc4NjIsImV4cCI6MjA3NjEwMzg2Mn0.nhPnwBRKkxL9re3Ik99frloldzf8MNtYszsQo2OkyiE` |

```ts
import { createClient } from '@supabase/supabase-js';
const sb = createClient(PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY, {
  db: { schema: 'fcbillar' }
});
```

## Taula `ranking_provisional` — projecció del proper rànquing

Una fila per jugador del rànquing vigent. **Només es publica** per a modalitats amb
≥1 jugador amb partides de competicions en curs (de moment, **pilot Tres Bandes,
`modalitat_codi = 1`**). Si la taula no té files per a una modalitat+`num_seq`, no
hi ha res a projectar.

| Columna | Tipus | Notes |
|---|---|---|
| `modalitat_codi` | int | 1=Tres Bandes, 2=Lliure, 3=Quadre 47/2, 4=Banda, 6=Quadre 71/2 |
| `num_seq` | int | Núm. seqüencial del rànquing oficial vigent que es projecta |
| `player_fcb_id` | text | ID intern del jugador (= `players.fcb_id`) |
| `posicio_oficial` | int | Posició al rànquing oficial |
| `mitjana_oficial` | real | Mitjana general oficial |
| `posicio_provisional` | int | Posició projectada (definitius abans que provisionals) |
| `mitjana_provisional` | real \| null | Mitjana projectada; **null** si el jugador no té partides noves |
| `partides_post` | int | Nº de partides pendents que mou aquest jugador (0 = no s'ha mogut) |
| `proj_won` / `proj_lost` / `proj_tie` | int \| null | G/P/E de la finestra projectada de 15 (només per als qui s'han mogut; sumen 15) |
| `window_game_ids` | jsonb \| null | IDs (de `games`) que entren a la finestra projectada — per ressaltar-los; les partides pendents NO hi són (venen de `pending_games`) |

PK: `(modalitat_codi, num_seq, player_fcb_id)`.

Moviment d'un jugador = `posicio_oficial − posicio_provisional` (positiu = puja).
Mostra el provisional d'un jugador només si `partides_post > 0`. Els camps de
desglossament (`proj_*`, `window_game_ids`) només estan plens per a aquests.

```ts
const { data } = await sb
  .from('ranking_provisional')
  .select('player_fcb_id, posicio_oficial, posicio_provisional, mitjana_oficial, mitjana_provisional, partides_post')
  .eq('modalitat_codi', 1)
  .eq('num_seq', NUM_SEQ_VIGENT)
  .order('posicio_provisional');
```

## Taula `pending_games` — partides pendents (detall)

Partides jugades en competicions en curs (copa, opens…) **encara no** al rànquing
oficial. Una fila **per jugador i partida** (perspectiva del jugador). Ja venen
deduplicades contra les partides oficials.

| Columna | Tipus | Notes |
|---|---|---|
| `player_fcb_id` | text | Jugador (= `players.fcb_id`) |
| `modalitat_codi` | int | Modalitat |
| `signatura` | text | Clau de dedup (parella + caramboles + entrades) |
| `competicio` | text | Nom de la competició (p. ex. `Copa`, `OPEN TRES BANDES COSTA DAURADA`) |
| `font` | text | `open_live` \| `copa` \| `lliga` |
| `opponent_nom` | text | Nom del rival |
| `opponent_fcb_id` | text \| null | ID del rival si està identificat |
| `caramboles` / `caramboles_opp` | int | Caramboles del jugador / del rival |
| `entrades` | int | Entrades |
| `serie` | int \| null | Sèrie major del jugador |

PK: `(player_fcb_id, modalitat_codi, signatura)`.

```ts
const { data } = await sb
  .from('pending_games')
  .select('competicio, font, opponent_nom, caramboles, caramboles_opp, entrades, serie')
  .eq('player_fcb_id', FCB_ID)
  .eq('modalitat_codi', 1);
```

## Notes de semàntica

- Les dues taules es **reconstrueixen senceres** a cada `publish-cloud` (esborrat +
  reinserció per modalitat). Quan es publica el rànquing oficial nou, les partides
  passen a `games` i deixen d'aparèixer aquí (dedup per signatura).
- `mitjana_provisional` = Σcaramboles / Σentrades sobre les 15 partides més recents
  (partides pendents + les de `games` dins els darrers 24 mesos), igual que el
  càlcul federatiu. Els **definitius** (≥15 partides computables) van sempre abans
  que els **provisionals** (<15).
- Cap dada és sensible: clau `anon` + RLS de només lectura.
