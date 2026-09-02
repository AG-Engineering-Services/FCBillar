"""Divisions del campionat individual, en PDF → jugador, divisió i club.

Cada temporada la federació publica a quina divisió juga cadascú el campionat
de Catalunya —Honor, 1ª… 6ª— i amb quin club hi va. És l'única font que diu
totes dues coses alhora, i arriba abans que el rànquing de la temporada nova:
el club que hi consta és el que tindrà la llicència aquest any, no el de l'any
passat.

## Com és el PDF

Una línia per jugador, amb els camps separats per espais:

```
Honor 1 MAS CANADELL, JOSEP Mª B.C.GRANOLLERS 1.6367 Definitiva
1ª    29 AMETLLER CONGOST, LLUIS C.B.BANYOLES  0.7778 Definitiva
```

El nom i el club porten tots dos espais, o sigui que no es poden separar
comptant camps. Es parteixen pel final: el club és el sufix més llarg que
coincideix amb un club del cens. La comparació és **normalitzada** perquè la
federació escriu el mateix club de maneres diferents segons el document —
«B.C.OLESA» i «BC OLESA», «S.B. LA GRAN PENYA» i «S.B.LA GRAN PENYA».

I la divisió s'escriu unes vegades amb ordinal femení i altres amb masculí
(«5ª» i «5º») dins del mateix fitxer.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

#: Ordre de les divisions, de més alta a més baixa.
DIVISIONS = ("Honor", "1ª", "2ª", "3ª", "4ª", "5ª", "6ª")

_RE_FILA = re.compile(r"^(Honor|\d+[ªº])\s+(\d+)\s+(.+?)\s+([\d.]+)\s+(Definitiva|Provisional)$")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", s)


@dataclass(frozen=True)
class Inscrit:
    """Un jugador amb la divisió que li toca aquesta temporada."""

    divisio: str  # 'Honor', '1ª'… '6ª'
    posicio: int  # ordre al rànquing de sortida
    jugador: str  # tal com l'escriu la federació: 'COGNOMS, NOM'
    club: str  # nom del club al cens
    mitjana: float
    definitiva: bool  # False = mitjana provisional, encara pot moure's

    @property
    def ordre_divisio(self) -> int:
        return DIVISIONS.index(self.divisio) if self.divisio in DIVISIONS else len(DIVISIONS)


def llegeix(pdf_path: str | Path, clubs: list[str]) -> tuple[list[Inscrit], list[str]]:
    """Llegeix el PDF de divisions.

    `clubs` és el cens amb què es parteix el nom del club del nom del jugador.
    Retorna els inscrits i les línies que no s'han pogut interpretar, que no
    s'amaguen: si la federació canvia el format, val més veure-ho.

    A la llista s'hi afegeixen els noms alternatius coneguts, i el club que en
    surt es torna sempre amb el nom del cens. No és cosmètic: el PDF escriu
    «S.B.LA UNIÓ CORAL» i el cens en diu «B.LA UNIÓ CORAL», i sense la variant el
    tall es fa pel nom curt i la «S.» sobrant se'n va al nom del jugador. Catorze
    jugadors del club van sortir com a «COGNOMS, NOM S.», que no casa amb ningú.
    """
    import pdfplumber

    from fcbillar.clubs import ALIES, canonic

    # Del més llarg al més curt: «C.B.SANT ADRIÀ» abans que «C.B.SANT», per no
    # deixar-nos mitja paraula dins del nom del jugador.
    cens = sorted(
        ({_norm(c): canonic(c) for c in [*clubs, *ALIES]}).items(),
        key=lambda kv: -len(kv[0]),
    )

    inscrits: list[Inscrit] = []
    rebutjades: list[str] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        linies = [
            ln for pg in pdf.pages for ln in (pg.extract_text() or "").splitlines() if ln.strip()
        ]

    for linia in linies:
        m = _RE_FILA.match(linia)
        if m is None:
            # Les capçaleres de pàgina no són errors.
            if not linia.startswith(("DIVISIONS", "3 BANDES", "TEMPORADA", "2026/", "Rnk")):
                rebutjades.append(linia)
            continue

        divisio, posicio, resta, mitjana, estat = m.groups()
        norm_resta = _norm(resta)
        parell = next(((n, c) for n, c in cens if norm_resta.endswith(n)), None)
        if parell is None:
            rebutjades.append(linia)
            continue

        norm_club, club = parell
        # El tall es fa sobre el text original, retallant tants caràcters com
        # calgui perquè el que quedi normalitzat sigui el nom del jugador.
        tall = len(resta)
        while tall > 0 and _norm(resta[:tall]) != norm_resta[: -len(norm_club)]:
            tall -= 1
        jugador = resta[:tall].strip(" ,")
        if not jugador:
            rebutjades.append(linia)
            continue

        inscrits.append(
            Inscrit(
                divisio=divisio.replace("º", "ª"),
                posicio=int(posicio),
                jugador=jugador,
                club=club,
                mitjana=float(mitjana),
                definitiva=estat == "Definitiva",
            )
        )

    return inscrits, rebutjades


def per_club(inscrits: list[Inscrit], club: str) -> list[Inscrit]:
    """Els inscrits d'un club, de la divisió més alta a la més baixa."""
    return sorted(
        (i for i in inscrits if _norm(club) in _norm(i.club)),
        key=lambda i: (i.ordre_divisio, i.posicio),
    )


class ResDesar(Exception):
    """No es desa el buit sobre el que ja hi ha."""


def desa(conn, inscrits: list[Inscrit], temporada: str) -> int:
    """Desa els inscrits a `inscrits_individual`, reemplaçant els de la temporada.

    El club es canonicalitza en desar-lo: el PDF fa servir els noms del cens
    oficial, però prou documents de la federació no ho fan i val més que la taula
    en tingui una sola versió.

    El reemplaçament és destructiu, o sigui que una llista buida s'enduria el que
    ja hi ha. Un PDF que ha canviat de format en dona una, i llavors el problema
    és el PDF, no les dades: val més plantar-se que buidar la taula en silenci.
    """
    from fcbillar.clubs import canonic

    if not inscrits:
        raise ResDesar(
            "Cap inscrit per desar. No esborro els que ja hi ha per posar-hi el buit: "
            "si el PDF no ha donat ningú, el problema és el PDF."
        )
    conn.execute("DELETE FROM inscrits_individual WHERE temporada = ?", (temporada,))
    conn.executemany(
        "INSERT INTO inscrits_individual "
        "(temporada, jugador, club, divisio, posicio, mitjana, definitiva) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                temporada,
                i.jugador,
                canonic(i.club),
                i.divisio,
                i.posicio,
                i.mitjana,
                int(i.definitiva),
            )
            for i in inscrits
        ],
    )
    conn.commit()
    return len(inscrits)


def traspassos(conn, temporada: str) -> list[tuple[str, str, str]]:
    """Qui ha canviat de club: (jugador, club d'abans, club d'ara).

    Compara el club que diu el PDF amb el que tenim fitxat a `players`. Els noms
    es comparen amb `clubs.mateix_club`, que és el que evita que un club escrit
    de dues maneres sembli un fitxatge: sense això, de 66 diferències només 30
    eren traspassos de debò.

    Qui no té club fitxat no hi surt: no sabem d'on ve, i dir que ve de «sense
    club» seria inventar-s'ho.
    """
    from fcbillar.clubs import mateix_club

    fitxat = {
        nom: club
        for nom, club in conn.execute(
            "SELECT p.nom, c.nom FROM players p LEFT JOIN clubs c ON c.id = p.club_id"
        )
    }
    canvis = []
    for jugador, club in conn.execute(
        "SELECT jugador, club FROM inscrits_individual WHERE temporada = ? ORDER BY jugador",
        (temporada,),
    ):
        abans = fitxat.get(jugador)
        if abans and not mateix_club(abans, club):
            canvis.append((jugador, abans, club))
    return canvis
