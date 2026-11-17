"""Quins jugadors espanyols de la UMB són a la fitxa del cens català.

La UMB escriu «LEGAZPI Ruben» (cognom en majúscules i nom), normalment amb un sol
cognom, i el cens «LEGAZPI CAÑIZARES, RUBEN». Aquí només es proposen candidats,
amb el mateix criteri que la Lliga Nacional (`nacional_fitxes`): un lligam no val
fins que algú el marca com a validat a `fonts/internacional/fitxes.csv`.

El lligam és pel `umb_id`, l'identificador que la UMB dóna a cada jugador i que es
manté d'una prova a l'altra.
"""

from __future__ import annotations

import csv
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from fcbillar.nacional_fitxes import JugadorCens, JugadorRfeb, _mots, _una_lletra, candidats

CAMPS = [
    "validat",
    "umb_id",
    "jugador_umb",
    "nacionalitat",
    "proves",
    "fcb_id",
    "nom_cens",
    "club_cens",
    "motiu",
]
_ESPANYOLS = ("ES", "ESP")


@dataclass(frozen=True)
class JugadorUmb:
    umb_id: str
    nom: str  # «COGNOM Nom»
    proves: int


def nom_natural(nom: str) -> str:
    """«LEGAZPI Ruben» -> «Ruben LEGAZPI», l'ordre que espera `nacional_fitxes`."""
    t = nom.split()
    n = 0
    while n < len(t) and not any(c.islower() for c in t[n]):
        n += 1
    if n == 0 or n == len(t):
        return nom
    return " ".join(t[n:] + t[:n])


def jugadors_espanyols(conn: sqlite3.Connection) -> tuple[list[JugadorUmb], int]:
    """Un jugador per `umb_id`, amb el nom que més surt. I quants no en tenen, d'id."""
    noms: dict[str, Counter[str]] = {}
    for umb_id, nom in conn.execute(
        "SELECT umb_id, nom FROM umb_jugadors "
        f"WHERE umb_id IS NOT NULL AND nacionalitat IN {_ESPANYOLS}"
    ):
        noms.setdefault(umb_id, Counter())[nom] += 1
    sense = conn.execute(
        "SELECT COUNT(DISTINCT nom) FROM umb_jugadors "
        f"WHERE umb_id IS NULL AND nacionalitat IN {_ESPANYOLS}"
    ).fetchone()[0]
    out = [JugadorUmb(i, n.most_common(1)[0][0], sum(n.values())) for i, n in noms.items()]
    return out, sense


def proposa(
    jugadors: list[JugadorUmb], cens: list[JugadorCens]
) -> list[tuple[JugadorUmb, str, JugadorCens]]:
    """(jugador UMB, motiu, fitxa del cens) per cada candidat."""
    per_nom = {nom_natural(j.nom): j for j in jugadors}
    rfeb = [JugadorRfeb(nom=n, equip="", divisio="") for n in per_nom]
    return [(per_nom[c.rfeb.nom], c.motiu, c.cens) for c in candidats(rfeb, cens)]


def escriu_candidats(
    trobats: list[tuple[JugadorUmb, str, JugadorCens]], cami: str | Path
) -> tuple[int, int]:
    """Afegeix al CSV els candidats nous i deixa intactes els que ja hi són (validats o no)."""
    cami = Path(cami)
    files: list[dict] = []
    if cami.exists():
        with cami.open(encoding="utf-8", newline="") as f:
            files = list(csv.DictReader(f))
    vistos = {(f["umb_id"], f["fcb_id"]) for f in files}
    nous = 0
    for j, motiu, c in trobats:
        if (j.umb_id, c.fcb_id) in vistos:
            continue
        vistos.add((j.umb_id, c.fcb_id))
        files.append(
            {
                "validat": "",
                "umb_id": j.umb_id,
                "jugador_umb": j.nom,
                "nacionalitat": "ES",
                "proves": j.proves,
                "fcb_id": c.fcb_id,
                "nom_cens": c.nom,
                "club_cens": c.club,
                "motiu": motiu,
            }
        )
        nous += 1
    files.sort(key=lambda f: (f["validat"] != "", f["jugador_umb"]))
    cami.parent.mkdir(parents=True, exist_ok=True)
    with cami.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPS, restval="")
        w.writeheader()
        w.writerows(files)
    return len(files) - nous, nous


def lligams_validats(cami: str | Path) -> dict[str, str]:
    """`{umb_id: fcb_id}` dels lligams marcats amb «si»."""
    cami = Path(cami)
    if not cami.exists():
        return {}
    with cami.open(encoding="utf-8", newline="") as f:
        return {
            r["umb_id"]: r["fcb_id"]
            for r in csv.DictReader(f)
            if r["validat"].strip().lower() == "si"
        }


# ------------------------- espanyols sense cap candidat -------------------------

CAMPS_SENSE = ["umb_id", "jugador_umb", "proves", "partides", "anys", "possibles"]


def _suggereix(nom_umb: str, cens: list[JugadorCens], n: int = 3) -> list[JugadorCens]:
    """Fitxes del cens que s'assemblen al nom UMB pel cognom; per mirar-les a mà, sense garantia."""
    mots = _mots(nom_natural(nom_umb))
    if len(mots) < 2:
        return []
    cognom, noms = mots[-1], mots[:-1]
    puntuats = []
    for c in cens:
        cognoms, _, pila = c.nom.partition(",")
        cs = _mots(cognoms)
        if not cs:
            continue
        pt = 0
        if cognom in cs:
            pt = 4 if cs[0] == cognom else 3
        elif len(cognom) >= 5 and any(len(x) >= 5 and _una_lletra(cognom, x) for x in cs):
            pt = 2
        if not pt:
            continue
        pila_m = _mots(pila)
        if pila_m and noms and pila_m[0][0] == noms[0][0]:
            pt += 2
        puntuats.append((-pt, c.nom, c))
    puntuats.sort(key=lambda t: t[:2])
    return [c for *_, c in puntuats[:n]]


def sense_candidat(
    conn: sqlite3.Connection,
    jugadors: list[JugadorUmb],
    amb_candidat: set[str],
    validats: dict[str, str],
    cens: list[JugadorCens],
) -> list[dict]:
    """Els espanyols (per `umb_id`) que no tenen ni lligam validat ni candidat, per revisar a mà."""
    quedats = [j for j in jugadors if j.umb_id not in amb_candidat and j.umb_id not in validats]
    out = []
    for j in quedats:
        noms = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT nom FROM umb_jugadors WHERE umb_id = ? AND nacionalitat IN "
                f"{_ESPANYOLS}",
                (j.umb_id,),
            )
        ]
        marques = ",".join("?" * len(noms))
        proves, partides, *_ = conn.execute(
            "SELECT (SELECT COUNT(DISTINCT esdeveniment_id) FROM umb_jugadors WHERE umb_id = ?), "
            "COUNT(*), MIN(substr(e.data_inici, 1, 4)), MAX(substr(e.data_inici, 1, 4)) "
            "FROM (SELECT esdeveniment_id, jugador_a AS nom FROM umb_partides "
            " UNION ALL SELECT esdeveniment_id, jugador_b FROM umb_partides) p "
            "JOIN umb_jugadors uj ON uj.esdeveniment_id = p.esdeveniment_id AND uj.nom = p.nom "
            f"JOIN umb_esdeveniments e ON e.id = p.esdeveniment_id WHERE uj.umb_id = ? AND p.nom IN ({marques})",
            (j.umb_id, j.umb_id, *noms),
        ).fetchone()
        anys_prova = conn.execute(
            "SELECT MIN(substr(e.data_inici, 1, 4)), MAX(substr(e.data_inici, 1, 4)) "
            "FROM umb_jugadors uj JOIN umb_esdeveniments e ON e.id = uj.esdeveniment_id "
            "WHERE uj.umb_id = ?",
            (j.umb_id,),
        ).fetchone()
        a, b = anys_prova
        out.append(
            {
                "umb_id": j.umb_id,
                "jugador_umb": j.nom,
                "proves": proves,
                "partides": partides,
                "anys": a if a == b else f"{a}-{b}",
                "possibles": " | ".join(
                    f"{c.fcb_id}:{c.nom} ({c.club})" if c.club else f"{c.fcb_id}:{c.nom}"
                    for c in _suggereix(j.nom, cens)
                ),
            }
        )
    out.sort(key=lambda f: (-f["partides"], f["jugador_umb"]))
    return out


def escriu_sense_candidat(files: list[dict], cami: str | Path) -> None:
    cami = Path(cami)
    cami.parent.mkdir(parents=True, exist_ok=True)
    with cami.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPS_SENSE)
        w.writeheader()
        w.writerows(files)
