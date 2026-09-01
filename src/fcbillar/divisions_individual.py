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

_RE_FILA = re.compile(
    r"^(Honor|\d+[ªº])\s+(\d+)\s+(.+?)\s+([\d.]+)\s+(Definitiva|Provisional)$"
)


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
    """
    import pdfplumber

    # Del més llarg al més curt: «C.B.SANT ADRIÀ» abans que «C.B.SANT», per no
    # deixar-nos mitja paraula dins del nom del jugador.
    cens = sorted(({_norm(c): c for c in clubs}).items(), key=lambda kv: -len(kv[0]))

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
