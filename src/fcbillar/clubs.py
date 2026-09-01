"""Un club, un nom.

A la base de dades hi ha 57 clubs per als 39 que hi ha de debò. No és brutícia
acumulada: la federació escriu el mateix club diferent a cada document, i cada
pàgina que ingerim en crea la seva versió. El de Molins de Rei és «SB FOMENT
MOLINS» al calendari de lliga i «S.B.F.MOLINS» al llistat oficial; el de Sant
Adrià és «SANT ADRIÀ» a les classificacions i «C.B.SANT ADRIÀ» al cens.

Mentre no es resolgui, qualsevol comparació de clubs dona soroll: confrontant el
club de cada jugador al campionat individual amb el que teníem sortien 40
diferències, i tres quartes parts no eren fitxatges sinó el mateix club dues
vegades.

## Com s'ha comprovat que són el mateix

No per semblança del nom, que és el que fa equivocar. De les nou parelles:

- Set tenen el nom nou **buit** —zero jugadors, zero equips—: són les fitxes que
  es van crear en importar el cens oficial i no s'hi ha enganxat mai res. Unir
  un registre buit amb un de ple no pot perdre res.
- **Coral Colón** i **Sant Feliu de Codines** tenien tots dos registres amb
  dades i semblaven dos clubs. Mirant a quina lliga juguen es veu que no: un
  registre porta l'equip de la lliga de Tres Bandes (36) i l'altre el de la de
  4 Modalitats (37), i mai coincideixen a la mateixa. És el mateix club amb
  l'equip de cada lliga sota el nom que li dona la pàgina d'aquella lliga.

## El que NO s'unifica

Vuit clubs de la base de dades no surten al cens oficial i es queden com estan:
són d'altres temporades —Montmeló, Diamond Barcelona, Casino Olotí, Dany-Ells,
L'Amistat, La Colmena, Mollerussa— i el **B.C.Olesa**, que és ben viu i juga a
divisió d'Honor però que la federació no té publicat al seu llistat.

I dos que no són clubs: «FEDERACIO CATALANA DE BILLAR», que surt com a
organitzadora, i «INDEPENDENT», que són els jugadors amb llicència pròpia.
"""

from __future__ import annotations

import re
import unicodedata

#: Nom antic → nom del cens oficial. La clau es compara normalitzada, o sigui
#: que els accents, els punts i els espais no compten.
ALIES: dict[str, str] = {
    "B. EL MASNOU": "BILLAR EL MASNOU",
    "B.C.SANT FELIU DE CODINES": "C.B.SANT FELIU",
    "C.B. CANET": "C.B.CANET DE MAR",
    "CASAL DE CERVERA": "S.E.CASAL CERVERA",
    "CORAL COLÓN": "S.B.CORAL COLÓN",
    "MATADEPERA": "C.B.MATADEPERA",
    "PUNT D'ATAC": "C.B.PUNT D'ATAC",
    "SANT ADRIÀ": "C.B.SANT ADRIÀ",
    "SB FOMENT MOLINS": "S.B.F.MOLINS",
}

#: No són clubs, encara que ocupin una fila a la taula.
NO_SON_CLUBS = frozenset({"FEDERACIO CATALANA DE BILLAR", "INDEPENDENT"})


def normalitza(nom: str) -> str:
    """'S.B. Coral Colón' -> 'SBCORALCOLON'."""
    s = unicodedata.normalize("NFKD", (nom or "").upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", s)


_ALIES_NORM = {normalitza(k): v for k, v in ALIES.items()}


def canonic(nom: str) -> str:
    """El nom oficial d'un club, sigui quin sigui el que ens n'hagi arribat.

    Els que no coneixem es tornen tal com vénen: val més un nom sense unificar
    que unificar-lo amb qui no toca.
    """
    return _ALIES_NORM.get(normalitza(nom), nom)


def mateix_club(a: str, b: str) -> bool:
    """Si dos noms són el mateix club."""
    return normalitza(canonic(a)) == normalitza(canonic(b))


def es_club(nom: str) -> bool:
    """Si això és un club i no la federació ni un jugador independent."""
    return normalitza(nom) not in {normalitza(x) for x in NO_SON_CLUBS}
