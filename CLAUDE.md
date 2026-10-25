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

<!-- antislop:start -->
## antislop

Per a feina d'interfície, textos, accessibilitat, disposició mòbil o comentaris
de codi, carrega la skill `antislop` (el nucli) i després la del tema:

- Interfície i aspecte visual: `antislop-ui`
- Textos i redacció: `antislop-copywriting`
- Persones (contrast, teclat, focus, estats): `antislop-human`
- Mòbil i disposició adaptable: `antislop-layoutmobile`
- Comentaris de codi: `antislop-code`

**Mode en aquest projecte: `during`**, triat per l'usuari el 2026-10-25 (després
d'una auditoria inicial del que ja existia). Compta com a instrucció explícita per
a cada sessió; si l'usuari en tria un altre durant la sessió, mana el de la sessió.
Anuncia `antislop active: during (instrucció del projecte).` una sola vegada, abans
de la primera edició.

La direcció de disseny (R-37) no és en cap `DESIGN.md`: si una tasca d'interfície
la necessita i no hi és, pregunta-la abans de construir.

Per actualitzar-la: `npx skills update -g`.
<!-- antislop:end -->
