"""Calendari oficial d'un grup de lliga, en PDF → encontres amb data.

La federació publica un PDF per grup («CALENDARI LLIGA TRES BANDES 2026-27
PRIMERA GRUP B») amb les catorze jornades i, per a cadascuna, la data i els
quatre encontres. És l'única font que concreta **el dia** de cada jornada: el
calendari esportiu general que llegeix `calendari_fed.py` només diu quina
setmana es juga, i per això la graella federativa de la zona soci va per
setmanes i no per dies.

## Com és el PDF

Dues pàgines apaïsades, i cada pàgina amb dos blocs de jornades de costat: a
l'esquerra la 1a-7a i a la dreta la 8a-14a, que són les mateixes tornades. A
sota del títol de cada jornada hi ha la data, i a sota els quatre encontres.
La columna de l'esquerra de tot és la llista numerada d'equips del grup i no
forma part de cap encontre.

```
1ª JORNADA                                8ª JORNADA
1 C.B. BANYOLES "A"   26/09/2026            09/01/2027
2 C.B. SANTS "A"      SANT ADRIA - MATARO   MATARO - SANT ADRIA
```

No es llegeix per línies de text: els noms d'equip porten espais i les columnes
es barrejarien. Es llegeix per posició — les paraules d'una fila es reparteixen
en columnes allà on hi ha un salt horitzontal ample.

## Les dates que la federació s'equivoca

El PDF de 2a divisió grup A de la 2026-27 porta `26/09/2026` a totes les
jornades menys la 1a i la 8a: en generar-lo no els van actualitzar el camp de
la data. Els altres grups porten les catorze dates bones i coincideixen entre
ells, perquè les jornades són comunes a tota la lliga.

Per això `dates_de_referencia()` treu el calendari de jornades a partir dels
grups que sí que el porten bé, i `esmena_dates()` el posa als que no. Una data
repetida no és una dada: és un camp que no s'ha tocat.
"""

from __future__ import annotations

import collections
import logging
import re
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

#: Salt horitzontal a partir del qual dues paraules són de columnes diferents.
#: Dins d'un nom d'equip els salts són de 2-3 punts; entre columnes, de 40 amunt.
_SALT_COLUMNA = 20.0

#: Tot el que comenci més a l'esquerra que això és la llista numerada d'equips
#: del grup, que no forma part de cap encontre.
_MARGE_LLISTA = 150.0

#: Dues paraules són de la mateixa fila si els seus `top` no es diferencien més
#: que això. Les files del PDF ballen un punt o dos entre columnes.
_TOLERANCIA_FILA = 3.0

_RE_JORNADA = re.compile(r"(\d+)ª\s+JORNADA")
_RE_DATA = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_RE_DIVISIO = re.compile(r"(\d+)ª\s+DIVISIÓ")
_RE_GRUP = re.compile(r'GRUP\s+"?([A-Z])"?')
_RE_TEMPORADA = re.compile(r"TEMPORADA\s+(\d{4}/\d{2,4})")


@dataclass(frozen=True)
class Encontre:
    """Un encontre del calendari oficial d'un grup."""

    jornada: int
    data: date
    local: str
    visitant: str


@dataclass(frozen=True)
class CalendariGrup:
    """El calendari sencer d'un grup, tal com el publica la federació."""

    temporada: str  # '2026/27'
    divisio: str  # '1a', '2a', '4a'
    grup: str  # 'B'
    equips: tuple[str, ...]
    encontres: tuple[Encontre, ...]

    @property
    def dates(self) -> dict[int, date]:
        """La data de cada jornada."""
        return {e.jornada: e.data for e in self.encontres}

    def de(self, equip: str) -> list[Encontre]:
        """Els encontres d'un equip, per ordre de jornada."""
        return sorted(
            (e for e in self.encontres if equip in (e.local, e.visitant)),
            key=lambda e: e.jornada,
        )


def _files(pagina) -> list[list[dict]]:
    """Les paraules de la pàgina agrupades per fila, cada fila d'esquerra a dreta."""
    per_fila: dict[int, list[dict]] = collections.defaultdict(list)
    for w in pagina.extract_words():
        per_fila[round(w["top"] / _TOLERANCIA_FILA)].append(w)
    return [
        sorted(ws, key=lambda w: w["x0"])
        for _, ws in sorted(per_fila.items(), key=lambda kv: kv[0])
    ]


def _columnes(fila: list[dict], *, nomes_dreta_de: float = 0.0) -> list[tuple[float, str]]:
    """Parteix una fila allà on hi ha un salt horitzontal ample.

    Retorna (x on comença, text) de cada columna.
    """
    out: list[tuple[float, str]] = []
    actual: list[dict] = []
    for w in fila:
        if w["x0"] < nomes_dreta_de:
            continue
        if actual and w["x0"] - actual[-1]["x1"] > _SALT_COLUMNA:
            out.append((actual[0]["x0"], " ".join(x["text"] for x in actual)))
            actual = []
        actual.append(w)
    if actual:
        out.append((actual[0]["x0"], " ".join(x["text"] for x in actual)))
    return out


def _data_de(text: str) -> date | None:
    m = _RE_DATA.search(text)
    if m is None:
        return None
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))


def llegeix(pdf_path: str | Path) -> CalendariGrup:
    """Llegeix el PDF del calendari d'un grup."""
    import pdfplumber

    capcalera = {"temporada": "", "divisio": "", "grup": ""}
    encontres: list[Encontre] = []

    # Un bloc és una capçalera de jornades («1ª JORNADA … 8ª JORNADA») amb la
    # seva fila de dates i les files d'encontres que hi pengen. N'hi ha uns
    # quants per pàgina, o sigui que es tanca quan n'arriba un de nou.
    jornades: list[tuple[float, int]] = []
    dates: dict[int, date] = {}
    files: list[list[tuple[float, str]]] = []

    def tanca_bloc() -> None:
        if jornades and dates and files:
            encontres.extend(_encontres_del_bloc(files, jornades, dates))
        files.clear()

    with pdfplumber.open(str(pdf_path)) as pdf:
        for pagina in pdf.pages:
            for fila in _files(pagina):
                text = " ".join(w["text"] for w in fila)
                _llegeix_capcalera(text, capcalera)

                if _RE_JORNADA.search(text):
                    tanca_bloc()
                    jornades = [
                        (x, int(m.group(1)))
                        for x, t in _columnes(fila)
                        if (m := _RE_JORNADA.match(t))
                    ]
                    dates = {}
                    continue

                cols = _columnes(fila)

                # La fila de les dates ve just sota la capçalera.
                if jornades and not dates and any(_RE_DATA.search(t) for _, t in cols):
                    for x, t in cols:
                        d = _data_de(t)
                        j = _bloc_de(x, jornades)
                        if d is not None and j is not None:
                            dates[j] = d
                    continue

                if jornades and dates:
                    files.append([(x, t) for x, t in cols if x >= _MARGE_LLISTA])
            tanca_bloc()

    # Els equips surten dels mateixos encontres. La llista numerada del marge
    # esquerre diria el mateix, però comparteix fila amb la data i amb el títol
    # del grup, i llegir-la demanava més excepcions que profit.
    vistos: list[str] = []
    for e in sorted(encontres, key=lambda e: e.jornada):
        for equip in (e.local, e.visitant):
            if equip not in vistos:
                vistos.append(equip)

    return CalendariGrup(
        temporada=capcalera["temporada"],
        divisio=capcalera["divisio"],
        grup=capcalera["grup"],
        equips=tuple(vistos),
        encontres=tuple(sorted(encontres, key=lambda e: (e.jornada, e.local))),
    )


def _llegeix_capcalera(text: str, dest: dict[str, str]) -> None:
    if not dest["temporada"] and (m := _RE_TEMPORADA.search(text)):
        dest["temporada"] = m.group(1)
    if not dest["divisio"] and (m := _RE_DIVISIO.search(text)):
        dest["divisio"] = f"{m.group(1)}a"
    if not dest["grup"] and (m := _RE_GRUP.search(text)):
        dest["grup"] = m.group(1)


def _encontres_del_bloc(
    files: list[list[tuple[float, str]]],
    jornades: list[tuple[float, int]],
    dates: dict[int, date],
) -> list[Encontre]:
    """Els encontres d'un bloc, assignant cada columna al seu lloc per posició.

    Aparellar les columnes per ordre d'aparició no serveix: als grups senars hi
    ha una jornada on un equip descansa, i llavors la seva fila té una columna
    sola que s'enganxaria amb la del bloc del costat i inventaria un encontre
    d'un equip contra ell mateix.

    Per això primer es miren totes les files alhora i se'n treuen les columnes
    de debò —n'hi ha dues per bloc, local i visitant—, i després cada fila posa
    el que tingui al seu lloc. Una fila amb una sola columna d'un bloc és un
    equip que descansa, i no genera cap encontre.
    """
    posicions = sorted({x for fila in files for x, _ in fila})
    if not posicions:
        return []

    columnes: list[float] = [posicions[0]]
    for x in posicions[1:]:
        if x - columnes[-1] > _SALT_COLUMNA:
            columnes.append(x)

    # Dues columnes per bloc: la de l'esquerra és el local i la de la dreta el
    # visitant. Es reparteixen entre les jornades del bloc per proximitat.
    per_jornada: dict[int, list[float]] = collections.defaultdict(list)
    for x in columnes:
        j = _bloc_de(x, jornades)
        if j is not None:
            per_jornada[j].append(x)

    out: list[Encontre] = []
    for fila in files:
        for jornada, xs in per_jornada.items():
            if len(xs) < 2 or jornada not in dates:
                continue
            x_local, x_visitant = xs[0], xs[-1]
            local = _text_a(fila, x_local)
            visitant = _text_a(fila, x_visitant)
            if not local or not visitant:
                continue  # equip que descansa, o fila sense encontre en aquest bloc
            out.append(
                Encontre(
                    jornada=jornada,
                    data=dates[jornada],
                    local=_neteja_equip(local),
                    visitant=_neteja_equip(visitant),
                )
            )
    return out


def _text_a(fila: list[tuple[float, str]], x: float) -> str:
    """El text de la fila que cau a la columna que comença a `x`."""
    for xc, t in fila:
        if abs(xc - x) <= _SALT_COLUMNA:
            return t
    return ""


_RE_NUM_LLISTA = re.compile(r"^\d+\s+")


def _neteja_equip(text: str) -> str:
    """Treu el número de la llista i normalitza els espais."""
    return re.sub(r"\s+", " ", _RE_NUM_LLISTA.sub("", text)).strip()


def _bloc_de(x: float, jornades: list[tuple[float, int]]) -> int | None:
    """A quina jornada pertany una columna que comença a `x`."""
    candidats = [(abs(x - xj), j) for xj, j in jornades]
    return min(candidats)[1] if candidats else None


def dates_de_referencia(calendaris: list[CalendariGrup]) -> dict[int, date]:
    """El calendari de jornades comú, tret dels grups que el porten bé.

    Les jornades són les mateixes per a tota la lliga, o sigui que la data
    correcta de cadascuna és la que diu la majoria. Un grup que repeteix la
    mateixa data a mitja graella no vota: el seu camp no s'ha tocat.
    """
    vots: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    for cal in calendaris:
        dates = cal.dates
        repetides = collections.Counter(dates.values())
        if repetides and repetides.most_common(1)[0][1] > 2:
            log.info(
                "%s grup %s: %d jornades amb la mateixa data, no compta com a referència",
                cal.divisio,
                cal.grup,
                repetides.most_common(1)[0][1],
            )
            continue
        for jornada, d in dates.items():
            vots[jornada][d] += 1
    return {j: c.most_common(1)[0][0] for j, c in sorted(vots.items()) if c}


def esmena_dates(cal: CalendariGrup, referencia: dict[int, date]) -> CalendariGrup:
    """Posa les dates de referència als encontres del grup.

    Els emparellaments del PDF són bons encara que les dates no ho siguin: el
    que s'esmena és només el dia.
    """
    return replace(
        cal,
        encontres=tuple(
            replace(e, data=referencia.get(e.jornada, e.data)) for e in cal.encontres
        ),
    )
