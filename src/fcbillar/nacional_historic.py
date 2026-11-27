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
    RE_FITXER_CONCENTRAT,
    FormatDesconegut,
    desa_classificacio_de_jugadors,
    desa_jornada,
    llegeix_classificacio_de_jugadors,
    llegeix_jornada,
    llegeix_jornades_concentrades,
    temporada_de,
)

_RE_DIVISIO = re.compile(r"liga[-_]nal[-_](h|1|2)", re.IGNORECASE)
#: `noticias2016`: la carpeta de la web vella on es publicava la temporada que
#: començava aquell any (la 2016-2017).
_RE_CARPETA_ANY = re.compile(r"noticias(\d{4})$", re.IGNORECASE)
#: Play-offs, fases d'ascens, i els PDF de fotos i d'horaris («_fotos», «_desB»).
_NO_ES_RESULTAT = re.compile(r"poff|ascper|_fotos|_des[A-D]?\.pdf", re.IGNORECASE)
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


def temporada_de_la_carpeta(carpeta: Path) -> str | None:
    """«noticias2016» -> «2016-2017». Per a les jornades que no porten data."""
    m = _RE_CARPETA_ANY.search(carpeta.name)
    return f"{m.group(1)}-{int(m.group(1)) + 1}" if m else None


def _llegeix(f: Path):
    """La jornada o la classificació d'un PDF, o l'error. Va en un altre procés."""
    try:
        if "cjug" in f.name:
            return llegeix_classificacio_de_jugadors(f)
        if RE_FITXER_CONCENTRAT.search(f.name):
            # Unes quantes jornades de cop (Honor 2020-21, per concentracions).
            return llegeix_jornades_concentrades(f)
        return llegeix_jornada(f)
    except FormatDesconegut as e:
        return e
    except Exception as e:
        # Algunes còpies de Wayback són fitxers truncats que ni s'obren.
        return FormatDesconegut(f"PDF il·legible: {type(e).__name__}: {e}")


def _desa_una(
    conn, f: Path, sub: Path, j, divisio: str, abans_de: str, temporades
) -> list[Resultat]:
    """Desa una jornada llegida de `f` i diu què n'ha passat."""
    # Les jornades d'Honor d'abans del 2019 no porten data: la temporada és la
    # de la carpeta de la web vella on es van publicar.
    temporada_carpeta = temporada_de_la_carpeta(sub)
    if j.data is None and temporada_carpeta is None:
        return [Resultat(str(f), "error", "jornada sense data")]
    # El format d'Honor no diu el grup. Quan una divisió de grups surt amb aquest
    # format, un PDF per grup, el grup és al nom del fitxer; sense, el segon grup
    # xafaria el primer.
    g = _RE_GRUP_AL_NOM.search(f.name)
    if g and len(j.grups) == 1 and j.grups[0].grup is None:
        j = replace(j, grups=[replace(j.grups[0], grup=g.group(1).upper())])
    temporada = temporada_de(j.data) if j.data else temporada_carpeta
    # La temporada 2020-21 va acabar l'1 d'agost del 2021 (Honor, jornades 21 i 22):
    # a l'agost, la de la carpeta de la web vella mana sobre la de la data.
    if j.data and j.data.month == 8 and temporada_carpeta == f"{j.data.year - 1}-{j.data.year}":
        temporada = temporada_carpeta
    temporades[temporada] += 1
    if temporada >= abans_de:
        return [Resultat(str(f), "saltat", f"temporada {temporada}, en curs")]
    desa_jornada(conn, j, divisio, temporada)
    return [Resultat(str(f), "desat", f"{temporada} {divisio} j{j.numero} {j.data or ''}")]


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
        if _divisio(f.name) and not _NO_ES_RESULTAT.search(f.name)
    ]
    with ProcessPoolExecutor() as pool:
        llegits = dict(zip(tots, pool.map(_llegeix, tots, chunksize=4), strict=True))

    out: list[Resultat] = []
    for carpeta in carpetes:
        for sub in sorted({f.parent for f in carpeta.rglob("*.pdf")}):
            temporades: Counter[str] = Counter()
            cjugs: list[tuple[Path, str]] = []
            # Les jornades soltes després de les concentracions: si una jornada és a
            # tots dos, mana la que porta la classificació de la seva jornada.
            ordenats = sorted(
                sub.glob("*.pdf"), key=lambda f: (not RE_FITXER_CONCENTRAT.search(f.name), f.name)
            )
            for f in ordenats:
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
                if f not in llegits:
                    # Play-offs, fases d'ascens, fotos i horaris: no es llegeixen.
                    out.append(Resultat(str(f), "saltat", "play-off, fase, fotos o horaris"))
                    continue
                llegit = llegits[f]
                if isinstance(llegit, FormatDesconegut):
                    out.append(Resultat(str(f), "error", str(llegit)[:160]))
                    continue
                for j in llegit if isinstance(llegit, list) else [llegit]:
                    out.extend(_desa_una(conn, f, sub, j, divisio, abans_de, temporades))

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
