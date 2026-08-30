# Fixtures

Dos webs, dos directoris.

## `nou/` — el web d'ara

Captures del **2026-08-30**, una per cada mena de pàgina que sabem llegir. Les
fa `scripts/captura_fixtures_web_nou.py`, i són les que fan servir els tests.

Dues excepcions:

- `lligues_partides_RECONSTRUIT_*.html` no és una captura: el detall d'encontre
  de lliga retorna HTTP 500 des del canvi de web, i no hi ha cap pàgina real per
  copiar. Les dades són de debò (surten de la captura antiga del mateix
  encontre) però el marcatge és el que fa servir la resta del portal. Quan la
  federació ho arregli, captura-la de veritat i substitueix el fitxer.
- `jugador/` no hi és i no hi ha de ser: el panell logat porta el número de
  llicència federativa i l'historial de partides de qui hi entra, i aquest
  repositori és públic. `scripts/explora_jugador.py` les desa allà, i el
  `.gitignore` les atura.

## Arrel — el web anterior

Captures del portal que la federació va tancar l'agost de 2026, quan tot penjava
de `www.fcbillar.cat/ca/...` amb una graella de `div`s en comptes de taules.
**Cap test les fa servir**: es guarden perquè són l'únic testimoni que queda
d'aquell marcatge, i perquè hi ha HTML antic arxivat que algun dia potser
voldrem tornar a llegir.

Si mai molesten, es poden esborrar sense por: el git les recorda.
