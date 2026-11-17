"""Quins jugadors de la CEB, la UMB i la RFEB són a la fitxa del cens català.

Com a la Lliga Nacional, cap font comparteix identificador amb la FCB i aquí
només es proposen candidats: un lligam no val fins que algú hi posa «si» a
`fonts/externes/fitxes.csv`.

- RFEB: escriu els noms com a la Lliga Nacional («José Mª Mas Canadell»), i es
  fan servir els mateixos candidats. Un nom que ja està validat a
  `fonts/nacional/fitxes.csv` val també aquí sense tornar-lo a validar.
- CEB i UMB: «COGNOM Nom», gairebé sempre amb un sol cognom. Només es proposen
  jugadors d'Espanya, i només quan al cens no hi ha cap altre jugador amb aquell
  primer cognom i aquell nom.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from fcbillar.nacional_fitxes import JugadorCens, JugadorRfeb, candidats

CAMPS = ["validat", "font", "jugador", "nacio", "fcb_id", "nom_cens", "club_cens", "motiu"]

#: Com escriu cada font el país d'Espanya.
NACIONS_ESPANYA = {"ES", "ESP"}


@dataclass(frozen=True)
class JugadorExtern:
    font: str  # rfeb | ceb | umb
    nom: str
    nacio: str  # país (CEB, UMB) o federació autonòmica (RFEB)


def nom_de_pila_primer(nom: str) -> str:
    """«MAS CANADELL José Mª» → «José Mª MAS CANADELL»: l'ordre de la RFEB.

    Les paraules tot en majúscules són cognoms; la resta, el nom.
    """
    paraules = nom.split()
    cognoms = [
        p
        for p in paraules
        # «Mª» és tot majúscules però és un nom.
        if p.upper() == p and any(c.isalpha() for c in p) and not p.startswith("Mª")
    ]
    noms = [p for p in paraules if p not in cognoms]
    if not cognoms or not noms:
        return nom
    return " ".join(noms + cognoms)


def proposa(jugadors: list[JugadorExtern], cens: list[JugadorCens]) -> list[tuple[JugadorExtern, JugadorCens, str]]:
    """(jugador de fora, fitxa del cens, motiu) que poden ser la mateixa persona."""
    out = []
    per_nom: dict[str, list[JugadorExtern]] = {}
    rfeb: list[JugadorRfeb] = []
    for j in jugadors:
        if j.font != "rfeb" and j.nacio.upper() not in NACIONS_ESPANYA:
            continue
        nom = j.nom if j.font == "rfeb" else nom_de_pila_primer(j.nom)
        per_nom.setdefault(nom, []).append(j)
        rfeb.append(JugadorRfeb(nom=nom, equip=j.nacio, divisio=j.font))
    for c in candidats(rfeb, cens):
        for j in per_nom.get(c.rfeb.nom, []):
            if j.font == c.rfeb.divisio:
                out.append((j, c.cens, c.motiu))
    return out


def escriu_candidats(trobats, cami: str | Path) -> tuple[int, int]:
    """Afegeix al CSV els candidats nous; els que ja hi són no es toquen."""
    cami = Path(cami)
    files = []
    if cami.exists():
        with cami.open(encoding="utf-8", newline="") as f:
            files = list(csv.DictReader(f))
    vistos = {(f["font"], f["jugador"], f["fcb_id"]) for f in files}
    nous = 0
    for j, c, motiu in trobats:
        if (j.font, j.nom, c.fcb_id) in vistos:
            continue
        vistos.add((j.font, j.nom, c.fcb_id))
        files.append(
            {
                "validat": "",
                "font": j.font,
                "jugador": j.nom,
                "nacio": j.nacio,
                "fcb_id": c.fcb_id,
                "nom_cens": c.nom,
                "club_cens": c.club,
                "motiu": motiu,
            }
        )
        nous += 1
    files.sort(key=lambda f: (f["validat"] != "", f["font"], f["jugador"]))
    cami.parent.mkdir(parents=True, exist_ok=True)
    with cami.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPS, restval="")
        w.writeheader()
        w.writerows(files)
    return len(files) - nous, nous


def lligams_validats(cami: str | Path, nacional: str | Path | None = None) -> dict[tuple[str, str], str]:
    """`{(font, nom): fcb_id}` dels lligams marcats amb «si».

    Amb `nacional`, els noms validats per a la Lliga Nacional valen també per a
    la RFEB: és la mateixa federació escrivint el mateix nom.
    """
    out: dict[tuple[str, str], str] = {}
    if nacional is not None:
        from fcbillar.nacional_fitxes import lligams_validats as validats_nacional

        for nom, fcb_id in validats_nacional(nacional).items():
            out[("rfeb", nom)] = fcb_id
    cami = Path(cami)
    if cami.exists():
        with cami.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r["validat"].strip().lower() == "si":
                    out[(r["font"], r["jugador"])] = r["fcb_id"]
    return out
