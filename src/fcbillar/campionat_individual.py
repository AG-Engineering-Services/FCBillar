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

Només la **primera fase** de cada divisió. És l'única data segura: la juga
tothom qui s'hi ha inscrit. A partir d'aquí cal classificar-se, i qui no passi
la pre-prèvia no jugarà la prèvia. Posar-hi les fases següents seria prometre
uns dies que potser no arriben.

Quina és la primera depèn de la divisió: a 6a és la pre-pre-prèvia, a 1a i 2a
la pre-prèvia, i a Honor —que no en té -— la prèvia mateixa.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from fcbillar.divisions_individual import DIVISIONS, Inscrit

#: Les fases, de la primera a l'última.
FASES = ("Pre-pre-prèvia", "Pre-prèvia", "Prèvia", "Final")

#: La final no és mai una data segura per a ningú abans de començar.
FINAL = "Final"

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
    #: Tal com la federació l'escriu al calendari: «Pre-Prèvia 3 Bandes 1ª
    #: Divisió». És la clau amb què la graella sap sota quin epígraf ha de
    #: penjar els nostres jugadors, i per això es desa sense tocar.
    text: str = ""

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
                    text=tros.strip(),
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
    """La fase per la qual cadascú comença, que és l'única data segura.

    Les que vénen després demanen haver passat l'anterior, i encara no se sap
    qui hi arribarà.
    """
    out: list[Cita] = []
    for i in inscrits:
        classificatories = [f for f in per_divisio.get(i.divisio, []) if f.fase != FINAL]
        if not classificatories:
            continue
        # Per ORDRE DE FASE, no per data. Qui hi entra ho fa per la pre-prèvia
        # encara que el calendari la posés després de la prèvia: primer s'ha de
        # classificar i després es juga, passi el que passi amb les dates. I ja
        # hem vist que la federació s'hi equivoca.
        out.append(Cita(inscrit=i, fase=min(classificatories, key=lambda f: f.ordre)))
    return sorted(
        out,
        key=lambda c: (c.fase.data_inici, c.inscrit.ordre_divisio, c.inscrit.posicio),
    )


def files_de_calendari(cites_: list[Cita], temporada: str) -> list[tuple]:
    """Les cites en la forma que demana `calendari_events`.

    Una fila per FASE, no per jugador, amb els nostres a dins. Amb una fila per
    jugador la graella els posava tots al mateix nivell que la competició i
    quedava una llista plana on no es veia qui juga què; així pengen de
    l'epígraf de la seva fase, que és on toca.

    A més, la clau primària de la taula és per setmana i grup: amb el jugador
    com a grup, dos que juguessin la mateixa fase no s'haurien trepitjat, però
    tampoc no s'haurien pogut agrupar. Amb la fase com a grup surt bé de totes
    dues maneres, perquè una divisió no té dues fases el mateix cap de setmana.

    `seu` porta el text de la fase tal com l'escriu la federació: és la clau
    amb què la graella l'enganxa sota l'epígraf que li toca.
    """
    per_fase: dict[tuple, list[Cita]] = {}
    for c in cites_:
        per_fase.setdefault((c.fase.data_inici, c.inscrit.divisio, c.fase.fase), []).append(c)

    files: list[tuple] = []
    for (_, divisio, fase), grup in sorted(per_fase.items(), key=lambda kv: kv[0]):
        f = grup[0].fase
        jugadors = [c.inscrit for c in sorted(grup, key=lambda c: c.inscrit.posicio)]
        # Punt volat i no coma: els noms són «COGNOMS, NOM» i la coma ja hi és
        # a dins, o sigui que qui ho llegeixi no sabria per on partir.
        titol = " · ".join(j.jugador for j in jugadors)
        files.append(
            (
                FONT,
                temporada,
                _dilluns(f.data_inici).isoformat(),
                "carambola",
                "catala",
                f"Campionat de Catalunya 3 bandes · {divisio} · {fase}",
                "individual",
                f.data_inici.isoformat(),
                f.data_fi.isoformat(),
                titol,
                f.text or None,
                None,
                None,
                1,
                f"{f.data_inici.isoformat()} {divisio} {fase}: {titol}",
            )
        )
    return files


class ResDesar(ValueError):
    """S'ha demanat de desar una llista buida damunt de dades que ja hi eren."""


def ingest(conn, cites_: list[Cita], temporada: str) -> int:
    """Desa les cites a `calendari_events`. Reemplaça les seves.

    El reemplaçament és destructiu —esborra i torna a escriure—, o sigui que una
    llista buida s'enduria el que ja hi havia. Passa amb un `--club` mal escrit:
    no casa amb ningú, no surt cap cita, i el calendari es queda sense res sense
    que ningú se n'assabenti. Per això no es desa mai el buit.
    """
    files = files_de_calendari(cites_, temporada)
    if not files:
        raise ResDesar(
            "No hi ha res per desar. No esborro el que ja hi ha per posar-hi el buit: "
            "si el filtre no ha trobat ningú, el problema és el filtre, no les dades."
        )
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
