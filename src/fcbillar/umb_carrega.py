"""Càrrega dels resultats de la UMB a la BBDD local.

Es llegeix la carpeta de PDF que ha baixat `umb_descarrega` (una subcarpeta per
prova) i es desa cada prova sencera: tornar-la a carregar la reemplaça, no la
duplica. Un PDF que no es pot llegir no tomba la prova ni la càrrega: queda a la
llista d'errors.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from fcbillar.umb import Llegit, clau, llegeix_prova
from fcbillar.umb_descarrega import Esdeveniment, carrega_esdeveniments

_DISCIPLINES = [
    (r"3[- ]?cushion|three[- ]?cushion|3[- ]?bandes", "3 bandes"),
    (r"1[- ]?cushion|one[- ]?cushion", "1 banda"),
    (r"5[- ]?pins?|five[- ]?pins?", "5 quilles"),
    (r"47[/-]?2|47/1|71/2|cadre|balkline", "quadre"),
    (r"artistic", "artistic"),
    (r"free|libre|straight", "lliure"),
    (r"pentathlon|biathlon|triathlon", "combinada"),
]


def disciplina_de(nom: str) -> str | None:
    for patro, valor in _DISCIPLINES:
        if re.search(patro, nom, re.I):
            return valor
    return None


@dataclass
class Resultat:
    esdeveniment: int
    nom: str
    estat: str  # desat | sense_pdf | buit
    detall: str = ""
    errors: list[str] = field(default_factory=list)


def esborra_esdeveniment(conn: sqlite3.Connection, id_: int) -> None:
    # Sense claus foranes actives per defecte a SQLite: es fa a mà.
    for t in ("umb_partides", "umb_classificacions", "umb_jugadors"):
        conn.execute(f"DELETE FROM {t} WHERE esdeveniment_id = ?", (id_,))
    conn.execute("DELETE FROM umb_esdeveniments WHERE id = ?", (id_,))


def desa_esdeveniment(conn: sqlite3.Connection, ev: Esdeveniment, ll: Llegit) -> None:
    """Desa una prova reemplaçant la que ja hi hagi amb el mateix id."""
    esborra_esdeveniment(conn, ev.id)
    conn.execute(
        "INSERT INTO umb_esdeveniments (id, nom, disciplina, lloc, data_inici, data_fi, font) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            ev.id,
            ev.nom,
            disciplina_de(ev.nom),
            ev.lloc,
            ev.inici,
            ev.fi,
            ev.font or f"https://www.umb-carom.org/events/{ev.id}",
        ),
    )
    conn.executemany(
        "INSERT OR REPLACE INTO umb_jugadors (esdeveniment_id, nom, umb_id, nacionalitat) "
        "VALUES (?, ?, ?, ?)",
        [(ev.id, j.nom, j.umb_id, j.nacionalitat) for j in ll.jugadors],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO umb_classificacions (esdeveniment_id, posicio, jugador, "
        "nacionalitat, ronda, punts, mitjana, mitjana_particular, serie1, serie2, caramboles, "
        "entrades) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                ev.id, c.posicio, c.jugador, c.nacionalitat, c.ronda, c.punts, c.mitjana,
                c.mitjana_particular, c.serie1, c.serie2, c.caramboles, c.entrades,
            )
            for c in ll.classificacio
        ],
    )  # fmt: skip
    conn.executemany(
        "INSERT OR REPLACE INTO umb_partides (esdeveniment_id, fase, grup, ordre, jugador_a, "
        "caramboles_a, entrades_a, mitjana_a, punts_a, serie_a, serie2_a, jugador_b, "
        "caramboles_b, entrades_b, mitjana_b, punts_b, serie_b, serie2_b) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                ev.id, p.fase, p.grup, p.ordre,
                p.a.jugador, p.a.caramboles, p.a.entrades, p.a.mitjana, p.a.punts, p.a.serie,
                p.a.serie2,
                p.b.jugador, p.b.caramboles, p.b.entrades, p.b.mitjana, p.b.punts, p.b.serie,
                p.b.serie2,
            )
            for p in ll.partides
        ],
    )  # fmt: skip


def _hereta_ids(conn: sqlite3.Connection) -> int:
    """Als PDF del 2018 no hi ha identificador UMB: es copia del mateix jugador d'una altra prova.

    Només si el nom (sense accents ni espais) i la nacionalitat apunten a un únic id.
    Es torna a fer a cada càrrega: els ids sintètics d'abans es refan amb el que hi hagi ara.
    """
    conn.execute("UPDATE umb_jugadors SET umb_id = NULL WHERE umb_id LIKE 'x:%'")
    ids: dict[tuple[str, str], set[str]] = defaultdict(set)
    for nom, nat, umb_id in conn.execute(
        "SELECT nom, nacionalitat, umb_id FROM umb_jugadors WHERE umb_id IS NOT NULL"
    ):
        ids[(clau(nom), nat or "")].add(umb_id)
    n = 0
    for e_id, nom, nat in conn.execute(
        "SELECT esdeveniment_id, nom, nacionalitat FROM umb_jugadors WHERE umb_id IS NULL"
    ).fetchall():
        trobats = ids.get((clau(nom), nat or ""))
        if trobats and len(trobats) == 1:
            conn.execute(
                "UPDATE umb_jugadors SET umb_id = ? WHERE esdeveniment_id = ? AND nom = ?",
                (next(iter(trobats)), e_id, nom),
            )
            n += 1
    # Sense cap id enlloc (la CEB no en dóna, ni els PDF del 2018): un id sintètic estable,
    # perquè igualment es pugui lligar amb la fitxa. Comença per «x:» i no és mai de la UMB.
    for e_id, nom, nat in conn.execute(
        "SELECT esdeveniment_id, nom, nacionalitat FROM umb_jugadors WHERE umb_id IS NULL"
    ).fetchall():
        conn.execute(
            "UPDATE umb_jugadors SET umb_id = ? WHERE esdeveniment_id = ? AND nom = ?",
            (f"x:{clau(nom)}:{nat or ''}", e_id, nom),
        )
    return n


def carrega_ceb(conn: sqlite3.Connection, cache: Path) -> list[Resultat]:
    """Desa els campionats d'Europa de la CEB baixats a `cache` (una pàgina HTML per prova)."""
    from fcbillar.ceb import DESPLACAMENT, llegeix_pagina

    out: list[Resultat] = []
    for ev in carrega_esdeveniments(cache):
        pagina = cache / f"{ev.id - DESPLACAMENT}.html"
        if not pagina.exists():
            out.append(Resultat(ev.id, ev.nom, "sense_pdf"))
            continue
        try:
            ll = llegeix_pagina(pagina.read_bytes())
        except Exception as e:
            out.append(Resultat(ev.id, ev.nom, "buit", f"{type(e).__name__}: {e}"))
            continue
        if not (ll.partides or ll.classificacio):
            out.append(
                Resultat(ev.id, ev.nom, "sense_dades", "la pàgina no té resultats", ll.errors)
            )
            esborra_esdeveniment(conn, ev.id)
            continue
        desa_esdeveniment(conn, ev, ll)
        out.append(
            Resultat(
                ev.id,
                ev.nom,
                "desat",
                f"{len(ll.jugadors)} jugadors, {len(ll.classificacio)} classificats, "
                f"{len(ll.partides)} partides",
                ll.errors,
            )
        )
    _hereta_ids(conn)
    conn.commit()
    return out


def _llegeix_carpeta(carpeta: Path) -> Llegit | str:
    """La prova d'una carpeta, o l'error en text. Va en un altre procés: llegir és el que triga."""
    try:
        return llegeix_prova(carpeta)
    except Exception as e:  # no ha de tombar la resta de proves
        return f"{type(e).__name__}: {e}"


def carrega(conn: sqlite3.Connection, cache: Path) -> list[Resultat]:
    """Desa totes les proves de `cache` que tinguin PDF."""
    from concurrent.futures import ProcessPoolExecutor

    out: list[Resultat] = []
    per_llegir: list[Esdeveniment] = []
    for ev in carrega_esdeveniments(cache):
        if not ev.pdfs or not (cache / str(ev.id)).is_dir():
            out.append(Resultat(ev.id, ev.nom, "sense_pdf"))
        else:
            per_llegir.append(ev)
    with ProcessPoolExecutor() as pool:
        llegits = list(pool.map(_llegeix_carpeta, [cache / str(e.id) for e in per_llegir]))
    for ev, ll in zip(per_llegir, llegits, strict=True):
        if isinstance(ll, str):
            out.append(Resultat(ev.id, ev.nom, "buit", ll))
        elif not (ll.partides or ll.classificacio):
            out.append(Resultat(ev.id, ev.nom, "buit", "cap partida ni classificació", ll.errors))
            esborra_esdeveniment(conn, ev.id)
        else:
            desa_esdeveniment(conn, ev, ll)
            out.append(
                Resultat(
                    ev.id,
                    ev.nom,
                    "desat",
                    f"{len(ll.jugadors)} jugadors, {len(ll.classificacio)} classificats, "
                    f"{len(ll.partides)} partides",
                    ll.errors,
                )
            )
    _hereta_ids(conn)
    conn.commit()
    return sorted(out, key=lambda r: r.esdeveniment)


def cobertura(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    """Proves desades per any (files) i disciplina (columnes)."""
    t: dict[str, dict[str, int]] = defaultdict(dict)
    for any_, d, n in conn.execute(
        "SELECT substr(data_inici, 1, 4), COALESCE(disciplina, '?'), COUNT(*) "
        "FROM umb_esdeveniments GROUP BY 1, 2"
    ):
        t[any_ or "?"][d] = n
    return dict(sorted(t.items()))


def resum(conn: sqlite3.Connection) -> dict[str, int]:
    def un(sql: str) -> int:
        return conn.execute(sql).fetchone()[0]

    return {
        "esdeveniments": un("SELECT COUNT(*) FROM umb_esdeveniments"),
        "jugadors_distints": un("SELECT COUNT(DISTINCT COALESCE(umb_id, nom)) FROM umb_jugadors"),
        "jugadors_amb_umb_id": un("SELECT COUNT(DISTINCT umb_id) FROM umb_jugadors"),
        "classificacions": un("SELECT COUNT(*) FROM umb_classificacions"),
        "partides": un("SELECT COUNT(*) FROM umb_partides"),
        "espanyols": un(
            "SELECT COUNT(DISTINCT COALESCE(umb_id, nom)) FROM umb_jugadors "
            "WHERE nacionalitat IN ('ES', 'ESP')"
        ),
    }


def per_motiu(resultats: list[Resultat]) -> Counter[str]:
    return Counter(r.estat for r in resultats)
