# FCBillar

Scraper i base de dades local per fer seguiment dels jugadors del club i d'altres jugadors d'interès en els campionats de caràmbola de la **Federació Catalana de Billar** (https://www.fcbillar.cat/).

## Què fa

- Es connecta a la intranet de jugador amb les teves credencials federatives.
- Descobreix els rànquings mensuals per modalitat (lliure, banda, tres bandes, quadre, etc.).
- Descarrega les partides que conformen cada rànquing per a cada jugador i les dedupliquica (les partides apareixen a tots dos jugadors i en més d'un rànquing per la finestra lliscant de 10-15 partides).
- Persisteix-ho tot en una BD SQLite local per consulta amb SQL/Pandas/notebooks.
- Gestiona els dos formats d'URL de rànquings (canvi recent: `data` → `datahome`).

## Requisits

- Python 3.12+
- uv (gestor de paquets/projecte)
- Credencials d'accés a la intranet de jugador de fcbillar.cat

## Instal·lació

```powershell
uv sync
uv run playwright install chromium
Copy-Item .env.example .env
# edita .env i posa FCB_USER / FCB_PASS
```

## Ús bàsic

```powershell
# Verifica que el login funciona i desa la sessió (resol captcha manualment)
uv run fcbillar login

# Crea/actualitza l'esquema de la BD (seedeja modalitats)
uv run fcbillar init-db

# Sincronitza: detecta i ingest rànquings nous publicats a la home
uv run fcbillar sync

# Ingest del rànquing actual d'una modalitat + partides dels top N jugadors
#   modalitats: 1=Tres bandes, 2=Lliure, 3=Quadre 47/2, 4=Banda, 6=Quadre 71/2
uv run fcbillar backfill 1 --top 20

# Mateix però només pels jugadors marcats com a seguits
uv run fcbillar backfill 1 --only-followed

# Marca/desmarca jugadors d'interès (pel seu fcb_id intern del portal)
uv run fcbillar follow 566
uv run fcbillar follow 566 --off

# Ingest puntual d'un rànquing concret
uv run fcbillar ingest-ranking 121 2

# Ingest puntual de les partides d'un jugador en un rànquing
uv run fcbillar ingest-partides 121 2 566

# Estat de la BD
uv run fcbillar status
```

## Identificadors

El portal exposa només un **ID intern numèric** per jugador (`fcb_id`, ex. "566"),
no el codi federatiu real. És aquest id el que apareix a les URLs `partideshome/.../.../{id}`.
Si en algun moment volem el codi federatiu real, s'haurà d'extreure del perfil
individual i afegir com a columna addicional.

## Estructura

```text
src/fcbillar/
├── config.py         # Settings (Pydantic)
├── auth.py           # Login intranet (polling estable del form)
├── scraper/
│   ├── client.py     # Playwright + caché + rate limit
│   ├── url_builder.py # URLs de rànquing (formats 'data' / 'datahome')
│   └── parsers.py    # parse_ranking, parse_partides_jugador, parse_home, parse_historial
├── db/               # schema.sql + migrations + repository (upserts idempotents)
├── models.py         # Dataclasses (Player, Game amb id_natural per dedup, ...)
├── pipeline.py       # ingest_ranking, ingest_partides, sync, backfill
└── cli.py            # CLI Typer
```

## Notes

Projecte per a ús personal de l'usuari (federat). No el feu servir per a recol·lecció massiva de dades ni distribuir-les sense permís de la federació.
