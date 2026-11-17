"""Càrrega de les classificacions individuals de la RFEB a la BBDD local.

Es llegeix una carpeta de PDF (la còpia de Wayback de la web vella, amb una
subcarpeta `noticiasAAAA` per any) i es desa cada classificació final a
`rfeb_proves` i `rfeb_classificacions`. Una prova es desa sencera o no es desa:
si una fila no quadra, el fitxer és un error i no en queda res a mitges.

Tornar-ho a carregar reemplaça, no duplica: la clau d'una prova és el seu `id`
(`noticias2015/res_ce_3b_2015`), i la d'una fila (prova, posició, jugador). I
si dos fitxers són la mateixa prova —el CE de Madrid del 2013 és a `noticias/` i
a `noticias2013/`— només se'n desa un: el primer per ordre d'`id`.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from fcbillar.lliga_nacional import FormatDesconegut
from fcbillar.rfeb_individuals import Prova, SenseTaula, llegeix_prova

#: Un fitxer d'aquests és una fase d'una prova que té el seu fitxer principal:
#: `_fp` fase prèvia, `_ff` fase final, `_fc` classificació, `_q` qualificació,
#: `_prov` provisional, `_all` tot el quadre, `_r8`/`_16` una ronda…
_RE_PARCIAL = re.compile(
    r"(?:_(?:fp|ff|fc|q|cuad|prov|all|det|rep|jug|r\d+\w*|2y1)|(?<!47)(?<!71)_\d{1,2})$"
)

#: Parts del nom que diuen que el fitxer no és d'un campionat individual de
#: carambola de la RFEB.
_FORA_D_ABAST = {
    "jds": "joc de sèrie per equips",
    "sedes": "joc de sèrie per equips (fase de seus)",
    "ssaa": "classificació per seleccions autonòmiques (equips), no per jugadors",
    "sel": "classificació per seleccions (equips), no per jugadors",
    "equipos": "classificació per equips",
    "ceu": "campionat d'Europa, no és de la RFEB",
    "cm": "campionat del món, no és de la RFEB",
}
_SENSE_SUPORT = {
    "5q": "cinc quilles: la taula és de sets i punts, sense caramboles ni entrades",
    "artistic": "artístic: la taula és de sets i punts, sense caramboles ni entrades",
}


@dataclass
class Resultat:
    fitxer: str
    estat: str  # desat | saltat | error
    #: El motiu en una frase que es repeteix igual a tots els fitxers que el comparteixen.
    motiu: str
    detall: str = ""


def id_de(cami: Path, arrel: Path) -> str:
    return f"{cami.parent.relative_to(arrel).as_posix()}/{cami.stem}"


def _tokens(nom: str) -> set[str]:
    return set(re.split(r"[_\-]", nom.lower()))


def _fora_d_abast(nom: str) -> str | None:
    for t in sorted(_tokens(nom)):
        if t in _FORA_D_ABAST:
            return _FORA_D_ABAST[t]
    return None


def _sense_suport(nom: str) -> str | None:
    n = nom.lower()
    if re.search(r"5q|5quillas", n):
        return _SENSE_SUPORT["5q"]
    if re.search(r"(?<![a-z])art(?![a-z])|artistico", n):
        return _SENSE_SUPORT["artistic"]
    return None


def _llegeix(args: tuple[Path, Path]) -> Prova | FormatDesconegut:
    """La prova d'un PDF, o l'error. Va en un altre procés: llegir és el que triga."""
    cami, arrel = args
    try:
        return llegeix_prova(cami, arrel)
    except FormatDesconegut as e:
        return e
    except Exception as e:
        # Algunes còpies de Wayback són fitxers truncats que ni s'obren.
        return FormatDesconegut(f"PDF il·legible: {type(e).__name__}: {e}")


def desa_prova(conn: sqlite3.Connection, p: Prova) -> None:
    """Desa una prova amb les seves files, reemplaçant la que ja hi hagi amb el mateix id."""
    esborra_prova(conn, p.id)
    conn.execute(
        """
        INSERT INTO rfeb_proves
            (id, temporada, modalitat, categoria, tipus, titol, lloc, data_inici, data_fi, font)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            p.id,
            p.temporada,
            p.modalitat,
            p.categoria,
            p.tipus,
            p.titol,
            p.lloc,
            p.data_inici,
            p.data_fi,
            p.font,
        ),
    )
    conn.executemany(
        """
        INSERT INTO rfeb_classificacions
            (prova_id, posicio, jugador, fed, ronda, posicio_empat, jugades, guanyades,
             empatades, perdudes, caramboles, entrades, mitjana, serie_major, punts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                p.id,
                f.posicio,
                f.jugador,
                f.fed,
                f.ronda,
                f.posicio_empat,
                f.jugades,
                f.guanyades,
                f.empatades,
                f.perdudes,
                f.caramboles,
                f.entrades,
                f.mitjana,
                f.serie_major,
                f.punts,
            )
            for f in p.files
        ],
    )


def esborra_prova(conn: sqlite3.Connection, prova_id: str) -> None:
    conn.execute("DELETE FROM rfeb_classificacions WHERE prova_id = ?", (prova_id,))
    conn.execute("DELETE FROM rfeb_proves WHERE id = ?", (prova_id,))


def carrega(conn: sqlite3.Connection, arrel: Path) -> list[Resultat]:
    """Desa totes les classificacions finals dels PDF de `arrel`."""
    from concurrent.futures import ProcessPoolExecutor

    pdfs = sorted(arrel.rglob("*.pdf"), key=lambda f: id_de(f, arrel))
    existents = {(f.parent, f.stem) for f in pdfs}
    out: dict[str, Resultat] = {}
    per_llegir: list[Path] = []
    for f in pdfs:
        fitxer = id_de(f, arrel)
        motiu = _fora_d_abast(f.stem)
        if motiu:
            out[fitxer] = Resultat(fitxer, "saltat", motiu)
            continue
        m = _RE_PARCIAL.search(f.stem)
        if m:
            base = f.stem[: m.start()]
            if (f.parent, base) in existents:
                out[fitxer] = Resultat(
                    fitxer, "saltat", "fase parcial d'una prova que té fitxer principal", base
                )
            else:
                out[fitxer] = Resultat(
                    fitxer, "saltat", "només hi ha la fase parcial, sense fitxer principal"
                )
            continue
        per_llegir.append(f)

    with ProcessPoolExecutor() as pool:
        llegits = list(pool.map(_llegeix, [(f, arrel) for f in per_llegir], chunksize=4))

    vistes: dict[tuple, str] = {}
    for f, llegit in zip(per_llegir, llegits, strict=True):
        fitxer = id_de(f, arrel)
        if isinstance(llegit, SenseTaula):
            motiu = _sense_suport(f.stem) or "sense taula de classificació de jugadors reconeguda"
            out[fitxer] = Resultat(fitxer, "saltat", motiu)
            continue
        if isinstance(llegit, FormatDesconegut):
            motiu = (
                "PDF il·legible (fitxer truncat o malmès)"
                if str(llegit).startswith("PDF il·legible")
                else "fila o taula que no quadra"
            )
            out[fitxer] = Resultat(fitxer, "error", motiu, str(llegit)[:200])
            # Un error no deixa res a mitges, ni el d'una càrrega anterior.
            esborra_prova(conn, fitxer)
            continue
        signatura = llegit.signatura()
        if signatura in vistes:
            out[fitxer] = Resultat(
                fitxer, "saltat", "duplicat d'una prova ja desada", vistes[signatura]
            )
            esborra_prova(conn, fitxer)
            continue
        vistes[signatura] = fitxer
        desa_prova(conn, llegit)
        out[fitxer] = Resultat(
            fitxer,
            "desat",
            "desat",
            f"{llegit.temporada} {llegit.modalitat} {llegit.categoria} {llegit.tipus} "
            f"{len(llegit.files)} files",
        )
    conn.commit()
    return [out[k] for k in sorted(out)]


def cobertura(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    """Proves desades per temporada (files) i modalitat (columnes)."""
    taula: dict[str, dict[str, int]] = defaultdict(dict)
    for temporada, modalitat, n in conn.execute(
        "SELECT temporada, modalitat, COUNT(*) FROM rfeb_proves GROUP BY temporada, modalitat"
    ):
        taula[temporada][modalitat] = n
    return dict(sorted(taula.items()))


def per_categoria(conn: sqlite3.Connection) -> dict[str, int]:
    return dict(
        conn.execute(
            "SELECT categoria, COUNT(*) FROM rfeb_proves GROUP BY categoria ORDER BY 2 DESC"
        ).fetchall()
    )


def resum(resultats: list[Resultat]) -> dict[str, Counter[str]]:
    """Per cada estat, quants fitxers hi ha amb cada motiu."""
    out: dict[str, Counter[str]] = defaultdict(Counter)
    for r in resultats:
        out[r.estat][r.motiu] += 1
    return dict(out)
