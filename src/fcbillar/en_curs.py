"""Què hi ha «en curs»: la lliga que es publica i la temporada que s'etiqueta.

Fins a l'octubre de 2026 això eren valors escrits a mà: `LLIGA_3B_ID = 38` i
`LLIGA_4M_ID = 39` a la publicació, i `--temporada "2026/2027"` per defecte a sis
comandes que la reingesta nocturna crida sense arguments. Tots funcionaven el
dia que es van escriure i tots s'haurien trencat igual: en silenci. La ingesta de
lliga ja seguia el llistat de la federació; la publicació no, i el setembre de
2026 el web va estar ensenyant la lliga de la temporada passada com si fos la
d'ara, amb el job en verd, fins que algú va canviar el número.

Aquí no hi ha cap número. Les dues preguntes es responen amb el que diu la
federació:

- **Quina lliga es publica** surt de `lligues_obertes`, que és el llistat de
  lligues de la intranet tal com l'ha vist l'última ingesta (`ingest-lliga` el
  desa cada nit). La de Tres Bandes i la de 4 Modalitats s'hi distingeixen pel
  que diu la mateixa fila, no per l'id.
- **Quina temporada és** surt de les dates del calendari d'aquelles lligues, o
  del límit d'inscripció si encara no tenen calendari.

I quan no es pot saber, no s'inventa: `NoDeterminat`, amb un missatge que diu què
falta i com es força a mà. Un pas que falla es veu; un pas que publica la
temporada passada, no.
"""

from __future__ import annotations

import os
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime

#: Les dues lligues que es publiquen, cadascuna a les seves taules.
MENA_3B = "3B"
MENA_4M = "4M"

_NOM_DE_MENA = {MENA_3B: "Tres Bandes", MENA_4M: "4 Modalitats"}


class NoDeterminat(RuntimeError):
    """No s'ha pogut saber quina lliga o quina temporada és la d'ara.

    És un error i no un valor per defecte a posta: tot el que hi havia abans
    d'aquest mòdul eren valors per defecte que es van quedar vells.
    """


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", s)


def mena_de_lliga(nom: str, modalitat: str = "") -> str | None:
    """`'3B'`, `'4M'` o `None`, segons el que diu la fila del llistat.

    Es mira la columna «Modalitat» i el nom junts: «Lliga Catalana 4 Modalitats»
    amb modalitat «4 Modalitats», «Lliga Catalana Tres Bandes» amb «Tres
    bandes». `None` és una lliga que no sabem on publicar —una de femenina o de
    veterans, el dia que n'hi hagi—: s'ingereix igualment, i la comprovació de
    frescor la treu a la llum.
    """
    n = _norm(f"{modalitat} {nom}")
    if "4MODALITATS" in n or "QUATREMODALITATS" in n:
        return MENA_4M
    if "TRESBANDES" in n or "3BANDES" in n:
        return MENA_3B
    return None


@dataclass(frozen=True)
class LligaVista:
    """Una fila de `lligues_obertes`."""

    lliga_id: int
    nom: str
    modalitat: str
    estat: str
    data_limit: date | None
    ultima_vista: str

    @property
    def mena(self) -> str | None:
        return mena_de_lliga(self.nom, self.modalitat)


def desa_lligues_obertes(conn: sqlite3.Connection, obertes, *, ara: datetime | None = None) -> int:
    """Apunta el llistat de lligues que la federació acaba d'ensenyar.

    Totes les files d'una mateixa lectura porten la mateixa `ultima_vista`, i
    això és el que després permet dir «les que hi havia a l'últim llistat»
    sense haver d'esborrar res: una lliga que ja no hi surt es queda a la taula
    amb la data de l'últim dia que s'hi va veure.

    `obertes` són `LligaOberta` (o qualsevol cosa amb els mateixos camps).
    """
    marca = (ara or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    for ll in obertes:
        limit = ll.data_limit.isoformat() if getattr(ll, "data_limit", None) else None
        conn.execute(
            """
            INSERT INTO lligues_obertes
                (lliga_id, nom, modalitat, estat, data_limit, primera_vista, ultima_vista)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (lliga_id) DO UPDATE SET
                nom = excluded.nom, modalitat = excluded.modalitat, estat = excluded.estat,
                data_limit = excluded.data_limit, ultima_vista = excluded.ultima_vista
            """,
            (ll.lliga_id, ll.nom, ll.modalitat or "", ll.estat or "", limit, marca, marca),
        )
    conn.commit()
    return len(obertes)


def lligues_vistes(conn: sqlite3.Connection) -> list[LligaVista]:
    """Totes les lligues que s'han vist mai al llistat, de més nova a més vella."""
    try:
        files = conn.execute(
            "SELECT lliga_id, nom, modalitat, estat, data_limit, ultima_vista "
            "FROM lligues_obertes ORDER BY ultima_vista DESC, lliga_id DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        # Una base que no ha passat per `ensure_schema` des que existeix la
        # taula. No se n'ha vist cap: és el mateix que tenir-la buida.
        return []
    return [
        LligaVista(
            lliga_id=f[0],
            nom=f[1],
            modalitat=f[2] or "",
            estat=f[3] or "",
            data_limit=date.fromisoformat(f[4]) if f[4] else None,
            ultima_vista=f[5],
        )
        for f in files
    ]


def lligues_de_l_ultim_llistat(conn: sqlite3.Connection) -> list[LligaVista]:
    """Les que hi havia l'última vegada que es va llegir el llistat."""
    vistes = lligues_vistes(conn)
    if not vistes:
        return []
    ultima = max(v.ultima_vista for v in vistes)
    return [v for v in vistes if v.ultima_vista == ultima]


def _variable(mena: str) -> str:
    return f"FCB_LLIGA_{mena}_ID"


def lliga_en_curs(conn: sqlite3.Connection, mena: str) -> int:
    """L'id de la lliga d'aquesta mena que toca publicar.

    Per ordre:

    1. La variable d'entorn `FCB_LLIGA_3B_ID` / `FCB_LLIGA_4M_ID`, per a qui
       vulgui forçar-ne una en una execució manual.
    2. La d'aquesta mena que hi havia a l'últim llistat llegit. Si n'hi ha dues
       —la que s'acaba i la que obre inscripcions—, la que està «Activa».
    3. Si a l'últim llistat no n'hi ha cap d'aquesta mena, l'última que s'hi va
       veure: a l'estiu la federació treu la lliga acabada del llistat abans
       d'obrir la següent, i la que s'ha d'ensenyar segueix sent aquella.

    Si no en surt exactament una, `NoDeterminat`. No hi ha cap id per defecte.
    """
    forcada = os.environ.get(_variable(mena), "").strip()
    if forcada:
        if not forcada.isdigit():
            raise NoDeterminat(f"{_variable(mena)}={forcada!r} no és un id de lliga.")
        return int(forcada)

    nom = _NOM_DE_MENA.get(mena, mena)
    de_la_mena = [v for v in lligues_vistes(conn) if v.mena == mena]
    if not de_la_mena:
        raise NoDeterminat(
            f"No sé quina és la lliga de {nom} en curs: la base de dades no ha vist mai "
            f"cap lliga d'aquesta mena al llistat de la federació. Executa `fcbillar "
            f"ingest-lliga` (sense id), que el llegeix i el desa, o força-la amb "
            f"{_variable(mena)}=<id>."
        )
    ultim_llistat = {v.lliga_id for v in lligues_de_l_ultim_llistat(conn)}
    candidates = [v for v in de_la_mena if v.lliga_id in ultim_llistat]
    if not candidates:
        # Cap al llistat d'ara: la darrera que s'hi va veure.
        darrera = max(v.ultima_vista for v in de_la_mena)
        candidates = [v for v in de_la_mena if v.ultima_vista == darrera]
    if len(candidates) > 1:
        actives = [v for v in candidates if _norm(v.estat) == "ACTIVA"]
        if len(actives) == 1:
            candidates = actives
    if len(candidates) != 1:
        detall = ", ".join(f"{v.lliga_id} «{v.nom}» ({v.estat or '?'})" for v in candidates)
        raise NoDeterminat(
            f"El llistat de la federació porta {len(candidates)} lligues de {nom} i no sé "
            f"quina és la d'ara: {detall}. Tria-la amb {_variable(mena)}=<id>."
        )
    return candidates[0].lliga_id


# --------------------------- la temporada ---------------------------


def any_d_inici(dia: date) -> int:
    """L'any en què comença la temporada d'un dia de competició.

    La temporada va de setembre a juliol i l'agost no es juga res: un dia
    d'agost en endavant és de la temporada que comença aquell any, i un d'abans,
    de la que va començar l'any anterior.
    """
    return dia.year if dia.month >= 8 else dia.year - 1


def amb_barra(any_inici: int) -> str:
    """«2026/2027», com l'escriuen les taules de la temporada en curs."""
    return f"{any_inici}/{any_inici + 1}"


def amb_guio(any_inici: int) -> str:
    """«2026-2027», com l'escriu la taula `temporades`."""
    return f"{any_inici}-{any_inici + 1}"


def _any_d_inici_de_lliga(conn: sqlite3.Connection, vista: LligaVista) -> int | None:
    """L'any d'inici d'una lliga: del seu calendari i, si no en té, de la inscripció.

    El calendari mana: la primera jornada és sempre a la tardor. El límit
    d'inscripció només es mira quan la lliga encara no té cap encontre, i es
    llegeix d'una altra manera: s'obre a la primavera o a l'estiu de l'any en
    què comença, o sigui que del maig en endavant ja és de la temporada nova.
    """
    fila = conn.execute(
        "SELECT MIN(data) FROM encontres_lliga WHERE lliga_id = ? AND data IS NOT NULL",
        (vista.lliga_id,),
    ).fetchone()
    if fila and fila[0]:
        return any_d_inici(date.fromisoformat(fila[0][:10]))
    if vista.data_limit is not None:
        d = vista.data_limit
        return d.year if d.month >= 5 else d.year - 1
    return None


def temporada_en_curs(conn: sqlite3.Connection) -> int:
    """L'any d'inici de la temporada en curs, segons les lligues de la federació.

    És la temporada de les lligues de l'últim llistat (o, si el llistat n'és
    buit, de les últimes que s'hi van veure). Totes han de dir el mateix any; si
    n'hi ha de dues temporades, mana la que està «Activa», i si ni així queda
    clar, no és aquí on s'ha de triar.

    Qui la vulgui forçar té `--temporada` a cada comanda i `FCB_TEMPORADA=2026`
    (l'any d'inici) per a totes de cop.
    """
    forcada = os.environ.get("FCB_TEMPORADA", "").strip()
    if forcada:
        m = re.match(r"^(\d{4})", forcada)
        if m is None:
            raise NoDeterminat(f"FCB_TEMPORADA={forcada!r}: ha de començar per l'any, ex. 2026.")
        return int(m.group(1))

    vistes = lligues_de_l_ultim_llistat(conn)
    if not vistes:
        raise NoDeterminat(
            "No sé quina temporada és: la base de dades no ha vist mai el llistat de "
            "lligues de la federació. Executa `fcbillar ingest-lliga` (sense id) o "
            "passa `--temporada 2026/2027`."
        )
    anys: dict[int, list[str]] = {}
    actives: set[int] = set()
    sense: list[str] = []
    for v in vistes:
        a = _any_d_inici_de_lliga(conn, v)
        if a is None:
            sense.append(f"{v.lliga_id} «{v.nom}»")
            continue
        anys.setdefault(a, []).append(f"{v.lliga_id} «{v.nom}»")
        if _norm(v.estat) == "ACTIVA":
            actives.add(a)
    if len(anys) == 1:
        return next(iter(anys))
    # A l'estiu conviuen la lliga que s'acaba («Activa») i la que obre
    # inscripcions: la temporada en curs és la de la que encara es juga.
    if len(actives) == 1:
        return next(iter(actives))
    if not anys:
        raise NoDeterminat(
            "No sé quina temporada és: cap lliga del llistat té calendari ni data límit "
            f"d'inscripció ({', '.join(sense)}). Passa `--temporada 2026/2027`."
        )
    detall = "; ".join(f"{amb_barra(a)}: {', '.join(ll)}" for a, ll in sorted(anys.items()))
    raise NoDeterminat(
        f"El llistat de la federació barreja lligues de temporades diferents ({detall}). "
        "Digues quina vols amb `--temporada`."
    )


def temporada_o_en_curs(conn: sqlite3.Connection, temporada: str | None) -> str:
    """La temporada que s'ha demanat o, si no se n'ha demanat cap, la que hi ha en curs.

    Sempre amb barra («2026/2027»), que és com la volen les comandes que la
    reben per `--temporada`.
    """
    if temporada:
        return temporada
    return amb_barra(temporada_en_curs(conn))
