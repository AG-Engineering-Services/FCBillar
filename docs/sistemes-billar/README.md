# Sistemes de tres bandes

Catàleg i entrenador de 58 sistemes de càlcul de carambola a tres bandes. Les fonts són dues:

- El recull *Sistemas de billar* (José Lazo, 2010, i capítols d'altres autors, com Ricardo Duarte): 47 fitxes.
- Els PDF de l'Escola de billar del Club Billar València (pàgines «Pase bolas», «Bricol», «Efecto contrario»,
  «Rodadas y cabañas» i «Las 40 en 1»): 11 fitxes noves, i exemples afegits a fitxes del llibre.

Publicat com a artefacte: https://claude.ai/artifact/AE6YDfkVvfKcmPpBz3PN8w (privat).

## Què hi ha

| Fitxer | Què és |
|---|---|
| `index.html` | La pàgina: catàleg, exemples gràfics, entrenador per sistema, entrenament barrejat, famílies i coincidències, i simulador i entrenador del sistema Argüello. |
| `systems/*.json` | Una fitxa per sistema (font editable). |
| `systems.json` | Totes les fitxes juntes, generades per `eines/build.py`. La pàgina carrega aquest fitxer. |
| `families.json` | Famílies de sistemes que comparteixen numeració o fórmula, amb coincidències i diferències. |
| `eines/build.py` | Ajunta les fitxes i unifica el vocabulari (arribada, diamant, bricola), sense tocar les cites ni els identificadors. |
| `eines/relcheck.js` | Comprova que cada fórmula de l'entrenador genera preguntes vàlides. |
| `eines/coh1.py` | Comprova l'aritmètica dels exemples, les preguntes i les regles. |
| `eines/BRIEF.md`, `TRAINER.md`, `VLC.md` | El format de les fitxes i les instruccions amb què es van extreure. |

Els PDF originals no són al repositori.

## Com es fa servir

```bash
cd docs/sistemes-billar
python3 eines/build.py        # després d'editar systems/*.json
node eines/relcheck.js        # ha de dir "bad relations 0"
python3 eines/coh1.py         # cadenes d'operacions a part, no hauria de sortir res
python3 -m http.server 8000   # i obre http://localhost:8000
```

La pàgina necessita un servidor, perquè carrega `systems.json` i `families.json` amb `fetch`.

## Format d'una fitxa

Taula en vertical, mesurada en diamants: `x` de 0 (llarga esquerra) a 4 (llarga dreta) i `y` de 0 (curta de dalt) a
8 (curta de baix). Cada fitxa té:

- `numberings`: punts `{x, y, v}` de cada numeració.
- `examples`: exemples amb un `path` (bola jugadora i cada contacte en ordre) i les `balls`.
- `trainer.calc`: variables, valors d'entrada, relacions en expressions JavaScript, condicions i recorregut generat.
- `trainer.quiz`: preguntes tretes de la font.

El detall és a `eines/BRIEF.md` i `eines/TRAINER.md`.

## Límits

- Els recorreguts són lectures dels dibuixos, amb un error d'1 o 2 dècimes de diamant. Els que s'han reconstruït a
  partir dels valors porten `path_built`.
- Cada fitxa té un apartat `uncertain` amb el que la font no deixa clar, les errates trobades i les decisions
  preses. La pàgina el mostra com a «Punts dubtosos».
- Els PDF del Club Billar València no diuen l'autor. Les fitxes posen «PDF de Julio A», que és qui els va pujar.
