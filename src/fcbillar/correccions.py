"""Correccions a mà de dades que la federació ha introduït malament.

De tant en tant una acta es pica malament: una partida que va durar 32 entrades
hi surt amb 9. La ingesta ho porta tal com és allà, i d'allà va a les mitjanes,
a les partides destacades i als cartells: un 30 a 9 en 9 entrades és una mitjana
de 3,333 que no ha fet ningú.

Aquí s'hi apunta, a mà i una per una, la dada bona mentre la federació no
l'arregla. Viuen a `correccions/lliga_partides.csv`, al repositori, perquè
quedi escrit qui ho va dir i per què.

Tres regles, perquè una correcció no es converteixi en una mentida:

- **Només s'aplica si la dada de la federació és exactament la que es va veure
  malament** (`valor_federacio`). Si la federació la canvia, la correcció deixa
  d'aplicar-se sola: mana sempre el que digui ella després d'haver-ho tocat.
- **Si la federació ja diu el valor bo, s'avisa** que la correcció es pot
  esborrar.
- **Si no es troba la partida, s'avisa** i no es toca res.

Només corregeix el que es publica al núvol. La base local es queda amb el que
diu la federació.
"""

from __future__ import annotations

import csv
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

#: On viuen les correccions de les partides de lliga, des de l'arrel del repositori.
FITXER_LLIGA = Path("correccions") / "lliga_partides.csv"

#: Els camps d'una partida que es poden corregir.
CAMPS = ("entrades", "caramboles_local", "caramboles_visitant")

Progress = Callable[[str, str], None]


@dataclass(frozen=True)
class Correccio:
    encontre_id: int
    #: Un tros del nom d'un dels dos jugadors, per trobar la partida dins de
    #: l'encontre. L'ordre de les partides no és estable; el nom sí.
    jugador: str
    camp: str
    valor_federacio: int
    valor_correcte: int
    motiu: str
    #: El dia de la jornada, en ISO. Cal per corregir també les partides
    #: pendents, que no porten l'encontre: sense data no s'hi aplica.
    data: str = ""


def _net(text: str | None) -> str:
    sense = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in sense if unicodedata.category(c) != "Mn").upper().strip()


def llegeix(cami: str | Path = FITXER_LLIGA) -> list[Correccio]:
    """Les correccions del fitxer. Buit si no n'hi ha. Una fila mal escrita peta."""
    cami = Path(cami)
    if not cami.exists():
        return []
    out: list[Correccio] = []
    with open(cami, encoding="utf-8", newline="") as f:
        for i, fila in enumerate(csv.DictReader(f), start=2):
            camp = (fila.get("camp") or "").strip()
            if camp not in CAMPS:
                raise ValueError(f"{cami}:{i}: camp desconegut {camp!r}; ha de ser un de {CAMPS}.")
            jugador = (fila.get("jugador") or "").strip()
            if not jugador:
                raise ValueError(f"{cami}:{i}: falta el jugador.")
            out.append(
                Correccio(
                    encontre_id=int(fila["encontre_id"]),
                    jugador=jugador,
                    camp=camp,
                    valor_federacio=int(fila["valor_federacio"]),
                    valor_correcte=int(fila["valor_correcte"]),
                    motiu=(fila.get("motiu") or "").strip(),
                    data=(fila.get("data") or "").strip(),
                )
            )
    return out


def aplica_a_partides(
    files: list[dict], correccions: list[Correccio], prog: Progress | None = None
) -> int:
    """Aplica les correccions a les files de partides que s'estan a punt de publicar.

    Modifica `files` al lloc i torna quantes n'ha aplicat. Vegeu la capçalera per
    a quan una correcció NO s'aplica.
    """
    avisa: Progress = prog or (lambda _nivell, _missatge: None)
    aplicades = 0
    encontres = {f.get("encontre_id") for f in files}
    for c in correccions:
        # El mateix fitxer serveix per a la lliga de Tres Bandes i la de 4
        # Modalitats, que es publiquen per separat: un encontre que no és en
        # aquesta tanda és de l'altra lliga, no una correcció perduda.
        if c.encontre_id not in encontres:
            continue
        clau = _net(c.jugador)
        candidates = [
            f
            for f in files
            if f.get("encontre_id") == c.encontre_id
            and (clau in _net(f.get("jugador_local")) or clau in _net(f.get("jugador_visitant")))
        ]
        if len(candidates) != 1:
            avisa(
                "warn",
                f"correcció no aplicada: a l'encontre {c.encontre_id} hi ha "
                f"{len(candidates)} partides de «{c.jugador}» (n'hi ha d'haver una).",
            )
            continue
        fila = candidates[0]
        actual = fila.get(c.camp)
        if actual == c.valor_federacio:
            fila[c.camp] = c.valor_correcte
            aplicades += 1
            avisa(
                "info",
                f"correcció aplicada: encontre {c.encontre_id}, «{c.jugador}», {c.camp} "
                f"{c.valor_federacio} → {c.valor_correcte} ({c.motiu})",
            )
        elif actual == c.valor_correcte:
            avisa(
                "warn",
                f"correcció que ja no cal: la federació ja diu {c.camp}={c.valor_correcte} a "
                f"l'encontre {c.encontre_id} («{c.jugador}»). Es pot esborrar del fitxer.",
            )
        else:
            avisa(
                "warn",
                f"correcció no aplicada: a l'encontre {c.encontre_id} («{c.jugador}») la "
                f"federació ara diu {c.camp}={actual}, ni {c.valor_federacio} ni "
                f"{c.valor_correcte}. Mana la federació; reviseu la correcció.",
            )
    return aplicades


def aplica_a_pendents(
    files: list[dict], correccions: list[Correccio], prog: Progress | None = None
) -> int:
    """El mateix per a `pending_games`: la partida vista des de cada jugador.

    Aquestes files alimenten la fitxa i el rànquing provisional, i no porten
    l'encontre: una partida s'hi reconeix pel nom del jugador dins de la
    signatura, pel dia de la jornada i pel valor mal picat. Per això només s'hi
    apliquen les correccions d'`entrades` que porten `data` —les caramboles hi
    van per jugador i no per local i visitant— i només a les partides de lliga.

    La signatura no es toca: és la que casa la partida amb la de `games` el dia
    que la federació la compti al rànquing, i allà hi haurà el valor de l'acta.

    Aquí no s'avisa quan no es troba res: la partida deixa de ser pendent quan
    entra a `games`, i això és el final normal d'una correcció, no un error.
    """
    avisa: Progress = prog or (lambda _nivell, _missatge: None)
    aplicades = 0
    for c in correccions:
        if c.camp != "entrades" or not c.data:
            continue
        clau = _net(c.jugador).lower()
        for fila in files:
            if (
                fila.get("font") == "lliga"
                and fila.get("data") == c.data
                and fila.get("entrades") == c.valor_federacio
                and clau in (fila.get("signatura") or "")
            ):
                fila["entrades"] = c.valor_correcte
                aplicades += 1
    if aplicades:
        avisa("info", f"correccions aplicades a les partides pendents: {aplicades} files")
    return aplicades
