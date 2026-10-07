"""La Lliga Nacional de tres bandes de la RFEB, llegida dels seus PDF.

La federació espanyola no té cap web de competició: de cada jornada de cada
divisió en penja un PDF (`liga_nal_1_j3.pdf`), i a part un amb la classificació
de jugadors (`liga_nal_1_cjug.pdf`). Porten text de debò, no imatges, i el
format és el mateix des del 2018 com a mínim.

Un PDF de jornada té una pàgina per grup, i a cada pàgina:

    JORNADA 1ª - 12 de septiembre de 2026
    la classificació del grup després de la jornada
    els encontres, DE DOS EN DOS, un al costat de l'altre

i una última pàgina amb les millors sèries i les millors partides.

El parany és el «de dos en dos». Si es llegeix el text línia a línia, cada línia
barreja un encontre amb el del costat, i a més els noms i els números d'una
mateixa partida no cauen sempre a la mateixa alçada: el nom pot quedar tres punts
més amunt que les seves caramboles. Per això aquí no es llegeixen línies sinó
PARAULES AMB LA SEVA POSICIÓ, i cada encontre es reconstrueix per columnes:

    equip local                 2   6    equip visitant
    jugador local       40  29   8       jugador visitant
    ...                 ...
    Prom. Gral: 0,821   128 156 128      Prom. Gral: 0,821

Les tres columnes de números del mig són caramboles del local, entrades i
caramboles del visitant. La primera fila hi porta el resultat de l'encontre i
l'última els totals; les del mig són les partides. Els jugadors es casen amb les
seves partides PER ORDRE, no per alçada.

No s'endevina res: si un encontre no té tants jugadors com partides, o li falten
números, es diu amb un error en lloc de tornar una cosa plausible.

Només la PRIMERA DIVISIÓ, de moment. La Divisió d'Honor i la Segona es publiquen
amb una altra disposició —pàgina vertical, un encontre per fila— i aquí donen
`FormatDesconegut`.

Dues coses que aquest mòdul NO ha de fer mai, i que valen per a tot el que es
construeixi a sobre:

  · No lliga cap jugador ni cap equip amb el cens de la federació catalana. La
    llicència espanyola i la catalana són independents: es pot jugar la lliga
    catalana amb un club i la nacional amb un altre, i les dues coses són
    veritat alhora. Aquí els noms es queden tal com els escriu la RFEB.
  · No alimenta cap rànquing ni cap mitjana de la federació catalana. Les
    partides de la lliga nacional no compten per al rànquing català, i
    barrejar-les el falsejaria.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

_MESOS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

#: Fins a quants punts d'alçada dues paraules es consideren de la mateixa línia.
_TOLERANCIA_Y = 2.5

#: Separació horitzontal a partir de la qual dos números són de columnes diferents.
_SALT_DE_COLUMNA = 12.0

#: Fins on arriba un encontre per sota de la línia dels «Prom. Gral:». Els totals
#: s'hi escriuen a la mateixa alçada o fins a una dotzena de punts més avall, segons
#: l'any; el resultat de l'encontre següent no comença fins força més enllà.
_MARGE_DELS_TOTALS = 14.0

_RE_ENTER = re.compile(r"^\d+$")
_RE_DECIMAL = re.compile(r"^\d+,\d+$")
_RE_DATA = re.compile(r"(\d{1,2})\s+de\s+([a-zñ]+)\s+de\s+(\d{4})", re.IGNORECASE)
_RE_JORNADA = re.compile(r"JORNADA\s+(\d+)", re.IGNORECASE)


class FormatDesconegut(ValueError):
    """El PDF no té la forma que s'esperava. No se n'aprofita res a mitges."""


@dataclass(frozen=True)
class FilaDeClassificacio:
    """Un equip a la classificació del seu grup després d'una jornada."""

    posicio: int
    equip: str
    jugats: int
    guanyats: int
    empatats: int
    perduts: int
    caramboles: int
    entrades: int
    mitjana: float
    #: Partides guanyades, sumades entre tots els encontres.
    parcials: int
    punts: int


@dataclass(frozen=True)
class PartidaNacional:
    """Una partida d'un encontre, entre un jugador de cada equip."""

    ordre: int
    jugador_local: str
    caramboles_local: int
    jugador_visitant: str
    caramboles_visitant: int
    entrades: int


@dataclass(frozen=True)
class EncontreNacional:
    """Un encontre entre dos equips, amb les seves partides."""

    local: str
    visitant: str
    #: Partides guanyades per cada equip: 6-2, 4-4, 8-0.
    punts_local: int
    punts_visitant: int
    caramboles_local: int
    caramboles_visitant: int
    entrades: int
    mitjana_local: float | None
    mitjana_visitant: float | None
    partides: list[PartidaNacional] = field(default_factory=list)


@dataclass(frozen=True)
class GrupDeJornada:
    """Un grup en una jornada: com queda la classificació i què s'hi ha jugat."""

    #: La lletra del grup, o `None` a les divisions d'un sol grup.
    grup: str | None
    classificacio: list[FilaDeClassificacio] = field(default_factory=list)
    encontres: list[EncontreNacional] = field(default_factory=list)


@dataclass(frozen=True)
class MillorSerie:
    jugador: str
    equip: str
    serie: int


@dataclass(frozen=True)
class Jornada:
    numero: int
    data: date | None
    grups: list[GrupDeJornada] = field(default_factory=list)
    millors_series: list[MillorSerie] = field(default_factory=list)


@dataclass(frozen=True)
class JugadorClassificat:
    """Un jugador a la classificació individual d'una divisió."""

    posicio: int
    jugador: str
    equip: str
    jugades: int
    guanyades: int
    empatades: int
    perdudes: int
    caramboles: int
    entrades: int
    mitjana: float
    punts: int


# --------------------------- paraules i línies ---------------------------


@dataclass(frozen=True)
class _Paraula:
    text: str
    x0: float
    x1: float
    y: float

    @property
    def centre(self) -> float:
        return (self.x0 + self.x1) / 2


def _paraules(pagina) -> list[_Paraula]:
    return [
        _Paraula(w["text"], float(w["x0"]), float(w["x1"]), float(w["top"]))
        for w in pagina.extract_words(x_tolerance=2, y_tolerance=2, keep_blank_chars=False)
    ]


def _linies(paraules: list[_Paraula]) -> list[list[_Paraula]]:
    """Les paraules agrupades per alçada, de dalt a baix i d'esquerra a dreta."""
    linies: list[list[_Paraula]] = []
    for p in sorted(paraules, key=lambda p: (p.y, p.x0)):
        if linies and abs(p.y - linies[-1][0].y) <= _TOLERANCIA_Y:
            linies[-1].append(p)
        else:
            linies.append([p])
    return [sorted(linia, key=lambda p: p.x0) for linia in linies]


def _text(paraules: list[_Paraula]) -> str:
    return " ".join(p.text for p in sorted(paraules, key=lambda p: p.x0)).strip()


def _decimal(text: str) -> float:
    return float(text.replace(".", "").replace(",", "."))


def _te_minuscules(text: str) -> bool:
    return any(c.islower() for c in text)


# --------------------------- capçalera ---------------------------


def _capcalera(linies: list[list[_Paraula]]) -> tuple[int, date | None] | None:
    """El número de jornada i la data, de la línia «JORNADA 1ª - 12 de … de 2026»."""
    for linia in linies[:4]:
        text = _text(linia)
        m = _RE_JORNADA.search(text)
        if not m:
            continue
        quan = None
        d = _RE_DATA.search(text)
        if d and d.group(2).lower() in _MESOS:
            quan = date(int(d.group(3)), _MESOS[d.group(2).lower()], int(d.group(1)))
        return int(m.group(1)), quan
    return None


# --------------------------- classificació del grup ---------------------------


def _classificacio(
    linies: list[list[_Paraula]],
) -> tuple[list[FilaDeClassificacio], str | None, float]:
    """La taula de dalt de la pàgina. Torna també la lletra del grup i on s'acaba."""
    cap = next(
        (li for li in linies if {"EQUIPO", "PTOS."} <= {p.text for p in li}),
        None,
    )
    if cap is None:
        raise FormatDesconegut("No trobo la capçalera de la classificació (EQUIPO … PTOS.).")
    # La primera columna és «Nº». Si no hi és, la capçalera és d'una altra taula
    # —la de jugadors també diu EQUIPO i PTOS.— i això no és una jornada.
    num = next((p for p in cap if p.text.startswith("N")), None)
    if num is None:
        raise FormatDesconegut("La taula no és la classificació d'un grup (falta la columna Nº).")
    x_equip = num.x0
    x_numeros = next(p.x0 for p in cap if p.text == "J") - 6

    files: list[FilaDeClassificacio] = []
    grup: str | None = None
    final = cap[0].y
    for linia in linies:
        if linia[0].y <= cap[0].y:
            continue
        numeros = [p for p in linia if p.x0 >= x_numeros]
        if len(numeros) != 9 or not all(
            _RE_ENTER.match(p.text) or _RE_DECIMAL.match(p.text) for p in numeros
        ):
            # La primera línia que ja no és una fila de la taula l'acaba, tret de
            # les que només porten el rètol del grup, que hi van intercalades.
            if files and not _es_al_marge(linia, x_equip):
                break
            continue
        resta = [p for p in linia if p.x0 < x_numeros]
        # La paraula «GRUPO» i la lletra del grup s'escriuen a l'esquerra de la
        # taula, a l'alçada d'una de les files: no són part del nom de l'equip.
        esquerra = [p for p in resta if p.x1 < x_equip - 2]
        for p in esquerra:
            if re.fullmatch(r"[A-Z]", p.text):
                grup = p.text
        dins = [p for p in resta if p.x1 >= x_equip - 2]
        if not dins or not _RE_ENTER.match(dins[0].text):
            raise FormatDesconegut(f"Fila de classificació sense posició: {_text(linia)!r}")
        j, g, e, per, car, ent, mit, parc, pts = (p.text for p in numeros)
        files.append(
            FilaDeClassificacio(
                posicio=int(dins[0].text),
                equip=_text(dins[1:]),
                jugats=int(j),
                guanyats=int(g),
                empatats=int(e),
                perduts=int(per),
                caramboles=int(car),
                entrades=int(ent),
                mitjana=_decimal(mit),
                parcials=int(parc),
                punts=int(pts),
            )
        )
        final = linia[0].y
    if grup is None:
        # La lletra pot anar sola en una línia, entre dues files de la taula.
        for linia in linies:
            if cap[0].y < linia[0].y <= final and _es_lletra_de_grup(linia, x_equip):
                grup = next(p.text for p in linia if re.fullmatch(r"[A-Z]", p.text))
    if not files:
        raise FormatDesconegut("La classificació del grup no té cap fila.")
    return files, grup, final


def _es_al_marge(linia: list[_Paraula], x_equip: float) -> bool:
    """La línia només porta el rètol del grup («GRUPO», «A»), a l'esquerra de la taula."""
    return all(p.x1 < x_equip - 2 for p in linia)


def _es_lletra_de_grup(linia: list[_Paraula], x_equip: float) -> bool:
    return _es_al_marge(linia, x_equip) and any(re.fullmatch(r"[A-Z]", p.text) for p in linia)


# --------------------------- encontres ---------------------------


def _columnes(numeros: list[_Paraula]) -> list[list[_Paraula]]:
    """Els números d'un encontre, repartits per columnes d'esquerra a dreta."""
    columnes: list[list[_Paraula]] = []
    for p in sorted(numeros, key=lambda p: p.centre):
        if columnes and p.centre - columnes[-1][-1].centre <= _SALT_DE_COLUMNA:
            columnes[-1].append(p)
        else:
            columnes.append([p])
    return [sorted(c, key=lambda p: p.y) for c in columnes]


def _encontre(paraules: list[_Paraula], on: str) -> EncontreNacional | None:
    """Un encontre, de les paraules de la seva meitat de bloc. `None` si és buida."""
    if not paraules:
        return None
    enters = [p for p in paraules if _RE_ENTER.match(p.text)]
    cols = _columnes(enters)
    if len(cols) != 3:
        raise FormatDesconegut(
            f"{on}: esperava tres columnes de números (caramboles, entrades, caramboles) "
            f"i n'hi ha {len(cols)}."
        )
    car_local, entrades, car_visitant = cols

    x_esquerra = min(p.x0 for p in car_local)
    x_dreta = max(p.x1 for p in car_visitant)
    paraules_de_nom = [
        p
        for p in paraules
        if not _RE_ENTER.match(p.text)
        and not _RE_DECIMAL.match(p.text)
        and p.text not in {"Prom.", "Gral:"}
    ]

    def costat(es_local: bool) -> tuple[str, list[str]]:
        seves = [p for p in paraules_de_nom if (p.x1 < x_esquerra if es_local else p.x0 > x_dreta)]
        equip: list[str] = []
        jugadors: list[str] = []
        for linia in _linies(seves):
            text = _text(linia)
            # Els equips van en majúscules; els jugadors, no. És l'única cosa que
            # els distingeix, perquè el nom d'un equip llarg salta de línia i pot
            # quedar a sota del resultat.
            (jugadors if _te_minuscules(text) else equip).append(text)
        return " ".join(equip), jugadors

    local, jugadors_local = costat(True)
    visitant, jugadors_visitant = costat(False)
    if not local or not visitant:
        raise FormatDesconegut(f"{on}: falta el nom d'un dels dos equips.")
    # Quantes partides hi ha ho diuen els jugadors. Les columnes de caramboles
    # porten a més el resultat a dalt, i totes tres els totals a baix: però els
    # totals no hi són cada any (el 2018 no s'escrivien), i llavors es calculen.
    n = len(jugadors_local)
    if n < 1 or len(jugadors_visitant) != n:
        raise FormatDesconegut(
            f"{on} ({local} - {visitant}): {len(jugadors_local)} jugadors locals i "
            f"{len(jugadors_visitant)} visitants."
        )
    amb_totals = len(entrades) == n + 1
    esperats = n + 2 if amb_totals else n + 1
    if (
        len(entrades) not in (n, n + 1)
        or len(car_local) != esperats
        or len(car_visitant) != esperats
    ):
        raise FormatDesconegut(
            f"{on} ({local} - {visitant}): {n} partides però els números no quadren "
            f"({len(car_local)} / {len(entrades)} / {len(car_visitant)})."
        )
    partides = [
        PartidaNacional(
            ordre=i + 1,
            jugador_local=jugadors_local[i],
            caramboles_local=int(car_local[i + 1].text),
            jugador_visitant=jugadors_visitant[i],
            caramboles_visitant=int(car_visitant[i + 1].text),
            entrades=int(entrades[i].text),
        )
        for i in range(n)
    ]

    def total(columna: list[_Paraula], de_les_partides: int) -> int:
        return int(columna[-1].text) if amb_totals else de_les_partides

    mitjanes = sorted((p for p in paraules if _RE_DECIMAL.match(p.text)), key=lambda p: p.x0)
    return EncontreNacional(
        local=local,
        visitant=visitant,
        punts_local=int(car_local[0].text),
        punts_visitant=int(car_visitant[0].text),
        caramboles_local=total(car_local, sum(p.caramboles_local for p in partides)),
        caramboles_visitant=total(car_visitant, sum(p.caramboles_visitant for p in partides)),
        entrades=total(entrades, sum(p.entrades for p in partides)),
        mitjana_local=_decimal(mitjanes[0].text) if len(mitjanes) >= 1 else None,
        mitjana_visitant=_decimal(mitjanes[-1].text) if len(mitjanes) >= 2 else None,
        partides=partides,
    )


def _encontres(paraules: list[_Paraula], des_de: float, amplada: float, on: str):
    """Tots els encontres d'una pàgina, que van de dos en dos sota la classificació."""
    sota = [p for p in paraules if p.y > des_de + _TOLERANCIA_Y]
    # Cada parella d'encontres s'acaba a la línia dels «Prom. Gral:», amb els totals.
    finals = sorted({round(p.y, 1) for p in sota if p.text == "Prom."})
    talls: list[float] = []
    for y in finals:
        if not talls or y - talls[-1] > 6 * _TOLERANCIA_Y:
            talls.append(y)
    mig = amplada / 2
    out: list[EncontreNacional] = []
    inici = des_de
    for i, y in enumerate(talls):
        fi = y + _MARGE_DELS_TOTALS
        bloc = [p for p in sota if inici < p.y <= fi]
        for costat, meitat in (
            ("esquerra", [p for p in bloc if p.centre < mig]),
            ("dreta", [p for p in bloc if p.centre >= mig]),
        ):
            e = _encontre(meitat, f"{on}, fila {i + 1}, {costat}")
            if e is not None:
                out.append(e)
        inici = fi
    return out


# --------------------------- millors sèries ---------------------------


def _millors_series(paraules: list[_Paraula], amplada: float) -> list[MillorSerie]:
    """La taula «MEJORES SERIES DE LA JORNADA», a la meitat esquerra de l'última pàgina."""
    titol = next((p for p in paraules if p.text == "MEJORES"), None)
    if titol is None:
        return []
    esquerra = [p for p in paraules if p.centre < amplada / 2 and p.y > titol.y + _TOLERANCIA_Y]
    out: list[MillorSerie] = []
    pendent: list[_Paraula] = []
    for linia in _linies(esquerra):
        pendent += linia
        series = [p for p in linia if _RE_ENTER.match(p.text)]
        if not series:
            continue
        serie = max(series, key=lambda p: p.x0)
        noms = sorted((p for p in pendent if p is not serie), key=lambda p: p.x0)
        # El jugador i l'equip són dues columnes: el salt gros entre paraules les separa.
        tall = max(range(1, len(noms)), key=lambda i: noms[i].x0 - noms[i - 1].x1, default=0)
        if tall:
            out.append(
                MillorSerie(
                    jugador=_text(noms[:tall]), equip=_text(noms[tall:]), serie=int(serie.text)
                )
            )
        pendent = []
    return out


# --------------------------- entrades públiques ---------------------------


def llegeix_jornada(cami: str | Path) -> Jornada:
    """Llegeix el PDF d'una jornada. Llança `FormatDesconegut` si no té la forma esperada."""
    import pdfplumber

    grups: list[GrupDeJornada] = []
    series: list[MillorSerie] = []
    capcalera: tuple[int, date | None] | None = None
    with pdfplumber.open(str(cami)) as pdf:
        for num, pagina in enumerate(pdf.pages, start=1):
            paraules = _paraules(pagina)
            if not paraules:
                continue
            linies = _linies(paraules)
            capcalera = capcalera or _capcalera(linies)
            if any(p.text == "MEJORES" for p in paraules):
                series = _millors_series(paraules, float(pagina.width))
                continue
            files, grup, final = _classificacio(linies)
            grups.append(
                GrupDeJornada(
                    grup=grup,
                    classificacio=files,
                    encontres=_encontres(paraules, final, float(pagina.width), f"pàgina {num}"),
                )
            )
    if capcalera is None:
        raise FormatDesconegut("No trobo la línia «JORNADA …» a cap pàgina.")
    if not grups:
        raise FormatDesconegut("El PDF no porta cap grup.")
    return Jornada(numero=capcalera[0], data=capcalera[1], grups=grups, millors_series=series)


def llegeix_classificacio_de_jugadors(cami: str | Path) -> list[JugadorClassificat]:
    """Llegeix el PDF «CLASIFICACIÓN DE JUGADORES» d'una divisió."""
    import pdfplumber

    out: list[JugadorClassificat] = []
    with pdfplumber.open(str(cami)) as pdf:
        x_equip = x_numeros = None
        for pagina in pdf.pages:
            for linia in _linies(_paraules(pagina)):
                textos = {p.text for p in linia}
                if {"JUGADOR", "EQUIPO"} <= textos:
                    x_equip = next(p.x0 for p in linia if p.text == "EQUIPO") - 3
                    x_numeros = next(p.x0 for p in linia if p.text == "J") - 6
                    continue
                if x_equip is None or x_numeros is None:
                    continue
                numeros = [p for p in linia if p.x0 >= x_numeros]
                if len(numeros) != 8 or not _RE_ENTER.match(linia[0].text):
                    continue
                j, g, e, per, car, ent, mit, pts = (p.text for p in numeros)
                # La capçalera «EQUIPO» va centrada sobre la columna i no diu on
                # comença: el nom de l'equip arrenca més a l'esquerra. El que separa
                # el jugador de l'equip és el salt més gros entre dues paraules.
                noms = [p for p in linia[1:] if p.x0 < x_numeros]
                if len(noms) < 2:
                    continue
                tall = max(range(1, len(noms)), key=lambda i: noms[i].x0 - noms[i - 1].x1)
                out.append(
                    JugadorClassificat(
                        posicio=int(linia[0].text),
                        jugador=_text(noms[:tall]),
                        equip=_text(noms[tall:]),
                        jugades=int(j),
                        guanyades=int(g),
                        empatades=int(e),
                        perdudes=int(per),
                        caramboles=int(car),
                        entrades=int(ent),
                        mitjana=_decimal(mit),
                        punts=int(pts),
                    )
                )
    if not out:
        raise FormatDesconegut("El PDF no porta cap fila de la classificació de jugadors.")
    return out
