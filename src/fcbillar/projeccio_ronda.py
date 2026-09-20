"""La ronda següent d'un campionat, projectada mentre la federació no la publiqui.

## Per què

Quan s'acaba una pre-prèvia ja se sap **qui passa**: la regla és escrita al PDF
del sorteig («els primers de cada grup i els set millors segons») i l'ordre entre
grups es pot calcular (posició al grup, punts, mitjana, sèrie major). El que la
federació tarda dies a publicar és **com queden repartits** a la ronda següent.

Això es projecta, com el rànquing provisional: es calcula sol quan hi ha les dades
per fer-ho i **la publicació oficial el substitueix** el dia que arriba.

## Què és projecció i què no

| | D'on surt | Fiabilitat |
|---|---|---|
| Qui passa | la regla del PDF + la classificació publicada | **exacte** |
| En quin bombo va | del nombre de places i la mida de grup | **exacte** |
| A quin grup va | el repartiment que fem aquí | **projecció** |

L'última fila és la que no es pot encertar, i s'ha de dir per què: el sorteig de la
federació és **geogràfic**. Al PDF de la prèvia d'Honor de 2026-27, la seu de cada
grup sempre té jugadors de casa i els clubs no se separen —tres del Granollers al
mateix grup—, i les seus no es publiquen fins que surt el sorteig. Amb el que
tenim, doncs, el repartiment per bombos és l'únic criteri defensable: un jugador de
cada bombo a cada grup, en serpentina.

O sigui que d'aquesta projecció el que val de debò són **els bombos**: qui et pot
tocar és algú de cada un dels altres, i això no canviarà quan surti el sorteig. El
grup concret sí.

## Com se substitueix

No cal esborrar res a mà. La projecció d'una fase només es té en compte mentre
aquella fase **no tingui grups publicats**: el dia que la federació els penja, la
ingesta els desa a `torneig_fase_grups` i la projecció deixa de comptar (i es
retira). Per això `projecta` es crida a cada ingesta i no un sol cop.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import unicodedata
from dataclasses import dataclass

log = logging.getLogger(__name__)

#: La mida de grup per defecte a les rondes de classificació. La federació juga a
#: tres o a quatre; amb 18 places, tres dona sis grups exactes.
MIDA_GRUP = 3

#: Els noms de les rondes, de la primera a l'última. Serveix per saber quina ve
#: després d'una pre-prèvia.
ORDRE_RONDES = ("PRE-PRE-PRÈVIA", "PRE-PRÈVIA", "PRÈVIA", "FINAL")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", s)


def ronda_seguent(nom_fase: str) -> str | None:
    """De «PRE-PRÈVIA» a «PRÈVIA». `None` si no se sap què ve després."""
    clau = _norm(nom_fase)
    noms = [_norm(x) for x in ORDRE_RONDES]
    if clau not in noms:
        return None
    i = noms.index(clau)
    return ORDRE_RONDES[i + 1] if i + 1 < len(ORDRE_RONDES) else None


@dataclass(frozen=True)
class Projectat:
    """Un jugador projectat a la ronda següent."""

    jugador: str
    #: L'ordre al rànquing de la ronda que acaba de jugar.
    posicio: int
    #: 1..mida_grup. És la part exacta: un de cada bombo per grup.
    bombo: int
    #: 'Grup A'… El repartiment que fem nosaltres. Projecció.
    grup_projectat: str


def projecta(classificats: list[str], mida_grup: int = MIDA_GRUP) -> list[Projectat]:
    """Reparteix els classificats en grups, un de cada bombo per grup.

    `classificats` ve ordenat pel rànquing de la ronda (posició al grup, punts,
    mitjana, sèrie major). Els bombos es fan per trams: amb 18 jugadors i grups de
    tres, els llocs 1-6 són el bombo 1, 7-12 el 2 i 13-18 el 3.

    El repartiment és en **serpentina**: el bombo 1 va del grup A al F i el bombo 2
    torna del F a l'A, que és el que reparteix els trams sense donar-los tots a un
    grup. No és el que fa la federació —el seu sorteig és geogràfic, vegeu la
    capçalera— i per això això és una projecció i va marcada com a tal.

    Si els classificats no són múltiple de la mida de grup, els que sobren van als
    primers grups: val més un grup de quatre que deixar algú fora.
    """
    if not classificats or mida_grup < 2:
        return []
    n_grups = max(1, len(classificats) // mida_grup)
    lletres = [chr(ord("A") + i) for i in range(n_grups)]

    out: list[Projectat] = []
    for i, jugador in enumerate(classificats):
        bombo = min(i // n_grups, mida_grup - 1) + 1
        dins = i % n_grups
        # Serpentina: els bombos parells van a l'inrevés.
        k = dins if (i // n_grups) % 2 == 0 else n_grups - 1 - dins
        out.append(
            Projectat(
                jugador=jugador,
                posicio=i + 1,
                bombo=bombo,
                grup_projectat=f"Grup {lletres[k]}",
            )
        )
    return out


def ja_publicada(conn: sqlite3.Connection, torneig_id: int, nom_ronda: str) -> bool:
    """La federació ja ha publicat els grups d'aquesta ronda?

    Mentre no els publiqui, la projecció val. El dia que ho faci, la ingesta els
    desa a `torneig_fase_grups` i això torna cert: la projecció es retira i el que
    s'ensenya és el que diu ella.
    """
    fila = conn.execute(
        """
        SELECT COUNT(*) FROM torneig_fase_grups g
          JOIN torneig_fases f ON f.id = g.fase_id
         WHERE f.torneig_id = ? AND UPPER(f.nom) = UPPER(?)
        """,
        (torneig_id, nom_ronda),
    ).fetchone()
    return bool(fila and fila[0])


def desa(
    conn: sqlite3.Connection,
    torneig_id: int,
    fase_origen_id: int,
    nom_ronda: str,
    files: list[Projectat],
    mida_grup: int = MIDA_GRUP,
) -> int:
    """Desa la projecció d'una ronda. Reemplaça la que hi hagués."""
    conn.execute(
        "DELETE FROM torneig_ronda_projectada WHERE torneig_id = ? AND ronda = ?",
        (torneig_id, nom_ronda),
    )
    conn.executemany(
        "INSERT INTO torneig_ronda_projectada (torneig_id, fase_origen_id, ronda, "
        "jugador_nom, posicio, bombo, grup_projectat, mida_grup) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                torneig_id,
                fase_origen_id,
                nom_ronda,
                p.jugador,
                p.posicio,
                p.bombo,
                p.grup_projectat,
                mida_grup,
            )
            for p in files
        ],
    )
    conn.commit()
    return len(files)


def retira(conn: sqlite3.Connection, torneig_id: int, nom_ronda: str) -> int:
    """Treu la projecció d'una ronda perquè la federació ja l'ha publicada."""
    cur = conn.execute(
        "DELETE FROM torneig_ronda_projectada WHERE torneig_id = ? AND ronda = ?",
        (torneig_id, nom_ronda),
    )
    conn.commit()
    return cur.rowcount or 0
