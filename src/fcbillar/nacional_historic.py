"""Temporades passades de la Lliga Nacional, carregades d'un sol cop.

Els PDF venen de dos llocs: la web vella de la RFEB, que ja no hi és i se'n
recuperen les còpies de Wayback Machine (una carpeta `noticiasAAAA` per any), i
la web nova, que té la 2025/26 sencera. Es desen amb `desa_jornada` i
`desa_classificacio_de_jugadors`, que reemplacen per clau: carregar-ho dues
vegades, o la mateixa jornada des de les dues fonts, no duplica res.

La temporada en curs no es toca mai: aquella la porta el procés de cada nit des
de `fonts/nacional/`.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from fcbillar.lliga_nacional import (
    FormatDesconegut,
    desa_classificacio_de_jugadors,
    desa_jornada,
    llegeix_classificacio_de_jugadors,
    llegeix_jornada,
    temporada_de,
)

_RE_DIVISIO = re.compile(r"liga[-_]nal[-_](h|1|2)", re.IGNORECASE)
#: `liga_nal_1a_j3.pdf`: el grup A de Primera, en un PDF a part.
_RE_GRUP_AL_NOM = re.compile(r"liga[-_]nal[-_][12]([a-d])[-_]j", re.IGNORECASE)


@dataclass
class Resultat:
    fitxer: str
    estat: str  # desat | saltat | error
    detall: str


def _divisio(nom: str) -> str | None:
    m = _RE_DIVISIO.search(nom)
    if m is None:
        return None
    return "honor" if m.group(1).lower() == "h" else m.group(1)


def _llegeix(f: Path):
    """La jornada o la classificació d'un PDF, o l'error. Va en un altre procés."""
    try:
        if "cjug" in f.name:
            return llegeix_classificacio_de_jugadors(f)
        return llegeix_jornada(f)
    except FormatDesconegut as e:
        return e
    except Exception as e:
        # Algunes còpies de Wayback són fitxers truncats que ni s'obren.
        return FormatDesconegut(f"PDF il·legible: {type(e).__name__}: {e}")


def carrega(conn, carpetes: list[Path], abans_de: str) -> list[Resultat]:
    """Desa les jornades i classificacions de les temporades anteriors a `abans_de`.

    `carpetes` per ordre de preferència creixent: si una jornada surt a dues
    carpetes, mana la de l'última. Una carpeta és una temporada o un any de la
    web vella; les classificacions de jugadors no porten data i prenen la
    temporada de les jornades de la seva carpeta.
    """
    from concurrent.futures import ProcessPoolExecutor

    # Llegir és el que triga (uns segons per PDF); es fa tot en paral·lel i
    # després es desa per ordre, que és el que fa manar la carpeta preferent.
    tots = [
        f
        for carpeta in carpetes
        for f in sorted(carpeta.rglob("*.pdf"))
        if _divisio(f.name) and "poff" not in f.name and "ascper" not in f.name
    ]
    with ProcessPoolExecutor() as pool:
        llegits = dict(zip(tots, pool.map(_llegeix, tots, chunksize=4), strict=True))

    out: list[Resultat] = []
    for carpeta in carpetes:
        for sub in sorted({f.parent for f in carpeta.rglob("*.pdf")}):
            temporades: Counter[str] = Counter()
            cjugs: list[tuple[Path, str]] = []
            for f in sorted(sub.glob("*.pdf")):
                divisio = _divisio(f.name)
                if divisio is None:
                    out.append(Resultat(str(f), "saltat", "no és de cap divisió"))
                    continue
                if "cjug" in f.name:
                    if "poff" in f.name or "ascper" in f.name:
                        out.append(Resultat(str(f), "saltat", "classificació de play-off o fase"))
                    else:
                        cjugs.append((f, divisio))
                    continue
                j = llegits[f]
                if isinstance(j, FormatDesconegut):
                    out.append(Resultat(str(f), "error", str(j)[:160]))
                    continue
                if j.data is None:
                    out.append(Resultat(str(f), "error", "jornada sense data"))
                    continue
                # El format d'Honor no diu el grup. Quan una divisió de grups surt
                # amb aquest format, un PDF per grup, el grup és al nom del fitxer;
                # sense, el segon grup xafaria el primer.
                g = _RE_GRUP_AL_NOM.search(f.name)
                if g and len(j.grups) == 1 and j.grups[0].grup is None:
                    j = replace(j, grups=[replace(j.grups[0], grup=g.group(1).upper())])
                temporada = temporada_de(j.data)
                temporades[temporada] += 1
                if temporada >= abans_de:
                    out.append(Resultat(str(f), "saltat", f"temporada {temporada}, en curs"))
                    continue
                desa_jornada(conn, j, divisio, temporada)
                out.append(Resultat(str(f), "desat", f"{temporada} {divisio} j{j.numero} {j.data}"))

            if len(temporades) != 1:
                for f, _ in cjugs:
                    motiu = "sense jornades" if not temporades else f"temporades {dict(temporades)}"
                    out.append(Resultat(str(f), "saltat", f"no sé la temporada ({motiu})"))
                continue
            [temporada] = temporades
            for f, divisio in cjugs:
                if temporada >= abans_de:
                    out.append(Resultat(str(f), "saltat", f"temporada {temporada}, en curs"))
                    continue
                jugadors = llegits[f]
                if isinstance(jugadors, FormatDesconegut):
                    out.append(Resultat(str(f), "error", str(jugadors)[:160]))
                    continue
                desa_classificacio_de_jugadors(conn, jugadors, divisio, temporada)
                out.append(
                    Resultat(str(f), "desat", f"{temporada} {divisio} {len(jugadors)} jugadors")
                )
    conn.commit()
    return out
