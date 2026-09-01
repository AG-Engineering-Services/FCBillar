"""Quan juga cada jugador el campionat individual, segons la seva divisió.

Dues fonts que fins ara no es parlaven:

- El PDF de divisions (`divisions_individual`) diu **a quina divisió** juga
  cadascú aquesta temporada.
- El calendari esportiu de la FCB (`calendari_events`) diu **quin cap de setmana**
  es juga cada fase de cada divisió.

Creuant-les surt el que li interessa al jugador: quan li toca a ell. Un de 6a
divisió comença al febrer i un de 1a al setembre, i això no ho diu cap dels dos
documents per separat.

## Les fases

La federació les escriu al calendari amb el nom sencer dins d'una cel·la
setmanal que pot portar-ne unes quantes, separades per punt volat:

    «Pre-Prèvia 3 Bandes 1ª Divisió · Prèvia 3 Bandes Div. Honor · …»

I no les escriu sempre igual: «6ª Divisió» i «6ª Div.», «FINAL 3 Bandes» i
«FINAL 3Bandes», «Pre- Pre-Prèvia» amb un espai pel mig. Per això el
reconeixement va per expressió regular tolerant i no per text exacte.

## Què hi va i què no

Només les fases **classificatòries**. Les juga tothom de la divisió, o sigui
que són una data segura per a qualsevol inscrit. La final no hi va: només hi
arriba qui passa les prèvies, i posar-la al calendari abans de saber-ho seria
prometre un dia que potser no arriba.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from fcbillar.divisions_individual import DIVISIONS, Inscrit

#: Les fases, de la primera a l'última.
FASES = ("Pre-pre-prèvia", "Pre-prèvia", "Prèvia", "Final")

#: Les que van al calendari: les que se sap del cert que es jugaran.
CLASSIFICATORIES = FASES[:-1]

FONT = "FCB-INDIVIDUAL"

_CAMPS_EVENT = (
    "font, temporada, setmana, disciplina, ambit, grup, tipus, data_inici, data_fi, "
    "titol, seu, dissabte, diumenge, col_span, raw"
)

# «Pre- Pre-Prèvia 3 B. 6ª Divisió», «FINAL 3Bandes Div. Honor», «Prèvia 3
# Bandes 5ª Divisió»… El que canvia és l'espaiat i l'abreujament; l'estructura
# és sempre fase + modalitat + divisió.
_RE_FASE = re.compile(
    r"^(?P<fase>pre-\s*pre-prèvia|pre-prèvia|prèvia|final)\s+"
    r"3\s*b(?:andes)?\.?\s+"
    r"(?:div\.?\s*)?(?P<divisio>honor|\d+[ªº])",
    re.IGNORECASE,
)

_FASE_CANONICA = {
    "prepreprevia": "Pre-pre-prèvia",
    "preprevia": "Pre-prèvia",
    "previa": "Prèvia",
    "final": "Final",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s)


@dataclass(frozen=True)
class Fase:
    """Una fase del campionat en una divisió, amb el cap de setmana que es juga."""

    divisio: str
    fase: str
    data_inici: date
    data_fi: date

    @property
    def ordre(self) -> int:
        return FASES.index(self.fase)


def fases_del_calendari(conn, temporada: str) -> dict[str, list[Fase]]:
    """Les fases de cada divisió, tretes del calendari esportiu ja ingerit.

    Una cel·la setmanal pot portar més d'una competició; es parteix pel punt
    volat, que és com les separa la federació.
    """
    per_divisio: dict[str, list[Fase]] = {}
    files = conn.execute(
        "SELECT data_inici, data_fi, titol FROM calendari_events "
        "WHERE temporada = ? AND font = 'FCB'",
        (temporada,),
    ).fetchall()

    for data_inici, data_fi, titol in files:
        for tros in str(titol).split("·"):
            m = _RE_FASE.match(tros.strip())
            if m is None:
                continue
            fase = _FASE_CANONICA.get(_norm(m.group("fase")))
            if fase is None:
                continue
            divisio = m.group("divisio").replace("º", "ª")
            divisio = "Honor" if divisio.lower() == "honor" else divisio
            per_divisio.setdefault(divisio, []).append(
                Fase(
                    divisio=divisio,
                    fase=fase,
                    data_inici=date.fromisoformat(data_inici),
                    data_fi=date.fromisoformat(data_fi),
                )
            )

    for fases in per_divisio.values():
        fases.sort(key=lambda f: (f.data_inici, f.ordre))
    return per_divisio


def _dilluns(d: date) -> date:
    from datetime import timedelta

    return d - timedelta(days=d.weekday())


@dataclass(frozen=True)
class Cita:
    """Un jugador, una fase i el cap de setmana que li toca."""

    inscrit: Inscrit
    fase: Fase


def cites(inscrits: list[Inscrit], per_divisio: dict[str, list[Fase]]) -> list[Cita]:
    """Les fases classificatòries que jugarà cadascú.

    La final no hi és: només hi arriba qui passa les prèvies, i fins llavors no
    és una data seva.
    """
    out: list[Cita] = []
    for i in inscrits:
        for f in per_divisio.get(i.divisio, []):
            if f.fase not in CLASSIFICATORIES:
                continue
            out.append(Cita(inscrit=i, fase=f))
    return sorted(
        out,
        key=lambda c: (c.fase.data_inici, c.inscrit.ordre_divisio, c.inscrit.posicio),
    )


def files_de_calendari(cites_: list[Cita], temporada: str) -> list[tuple]:
    """Les cites en la forma que demana `calendari_events`.

    El grup és el jugador: la clau primària de la taula és per setmana i grup, i
    així dos jugadors del club poden jugar el mateix cap de setmana sense
    trepitjar-se. De passada, la graella els agrupa per persona.
    """
    files: list[tuple] = []
    for c in cites_:
        i, f = c.inscrit, c.fase
        titol = f"{i.jugador} · {i.divisio} · {f.fase}"
        files.append(
            (
                FONT,
                temporada,
                _dilluns(f.data_inici).isoformat(),
                "carambola",
                "catala",
                f"Campionat de Catalunya 3 bandes · {i.jugador}",
                "individual",
                f.data_inici.isoformat(),
                f.data_fi.isoformat(),
                titol,
                None,
                None,
                None,
                1,
                f"{f.data_inici.isoformat()} {titol}",
            )
        )
    return files


def ingest(conn, cites_: list[Cita], temporada: str) -> int:
    """Desa les cites a `calendari_events`. Reemplaça les seves."""
    files = files_de_calendari(cites_, temporada)
    conn.execute(
        "DELETE FROM calendari_events WHERE font = ? AND temporada = ?", (FONT, temporada)
    )
    conn.executemany(
        f"INSERT INTO calendari_events ({_CAMPS_EVENT}) VALUES ({','.join('?' * 15)})",
        files,
    )
    conn.commit()
    return len(files)


def resum_per_divisio(per_divisio: dict[str, list[Fase]]) -> list[str]:
    """Una línia per divisió amb les seves fases, per ensenyar-ho a la consola."""
    out = []
    for divisio in DIVISIONS:
        fases = per_divisio.get(divisio)
        if not fases:
            continue
        detall = " · ".join(f"{f.fase} {f.data_inici:%d/%m}" for f in fases)
        out.append(f"{divisio:6s} {detall}")
    return out
