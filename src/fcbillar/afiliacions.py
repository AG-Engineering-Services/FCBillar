"""Amb quin club juga cadascú cada competició d'aquesta temporada.

## Per què no n'hi ha prou amb un club per jugador

Perquè un jugador no en té un: en té un per competició, i la federació ho
publica així.

- Es pot anar **fitxat a la lliga** per un club i jugar el **campionat
  individual** pel de sempre. A la prèvia d'Honor de 2026-27, PARERAS MÉNDEZ
  juga l'individual per GRANOLLERS i MORENO CORTÉS per LLEIDA, i no és el que
  diria cap plantilla.
- I es pot anar fitxat a la **lliga de tres bandes** per un club i a la de **4
  Modalitats** per un altre: són dues lligues, dues inscripcions i dos terminis.

`players.club_id` és una columna sola i per tant no pot dir res d'això: el que
hi ha escrit és el club d'on ve l'última cosa que hem ingerit. Es queda perquè hi
ha catorze temporades penjades d'ella, però per a la temporada en curs la font és
`afiliacions`.

## D'on surt cada cosa

| Competició | Font | Què hi diu |
|---|---|---|
| Lliga (una fila per lliga) | `lliga_inscrits`, de `lligues/participants/{lliga}/{club}` | el club i si hi ve fitxat |
| Campionat individual | `sorteig_fase`, dels PDF del sorteig de cada ronda | el club, sense marca de fitxatge |

El portal **no** publica el club de l'individual enlloc: ni a divisions, ni a
fases, ni a grups, ni a participants, i `individuals/inscripcions/216` del
campionat de tres bandes de 2026-27 està buida. L'única font és el PDF del
sorteig de cada fase, i per això `sorteig_fase` existeix.

## El fitxatge de la lliga: dues files, i totes dues volen dir alguna cosa

A `lliga_inscrits` qui ve d'un altre club surt **dues vegades**: a la llista del
seu club sense marca i a la del club que se l'endú amb `(Fitxatge)`. No és cap
error de la font. Però per a «amb quin club juga la lliga» la resposta és una:
**el club que el fitxa**. Aquí es resol així, i la fila de l'altre club es
descarta —sense oblidar-la, que és per això que `lliga_inscrits` es queda tal com
la publica la federació.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import unicodedata
from dataclasses import dataclass

log = logging.getLogger(__name__)

#: Les competicions que sap distingir. 'LLIGA' porta la modalitat de la lliga i
#: 'INDIVIDUAL' la del campionat, que no són la mateixa cosa.
LLIGA = "LLIGA"
INDIVIDUAL = "INDIVIDUAL"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", s)


@dataclass(frozen=True)
class Afiliacio:
    """Amb quin club juga un jugador una competició d'una temporada."""

    temporada: str
    competicio: str  # LLIGA | INDIVIDUAL
    modalitat: str  # 'Tres bandes', '4 Modalitats', 'Quadre 47/2'…
    jugador: str
    club: str
    fitxatge: bool
    font: str


def de_la_lliga(conn: sqlite3.Connection, temporada: str) -> tuple[list[Afiliacio], list[str]]:
    """Les afiliacions de lliga, de `lliga_inscrits`. Retorna (files, avisos).

    Una lliga per modalitat i un jugador per lliga: el club que el fitxa si hi ha
    fitxatge, i si no el seu. Dos clubs que el reclamen sense que cap fila porti
    la marca no es pot resoldre, i llavors no se'n desa cap: escollir-ne un a
    l'atzar seria inventar-se un fitxatge.
    """
    per_jugador: dict[tuple[int, str], list[sqlite3.Row]] = {}
    modalitats: dict[int, str] = {}
    for r in conn.execute(
        "SELECT lliga_id, lliga, modalitat, club, jugador, fitxatge FROM lliga_inscrits "
        "WHERE temporada = ? ORDER BY lliga_id, jugador, club",
        (temporada,),
    ):
        per_jugador.setdefault((r[0], _norm(r[4])), []).append(r)
        modalitats[r[0]] = r[2] or ""

    out: list[Afiliacio] = []
    avisos: list[str] = []
    for (lliga_id, _clau), files in sorted(per_jugador.items()):
        fitxatges = [f for f in files if f[5]]
        propis = [f for f in files if not f[5]]
        if len(fitxatges) > 1:
            avisos.append(
                f"lliga {lliga_id}: {files[0][4]} consta fitxat per "
                f"{len(fitxatges)} clubs ({', '.join(f[3] for f in fitxatges)}); no el deso"
            )
            continue
        if fitxatges:
            tria, fitxat = fitxatges[0], True
        elif len(propis) == 1:
            tria, fitxat = propis[0], False
        else:
            avisos.append(
                f"lliga {lliga_id}: {files[0][4]} surt a {len(propis)} clubs sense "
                f"cap marca de fitxatge ({', '.join(f[3] for f in propis)}); no el deso"
            )
            continue
        out.append(
            Afiliacio(
                temporada=temporada,
                competicio=LLIGA,
                modalitat=modalitats.get(lliga_id, ""),
                jugador=tria[4],
                club=tria[3],
                fitxatge=fitxat,
                font="lliga_inscrits",
            )
        )
    return out, avisos


def resol_club(repo, nom: str, cens: list[str]) -> str | None:
    """El nom del cens que correspon a com el PDF escriu un club.

    Primer el resolutor del repositori —exacte, normalitzat, àlies, i sense la
    lletra d'equip—, que és el que fa servir la ingesta de lliga i el que sap
    els casos que no es poden deduir del nom («CANET» → «C.B.CANET DE MAR»).

    I si no en surt res, per **sufix**: «GRANOLLERS» casa amb «B.C.GRANOLLERS»
    perquè aquell acaba amb aquest. Cal perquè el PDF els escriu curts i sense
    prefix, i el resolutor sol només se'n surt quan algú n'ha registrat l'àlies
    —a la base de dades de debò n'hi ha 222 registrats i per això hi funciona,
    però un club nou o una base de dades acabada de fer no en tenen cap.

    Si el sufix casa amb més d'un club, no es tria: el web té «BC OLESA» i
    «C.B.OLESA» com a dos clubs diferents, i endevinar quin és seria escriure una
    dada que ningú no podria comprovar després.
    """
    cid = repo.resolve_club_id_by_nom(nom)
    if cid is not None:
        fila = repo.conn.execute("SELECT nom FROM clubs WHERE id = ?", (cid,)).fetchone()
        if fila:
            return fila[0]
    clau = _norm(nom)
    candidats = sorted({c for c in cens if _norm(c).endswith(clau)})
    return candidats[0] if len(candidats) == 1 else None


def del_sorteig(
    repo, sorteig, temporada: str, modalitat: str
) -> tuple[list[Afiliacio], list[str]]:
    """Les afiliacions d'individual, d'un PDF de sorteig ja llegit.

    El club es canonicalitza amb `resol_club`: el PDF els escriu curts i sense
    prefix («GRANOLLERS», «SANT ADRIÀ», «CANET») i el cens els porta sencers.
    """
    out: list[Afiliacio] = []
    avisos: list[str] = []
    cens = [r[0] for r in repo.conn.execute("SELECT nom FROM clubs")]
    per_nom: dict[str, str | None] = {}
    for j in sorteig.jugadors:
        if j.club not in per_nom:
            per_nom[j.club] = resol_club(repo, j.club, cens)
        club = per_nom[j.club]
        if club is None:
            avisos.append(f"{sorteig.titol}: club «{j.club}» ({j.jugador}) no és al cens")
            continue
        out.append(
            Afiliacio(
                temporada=temporada,
                competicio=INDIVIDUAL,
                modalitat=modalitat,
                jugador=j.jugador,
                club=club,
                # El sorteig no marca els fitxatges: diu el club i prou.
                fitxatge=False,
                font="sorteig_fase",
            )
        )
    return out, avisos


def desa(conn: sqlite3.Connection, files: list[Afiliacio]) -> int:
    """Desa les afiliacions. Reemplaça les de cada (temporada, competició, modalitat).

    Es reemplaça per competició i no de cop: la ingesta de la lliga i la de
    l'individual van per camins diferents i s'executen per separat, i esborrar-ho
    tot deixaria l'altra meitat sense res fins que tornés a córrer.

    Una llista buida no esborra res: voldria dir que no hem sabut llegir la font,
    i substituir el que teníem per un silenci és pitjor que deixar-hi el que hi ha.
    """
    if not files:
        return 0
    claus = {(f.temporada, f.competicio, f.modalitat) for f in files}
    for temporada, competicio, modalitat in claus:
        conn.execute(
            "DELETE FROM afiliacions WHERE temporada = ? AND competicio = ? AND modalitat = ?",
            (temporada, competicio, modalitat),
        )
    conn.executemany(
        "INSERT OR REPLACE INTO afiliacions "
        "(temporada, competicio, modalitat, jugador, club, fitxatge, font) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (f.temporada, f.competicio, f.modalitat, f.jugador, f.club, int(f.fitxatge), f.font)
            for f in files
        ],
    )
    conn.commit()
    return len(files)


def canvia_de_club(conn: sqlite3.Connection, temporada: str) -> list[tuple[str, dict[str, str]]]:
    """Qui juga per clubs diferents segons la competició, i per quins.

    És la llista que interessa mirar: si surt buida, tothom juga tot amb el
    mateix club i la columna sola de `players` hauria fet el fet. Si no, cada
    fila és algú de qui la pregunta «de quin club és?» no té una sola resposta.
    """
    per_jugador: dict[str, dict[str, str]] = {}
    for r in conn.execute(
        "SELECT jugador, competicio, modalitat, club FROM afiliacions "
        "WHERE temporada = ? ORDER BY jugador, competicio, modalitat",
        (temporada,),
    ):
        etiqueta = f"{r[1]} {r[2]}".strip()
        per_jugador.setdefault(r[0], {})[etiqueta] = r[3]
    return [
        (jugador, clubs)
        for jugador, clubs in sorted(per_jugador.items())
        if len({_norm(c) for c in clubs.values()}) > 1
    ]
