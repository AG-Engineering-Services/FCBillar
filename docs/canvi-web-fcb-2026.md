# El web de la FCB ha canviat (agost 2026) — impacte i pla

Revisió feta el **2026-08-30** contra el web en viu, i **repassada el
2026-09-20**, quan la temporada ja havia començat. Cada fila de les taules
d'aquest document s'ha comprovat amb una petició real; l'estat que hi diu és el
que retorna el servidor, no una suposició.

El que va canviar amb la temporada en joc és a les seccions **§2.8 a §2.11**: el
detall d'encontre de lliga s'ha curat (i la seva taula no era la que s'havia
suposat), els encontres no jugats sí que es publiquen, el campionat de Catalunya
d'individuals ja es juga, el club és un per competició —i la caché de disc no
caducava, que és el que feia que res d'això es ves.

---

## Resum en cinc línies

1. **Les dades són les mateixes i els identificadors no han canviat.** No cal
   refer cap ingesta: el que tenim a `data/fcbillar.db` continua sent vàlid i
   enllaçable amb l'origen.
2. **Tot el codi de scraping està trencat**, però per motius mecànics: domini
   nou, rutes noves i marcatge HTML completament diferent.
3. **Ja no cal login, ni captcha, ni Playwright**: rànquings i partides ara són
   públics i es baixen amb un `GET` normal.
4. **Han desaparegut dues fonts**: la classificació final d'individuals i
   l'històric per temporades. També tot `/media/**` (els PDF antics).
5. ~~Un endpoint està trencat al seu servidor: el detall d'encontre de lliga
   retorna HTTP 500.~~ **Curat el setembre** (§2.8), i amb una taula que no era
   la que s'havia suposat mentre no es podia veure.
6. **La caché de disc no caducava** i la ingesta llegia pàgines de mesos enrere
   sense fallar mai (§2.11). És el que tapava tots els punts anteriors.

---

## 1. Què ha canviat exactament

On abans hi havia un sol web, ara n'hi ha tres:

| Peça | Adreça | Tecnologia | Què hi ha |
|---|---|---|---|
| Web públic | `https://fcbillar.cat` | WordPress (Divi + Yoast + WP File Download) | Notícies, agenda, clubs, documents i PDF |
| Zona de competició | `https://intranet.fcbillar.cat/frontend/…` | CodeIgniter + Bootstrap `sb-admin-2` | Rànquings, lligues, individuals, copa — **tot públic** |
| Panells privats | `https://intranet.fcbillar.cat/{jugador,club}/login` | Idem, amb captcha | Zona federada personal |

La versió que declara la intranet és `a-2026.08.25`, i el WordPress es va
publicar el 2026-07-07. És a dir: el canvi és de fa poques setmanes.

### 1.1 El domini `www` ja no serveix

`www.fcbillar.cat` resol per DNS però la connexió falla. El nostre
`Settings.base_url` per defecte és exactament `https://www.fcbillar.cat`
([config.py:24](../src/fcbillar/config.py#L24)), i tots els scrapers de
`fcb_opens` el porten escrit a dins. Qualsevol ingesta mor a la primera
petició.

### 1.2 El marcatge HTML és un altre

Els parsers estan escrits contra una graella tipus Skeleton:

```
section.three.fourths.padded   ← 15 usos a parsers.py
div.row.box.info               ← llistes de grups, jornades
div.two.ninths / three.ninths  ← detall de partida de lliga
```

Cap d'aquests selectors existeix ara. El web nou fa taules Bootstrap normals:

```html
<table class="table table-bordered table-hover">
  <thead><tr><th>#</th><th>Jugador</th><th>MJ</th>…</tr></thead>
```

Això és, de fet, una **millora**: el marcatge nou és uniforme i té `<thead>`
de debò, i es pot llegir amb un únic parser genèric de taules.

### 1.3 El login ja no cal

El rànquing i les partides de cada jugador eren la part logada, la que obligava
a mantenir Playwright, `storage_state.json`, el captcha manual i la finestra
setmanal amb l'usuari al davant. **Ara són públiques.** Verificat: una petició
sense cap galeta ni capçalera especial retorna la pàgina sencera.

---

## 2. Mapa d'URLs, endpoint per endpoint

Base antiga: `https://www.fcbillar.cat`. Base nova: `https://intranet.fcbillar.cat`
(competició) o `https://fcbillar.cat` (WordPress).

### 2.1 Rànquings i partides — de rutes a paràmetres

| Què | Abans | Ara | Estat |
|---|---|---|---|
| Descoberta de rànquings | `/ca/jugador/ranking/historial/` **(logat)** | `/frontend/rankings/llistat` | ✅ públic |
| Rànquing vigent | `/ca/jugador/ranking/datahome/{n}/{m}` | `/frontend/rankings/llistat-dades?idranking={n}&idmodalitat={m}` | ✅ |
| Rànquing històric | `/ca/jugador/ranking/data/{n}/{m}` | `/frontend/rankings/historial-dades?idranking={n}&idmodalitat={m}` | ✅ |
| Partides d'un jugador (vigent) | `/ca/jugador/ranking/partideshome/{n}/{m}/{id}` | `/frontend/rankings/llistat-partides?idranking={n}&idmodalitat={m}&idjugador={id}` | ✅ |
| Partides d'un jugador (històric) | `/ca/jugador/ranking/partides/{n}/{m}/{id}` | `/frontend/rankings/historial-partides?…` | ✅ |

Conseqüència directa: **`url_builder.py` desapareix**. Els dos formats
(`data`/`datahome`) que ens fèiem venir bé ja no són dos formats d'URL sinó dos
endpoints amb significat diferent — vigent contra històric — i el web ens diu
quin toca a `/frontend/rankings/llistat`.

Aquesta pàgina llista **1 rànquing vigent + 15 d'històric**, els mateixos 16 de
sempre. El vigent avui és `idranking=124`, del **2026-07-27**, que és
exactament l'últim que tenim ingerit. **No hem perdut cap rànquing.**

Les columnes de la taula són idèntiques a les d'abans
(`#, Jugador, MJ, MR, Rang, C, E, P/PT, Def, Partides`), amb un detall a
favor nostre: el rànquing vigent ara publica **5 decimals** (`1.63665`) mentre
que l'històric en publica 3 (`1.633`).

### 2.2 Lliga — mateixa gramàtica, prefix nou

| Què | Abans | Ara | Estat |
|---|---|---|---|
| Llistat | — | `/frontend/lligues/llistat` | ✅ |
| Divisions | `/ca/lligues/divisions/{lliga}` | `/frontend/lligues/divisions/{lliga}` | ✅ |
| Grups | `/ca/lligues/grups/{l}/{d}` | `/frontend/lligues/grups/{l}/{d}` | ✅ |
| Jornades | `/ca/lligues/jornades/{l}/{d}/{g}` | `/frontend/lligues/jornades/{l}/{d}/{g}` | ✅ |
| Encontres | `/ca/lligues/encontres/{l}/{d}/{g}/{j}` | `/frontend/lligues/encontres/{l}/{d}/{g}/{j}` | ✅ |
| Classificació | `/ca/lligues/classificacio/{l}/{d}/{g}` | `/frontend/lligues/classificacio/{l}/{d}/{g}` | ✅ |
| **Detall d'encontre** | `/ca/lligues/partides/{l}/{d}/{g}/{j}/{e}` | `/frontend/lligues/partides/{l}/{d}/{g}/{j}/{e}` | ✅ **curat** (§2.8) |
| Inscripcions (club → equip) | — | `/frontend/lligues/inscripcions/{lliga}` | 🆕 |
| **Inscrits d'un club** (club → jugador) | — | `/frontend/lligues/participants/{lliga}/{club}` | 🆕 (setembre) |

⚠→✅ **El detall d'encontre de lliga tornava HTTP 500 i ja no.** Comprovat el
**2026-09-20**: funciona, i **per a totes les temporades**, també la 36 de
2025-26, que era la que petava sempre. Era un error seu, com feia pensar el fet
que el detall de copa sí que anés.

La taula, però, **no és la que s'havia suposat** mentre no es podia veure, i per
tant el parser escrit a cegues no en treia ni una partida. Vegeu §2.8.

La temporada 2025-26 (lliga **36**) continua accessible pel seu id encara que
no surti al llistat, amb les mateixes divisions (148-152) i els mateixos grups
(316, 317, 333, 338) que fem servir al README. Les lligues noves són la **38** i
la **39**.

### 2.3 Individuals i opens — dos renoms

| Què | Abans | Ara | Estat |
|---|---|---|---|
| Llistat de torneigs | `/ca/individuals/llistat` | `/frontend/individuals/llistat` | ✅ |
| Divisions | `/ca/individuals/divisions/{t}` | `/frontend/individuals/divisions/{t}` | ✅ |
| Fases | `/ca/individuals/fases/{t}/{d}` | `/frontend/individuals/fases/{t}/{d}` | ✅ |
| Grups | `/ca/individuals/grups/{t}/{d}/{f}` | `/frontend/individuals/grups/{t}/{d}/{f}` | ✅ |
| Partides d'un grup | `/ca/individuals/partidesgrups/…` | `/frontend/individuals/**partides-grup**/{t}/{d}/{f}/{g}` | ✅ renom |
| Partides d'eliminatòria | `/ca/individuals/partideseliminatoria/…` | `/frontend/individuals/**partides-eliminatories**/{t}/{d}/{e}` | ✅ renom |
| **Classificació final** | `/ca/individuals/classificaciofinal/{d}/{c}` | — | ❌ **desapareguda** (§2.7: la calculem) |
| Inscripcions | — | `/frontend/individuals/inscripcions/{t}` | 🆕 |

Els ids antics continuen resolent: `divisions/211` és l'OPEN TRES BANDES
MATARÓ i `divisions/14` és el CAMPIONAT CATALUNYA HISTÒRIC QUADRE 47/2 de la
importació 2012-2014. **Tot el nostre catàleg de 392 torneigs segueix
enllaçable.**

La pàgina de partides d'un grup ha guanyat qualitat: dona sèrie major,
caramboles, entrades, àrbitre i estat per partida.

### 2.4 Copa — tota renombrada

| Què | Abans | Ara | Estat |
|---|---|---|---|
| Llistat | — | `/frontend/copa/llistat` | ✅ (buit ara: cap edició oberta) |
| Fases | `/ca/copa/faseGrups/{e}` | `/frontend/copa/**fase-grups**/{e}` | ✅ |
| Grups d'una jornada | `/ca/copa/grups/{e}/{j}` | `/frontend/copa/grups/{e}/{j}` | ✅ |
| Encontres d'un grup | `/ca/copa/encontresGrup/{e}/{j}/{g}` | `/frontend/copa/**encontres-grup**/{e}/{j}/{g}` | ✅ |
| Partides d'un encontre | `/ca/copa/partidesGrup/{e}/{j}/{g}/…` | `/frontend/copa/**partides-grup**/{e}/{j}/{g}/{enc}/{eqA}/{eqB}` | ✅ |

L'edició 7 (2025-26) continua accessible i el detall de partida **sí que
funciona** — amb sèrie major, caramboles, punts, entrades i àrbitre. És la
prova que el 500 de la lliga és un error puntual seu, no un tancament
deliberat.

### 2.5 Clubs, documents i calendari — ara al WordPress

| Què | Abans | Ara | Estat |
|---|---|---|---|
| Llistat de clubs | `/ca/clubs/5/Federacio` | `https://fcbillar.cat/federacio/llistat-de-clubs-federacio-catalana-de-billar/` | ✅ **més ric** |
| Documents de competició | `/ca/docs/s/1/Carambola/c/68/15` | `https://fcbillar.cat/wpfd_file-sitemap.xml` → `/wpfd_file/{slug}/` → `/download/{cat}/{categoria}/{id}/{fitxer}.pdf` | ✅ mecanisme nou |
| PDF antics | `/media/**` | — | ❌ **404, tots** |
| Calendari FCB | `/media/{temp}/CALENDARIS/*.pdf` | `/download/36/calendari/232324/calendari-fcb-2026-27-v-2.pdf` | ✅ patró nou |
| Rànquing mensual públic | `/ca/rankings/s/1/Carambola/m/{mes}/1/` | — | ❌ desaparegut (era duplicat) |

El llistat de clubs ha millorat: ara són **39 clubs amb telèfon, correu,
adreça i web**, camps que abans no teníem.

Els documents es descobreixen millor que abans: el sitemap de Yoast
(`wpfd_file-sitemap.xml`) llista **els 37 fitxers** publicats, i cada pàgina
`/wpfd_file/{slug}/` conté l'enllaç directe al PDF. Substitueix el
`DOCS_OPENS_BASE` amb offsets de 20 en 20 i l'URL fixa de
[official_pdf.py:13](../src/fcb_opens/scraper/official_pdf.py#L13).

El descobriment del calendari de
[calendari_fed.py](../src/fcbillar/calendari_fed.py) busca amb regex
`/media/{temporada}/CALENDARIS/*.pdf` a la portada. Aquest patró ja no
existeix; el calendari 2026-27 v-2 és a la categoria `calendari` del WPFD.

---

### 2.6 Font nova de setembre: de qui està fet cada club

El 2026-09-04, tres dies després de tancar el termini d'inscripció de la lliga
de tres bandes, la federació va penjar un botó «Veure inscrits» a cada club de
la pàgina d'inscripcions. Darrere hi ha
`/frontend/lligues/participants/{lliga}/{club}`: **els jugadors que cada club
inscriu, amb la mitjana i una etiqueta per als fitxatges**.

És la primera vegada que publica això. Fins ara `plantilles.py` ho havia
d'estimar de qui havia jugat les dues últimes temporades, i ho deia clarament
que era una estimació.

El que en surt de la lliga 38 (Tres Bandes 2026-27): **38 clubs, 93 equips, 680
inscripcions de 669 jugadors i 11 fitxatges**. Les 676 mitjanes que es poden
contrastar **coincideixen amb el rànquing 124 fins als 5 decimals, sense cap
diferència**: la columna és exactament la MJ del rànquing vigent.

Tres coses que cal saber per llegir-la bé:

1. **És per club, no per equip.** Diu qui juga amb cada club, no si va a l'"A" o
   a la "D", encara que el club tingui cinc equips.
2. **Un fitxatge surt dues vegades i està bé.** Qui ve d'un altre club apareix a
   la llista del seu club sense marca i a la del club que se l'endú amb
   `(Fitxatge)`. Sembla una contradicció i no ho és: comprovat contra el
   llistat de divisions de l'individual 2026/2027, que és una font
   independent, **el club sense marca és el que hi consta 349 vegades de 349**.
3. **El club només s'escriu al primer equip de cada club** a la pàgina
   d'inscripcions; les altres files el porten buit. Filtrar-les —que és el que
   feia `parse_lliga_inscripcions`— tornava 38 equips en comptes de 93.

Vuit files no es poden llegir com a bones, i les treu la mateixa comanda
(`fcbillar ingest-inscrits-lliga`, avisos de `inscrits_lliga.revisa`): dos
jugadors que dos clubs es reclamen sense que cap fila porti la marca, dos
fitxatges que cap club no dona, dues mitjanes a zero d'algú que ha jugat, i
dues mitjanes que no són al rànquing i per tant no es poden contrastar.

I la **lliga de 4 Modalitats (39) té 29 equips de 20 clubs i cap jugador
publicat a cap dels vint**, tot i que el seu termini va tancar una setmana
abans. La ingesta ho detecta, no desa res d'aquella lliga i continua.

### 2.8 El detall d'encontre de lliga: curat, i amb una taula que no esperàvem

Revisió del **2026-09-20**. Les tres coses que la lliga no carregava bé són totes
d'aquesta secció.

**a) Les partides individuals no es llegien.** La pàgina va tornar a funcionar,
però la seva taula no té la forma de les d'individuals i de copa, que és contra la
qual el parser s'havia escrit mentre l'endpoint donava 500:

```
<equip local> | <equip visitant> | SM/Caramboles | SM/Caramboles |
Entrades | Modalitat | Estat | <punts de la partida>
```

Els **equips són les capçaleres** de les dues primeres columnes, cada resultat ve
aparellat dins d'una sola cel·la (`4 / 27` = sèrie major 4, 27 caramboles) i
l'última columna, que no té títol, són els punts (`2 / 0`, o `1 / 1` si han
empatat). El parser buscava columnes «Local», «Visitant» i «Entrades» i per tant
no trobava cap taula: **zero partides, sense cap error**. D'aquí que de la lliga
només en sortís el resultat de l'encontre.

Guanys i pèrdues respecte del web antic: hi ha la **modalitat per partida** —que a
la lliga de 4 Modalitats és imprescindible, perquè cada partida d'un encontre
juga una modalitat diferent— i els **punts per partida**, que abans no s'hi
publicaven. Però **ja no hi ha data, ni àrbitre, ni assistència**: el web antic
els donava i el nou no. L'única font que encara dona l'àrbitre és el panell del
jugador logat (§9), i només per a un jugador.

**b) Els encontres no jugats sí que es publiquen.** Es donava per fet que no
—«a la seva web, un enfrontament no disputat no porta ni enllaç ni
identificador»— i és mig veritat: no porta **identificador**, però hi surt
igualment, amb els dos equips, l'estat «Oberta» i els punts a zero. La pàgina
d'encontres publica **totes les jornades senceres des del primer dia**, fins a la
catorzena.

El parser els saltava perquè en treia els ids de l'enllaç, i sense enllaç no podia
situar la fila. I encara que no els hagués saltat, no s'haurien pogut desar:
`encontres_lliga` tenia `encontre_id_extern` NOT NULL i dins de la clau única.

Per això la identitat d'un encontre passa a ser **la parella dins de la jornada**
(esquema v23). L'identificador de la federació no és una part de la identitat: és
un atribut que arriba el dia que algú introdueix el resultat, i llavors entra a la
fila que ja hi havia. Un encontre es desa el dia que es publica el calendari i
s'omple quan es juga.

Compte, que és la trampa d'aquesta clau: dos encontres de la mateixa parella dins
de la mateixa jornada passen a ser un de sol. No hi són —una parella juga un cop
per jornada— i la migració ho comprova abans de refer la taula, però vol dir que
fusionar dos clubs pot fer-ne aparèixer si les seves fitxes tenen encontres contra
el mateix rival a la mateixa jornada.

Conseqüència: **`lliga_calendari` ja no és l'única font del calendari**. El PDF de
cada grup continua sent útil (arriba abans que la competició existeixi i porta les
dates), però la competició mateixa ja publica tots els enfrontaments, i quan les
dues hi són mana la competició.

Prova: la lliga 38 sencera dóna **672 encontres** (12 grups × 14 jornades × 4), dels
quals 7 jugats i 665 de calendari. Abans en sortien els 7.

**c) La classificació sortia amb mitja graella.** Aquesta no era del web: era
nostra. `publish_lliga` construïa les files recorrent els encontres ingerits, i els
encontres només diuen **qui ha jugat**. La classificació oficial —que sí que és el
cens dels equips d'un grup i els publica **tots des del primer dia**, amb PM, PP i
J— només s'usava quan no s'havia jugat *res*. El cas de mig grup, que és el normal
tota la temporada, queia entremig: a la primera jornada d'Honor Grup A de la 26/27
la web ensenyava quatre equips de vuit, i els altres quatre no hi eren ni a zero.

Ara es recorre la classificació oficial i els encontres només hi posen els
comptadors. Un equip del qual tenim encontres i que l'oficial no llista —una
promoció, un canvi de nom a mitja temporada— va al final amb el que n'hem comptat,
que és pitjor que ordenat però molt millor que desaparegut.

### 2.9 El campionat de Catalunya d'individuals: la temporada en curs

El llistat d'individuals de la 2026-27 porta quatre torneigs: dos opens (217 Punt
d'Atac, 219 Banda Granollers) i **dos campionats de Catalunya** (216 TRES BANDES
INDIVIDUAL, 218 QUADRE 47/2). El 216 no és un open: té **vuit divisions** —Honor,
1a a 6a i Única— i les seves fases es diuen PRE-PRÈVIA i PRÈVIA.

El 2026-09-19 ja se n'havien jugat tres: la **prèvia d'Honor** (4 grups, 16
jugadors), i les **pre-prèvies de 1a** (11 grups, 33) i de **2a** (14 grups, 42).
Hi eren al web i no s'ingerien per dos motius que es resolen aquí.

**a) La classificació de cada grup no la llegia ningú.** La pàgina de partides d'un
grup porta DUES taules, i només se'n llegia una:

```
Grup I - CLASSIFICACIÓ     Jugador | Punts | Mitjana
Grup I - PARTIDES          Local | SM | Caramboles | Visitant | ...
```

Aquella primera taula és **l'única cosa que diu qui s'ha classificat**. Dos punts
per victòria, un per empat, i la mitjana del grup; ve ja ordenada i la posició és
l'ordre de la fila. Ara va a `torneig_fase_grups` (esquema v23), amb la posició,
els punts i la mitjana.

De passada resol una cosa: la taula de participants de la fase **no és completa**.
Es deixa qui no ha jugat cap partida —dos dels 33 de la pre-prèvia de 1a—, i la
classificació del grup els porta tots, amb la mitjana buida. Les dues fonts
s'uneixen.

**b) L'ordre ENTRE grups no el publica ningú, i fa falta.** Els PDF de sorteig
diuen qui passa de ronda i no sempre és el mateix:

| Fase | Qui passa |
|---|---|
| Prèvia d'Honor | «els dos primers de cada grup» |
| Pre-prèvia de 1a | «els primers de cada grup i els **set millors segons**» |
| Pre-prèvia de 2a | «el primer de cada grup i els **quatre millors segons**» |

«Els set millors segons» vol dir que els segons dels onze grups s'han de poder
comparar entre ells, i això la federació no ho publica enlloc. Es calcula
(`individuals.ranquing_fase`) amb l'ordre que ella mateixa aplica: **posició dins
del grup, després punts de la ronda, i a igualtat de tots dos la mitjana**. O
sigui tots els primers ordenats entre ells, després tots els segons, i així fins
al final. Qui no ha jugat cap partida hi surt l'últim del seu lloc, que és on li
toca.

La classificació deduïda d'un torneig (§2.7) també se'n serveix: on hi ha
classificació de grup mana ella, i el criteri vell —«qui va guanyar l'última
partida»— es queda per a les eliminatòries, que és on vol dir alguna cosa.

Al núvol hi va com `open_fases` + `open_fase_ranquing` (migració 0017), que és una
cosa diferent d'`open_classifications`: aquella és la classificació final del
torneig i això és la foto d'una ronda mentre es juga.

### 2.10 Amb quin club juga cadascú: una resposta per competició

Un jugador no té un club: en té un per competició, i les dues coses passen a la
2026-27.

| Cas | Quants, el 2026-09-20 |
|---|---|
| Fitxat a la lliga de 4 Modalitats per un club i a la de tres bandes per un altre | **4** |
| Juga el campionat individual per un club diferent del de la lliga | **2** |

`players.club_id` és una columna sola i per tant no ho pot dir: el que hi ha
escrit és el club d'on ve l'última cosa ingerida. Es queda per a l'històric —hi ha
catorze temporades penjades d'ella— però per a la temporada en curs la font és la
taula nova **`afiliacions`** (esquema v24), amb una fila per (temporada,
competició, modalitat, jugador). Es refa amb `fcbillar afiliacions`, que a més
llista qui juga per clubs diferents segons la competició.

D'on surt cada meitat:

- **Lliga**: de `lliga_inscrits`, que ja s'ingeria. Qui ve fitxat surt a dues
  llistes —al seu club sense marca i al que se l'enduà amb `(Fitxatge)`— i per a
  «amb quin club juga» la resposta és una: el club que el fitxa.
- **Campionat individual**: dels **PDF de sorteig de cada fase**. El portal no
  publica el club de l'individual a **cap** pàgina del campionat, i
  `individuals/inscripcions/216` està buida («0 registres»). El PDF sí, i és de
  **dues columnes**: llegit per línies barreja un jugador del grup de l'esquerra
  amb un del de la dreta i els clubs es creuen. Es llegeix per coordenada `x`
  (`sorteig_fase`) i es descobreix pel sitemap del WordPress filtrant per
  categoria `individuals-*`, que és l'única cosa que el distingeix del sorteig
  d'un open.

Dues coses que no es resolen i s'apunten: dos jugadors de la lliga 38 que dos
clubs es reclamen sense que cap fila porti la marca de fitxatge. Triar-ne un
seria inventar-se un fitxatge.

I la **lliga de 4 Modalitats (39) ja publica els seus jugadors**: 328 inscrits de
19 clubs i 9 fitxatges. El §2.6 deia que no en publicava cap i era veritat el dia
que es va escriure; el que va impedir veure-ho quan van aparèixer és el §2.11.

### 2.11 La caché no caducava, i per tant la ingesta no veia res de nou

El problema més gros de tots, i el que no fallava mai.

`ScraperClient` desa cada pàgina a disc i la tornava a servir **per sempre**. El
2026-09-20 hi havia **157.856 fitxers a `data/cache` amb una edat mitjana de 82
dies**. Les pàgines que ingerim són de competicions en joc, o sigui que una
ingesta nocturna llegia la pàgina del dia que es va baixar per primer cop.

Es va veure aquí: els inscrits de la lliga de 4 Modalitats van estar **setze
dies** sortint buits perquè el dia que es van demanar per primera vegada la
federació encara no n'havia publicat cap. La comanda deia «29 equips de 20 clubs,
però cap jugador publicat. No deso res d'aquesta lliga», que era exactament el que
hi havia... a la còpia de setze dies abans.

Ara la caché caduca (`Settings.cache_max_age_sec`, una hora per defecte): prou per
no repetir una pàgina dins d'una execució ni mentre s'hi treballa a sobre, i prou
poc per no tapar res a una tasca que corre cada nit. `0` la deixa sense caducitat,
que és el que feia abans.

### 2.7 Els opens: de la classificació morta al quadre sencer

La ingesta d'individuals demanava la classificació final de cada divisió i en
treia els participants amb la seva posició. Aquella pàgina ja no existeix, o
sigui que **la ingesta corria sense fallar i no desava res**: tres torneigs
descoberts, zero participants, i un «OK» al final. El fallo s'apuntava com un
avís per torneig i no el veia ningú.

Ara es recorre el que el web nou sí que publica, que és més ric del que hem
perdut: fases → grups (amb qui hi juga) → partides, i les eliminatòries. De
cada partida en surten caramboles, entrades, sèrie major, àrbitre i estat.

Hi havia una peça que no llegia ningú: **l'id d'un grup no s'escriu enlloc**,
només és a l'enllaç de la seva fila a la pàgina de la fase. Sense
`parse_individuals_grups` les partides dels grups són inabastables encara que
la pàgina que les serveix funcioni — a l'open de proves, 37 de 44.

**La classificació la deduïm del quadre** i s'ha de dir: la darrera fase que va
jugar cadascú marca fins on va arribar, dins d'una fase mana qui va guanyar
l'última partida, i si encara empaten, la mitjana general del torneig. No és
cap invenció —és l'ordre que el reglament d'opens ja dona per bo quan puntua,
on la 3a i la 4a valen igual— però tampoc no és oficial, perquè oficial ja no
n'hi ha cap.

Provat contra l'**OPEN LLIURE PUNT D'ATAC** (torneig 217), tancat el
2026-09-06: 6 fases, 13 grups, **44 partides i 24 participants**, i el quadre
retorna el campió (CARBONELL TRILLA, MATEU), el finalista i els dos
semifinalistes al lloc que els toca. Les seves pàgines són a
`tests/fixtures/nou/` com a prova de regressió.

Un torneig publicat però sense cap partida jugada —el 216 i el 218 ara
mateix— ja no compta com a fallada: no hi ha res a desar perquè encara no ha
passat res, i la comanda ho diu.

## 3. Impacte mòdul a mòdul

| Mòdul | Estat | Feina |
|---|---|---|
| [config.py](../src/fcbillar/config.py) | ✅ **Fet** | `base_url` apunta a la intranet; fora `session_dir` i `headless` |
| ~~`auth.py`~~ | ⚫ **Esborrat** | Ja no cal login per a res que ingerim |
| [scraper/client.py](../src/fcbillar/scraper/client.py) | ✅ **Fet** | Playwright + sessió → `httpx` amb caché **que caduca** (§2.11), ritme i reintents |
| ~~`scraper/url_builder.py`~~ | ⚫ **Esborrat** | Els dos formats ja no existeixen |
| [scraper/parsers.py](../src/fcbillar/scraper/parsers.py) | ✅ **Fet** | Reescrit sobre `taules.py`, el lector genèric |
| [pipeline.py](../src/fcbillar/pipeline.py) | ✅ **Fet** | Ara construeix les URLs amb `scraper/urls` |
| [db/](../src/fcbillar/db/) | 🟠 v23 i v24 | L'encontre és la parella, no l'id (§2.8); la classificació de grup i `afiliacions` (§2.9, §2.10) |
| [cloud_sync.py](../src/fcbillar/cloud_sync.py) | ✅ **Fet** | La classificació surt del cens oficial (§2.8c) i s'hi afegeixen `publish_open_fases` i `publish_afiliacions` |
| [calendari_fed.py](../src/fcbillar/calendari_fed.py) | 🟠 Descoberta | Regex `/media/` → WPFD |
| `fcb_opens/scraper/` (4.695 l.) | 🔴 Trencat | 8 mòduls amb `www.fcbillar.cat` a dins |
| `fcb_opens/lliga/parser.py` | 🔴 Trencat | Marcatge antic |
| [scripts/weekly_reingest.ps1](../scripts/weekly_reingest.ps1) | 🔴 Trencat | Tots els passos d'ingesta |
| `web/` (SvelteKit → Neon) | 🟢 **Intacte** | No toca la FCB; segueix servint |
| `desktop/` (PyQt6 → SQLite) | 🟢 **Intacte** | Llegeix la BD local |

Les dues aplicacions que l'usuari veu **no s'han aturat**. El que s'ha aturat
és l'alimentació.

---

## 4. Què NO cal refer

Aquesta és la part que estalvia setmanes de feina. Comprovacions fetes:

| Comprovació | Resultat |
|---|---|
| `idjugador=843` | MAS CANADELL, JOSEP Mª → **el mateix `fcb_id` que a la nostra BD** |
| `lligues/divisions/36` | 2025-26 amb les 4 divisions de sempre |
| `individuals/divisions/14` | HISTÒRIC QUADRE 47/2, de la importació 2012-2014 |
| `idranking=124` | 2026-07-27 = l'últim rànquing que tenim |
| Columnes del rànquing | Idèntiques |
| Competició de cada partida | Continua explícita (Lliga / Individual / Copa) |
| **Reingesta del 124/1 amb el codi nou** | **0 jugadors amb estadístiques diferents** |

L'última fila és la comprovació que importa, i es va fer el 2026-08-30: es va
reingerir el rànquing vigent sencer des del web nou a una base de dades buida i
es va comparar jugador a jugador amb el que teníem des del 30 de juliol. Dels
611 que surten a totes dues lectures, **cap no té cap diferència** ni al nom, ni
a la mitjana, ni a cap dels extres —mitjana dels contraris, rang, caramboles,
entrades, punts, definitiva.

### 4.1 Però el rànquing vigent no està congelat

La mateixa comparació va destapar una cosa que no sabíem: entre el 30 de juliol
i el 30 d'agost la federació ha **afegit 104 jugadors** al rànquing 124 i n'ha
tret 2, cosa que ha mogut 505 posicions. És la renovació de llicències de la
temporada nova entrant a poc a poc.

Conseqüència pràctica: **el rànquing vigent s'ha de tornar a ingerir mentre ho
sigui**, no només el dia que apareix. Ara mateix la nostra còpia del 124 de tres
bandes va 102 jugadors curta.

**És el mateix sistema darrere, amb una capa web nova al davant.** No hi ha cap
motiu per reingerir res «per si de cas»: la deduplicació per `id_natural` fa que
qualsevol reingesta sigui idempotent, i les que valgui la pena fer són
puntuals i estan a la fase 3 del pla.

---

## 5. Oportunitat: el scraper es fa molt més petit

El canvi permet esborrar més codi del que obliga a escriure:

**Fora** (fet)
- Playwright, `storage_state.json`, el captcha i el login interactiu. Amb ells
  se'n van `auth.py`, les comandes `fcbillar login` i `fcbillar session-check`,
  el blob de sessió que viatjava a R2 (`state push --session`) i el banner de
  «sessió caducada» del PWA, que ja no es pot encendre.
- `url_builder.py` i la lògica de fallback entre `data` i `datahome`.
- La separació entre «ingesta logada local» i «ingesta no-logada al núvol» de
  [weekly_reingest.ps1](../scripts/weekly_reingest.ps1): **tot pot anar a
  GitHub Actions**, sense PC encès ni sessió que caduca.

**Dins**
- Un `http.py` compartit amb `httpx`: caché a disc, límit de ritme i
  reintents. `fcb_opens` ja en té un ([scraper/http.py](../src/fcb_opens/scraper/http.py));
  serveix per als dos.
- Un parser genèric de taules Bootstrap: `taula(html, i) -> list[dict]` amb les
  claus del `<thead>`. Amb això i quatre adaptadors es cobreix gairebé tot el
  que avui són 1.285 + 4.695 línies de parsing a mida.

**Val la pena unificar `fcbillar` i `fcb_opens` alhora.** Ara mateix són dos
paquets, dues BD i dos scrapers que llegeixen el mateix web i guarden les
mateixes coses amb noms diferents (`players` × 2, lliga × 2, rànquings × 2).
Reescriure dos scrapers en comptes d'un no té defensa.

---

## 6. Oportunitat: estructura i classificació del que ja tenim

Perfil de `data/fcbillar.db` avui — **55.658 partides, de 2012-09-08 a
2026-07-26, 14 temporades**:

### 6.1 La temporada és el forat gros

| Competició | Sense `temporada_id` | Total |
|---|---:|---:|
| INDIVIDUAL | **23.827** | 23.827 (100 %) |
| COPA | **1.411** | 1.411 (100 %) |
| LLIGA | 8.230 | 30.420 (27 %) |
| **Total** | **33.468** | **55.658 (60 %)** |

Sis de cada deu partides no es poden agrupar per temporada, tot i que **totes
tenen data**. La temporada federativa va de setembre a agost: és una regla
d'una línia. És la millora de classificació amb més retorn per esforç de tot el
document — desbloqueja «temporada a temporada» a fitxes, clubs i palmarès.

### 6.2 Columnes mortes i càrrega útil amagada al JSON

| Columna | Files amb valor |
|---|---|
| `ranking_entries.mitjana_particular` | **0** de 131.806 |
| `ranking_entries.partides` | **0** de 131.806 |
| `games.mitjana1` / `mitjana2` | **0** de 55.658 |
| `ranking_entries.extras_json` | **131.806** de 131.806 |
| `games.extras_json` | **55.658** de 55.658 |

Les columnes de debò són buides i el 100 % de les files porten `extras_json`
amb l'estructura **sempre igual**: `mitjana_contraris`, `rang`, `caramboles`,
`entrades`, `punts`, `punts_totals`, `definitiva`. No són extres: són les
dades. Cal pujar-les a columnes (indexables, consultables, tipades) i esborrar
les tres columnes mortes.

### 6.3 Altres buits mesurats

| Buit | Xifra | Font per omplir-lo |
|---|---|---|
| Jugadors sense club | **877 / 1.534 (57 %)** | `lliga_player_clubs` (12.627 files, ja ingerides) + `lligues/inscripcions/{lliga}` |
| Torneigs sense modalitat | **41 / 392** | Nom del torneig + `torneig_naming` |
| Partides de lliga sense encontre | ~2.600 | Bloquejat pel 500 |
| `lliga_pending_partides` | **2.464** | ~~Bloquejat pel 500~~ — i no era cap endarreriment: vegeu sota |
| Partides d'individual sense torneig | 472 | `link-individuals` |
| Clubs sense contacte | 57 clubs | Llistat WP nou (telèfon, correu, adreça, web) |

### 6.4 Duplicacions estructurals a resoldre

- **Dues bases de dades** amb les mateixes entitats: `players` (1.534 / 762),
  lliga (`encontres_lliga` 7.719 / `league_encontres` 659), rànquings
  (`rankings` 584 / `monthly_rankings` 10). La segona font
  (`/ca/rankings/s/1/Carambola/…`) ja no existeix, o sigui que la decisió ve
  donada: **`fcb_opens` ha de llegir els rànquings de `fcbillar`**.
- **57 clubs i 222 àlies** per a 39 clubs oficials. La resolució a tres nivells
  funciona, però amb el llistat nou (i les inscripcions per equip) es pot
  consolidar i reduir molt la taula d'àlies.
- Els punts 6-9 i 17 de la [Part D del mapa funcional](mapa-funcional.md)
  (projecció calculada dues vegades, tipus de torneig deduït en tres llocs,
  `/clubs` agrupant per nom, ids de temporada fixats al codi) segueixen oberts
  i toquen exactament el mateix codi que ara reescriurem.

---

## 7. Pla proposat

### Fase 0 — Aturar l'hemorràgia *(mig dia)*
1. Desactivar la tasca programada i el workflow diari: ara mateix fallen cada
   dia i omplen els logs d'error.
2. Congelar una còpia de `data/fcbillar.db` i `data/fcb_opens.db` com a
   referència de «l'últim estat bo».
3. Anotar el 500 de `lligues/partides` i preparar l'avís a la federació.

### Fase 1 — Tornar a ingerir el que és públic i estable *(fet, tret del punt 8)*
4. `config.py`: `intranet_url` + `web_url`, sense `www`.
5. `http.py` compartit amb `httpx` (caché, ritme, reintents) i **retirada de
   Playwright, `auth.py` i `url_builder.py`**.
6. Parser genèric de taules Bootstrap + adaptadors per rànquing, partides,
   lliga, individuals i copa.
7. Reconnectar `pipeline.py` a les URLs noves (§2) i comprovar contra el
   rànquing 124, que ja tenim ingerit: **la reingesta ha de sortir idèntica**.
   És la prova de regressió que ens regala la deduplicació per `id_natural`.
8. Portar la ingesta sencera a GitHub Actions: ja no hi ha res que necessiti el
   PC de casa. **Pendent.**
8b. Tornar a ingerir el rànquing vigent cada setmana mentre ho sigui, no només
   el dia que apareix (§4.1). **Pendent.**

### Fase 2 — Fonts noves i fonts perdudes
9. Llistat de clubs des del WordPress, amb els camps de contacte nous.
10. Descobriment de documents pel sitemap WPFD (calendari, rànquings d'opens,
    reglaments) i arreglar `calendari_fed.descobreix_fcb`.
11. Decidir què fem amb la **classificació final d'individuals**: o la calculem
    nosaltres a partir de grups i eliminatòries, o la llegim dels PDF de
    rànquing del WPFD. **Fet** (§2.7): la calculem, que ens fa independents.
12. Aprofitar `lligues/inscripcions/{lliga}` per a la relació club → equip →
    jugador de la temporada nova. **Fet** (§2.6): `fcbillar ingest-inscrits-lliga`
    → `lliga_inscrits`.

### Fase 3 — Classificació del que ja tenim *(independent de la Fase 1; es pot fer en paral·lel)*
13. Derivar `temporada_id` de la data per a les 33.468 partides que no en tenen.
14. Pujar `extras_json` a columnes i esborrar les tres columnes 100 % nul·les.
15. Propagar el club als 877 jugadors que no en tenen.
16. Completar la modalitat dels 41 torneigs que no en tenen.
17. Unificar `fcbillar` i `fcb_opens` en un sol model de dades.

### Fase 4 — Quan comenci la temporada (a partir del 14 de setembre)
18. Reprovar el detall d'encontre de lliga. **Fet** (§2.8): funciona per a totes
    les temporades, i el parser s'ha refet contra la taula de debò. La lliga 36
    s'ha reingerit sencera.

    Del comptador de 2.464 a `lliga_pending_partides` se n'havia tret una
    conclusió falsa. **No és un endarreriment**: aquella taula és un **mirall** de
    les partides que les pàgines de lliga donen com a jugades, i la reingesta la
    reescriu sencera (DELETE + INSERT per encontre). Qui decideix què encara és
    pendent és `publish_pending_games`, que la compara amb `games` per signatura
    al moment de publicar. O sigui que el número no ha de baixar amb la
    reingesta, i de fet puja: passa de 2.464 a 2.492 perquè ara se'n llegeixen
    totes.

    I mesurat després de reingerir-la, **la lliga 36 no li faltava res**: les
    2.493 partides ja tenien la sèrie major, i 2.457 l'àrbitre i l'assistència.
    És lògic i no s'havia pensat: la temporada 2025-26 es va jugar i ingerir
    mentre el web ANTIC encara funcionava, i aquell sí que donava el detall
    d'encontre. El 500 va començar a finals d'agost de 2026, quan aquella
    temporada ja estava acabada, i per tant no li va poder prendre res.

    O sigui que **la reingesta de la 36 no calia**: no arregla cap buit, només
    reescriu el que ja hi havia (els `COALESCE` de `enrich_game_by_signature`
    protegeixen l'àrbitre i l'assistència, que el web nou ja no dona). El que el
    500 sí que va bloquejar és la temporada **2026-27**, que és la que començava
    quan es va trencar.

    Val la pena dir-ho perquè el número 2.464 va fer pensar en un endarreriment
    de mesos que no existia, i la feina que hi ha darrere d'aquesta xifra és una
    lectura mal feta d'un comptador, no una pèrdua de dades.
19. Ingerir les lligues 38 i 39 i els torneigs 216 i 217. **Fet**: la 38 dona 672
    encontres (7 jugats, 665 de calendari) i la 39 ja publica els seus 328
    inscrits; dels individuals, els quatre de la temporada, amb la classificació
    de cada grup (§2.9).
20. Confirmar les subrutes de copa quan la federació obri l'edició nova.
    **Pendent**: el llistat de copa continua buit.

### Fase 5 — El que ha obert la temporada en joc
21. **Ja no fa falta el PDF del calendari per saber els enfrontaments** (§2.8b).
    `lliga_calendari` es queda perquè arriba abans, però quan les dues fonts hi
    són mana la competició. Cal repassar qui llegeix `lliga_calendari` —aquí i a
    NouProjecte— i deixar-hi la competició com a font principal.
22. Publicar el rànquing de fase al web (`open_fases`, `open_fase_ranquing`) a la
    pàgina de campionats, que és el que respon «m'he classificat?».
23. Fer servir `afiliacions` al lloc de `players.club_id` per a la temporada en
    curs a tot el que ensenya «el club de» algú.

---

## 8. Pendents de verificar

- ~~El detall d'encontre de lliga (500).~~ **Resolt** (§2.8). El que s'ha perdut
  per sempre és l'àrbitre i l'assistència per partida: el web antic els donava i
  el nou no. L'única font que queda és el panell de jugador logat (§9), i només
  per a un jugador.
- **El club de l'individual d'una modalitat que no sigui tres bandes.** Els PDF de
  sorteig (§2.10) existeixen per categoria del gestor de fitxers, i de moment
  només s'ha vist `individuals-tres-bandes`. Quan la federació pengi el sorteig
  del quadre 47/2 (torneig 218) caldrà comprovar que la categoria s'hi diu igual.
- Les subrutes de copa amb una edició en joc (l'edició 7 es comporta bé, però
  està tancada).
- Si la federació manté una còpia dels PDF de `/media/**` en algun lloc, o si
  s'han perdut definitivament.

---

## 9. Què hi ha al panell de jugador logat

Explorat el 2026-08-30 amb `scripts/explora_jugador.py`, que obre un navegador,
espera que resolguis el captcha i recorre el panell. **Les pàgines que en surten
no es commiten**: porten el número de llicència federativa i l'historial de
partides de qui hi entra, i el repositori és públic.

| Secció | Què hi ha | Ens serveix? |
|---|---|---|
| `/jugador/rankings/**` | Les mateixes pàgines que la part pública, columna per columna | No: ja les tenim |
| `/jugador/perfil` | **Número de llicència federativa**, tipus i validesa | Sí — és el codi federatiu real que el README dona per no disponible |
| `/jugador/lligues/partides` | «Les meves últimes partides de lliga» | Sí — vegeu sota |
| `/jugador/copa/partides` | Igual, per a la copa | Sí |
| `/jugador/individuals/partides-fasegrups` · `-eliminatories` | Igual, per als individuals | Sí |
| `/jugador/dashboard` | Resum en targetes, sense taules | No |

Les quatre pàgines de partides tenen **més camps que res del que és públic**:

```
Data | Local SM/Caramboles/Punts | Visitant SM/Caramboles/Punts |
Entrades | Àrbitre | Assistència | Modalitat | Observacions
```

La taula pública de partides d'un rànquing només dona data, punts, caramboles i
entrades. Aquí hi ha a més **sèrie major, àrbitre, assistència i modalitat** —
exactament els camps que ens dona el detall d'encontre de lliga que ara retorna
500. **És una solució de recanvi parcial per al 500**, però només per a un
jugador: són «les meves» partides, i només les últimes (26 de lliga, 12 de copa,
28 de fase de grups). No escala al club sencer ni substitueix l'endpoint trencat.
