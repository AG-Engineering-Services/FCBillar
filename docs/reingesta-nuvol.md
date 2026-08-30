# Reingesta al núvol (GitHub Actions + Cloudflare R2)

La reingesta setmanal de FCBillar ja **no depèn del PC**. Corre a GitHub Actions
([.github/workflows/reingest.yml](../.github/workflows/reingest.yml)), baixa l'estat
canònic de Cloudflare R2, incorpora les novetats de la federació i publica a Supabase.

Des del canvi de web de la federació (agost de 2026) **ja no hi ha res lligat al
PC**: el login amb captcha, que era l'última cosa que hi quedava, ha deixat de
caldre perquè rànquings i partides són públics. Vegeu
[`canvi-web-fcb-2026.md`](canvi-web-fcb-2026.md). L'únic ús que li queda al PC
són les **edicions curades** opcionals de la base de dades.

## Arquitectura

```
   PC (opcional)                  Cloudflare R2 (canònic)            GitHub Actions
 ┌────────────────┐   push       ┌──────────────────────┐   pull   ┌────────────────┐
 │ edicions BD    │ ───────────▶ │ fcbillar.db (169MB)  │ ───────▶ │ reingesta      │
 │                │ ◀─────────── │ fcb_opens.db         │ ◀─────── │ publish-cloud  │
 └────────────────┘   pull       │ generation           │   push   └───────┬────────┘
                                  └──────────────────────┘                  │ publish
                                                                            ▼
                                                                       Neon → Vercel (web)
```

- **R2** guarda la còpia **canònica** de les dues bases de dades. S'hi tria R2
  perquè no cobra egress i aguanta fitxers grans.
- El **botó "↻ Reingesta"** del PWA encua una fila a `fcbillar.reingest_requests`;
  [reingest-dispatch.yml](../.github/workflows/reingest-dispatch.yml) la veu (cada 15
  min) i dispara `reingest.yml`. Substitueix el watcher local.
- Ja no hi ha cap pas que depengui d'una sessió, així que `cloud_status.session_ok`
  és sempre cert i el banner de «sessió caducada» del PWA no s'encén mai. La
  columna es manté perquè el web la llegeix.

## Posada en marxa (un sol cop)

### 1. Cloudflare R2
1. Crea un **bucket R2** privat, p.ex. `fcb-state`.
2. Crea un **API Token** de R2 amb *Object Read & Write* sobre aquell bucket.
   Anota `Account ID`, `Access Key ID` i `Secret Access Key`.

### 2. Secrets de GitHub (Settings → Secrets and variables → Actions)
Ja existents: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`. Afegeix:
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`
- `GH_DISPATCH_PAT` — PAT **fine-grained**, només aquest repo, permís
  **Actions: Read and write** (el `GITHUB_TOKEN` no pot disparar altres workflows).

### 3. `.env` local (PC)
Afegeix-hi els mateixos `R2_*` perquè `fcbillar state push/pull` funcioni des de casa.

### 4. Migració Supabase
Aplica [supabase/migrations/0013_fcbillar_cloud_status.sql](../supabase/migrations/0013_fcbillar_cloud_status.sql)
(taula d'estat per al banner del PWA).

### 5. Sembra l'estat canònic a R2 (des del PC)
```powershell
uv run fcbillar state push       # puja les dues BD a R2
uv run fcbillar state status     # comprova generació i mides
```

### 6. Primera prova al núvol
Llança `reingest.yml` a mà (Actions → Reingesta (núvol) → Run workflow) amb
`force=true`. Verifica: baixa ~182MB, els passos d'ingesta, publicació,
repuja l'estat i `cloud_status` actualitzat. Comprova que el PWA mostra dades fresques.

### 7. Cutover
Després d'1–2 execucions **cron** correctes, **desactiva** la tasca de Windows:
```powershell
Disable-ScheduledTask -TaskName "FCBillar - Reingesta setmanal"
```
([scripts/weekly_reingest.ps1](../scripts/weekly_reingest.ps1) queda com a fallback
local manual; en acabar puja l'estat a R2 per mantenir el núvol canònic.)

## Operativa habitual

| Situació | Acció |
|----------|-------|
| Reingesta setmanal | Automàtica (cron dilluns 02:00 UTC). Res a fer. |
| Vull refrescar ara | Botó "↻ Reingesta" al PWA, o Run workflow manual. |
| Banner "sessió caducada" | No hi hauria de sortir mai: ja no hi ha sessió. Si surt, és una fila antiga a `cloud_status`. |
| Edició curada de la BD | `state pull` → editar al desktop → `state push --check-generation`. |

## Detalls

- **Guardó de divergència:** un comptador `generation` a R2. `state pull` el desa a
  `data/.state_gen`; `state push --check-generation` es nega si el núvol ha avançat
  (cal `pull` primer o `--force`). El job del núvol queda serialitzat per la
  `concurrency: { group: reingest, cancel-in-progress: false }`.
- **`session-check` ja no existeix**: era la comanda que comprovava si la sessió
  federativa seguia viva. Codis que retornava, per si els trobeu a scripts antics:
  0 = vàlida · 2 = sense sessió · 3 = caducada ·
  1 = error transitori (no marca la sessió com a caducada).
- **Aturada d'estiu:** el job s'omet de l'1 al 24 d'agost (UTC) tret de `force=true`.
