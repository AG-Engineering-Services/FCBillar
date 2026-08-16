# FCBillar

Scraper i base de dades local per seguir els jugadors del club i altres jugadors
d'interes als campionats de carambola de la Federacio Catalana de Billar.

## Regles

Aquest projecte segueix les [regles d'AGenginyeria](../ag-standards/REGLES.md).
En cas de conflicte, les regles manen.

## Stack

Python amb `pyproject.toml` a `api/`, frontend Svelte, versio d'escriptori i
documentacio. CI a GitHub Actions.

## Com s'executa

```bash
uv sync
# consulta docs/ per als comandaments d'ingesta i publicacio
```

## Com es prova

```bash
pytest tests/
```

## Estat

Actiu. Migrat a Neon (vegeu `MIGRACIO-NEON.md`). Es un **actiu de dades**:
alimenta NouProjecte amb fitxes i ranquings federatius.
