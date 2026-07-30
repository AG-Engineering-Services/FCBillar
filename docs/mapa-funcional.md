# Mapa funcional de FCBillar — què s'espera, què fa i com ho fa

Document de referència per **revisar secció a secció** les dues aplicacions del projecte:

- **App web (PWA)** — `web/`, SvelteKit 5 + Tailwind, desplegada a Vercel, llegeix Supabase
  (schema `fcbillar`) amb la clau `anon` (només lectura, RLS).
- **App d'escriptori** — `desktop/`, PyQt6 (MVC), llegeix **directament** el SQLite local
  `data/fcbillar.db` i llança les reingestes.

Per a cada secció hi ha quatre blocs:

| Bloc | Significat |
|---|---|
| **S'espera** | Objectiu funcional: què hauria de resoldre a l'usuari. |
| **Fa** | Comportament real avui, tal com és al codi. |
| **Com** | Fonts de dades i lògica clau (taules, publicadors, càlculs). |
| **A revisar** | Diferències, riscos i coses a decidir. ⚠ = problema verificat. |

Data de la revisió del codi: **2026-07-27**. Comprovacions de dades fetes contra el Supabase
de producció (schema `fcbillar`).

---

## 0. Arquitectura en una pàgina

```
        fcbillar.cat (portal FCB)
                 │  scraping (logat: rànquings+partides · no logat: lliga/copa/opens)
                 ▼
   data/fcbillar.db  +  data/fcb_opens.db        ← SQLite canònic, al PC
        │                        │
        │ desktop/ (PyQt6)       │ fcb_opens
        │ llegeix directament    │
        ▼                        ▼
   [App d'escriptori]     fcbillar publish-cloud / fcb_opens supabase-sync
                                 │
                                 ▼
                  Supabase · schema fcbillar (+ public, app germana)
                                 │  anon + RLS (només SELECT)
                                 ▼
                     [App web PWA · Vercel]
```

Automatismes:

- `scripts/weekly_reingest.ps1` (Tasca Programada, Ds/Dg): part **logada** (rànquings + `backfill`
  de partides de les 5 modalitats) + ingesta d'individuals/copa/opens/lliga + `publish-cloud` +
  `supabase-sync` + pujada de les BD al GitHub Release `fcb-state`. Finestra 25-ago → 31-jul, amb
  lock anti-concurrència.
- `.github/workflows/reingest-nologin.yml` (diari): part **no logada** al núvol, partint de les BD
  del release. Hi va també `ingest-calendari` (calendari federatiu en PDF: RFEB
  parsejat + detecció del de la FCB), que és HTTP pur i s'ha de repassar sovint perquè les
  federacions en publiquen revisions.
- `.github/workflows/publish-live-opens.yml`: refresc d'`open_live` durant les competicions.
- Watchers locals (`scripts/reingest_watcher.ps1`, `scripts/open_projection_watcher.ps1`) que
  consumeixen les cues `reingest_requests` i `open_projection_requests` que escriu la PWA.

---

# PART A — Aplicació web (PWA)

## A.0 Comportament comú a totes les seccions

**S'espera** — Una PWA de consulta ràpida des del mòbil, en català, amb dades sempre fresques
sense re-desplegar.

**Fa** — `+layout.svelte` pinta capçalera + 10 pestanyes, marca d'aigua d'autoria, peu amb avís de
no distribució, i commutador clar/fosc. Torna a dalt en cada navegació excepte a les tornades
enrere (`popstate`). Punt vermell llampegant a «Opens» quan hi ha competició en directe.

**Com**
- Client únic `$lib/supabase.ts` fixat a `db.schema = 'fcbillar'`, sense sessió.
- Punt d'«en directe»: `count` de `open_live` amb `captured_at` de fa < 90 min.
- Avís de sessió federativa caducada (`cloud_status.session_ok = false`) **només** si el
  dispositiu té `localStorage.fcb_admin = '1'` (el posa el botó de reingesta).
- `service-worker.js`: cache-first per a assets versionats, network-first per a HTML, i **no toca**
  les crides a Supabase (sempre en directe).
- Tema a `$lib/theme.ts` (classe `dark` a l'arrel); els gràfics SVG llegeixen `$theme` per als colors.
- Seguits (jugadors i clubs) a `localStorage`, per dispositiu (`$lib/follows.ts`).
- `/fitxa/[id]` és una vista "kiosk": el layout hi amaga capçalera i navegació.

**A revisar**
- ⚠ **Límit de 1000 files de PostgREST** (verificat: `GET /players?select=fcb_id` retorna
  exactament 1000 de 1556 files). Qualsevol `select()` sense `.range()` queda tallat en silenci.
  Ja es paginen `open_ranking`, `ranking_full` (a `/opens`) i `open_partides`; **no** es paginen
  `players` a `/cerca`, `/comparar` i `/seguiment` (vegeu les seccions respectives).
  Taules a vigilar perquè s'hi acosten: `lliga_player_rankings` (793), `ranking_full` de 3 bandes
  (613 al rànquing 124).
- Cap secció mostra la data de l'última actualització de dades (excepte l'open en directe).
  Val la pena exposar `cloud_status.last_run` a tothom, no només a l'admin.

---

## A.1 Rànquings — `/` (pestanya «Rànquings»)

**S'espera** — La portada: el rànquing oficial vigent de cada modalitat, poder recular a
rànquings anteriors i veure la projecció del proper.

**Fa**
- Xips de modalitat; slider `‹ ›` entre snapshots, amb la **projecció «Provisional calculat»**
  com a posició extra a la dreta de l'oficial vigent.
- Sobre l'oficial vigent, marques en línia ▲▼ (verd/vermell) de diferència de mitjana i posició.
- Cerca amb àmbit **Tot / Jugador / Club** i ordenació per **posició oficial** o per **promig**.
- Cada fila enllaça a `/jugador/[fcb_id]`.

**Com**
- `modalitats`, `rankings` (`num_seq`, `any_pub`, `mes_pub`), `ranking_full` filtrat per
  `(modalitat_codi, num_seq)`.
- Projecció: taula `ranking_provisional` sencera per modalitat (`publish_provisional_ranking`).
  L'slider només ofereix la posició provisional si algú té `partides_post > 0` o canvia de posició.
- Etiqueta del snapshot des de `mes_pub`/`any_pub` (derivats de `rankings.data_pub`), amb
  fallback a `Rànquing #num_seq`.
- Cerca: `playerMatches` / `clubMatches` de `$lib/search.ts` (`clubKey` ignora "Club"/"Billar"/"C.B.").

**A revisar**
- Aquesta secció ja fa servir `mes_pub`/`any_pub`; la fitxa i «Seguits» encara fan servir
  l'heurística `ymFromSeq` (vegeu A.2 ⚠). Convindria unificar-ho en un helper compartit.
- `ranking_full` no es pagina aquí; avui cap rànquing arriba a 1000 files, però és el mateix
  patró que ja va caldre paginar a `/opens`.
- Quan `ranking_provisional` és buida (ara mateix ho és, fora de temporada) l'slider no mostra
  cap posició provisional; és el comportament volgut, però no hi ha cap missatge que ho expliqui.

---

## A.2 Fitxa de jugador — `/jugador/[fcb_id]` i `/fitxa/[fcb_id]`

És el component més gran de l'app (`$lib/components/PlayerProfile.svelte`, ~1.760 línies),
compartit per la pàgina normal i per la vista aïllada `kiosk`.

**S'espera** — Tot el que se sap d'un jugador: KPIs, evolució, rendiment, palmarès i el llistat
de partides, amb la previsió del proper rànquing.

**Fa** (per modalitat seleccionada; els xips s'ordenen per nombre de partides)
1. **KPIs històrics** (partides, mitjana, sèrie màxima —clicable per filtrar—, % victòries, millor
   mitjana) + **temporada actual** i **temporada anterior**.
2. **Rànquing actual · 15 partides**: posició, mitjana, S.M., millor posició i millor mitjana
   històriques, **mitjana i posició del proper rànquing** amb ▲▼, posició a l'inici de temporada
   i posició dins del club.
3. **Efectivitat per competició** (Lliga / Open / Individual / Copa), amb la victòria valent 3 a la Copa.
4. **Rànquing d'Opens 3 Bandes** i, si escau, **Circuit Català Femení** (posició, millor posició,
   millor resultat en una prova, punts).
5. **Palmarès individual** (podis 1r-3r) agrupat per temporada, amb etiqueta Campionat/Open/Torneig.
6. **Rivals destacats**: més partides, més victòries, més derrotes.
7. **Millor partida** (o partides, si empaten) per mitjana.
8. **Rendiment per nivell d'oponent**: aranya (`RadarChart`), índex de rendiment i nivell de
   competitivitat (crossover).
9. **Gràfics**: mitjana al rànquing, posició al rànquing (invertida), **mitjana mòbil de 15
   partides** amb slider i finestra de 25 punts, i **histograma** de la mitjana per partida amb
   línia de mitjana i franja ±1σ (àmbit *tot* o *temporada*).
10. **Clubs** per trams de temporades consecutives.
11. **Partides pendents** (blau) i **taula de partides** amb les 15 que computen ressaltades en ambre.
12. Impressió: A4, s'expandeixen totes les partides i s'amaguen navegació i controls.

**Com**
- `players`, `clubs`, `games` (`limit(1000)`, `or(player1…,player2…)`), `pending_games`,
  `ranking_provisional`, `player_clubs`, `open_classifications` + `opens` (palmarès),
  `open_ranking` (general i femení), `ranking_entries` (històric), `player_rating_buckets` /
  `player_rating_index` (aranya).
- La **previsió** ja **no es recalcula al client**: llegeix `mitjana_provisional`,
  `posicio_provisional`, `proj_won/lost/tie`, `window_game_ids` i `current_game_ids` de
  `ranking_provisional`. Hi ha un fallback heurístic per dates per a les 15 actuals si no hi ha
  `current_game_ids`.
- El palmarès dedueix modalitat, categoria i tipus (campionat/open/torneig) **del nom del torneig**
  amb expressions regulars dins del component.
- Botó **↻ Reingesta** només a `fcbId === '278'`: demana el correu, marca `fcb_admin` a
  `localStorage` i insereix a `reingest_requests` (gate real per RLS al servidor).
- Paràmetres d'URL `?mod=` i `?game=` (els fa servir «Rècords») per obrir la modalitat correcta i
  desplaçar-se fins a la partida.

**A revisar**
- ⚠ **`ymFromSeq` és incorrecta per als rànquings ≥ 122.** Està ancorada a «122 = juny 2026» i el
  bucle `for (i = 0; i < 122 - seq; i++)` no s'executa mai si `seq > 122`: per als rànquings **123 i
  124 retorna «Juny '26»**. Afecta les etiquetes de l'eix X dels gràfics, el rètol del punt
  seleccionat, `seasonStartRank` i el fallback de `currentRank15`. El rànquing vigent és el 124
  (agost 2026). **Cal llegir `rankings.mes_pub`/`any_pub` com fa la portada.** Mateix codi duplicat
  a `/seguiment`.
- La classificació del palmarès per regex sobre el nom del torneig duplica la lògica de
  `fcbillar.torneig_naming` (que ja s'exposa com `tipusOf` a `$lib/supabase.ts`). Dues fonts de
  veritat que poden divergir.
- `games` es demana amb `limit(1000)` sense paginar: avui el jugador amb més partides en té 542,
  així que no talla, però queda a mig camí del límit.
- En mode `kiosk` s'amaguen els enllaços i el botó «Seguir», però **el botó ↻ Reingesta no
  s'amaga**: es veuria a `/fitxa/278`. Avui no s'usa cap fitxa kiosk d'aquest jugador.
- Component molt gran: val la pena extreure'n almenys els gràfics i el bloc de previsió.

---

## A.3 Lliga — `/lliga`

**S'espera** — Classificacions i resultats de la Lliga Catalana de Tres Bandes de la temporada en
curs, amb accés a l'històric.

**Fa**
- Selector de temporada: actual o històrica.
- Xips de divisió; commutador **Equips / Jugadors**; en jugadors, àmbit **per grup** o **tota la
  categoria**; filtre de text.
- Equips: posició, G-E-P, PJ, punts i marca vermella **«− n sanció»** quan hi ha penalització.
- Jugadors: posició, PJ, mitjana i punts, amb enllaç a la fitxa.
- Per grup, navegador de **jornades** amb els encontres; cada encontre es desplega amb les partides.
- Temporada històrica: llistes per lliga+divisió amb posició, PM i PP.

**Com**
- `lliga_groups`, `lliga_standings`, `lliga_player_rankings`, `lliga_encontres` (tot d'una) i
  `lliga_partides` sota demanda en desplegar un encontre.
- La classificació de la temporada en curs pren **posició i punts de la taula oficial scrapejada**
  (amb penalitzacions i desempats), no del càlcul 3G+E — vegeu `_fetch_official_lliga_standings`.
- Històric: taula `lliga_history`.

**A revisar**
- ⚠ **Ningú publica `lliga_history`.** La taula existeix a Supabase (541 files, màxim 2024-2025)
  però **cap fitxer del repositori l'escriu**. El que sí que es publica és `lliga_standings_hist`
  (654 files, `publish_lliga_standings_hist` dins de `publish-cloud`), que el web **no llegeix**:
  només la fa servir l'app germana. Resultat: el selector històric de la web mai s'actualitzarà.
  Cal decidir-ho: fer que el web llegeixi `lliga_standings_hist` (té nom real de grup i fase FINAL)
  i esborrar `lliga_history`, o documentar-la com a càrrega manual.
- Cap de les dues taules té la temporada **2025-2026**; caldrà re-executar
  `scripts/import_lliga_standings.py` quan el portal en publiqui l'historial.
- La secció només cobreix la **Lliga de Tres Bandes** (id 36, fixat al codi i a la reingesta), però
  a `games` hi ha 7.246 partides de «Lliga 4 Modalitats» sense cap secció que les mostri.
- L'error de la consulta de `lliga_history` s'ignora (`const { data: hs } = …`): si falla, el
  selector simplement no apareix i ningú se n'assabenta.
- `lliga_player_rankings` (793 files) es carrega sense paginar: és el candidat més proper a topar
  amb el límit de 1000.

---

## A.4 Copa — `/copa`

**S'espera** — Seguiment de la Copa Catalana per fases, amb classificacions d'equips i el
rànquing individual de la competició.

**Fa** — Commutador Equips/Jugadors; en equips, xips de fase i grups plegables amb posició,
mitjana i punts, i els encontres desplegables; en jugadors, **rànquing únic de tota la Copa**.

**Com** — `copa_groups`, `copa_standings`, `copa_player_rankings`, `copa_encontres` i
`copa_partides` sota demanda. El rànquing de competició fa servir la sentinella `jornada=0`,
`grup=0` (`publish_copa_player_rankings`).

**A revisar**
- En mode «Jugadors» el filtre de text s'aplica al rànquing global però `playerRows()` (per grup)
  **no** aplica `matchQ`; és codi que ara mateix no es fa servir en aquesta vista.
- L'edició de la Copa està fixada per paràmetre a la reingesta (`CopaEdicio = 7`): cal actualitzar-la
  cada temporada, i no hi ha cap avís si es queda enrere.

---

## A.5 Opens — `/opens`

**S'espera** — Porta d'entrada als opens: els que s'estan jugant ara, el llistat per temporada i el
Rànquing Català d'Opens de 3 Bandes.

**Fa**
1. **En directe**: targetes dels opens d'`open_live` amb resum d'estat (fase activa i partides
   jugades/total) i badge **«projecció»** si encara no hi ha sorteig oficial.
2. **Opens**: selector de temporada + cerca, llistat cap a `/opens/[open_id]`.
3. **Rànquing**: slider de rondes amb el detall per jugador (desplegable) i columna **3B** (mitjana
   i posició al rànquing vigent de tres bandes) com a context de nivell.
4. **Admin** (plegat al peu): pujar el PDF *RÀNQUING INICIAL* per generar un open projectat.

**Com**
- `opens` (tipus real o derivat amb `tipusOf`), `open_live`, `open_ranking` (paginat) i
  `ranking_full` de la modalitat 1 (paginat) per a la columna 3B.
- La **ronda calculada** no es fixa de la ronda publicada que ja conté l'open en curs (el PDF
  oficial la desalinea): parteix de l'última ronda *neta*, en conserva els 4 opens acabats més
  recents i hi afegeix l'open en directe amb els punts de la classificació provisional
  (`payload.classification[].open_points`), reordenant per punts → millor resultat → nom.
- Rondes **provisionals** publicades (`open_ranking.provisional`) es pinten igual, en ambre, amb
  avís propi.
- L'admin converteix el PDF a base64 i l'insereix a `open_projection_requests`; el watcher del PC
  executa `fcbillar project-open-ranking` i publica l'open projectat.

**A revisar**
- La detecció de l'open de 3 bandes en directe és per **nom** (`is3BLive`, regex sobre el títol);
  si la federació canvia la nomenclatura, la ronda calculada desapareix sense avís.
- La ronda calculada assumeix una finestra de 5 opens (4 + l'actual). Està documentat com a
  Art. XVIII, però és un número fixat al codi (`L - 4`).
- El gate d'admin és **client-side** (`prompt` + comparació de correu). La protecció real és la RLS;
  val la pena confirmar que la política d'`open_projection_requests` i `reingest_requests` filtra
  per `requested_email` i no permet inserir res més.
- Els PDFs es guarden com a base64 dins d'una taula; sense retenció definida pot créixer.

---

## A.6 Open en directe — `/opens/directe/[id]`

La secció més complexa del web (~770 línies).

**S'espera** — Seguiment en viu d'un open: fases, grups, classificats, marcadors i classificació
provisional amb premis.

**Fa**
- Capçalera amb modalitat, badge **En directe** o **Projecció · no oficial** i «actualitzat fa N min».
- Selector de fases amb estat (`✓` acabada, `●` en joc, `○` pendent, `· proj` projectada) i pestanya
  **Classificació**.
- **Millor sèrie** del torneig, excloent-ne els 8 primers classificats (que ja tenen premi propi).
- Fases de grup: **classificats per a la ronda següent** (1rs + millors 2ns, amb ✓ de plaça
  assegurada), targetes de grup amb classificació, horaris (dia, billar, hores per tipus de
  partida), partides disputades i **«En joc ara»** amb el marcador OCR de YouTube.
- Fases KO: llista de classificats amb la mitjana amb què hi entren i emparellaments **oficials +
  calculats**, amb w.o. i guanyador ressaltat.
- Classificació provisional per trams (ronda on cauen), amb posició, punts d'open, rànquing 3B entre
  parèntesis i premis (llocs 1-8 i per banda de rànquing).
- Refresc automàtic: payload cada 90 s, marcadors OCR cada 30 s, només si la pestanya és visible.

**Com**
- `open_live.payload_json` (publicat per `publish-live-opens`) i `open_live_scores` (worker OCR).
- Cache en mòdul (`rowCache`, `phaseCache`) perquè en tornar enrere la pàgina es repinti a l'instant.
- **Premis per banda recalculats al navegador**: l'usuari tria quina publicació del rànquing de 3
  bandes s'aplica (la de la convocatòria, sovint no la darrera); es desa a `localStorage` per
  divisió i es llegeix `ranking_entries`. Prioritat: tria de l'usuari > `payload.prize_num_seq`
  (fixat al publicador) > darrer publicat.
- Regles fines ja resoltes: grup tancat per no-show (dues partides del mateix parell),
  incompareixença (`isWalkover`), guanyador KO per punts → caramboles, i descart de marcadors OCR
  **obsolets** (grup ja tancat o partida ja registrada) i **antics** (> 12 min).

**A revisar**
- La lògica de premis viu **duplicada**: al publicador (`_enrich_live_payload`) i al navegador
  (`prizeByPlayer`). Si canvien les bandes (61-180 / 181+), s'ha de tocar a dos llocs.
- `open_live_scores` és buida i el worker d'OCR està en pausa: el bloc «En joc ara» no s'exercita.
  Convé decidir si es manté el codi o es marca com a experimental.
- Detecció d'open de 3 bandes per regex sobre el nom, un altre cop, i amb dues variants lleugerament
  diferents (`is3b` i el `test` de dins de `load()`).
- Si l'open desapareix d'`open_live` la pàgina mostra «Aquest Open ja no està en curs» sense
  redirigir a la fitxa històrica de l'open, que sí que existeix.

---

## A.7 Fitxa d'open — `/opens/[open_id]`

**S'espera** — Classificació final d'un open o campionat ja disputat, amb el desglòs de partides.

**Fa** — Títol net, cerca si hi ha més de 10 files, classificació (posició, PJ, mitjana, punts) i,
en tocar un jugador, les seves partides del torneig i enllaç a la fitxa completa.

**Com** — `opens`, `open_classifications` i `open_partides` (paginat).

**A revisar**
- El desglòs de partides casa **per nom normalitzat**, no per `player_fcb_id`: amb dos jugadors del
  mateix nom (cas conegut de cognoms repetits) barrejaria partides.
- No hi ha enllaç invers cap a l'open en directe quan encara s'està jugant.

---

## A.8 Campionats de Catalunya — `/campionats`

**S'espera** — Els campionats oficials, separats dels opens.

**Fa** — Llistat agrupat per temporada (més recent primer) i ordenat per modalitat canònica, amb cerca.

**Com** — Mateixa taula `opens`, filtrada per `tipusOf(o) === 'campionat'`. La modalitat es
**dedueix del nom** amb paraules clau; l'ordre canònic és una llista fixa.

**A revisar**
- La modalitat no és una columna: si un nom no encaixa cau a «Altres» i es perd l'ordre.
  `opens.modalitat` seria una millora barata al publicador.
- Les dues llistes (`/opens` i `/campionats`) apliquen `clean()` i `tipusOf` per separat: mateix
  codi copiat a dos fitxers.

---

## A.9 Anàlisi de clubs — `/clubs`

**S'espera** — Comparar clubs per la qualitat del seu planter, de forma comparable entre modalitats.

**Fa** — Selector de modalitat (o **Global** = millor disciplina de cada jugador), controls de mida
d'equip **K** (2-8) i pes **w** del CQI, mapa de bombolles Potència × Profunditat, rànquing de clubs
amb barres i plantilla desplegable (TOP K marcat) i enllaç a la fitxa del club.

**Com** — `ranking_full` del darrer `num_seq` de cada modalitat; tot el càlcul és al client
(`$lib/clubs.ts`): **nivell** = percentil de la posició, **Potència** = mitjana dels K millors,
**Profunditat** = massa de jugadors per damunt de la mediana, **CQI** = w·Potència + (1−w)·Profunditat.

**A revisar**
- Declarat «prototip»: caldria decidir si es consolida (càlcul al publicador, valors estables entre
  visites) o es manté client-side.
- El club s'agrupa pel **nom** (`ranking_full.club`), no per `club_fcb_id`; amb variants de nom
  («C.B.Banyoles» vs «Club Billar Banyoles») es partiria un club en dos. `$lib/search.ts` ja té
  `clubKey` per a això i aquí no es fa servir.
- En mode Global es descarreguen totes les modalitats de cop; sense pagineig, mateix risc de límit.

---

## A.10 Fitxa de club — `/club/[fcb_id]`

**S'espera** — El planter d'un club i el seu ordre intern.

**Fa** — Nom, comptadors, botó de seguir, llista **al rànquing de 3 bandes ordenada per mitjana**
(amb la posició oficial a sota) i llista d'«altres jugadors» sense rànquing.

**Com** — `clubs`, `players` per `club_fcb_id` i `ranking_entries` del darrer `num_seq` de la
modalitat 1. `clubs.fcb_id` **és** el nom del club (p. ex. `B.C.GRANOLLERS`), per això les URLs el
porten literal.

**A revisar**
- Només 3 bandes: no hi ha selector de modalitat, a diferència de `/clubs`.
- El planter surt de `players.club_fcb_id` (club actual del jugador), no de `player_clubs`
  (club per temporada+competició): coherent amb el model de club "actual", però convé tenir-ho
  present quan es compara amb el Focus club de l'escriptori.

---

## A.11 Cerca — `/cerca`

**S'espera** — Trobar **qualsevol** jugador federat, surti o no al rànquing.

**Fa** — Carrega tots els jugadors i filtra localment per nom sense accents, màxim 60 resultats.

**Com** — `players` + `clubs` en una sola càrrega, ordenats per nom al client.

**A revisar**
- ⚠ **No troba tots els jugadors**: `players` té 1.556 files i la consulta no pagina, de manera que
  només se'n descarreguen **1.000**. El text de la pantalla («Escriu un nom per cercar entre N
  jugadors») mostra 1000 i sembla correcte. Cal paginar amb `.range()` com fa `/opens`, o passar a
  cerca server-side amb `ilike` + `limit`.
- Filtra només per nom, tot i que carrega el club: cercar per club no funciona aquí (sí a `/`).

---

## A.12 Comparador — `/comparar`

**S'espera** — Comparar fins a 4 jugadors cara a cara.

**Fa** — Cercador amb suggeriments, xips de color, taula de mitjanes per modalitat, KPIs de la
modalitat triada (posició, mitjana de rànquing, partides, sèrie màxima, % victòries), **cara a cara
directe** i gràfic superposat d'evolució de la mitjana.

**Com** — `players` (autocompletar), i per cada jugador afegit `games` (`limit(1000)`) i
`ranking_entries` complet.

**A revisar**
- ⚠ Mateix problema de les **1.000 files** a `players`: els jugadors a partir del miler no es poden
  afegir al comparador.
- El cara a cara es calcula des de les partides **del primer jugador seleccionat**; si el seu límit
  de 1000 tallés, el marcador seria incomplet.
- Els noms de modalitat estan escrits al codi (`MODNOM`) en comptes de llegir `modalitats`.

---

## A.13 Rècords — `/records`

**S'espera** — Les millors marques històriques per modalitat i categoria.

**Fa** — Xips de modalitat, targetes per categoria amb top-N, valor i detall (data, rival, marcador,
entrades, o bé rànquing i posició), amb enllaç a la fitxa **obrint la modalitat i la partida
concretes** (`?mod=&game=`).

**Com** — Taula `records` (categoria, ordre, jugador, valor, `detall` en JSON).

**A revisar**
- ⚠ **La taula `records` no la manté cap automatisme.** L'únic productor és
  `scripts/publish_records.py`, que **no** apareix ni a `weekly_reingest.ps1`, ni a `publish-cloud`,
  ni a cap workflow (l'única referència al repositori és el seu test). Els 113 rècords publicats
  quedaran congelats fins que algú executi l'script a mà. Cal afegir-lo a la reingesta setmanal o
  documentar-ho com a pas manual.
- No hi ha data de càlcul visible, així que un rècord obsolet no es distingeix d'un de vigent.

---

## A.14 Seguits — `/seguiment`

**S'espera** — Vista personal: els clubs i jugadors que segueixo, amb la seva evolució.

**Fa**
- **Clubs seguits**: cercador per afegir-ne, seccions plegables amb el planter ordenat per mitjana i,
  quan escau, `→ prev. X.XXX` (previsió) en blau.
- **Jugadors seguits**: dos gràfics superposats (mitjana i posició) amb selector de punt i llegenda,
  i llista ordenada per posició amb botó per deixar de seguir.

**Com** — `players`, `clubs`, `rankings`/`ranking_entries` de la modalitat 1. La previsió dels
membres del club es **recalcula al navegador**: baixa `games` (paginat) i `copa_partides` (paginat),
dedueix les pendents per signatura, agafa les 15 més recents dins de la finestra de 24 mesos i en
recalcula la mitjana.

**A revisar**
- ⚠ **Duplica la lògica de projecció** que ja viu al backend (`ranking_provisional` + `pending_games`),
  que és la font que fa servir la fitxa. Aquí només es consideren la modalitat 1 i les pendents de
  **Copa**, mentre que `publish_pending_games` també cobreix opens i lliga → els dos números poden
  no coincidir. Recomanació: llegir `ranking_provisional` com fa la fitxa.
- ⚠ Conté una **còpia de `ymFromSeq`** amb la mateixa ancoratge «122 = juny 2026» i el mateix error
  per a `seq > 122`: les etiquetes de data dels gràfics es queden a «Juny '26».
- ⚠ `allPlayers` torna a ser `players` sense paginar (1.000 de 1.556): un club pot sortir amb menys
  membres dels que té.
- Els seguits viuen a `localStorage`: es perden en canviar de dispositiu o netejar dades.

---

---

## A.15 Calendari federatiu — `/calendari`

**S'espera** — Saber **què es juga cada setmana** a caràmbola, separant per equips i individual,
sense haver d'obrir el PDF de la federació. La FCB publica el seu calendari tard; el de la RFEB
(estatal + internacional) surt al juliol i és el que hi ha al començament de temporada.

**Fa**
- Xips de temporada (si n'hi ha més d'una), de tipus (Tot / Equips / Individual) i d'àmbit
  (Tots / Estatal / Internacional), més una casella «només caràmbola» activada per defecte.
- Bloc fix a dalt amb **aquesta setmana** i, si és buida, la **següent**.
- Llista per setmanes agrupada per mes, d'aquesta setmana endavant; el passat queda plegat.
- Desplegable amb els **canvis de l'última revisió** del PDF (altes, baixes i modificacions).
- Peu amb la versió del PDF, la data en què la federació el va actualitzar, la data de l'última
  comprovació i l'enllaç al PDF original.

**Com**
- Taules `calendari_events`, `calendari_revisions` i `calendari_canvis` (migració `0016`),
  publicades per `publish_calendari` des de la BD local.
- Parser a `fcbillar/calendari_fed.py`, ingesta amb `fcbillar ingest-calendari` (dins de
  `weekly_reingest.ps1` i del workflow diari `reingest-nologin.yml`, perquè és HTTP pur i no
  necessita login ni Chromium).
- La graella del PDF de la RFEB té una setmana per cada **tres files** (dilluns / dissabte /
  diumenge) i nou columnes fulla (caràmbola nacional 3B i jocs de sèrie × equips/individual,
  caràmbola internacional × equips/individual, pool nacional, pool internacional i snooker).
  L'ordre d'aquestes columnes és el contracte: si el PDF no en té nou, el parser **peta** en
  comptes d'assignar malament una competició.
- El PDF no escriu l'any: les dates es deriven buscant **quin dilluns d'arrencada fa quadrar els
  159 números de dia alhora** (comprovació de 53 setmanes; una sola solució possible).
- Revisions: es fa `GET` condicional per `ETag`; si el fitxer no ha canviat no es parseja res i
  només es refresca `last_checked_at`. Quan canvia, es desa la revisió nova, es calcula el diff
  contra l'anterior i es **reemplaça** la temporada sencera (perquè les baixes desapareguin).
- Font FCB: `registra_fcb` descobreix el PDF vigent llegint qualsevol pàgina de fcbillar.cat
  (l'enllaç `/media/{temporada}/CALENDARIS/CALENDARI FCB … V-N.pdf` surt al layout comú) i
  n'apunta versió, URL i sha256. **Encara no se'n parsegen els esdeveniments** (vegeu «A revisar»).

**A revisar**
- ⚠ **La font FCB només està detectada, no parsejada.** `/media/2026-2027` responia 404 el
  2026-07-30: de la temporada vinent no hi ha res publicat. El calendari de la 25/26 sí que hi és
  (`CALENDARI FCB 2025-26 V-9.pdf` — nou revisions en una temporada) i se n'ha mesurat la graella:
  A4 horitzontal, 4 pàgines, columna DATA a x 51,2–89,4 i **12 columnes de 55,1pt**, amb **una fila
  per dia** (`13-sep. SAB`) en lloc d'una per setmana. Blocs de columnes: lligues catalanes
  (Honor/1a/2a/3a | 4a), campionats de Catalunya (prèvies | qualificació i finals), opens catalans,
  lliga nacional, pool, campionats d'Espanya, d'Europa i del Món.
  El que **encara no és fiable** és l'atribució columna → significat: el full de càlcul de la FCB
  deixa text a cavall de columnes (per exemple «Open Punt d'Atac 71/2» cau a la columna de Lliga
  Nacional el 30-ago i el 6-set) i les línies ajustades s'entrellacen si es llegeixen per
  coordenada x sense agrupar-les abans per `top`. Cal decidir si es parseja amb la 25/26 com a
  referència o si s'espera el PDF real de la 26/27.
- El calendari federatiu només concreta el **cap de setmana**, no el dia ni l'hora. Amb la font FCB
  (files per dia) es podria baixar a granularitat de dia.
- La classificació per columnes és la del PDF, no la lògica: la RFEB va posar «CTO. ESPAÑA FEM. /
  TRES BANDAS / Cerdanyola» a la columna de *jocs de sèrie · equips*. Es reflecteix tal com és.
- `calendari_events.raw` (les línies crues) es queda a la BD local i no es publica: serveix per
  auditar el parser des del PC.

# PART B — Aplicació d'escriptori (PyQt6)

Arquitectura: `desktop/app.py` → `MainWindow` (sidebar + `QStackedWidget`) → vistes que parlen amb
`MainController`, que executa cada consulta en un `QueryWorker` (fil a part) i retorna per signal.
Les dades surten de `DataSource` (SQLite `data/fcbillar.db`, ~2.300 línies de consultes).
En canviar de secció es crida `request_data()` de la vista.

## B.1 Inici

**S'espera** — Estat global de la base local d'un cop d'ull.
**Fa** — KPIs (clubs, jugadors, rànquings, partides, encontres de lliga, temporades) i pestanya per
modalitat amb el **top 10** del rànquing actual (Pos, Jugador, fcb_id, MJ, MR, C, E, P/PT, Def).
**Com** — `DataSource.counts()` i `top_ranking_per_modalitat(10)`.
**A revisar** — No indica la data de l'última ingesta ni si la BD està desfasada respecte del núvol.

## B.2 Rànquings

**S'espera** — Consultar qualsevol rànquing publicat, de qualsevol modalitat.
**Fa** — Combos de modalitat i de snapshot + taula completa.
**Com** — `modalitats()`, `ranking_snapshots(codi)`, `ranking_full(codi, num_seq)`.
**A revisar** — Els snapshots es mostren com «Rànquing N»: la BD local ja té la data de publicació
(`data_pub`, reconciliada per `reconcile-ranking-dates`) i seria molt més llegible «Juny 2026».

## B.3 Jugadors

**S'espera** — Cercar un jugador i veure'n la fitxa completa en local.
**Fa** — Cerca per nom o `fcb_id`, taula de resultats (amb ★ de seguiment) i, a sota, perfil:
capçalera, KPIs (partides, guanyades, perdudes, % victòria, sèrie màx), **evolució de la mitjana al
rànquing** per modalitat, graella 2×2 de **millors/pitjors mitjanes i victòries/derrotes** i les
últimes 100 partides.
**Com** — `search_players`, `player_summary`, `player_ranking_history`, `player_best_worst_games`,
`player_games`; quatre workers en paral·lel amb guarda anti-obsolet (`snapshot != _selected_fcb`).
**A revisar**
- Molt per darrere de la fitxa web: no hi ha previsió del proper rànquing, ni rànquing d'opens, ni
  palmarès, ni aranya de rendiment, ni histograma, ni mitjana mòbil.
- `DataSource` té `player_rating_breakdown()` i `player_opens_femeni()` que **cap vista utilitza**.

## B.4 Partides

**S'espera** — Cercador global de partides amb filtres.
**Fa** — Filtres de jugador, club, modalitat, competició, «només temporada actual» i límit 300 files.
**Com** — `search_games()`, SQL amb `LIKE` sobre noms de jugador, club (equip o club del jugador) i
competició.
**A revisar**
- El combo de competicions està fixat a **Totes / LLIGA / INDIVIDUAL / COPA**. Els valors reals de
  competició inclouen «Lliga 3 Bandes», «Lliga 4 Modalitats», «Camp. Catalunya …» i «OPEN …»:
  *LLIGA* i *COPA* funcionen per `LIKE`, però **INDIVIDUAL no captura els Campionats de Catalunya**
  i **no hi ha opció per als opens**. Millor omplir el combo des de la taula `competicions`.
- El límit de 300 files és fix i no s'avisa quan es talla.

## B.5 Resultats

**S'espera** — Classificacions de lliga, resultats de copa i classificacions individuals.
**Fa** — Tres pestanyes: **Lliga** (combo de grups + classificació completa amb PF/PC),
**Copa** (llistat de partides amb comptador) i **Individuals** (temporada → torneig → classificació
amb MG, MP i sèrie).
**Com** — `lliga_groups`, `lliga_standings`, `copa_games`, `individuals_seasons`, `individuals_list`,
`individual_classification`.
**A revisar**
- Els grups de lliga es descriuen amb ids (`Lliga 36 · Div 2 · Grup 5`) tot i que `DataSource` té
  `_lliga_noms_map()` i `lliga_tree()` amb els noms reals.
- La classificació de lliga aquí es **calcula** dels encontres; el web mostra l'**oficial** amb
  penalitzacions. Dues visions diferents del mateix: convé alinear-les o etiquetar-les.
- `copa_edicions`, `copa_jornades`, `copa_grup`, `copa_encontre_detail`, `lliga_jornades`,
  `encontre_detail`, `lliga_player_ranking`, `copa_player_ranking` existeixen a `DataSource` i
  **no es fan servir** en aquesta vista.

## B.6 Clubs

**S'espera** — Llistat de clubs amb KPIs i drill-down al planter.
**Fa** — KPIs globals, taula de clubs (jugadors, equips, partides) i, en seleccionar-ne un, els seus
jugadors de la temporada actual.
**Com** — `clubs_with_kpis()`, `club_players(fcb_id, current_season_only=True)`.
**A revisar** — Existeixen `club_summary()` i `club_best_worst_games()` sense fer servir (la feina
la fa ara «Focus club»); és el mateix contingut per dos camins.

## B.7 Focus club

**S'espera** — Dashboard d'un club **real o virtual**, i sobretot **l'ordre intern al rànquing**, que
és el que fixa la composició dels equips de la temporada vinent.
**Fa** — Combo amb clubs reals (🏛) i virtuals (⭐), checkbox de temporada, KPIs agregats, membres,
graella 2×2 d'actuacions destacades i pestanya per modalitat amb **gràfic d'ordre intern** (eix
invertit, 1 = millor) més la taula equivalent.
**Com** — `real_club_player_ids` / `virtual_club_player_ids` → `focus_summary`, `focus_players`,
`focus_best_worst_games`, `focus_order_evolution`; totes amb clau de focus per descartar resultats
obsolets.
**A revisar**
- Club per defecte fixat al codi: `DEFAULT_CLUB = "C.B.BANYOLES"`.
- És la funcionalitat més valuosa de l'escriptori i **no té equivalent al web** (el bump chart del
  Focus club encara no s'ha portat a la PWA).

## B.8 Clubs virtuals

**S'espera** — Definir seleccions arbitràries de jugadors (cas Club Foment Martinenc) per analitzar-les
com si fossin un club.
**Fa** — CRUD de clubs virtuals i gestió de membres (cercar i afegir/treure).
**Com** — Taules locals de clubs virtuals via `DataSource` (`list/create/update/delete_virtual_club`,
`add/remove_virtual_club_member`).
**A revisar** — Viuen només al SQLite local: no es publiquen ni es poden consultar des del web.

## B.9 Reingesta

**S'espera** — El centre de comandament de la ingesta, sense haver de recordar comandes.
**Fa** — Dos panells:
- **Logada** (necessita login amb captcha): re-login amb Chromium; «només rànquing recent»
  (`sync` + `backfill 1`) o «reimport històric complet» (`import-temporada --historical`).
- **No logada**: lliga, copa, opens (temporada actual o històric complet), rànquing d'opens en
  directe, **diff del PDF oficial d'opens vs calculat**, edició de Copa i «publica al núvol en
  acabar». Botó separat de «només publicar».

Cada acció encua passos que s'executen **en sèrie** amb log en viu; si un falla, la resta continua.
**Com** — `SubprocessWorker` executant `uv run fcbillar …` i `uv run python -m fcb_opens.cli …`;
publicació = `publish-cloud` + `supabase-sync`.
**A revisar**
- ⚠ La reingesta logada **només fa `backfill 1`** (Tres Bandes), mentre que `weekly_reingest.ps1`
  fa el backfill de les 5 modalitats (1, 2, 3, 4, 6). Qui llanci la reingesta des de l'escriptori es
  deixarà les partides de lliure, banda i quadres.
- No executa `scripts/publish_records.py` (vegeu A.13) ni cap pas de verificació de codificació,
  que el script setmanal sí que fa.
- L'edició de la Copa i l'id de lliga (36) estan fixats a la interfície.
- No hi ha botó d'aturada de la seqüència en curs.

## B.10 Codi orfe a l'escriptori

- `desktop/views/banyoles_view.py` (208 línies) — versió anterior del Focus club, **no registrada** a
  `MainWindow`.
- `desktop/views/scraping_view.py` (117 línies) — substituïda per `ReingestaView`, **no registrada**.

Cap de les dues és accessible des de la interfície. Convé esborrar-les o marcar-les com a obsoletes.

---

# PART C — Qui alimenta cada secció

| Secció web | Taules Supabase | Publicador |
|---|---|---|
| Rànquings `/` | `modalitats`, `rankings`, `ranking_full`, `ranking_provisional` | `publish_rankings`, `publish_provisional_ranking` |
| Fitxa jugador | `players`, `clubs`, `games`, `pending_games`, `ranking_provisional`, `ranking_entries`, `player_clubs`, `open_classifications`, `open_ranking`, `player_rating_buckets/index` | `publish_games`, `publish_pending_games`, `publish_player_clubs`, `publish_rating_buckets`, `publish_opens`, `publish_open_ranking(_femeni)` |
| Lliga | `lliga_groups`, `lliga_standings`, `lliga_player_rankings`, `lliga_encontres`, `lliga_partides` | `publish_lliga`, `publish_lliga_player_rankings`, `publish_lliga_encontres` |
| Lliga (històric) | `lliga_history` | **cap** ⚠ (es publica `lliga_standings_hist`, que el web no llegeix) |
| Copa | `copa_groups`, `copa_standings`, `copa_player_rankings`, `copa_encontres`, `copa_partides` | `publish_copa`, `publish_copa_player_rankings`, `publish_copa_encontres` |
| Opens / Campionats | `opens`, `open_classifications`, `open_partides`, `open_ranking` | `publish_opens`, `publish_open_partides`, `publish_open_ranking` |
| Open en directe | `open_live`, `open_live_scores` | `publish-live-opens` (workflow) · worker OCR (en pausa) |
| Clubs / Fitxa club | `clubs`, `players`, `ranking_full`, `ranking_entries` | `publish_rankings` |
| Cerca / Comparar / Seguits | `players`, `clubs`, `games`, `ranking_entries`, `copa_partides` | — |
| Calendari `/calendari` | `calendari_events`, `calendari_revisions`, `calendari_canvis` | `publish_calendari` |
| Rècords | `records` | `scripts/publish_records.py` ⚠ **manual** |
| Admin (cues) | `reingest_requests`, `open_projection_requests`, `cloud_status` | watchers locals + `state report` |

L'escriptori no passa per Supabase: llegeix `data/fcbillar.db` directament. Per tant **pot mostrar
dades diferents del web** si la publicació ha fallat o si el workflow del núvol ha escrit per sobre.

---

# PART D — Llista prioritzada de coses a corregir

### Prioritat 1 — Errors verificats que afecten el que veu l'usuari

1. **`ymFromSeq` retorna «Juny 2026» per a tots els rànquings ≥ 122** (`PlayerProfile.svelte`,
   `seguiment/+page.svelte`). El vigent és el 124. Substituir per `rankings.mes_pub`/`any_pub`,
   compartit en un únic helper.
2. **`/cerca`, `/comparar` i `/seguiment` només veuen 1.000 dels 1.556 jugadors** (límit de
   PostgREST). Paginar amb `.range()` o fer cerca server-side.
3. **La pestanya Rècords està congelada**: `scripts/publish_records.py` no s'executa des de cap
   automatisme. Afegir-lo a `weekly_reingest.ps1` (o a `publish-cloud`).
4. **`lliga_history` no té productor**: l'històric de lliga del web no s'actualitzarà mai. Decidir
   entre migrar el web a `lliga_standings_hist` o documentar la càrrega manual. A més, cap de les
   dues taules té la temporada 2025-2026.
5. **La reingesta logada de l'escriptori només fa `backfill 1`**, no les 5 modalitats.

### Prioritat 2 — Duplicacions que faran divergir les dades

6. Projecció del proper rànquing calculada **dues vegades**: backend (`ranking_provisional`,
   la fa servir la fitxa) i navegador (`/seguiment`, només modalitat 1 i pendents de Copa).
7. Premis per banda de rànquing 3B calculats al publicador **i** al navegador (`/opens/directe`).
8. Tipus de torneig i modalitat deduïts del nom en tres llocs: `torneig_naming` (Python),
   `tipusOf` (`$lib/supabase.ts`) i les regex del palmarès dins de `PlayerProfile`.
9. `/clubs` agrupa per **nom** de club mentre que la resta fa servir `club_fcb_id`; `clubKey()` ja
   existeix i no s'hi aplica.

### Prioritat 3 — Cobertura funcional

10. La **Lliga 4 Modalitats** (7.246 partides a `games`) no té secció enlloc; el web només cobreix
    la lliga 36 (Tres Bandes).
11. La fitxa de club del web és **només 3 bandes**, sense selector de modalitat.
12. L'**ordre intern al rànquing** (bump chart del Focus club) segueix sent exclusiu de l'escriptori.
13. La fitxa de jugador de l'escriptori s'ha quedat molt enrere respecte de la web (sense previsió,
    opens, palmarès, aranya ni histograma).
14. Cap secció web mostra **quan es van actualitzar les dades**; `cloud_status.last_run` només es
    consulta per a l'avís d'admin.

### Prioritat 4 — Manteniment i neteja

15. Esborrar o marcar com a obsoletes `desktop/views/banyoles_view.py` i `scraping_view.py`.
16. Mètodes de `DataSource` sense cap consumidor (`player_rating_breakdown`, `player_opens_femeni`,
    `copa_edicions`, `copa_jornades`, `copa_grup`, `copa_encontre_detail`, `lliga_jornades`,
    `encontre_detail`, `lliga_player_ranking`, `copa_player_ranking`, `club_summary`,
    `club_best_worst_games`, `lliga_tree`): decidir si es porten a la interfície o s'eliminen.
17. Valors fixats al codi que caduquen cada temporada: edició de Copa (7), id de lliga (36),
    `DEFAULT_CLUB`, finestra de 5 opens, ancoratge del `num_seq`.
18. `PlayerProfile.svelte` (1.760 línies) i `/opens/directe` (770): candidats a extracció de components.
19. Confirmar les polítiques RLS de `reingest_requests` i `open_projection_requests` (els gates de
    correu són només client-side) i definir una retenció per als PDFs en base64.
20. `/opens/[open_id]` casa les partides **pel nom** del jugador, no per `player_fcb_id`.
