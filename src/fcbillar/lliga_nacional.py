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


# --------------------------- desar ---------------------------

#: Les divisions de la Lliga Nacional, tal com es desen.
DIVISIONS = ("honor", "1", "2")


def temporada_de(dia: date) -> str:
    """La temporada d'un dia de joc: comença a l'agost. «2026-2027»."""
    inici = dia.year if dia.month >= 8 else dia.year - 1
    return f"{inici}-{inici + 1}"


def desa_jornada(conn, jornada: Jornada, divisio: str, temporada: str | None = None) -> str:
    """Desa una jornada sencera, reemplaçant el que hi hagués d'aquella jornada.

    La temporada surt de la data de la jornada; es pot donar a mà per als PDF
    que no en porten. Torna la temporada amb què s'ha desat.

    Només s'escriu a les taules `nacional_*`. No es toca cap jugador, cap club
    ni cap partida de la federació catalana: vegeu la capçalera del mòdul.
    """
    if divisio not in DIVISIONS:
        raise ValueError(f"Divisió desconeguda: {divisio!r}. Ha de ser una de {DIVISIONS}.")
    if temporada is None:
        if jornada.data is None:
            raise ValueError("La jornada no porta data: cal dir-ne la temporada.")
        temporada = temporada_de(jornada.data)
    quan = jornada.data.isoformat() if jornada.data else None
    clau = (temporada, divisio, jornada.numero)

    conn.execute(
        "DELETE FROM nacional_partides WHERE temporada = ? AND divisio = ? AND jornada = ?", clau
    )
    conn.execute(
        "DELETE FROM nacional_encontres WHERE temporada = ? AND divisio = ? AND jornada = ?", clau
    )
    conn.execute(
        "DELETE FROM nacional_classificacio WHERE temporada = ? AND divisio = ? AND jornada = ?",
        clau,
    )
    conn.execute(
        "DELETE FROM nacional_millors_series WHERE temporada = ? AND divisio = ? AND jornada = ?",
        clau,
    )
    for g in jornada.grups:
        grup = g.grup or ""
        conn.executemany(
            "INSERT INTO nacional_classificacio (temporada, divisio, grup, jornada, posicio, "
            "equip, jugats, guanyats, empatats, perduts, caramboles, entrades, mitjana, "
            "parcials, punts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    temporada,
                    divisio,
                    grup,
                    jornada.numero,
                    f.posicio,
                    f.equip,
                    f.jugats,
                    f.guanyats,
                    f.empatats,
                    f.perduts,
                    f.caramboles,
                    f.entrades,
                    f.mitjana,
                    f.parcials,
                    f.punts,
                )
                for f in g.classificacio
            ],
        )
        for ordre, e in enumerate(g.encontres, start=1):
            conn.execute(
                "INSERT INTO nacional_encontres (temporada, divisio, grup, jornada, ordre, data, "
                "local, visitant, punts_local, punts_visitant, caramboles_local, "
                "caramboles_visitant, entrades, mitjana_local, mitjana_visitant) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    temporada,
                    divisio,
                    grup,
                    jornada.numero,
                    ordre,
                    quan,
                    e.local,
                    e.visitant,
                    e.punts_local,
                    e.punts_visitant,
                    e.caramboles_local,
                    e.caramboles_visitant,
                    e.entrades,
                    e.mitjana_local,
                    e.mitjana_visitant,
                ),
            )
            conn.executemany(
                "INSERT INTO nacional_partides (temporada, divisio, grup, jornada, "
                "ordre_encontre, ordre, jugador_local, caramboles_local, jugador_visitant, "
                "caramboles_visitant, entrades) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        temporada,
                        divisio,
                        grup,
                        jornada.numero,
                        ordre,
                        p.ordre,
                        p.jugador_local,
                        p.caramboles_local,
                        p.jugador_visitant,
                        p.caramboles_visitant,
                        p.entrades,
                    )
                    for p in e.partides
                ],
            )
    conn.executemany(
        "INSERT INTO nacional_millors_series (temporada, divisio, jornada, ordre, jugador, "
        "equip, serie) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (temporada, divisio, jornada.numero, i, s.jugador, s.equip, s.serie)
            for i, s in enumerate(jornada.millors_series, start=1)
        ],
    )
    conn.commit()
    return temporada


def desa_classificacio_de_jugadors(
    conn, jugadors: list[JugadorClassificat], divisio: str, temporada: str
) -> int:
    """Desa la classificació de jugadors d'una divisió, reemplaçant la que hi hagués.

    És acumulada: cada PDF nou porta tota la temporada fins a aquell dia.
    """
    if divisio not in DIVISIONS:
        raise ValueError(f"Divisió desconeguda: {divisio!r}. Ha de ser una de {DIVISIONS}.")
    if not jugadors:
        raise ValueError("Cap jugador: no esborro la classificació que hi ha per posar-hi el buit.")
    conn.execute(
        "DELETE FROM nacional_jugadors WHERE temporada = ? AND divisio = ?", (temporada, divisio)
    )
    conn.executemany(
        "INSERT OR REPLACE INTO nacional_jugadors (temporada, divisio, posicio, jugador, equip, "
        "jugades, guanyades, empatades, perdudes, caramboles, entrades, mitjana, punts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                temporada,
                divisio,
                j.posicio,
                j.jugador,
                j.equip,
                j.jugades,
                j.guanyades,
                j.empatades,
                j.perdudes,
                j.caramboles,
                j.entrades,
                j.mitjana,
                j.punts,
            )
            for j in jugadors
        ],
    )
    conn.commit()
    return len(jugadors)


# --------------------------- alineacions ---------------------------
#
# L'«orden de fuerza» és el document on cada club diu quins jugadors té inscrits,
# per ordre. A més dels jugadors hi ha l'adreça del club i el nom, el telèfon i el
# correu del president i del director esportiu.
#
# D'aquí NOMÉS en surten els jugadors. No és una qüestió de què es desa després:
# les dades de contacte ni tan sols es llegeixen. Són a la banda esquerra de la
# pàgina, i tot el que queda a l'esquerra de les columnes de jugadors es descarta
# abans de mirar-ne el contingut. L'única cosa que s'agafa d'allà és el nom del
# club, que és a la línia que acaba amb la província entre parèntesis.


@dataclass(frozen=True)
class Alineacio:
    """Un jugador inscrit per un equip, amb el seu número d'ordre de força."""

    grup: str
    equip: str
    ordre: int
    jugador: str


_RE_TITOL_GRUP = re.compile(r"^(?:HONOR|PRIMERA|SEGUNDA)(?:\s+([A-Z]))?$")


def _alineacions_de_linies(linies: list[list[_Paraula]]) -> list[Alineacio]:
    """Les alineacions d'unes línies ja agrupades. Separat de pdfplumber per provar-ho."""
    # On comencen les columnes de jugadors: a la x del número més a l'esquerra que
    # obre una fila de jugadors. Tot el que hi ha abans no es mira.
    numeros = [p for linia in linies for p in linia if _RE_ENTER.match(p.text)]
    if not numeros:
        raise FormatDesconegut("No hi trobo cap número d'ordre de força.")
    # Els números d'ordre fan dues columnes verticals: són les dues x on més es
    # repeteixen els enters.
    recompte: dict[int, int] = {}
    for p in numeros:
        recompte[round(p.x0 / 6)] = recompte.get(round(p.x0 / 6), 0) + 1
    columnes = sorted(sorted(recompte, key=lambda k: -recompte[k])[:2])
    if len(columnes) < 2:
        raise FormatDesconegut("No distingeixo les dues columnes de jugadors.")
    x_primera = columnes[0] * 6 - 6
    x_segona = columnes[1] * 6 - 6

    out: list[Alineacio] = []
    grup = ""
    equip: str | None = None
    for linia in linies:
        text = _text(linia)
        titol = _RE_TITOL_GRUP.match(text)
        if titol:
            grup = titol.group(1) or ""
            equip = None
            continue
        # La línia del club: «C.B. MIJAS      Mijas (MÁLAGA)». A l'esquerra hi va el
        # nom, tot en majúscules, i a la dreta la població, que no interessa. No
        # es pot reconèixer per la província entre parèntesis, perquè no sempre
        # n'hi ha («C.B. SEVILLA      SEVILLA») i n'hi ha de dues paraules.
        #
        # Les línies de contacte que comparteixen aquella banda no hi encaixen
        # mai: porten minúscules, dos punts, una arrova o xifres.
        esquerra = [p for p in linia if p.x0 < x_primera]
        nom = _text(esquerra)
        if (
            esquerra
            and not _te_minuscules(nom)
            and not any(c in nom for c in ":@")
            and not any(_RE_ENTER.match(p.text) for p in linia)
        ):
            equip = nom
            continue
        if equip is None:
            continue
        # Només la banda dels jugadors. El que hi ha a l'esquerra no es toca.
        for inici, fi in ((x_primera, x_segona), (x_segona, float("inf"))):
            tram = [p for p in linia if inici <= p.x0 < fi]
            if len(tram) < 2 or not _RE_ENTER.match(tram[0].text):
                continue
            out.append(
                Alineacio(grup=grup, equip=equip, ordre=int(tram[0].text), jugador=_text(tram[1:]))
            )
    if not out:
        raise FormatDesconegut("El document no porta cap alineació.")
    return out


def llegeix_alineacions(cami: str | Path) -> list[Alineacio]:
    """Llegeix l'«orden de fuerza» d'una divisió. Només en treu els jugadors."""
    import pdfplumber

    linies: list[list[_Paraula]] = []
    with pdfplumber.open(str(cami)) as pdf:
        for pagina in pdf.pages:
            linies += _linies(_paraules(pagina))
    return _alineacions_de_linies(linies)


def escriu_alineacions_csv(alineacions: list[Alineacio], cami: str | Path) -> None:
    """Desa les alineacions en un CSV net, que és el que es pot guardar al repositori.

    El PDF original no s'hi ha de guardar: porta telèfons i correus. El CSV només
    té grup, equip, ordre i jugador.
    """
    import csv

    with open(cami, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["grup", "equip", "ordre", "jugador"])
        for a in alineacions:
            w.writerow([a.grup, a.equip, a.ordre, a.jugador])


def llegeix_alineacions_csv(cami: str | Path) -> list[Alineacio]:
    import csv

    with open(cami, encoding="utf-8", newline="") as f:
        return [
            Alineacio(grup=r["grup"], equip=r["equip"], ordre=int(r["ordre"]), jugador=r["jugador"])
            for r in csv.DictReader(f)
        ]


def desa_alineacions(conn, alineacions: list[Alineacio], divisio: str, temporada: str) -> int:
    """Desa les alineacions d'una divisió, reemplaçant les que hi hagués."""
    if divisio not in DIVISIONS:
        raise ValueError(f"Divisió desconeguda: {divisio!r}. Ha de ser una de {DIVISIONS}.")
    if not alineacions:
        raise ValueError("Cap alineació: no esborro les que hi ha per posar-hi el buit.")
    conn.execute(
        "DELETE FROM nacional_alineacions WHERE temporada = ? AND divisio = ?",
        (temporada, divisio),
    )
    conn.executemany(
        "INSERT OR REPLACE INTO nacional_alineacions (temporada, divisio, grup, equip, ordre, "
        "jugador) VALUES (?, ?, ?, ?, ?, ?)",
        [(temporada, divisio, a.grup, a.equip, a.ordre, a.jugador) for a in alineacions],
    )
    conn.commit()
    return len(alineacions)


# --------------------------- calendari ---------------------------


@dataclass(frozen=True)
class EncontreDeCalendari:
    """Un encontre del calendari de la temporada: encara sense resultat."""

    jornada: int
    data: date | None
    grup: str
    local: str
    visitant: str


_RE_DIA = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def _parella(paraules: list[_Paraula]) -> tuple[str, str] | None:
    """Local i visitant d'un tros de línia amb un sol guió entre tots dos."""
    guions = [i for i, p in enumerate(paraules) if p.text == "-"]
    if len(guions) != 1:
        return None
    local, visitant = _text(paraules[: guions[0]]), _text(paraules[guions[0] + 1 :])
    return (local, visitant) if local and visitant else None


def _encontres_de_linia(linia: list[_Paraula]) -> list[tuple[str, str]]:
    """Els dos encontres que el calendari escriu a cada línia, de costat.

    Cada encontre va centrat al seu guió: el visitant del primer comença arran del
    guió i el local del segon acaba arran del seu, o sigui que entre tots dos hi ha
    el forat més gran de la línia. Partir pel text no val: quan els noms són
    llargs s'enganxen («…Gandia 'B'Inviktcues…»).
    """
    guions = [i for i, p in enumerate(linia) if p.text == "-"]
    if len(guions) == 1:
        parella = _parella(linia)
        return [parella] if parella else []
    if len(guions) != 2:
        return []
    entremig = range(guions[0] + 1, guions[1] - 1)
    if not entremig:
        return []
    tall = max(entremig, key=lambda i: linia[i + 1].x0 - linia[i].x1) + 1
    parelles = [_parella(linia[:tall]), _parella(linia[tall:])]
    return [p for p in parelles if p]


def llegeix_calendari(cami: str | Path) -> list[EncontreDeCalendari]:
    """Llegeix el calendari d'una divisió: totes les jornades, amb dia i grup.

    Cada jornada són quatre línies d'encontres, dues per grup, amb la lletra del
    grup al marge entre les seves dues i el número i el dia de la jornada entre
    els dos grups. La lletra es busca per alçada, que és la que cau més a prop;
    la jornada, per ordre: cada vegada que es torna al primer grup n'ha començat
    una altra.
    """
    import pdfplumber

    sortida: list[EncontreDeCalendari] = []
    es_calendari = False
    with pdfplumber.open(str(cami)) as pdf:
        for pagina in pdf.pages:
            linies = _linies(_paraules(pagina))
            if any(_text(linia).upper() == "CALENDARIO" for linia in linies):
                es_calendari = True
            lletres = [
                (linia[0].y, linia[0].text)
                for linia in linies
                if len(linia) == 1 and re.fullmatch(r"[A-Z]", linia[0].text)
            ]
            jornades: list[tuple[int, date | None]] = []
            for linia in linies:
                if len(linia) == 2 and _RE_ENTER.match(linia[0].text):
                    dia = _RE_DIA.match(linia[1].text)
                    if dia:
                        d, m, a = (int(x) for x in dia.groups())
                        jornades.append((int(linia[0].text), date(a, m, d)))
            if not lletres or not jornades:
                continue
            primer = min(lletra for _, lletra in lletres)
            quina = -1
            anterior: str | None = None
            for linia in linies:
                parelles = _encontres_de_linia(linia)
                if not parelles:
                    continue
                grup = min(lletres, key=lambda ll: abs(ll[0] - linia[0].y))[1]
                if grup == primer and anterior != primer:
                    quina += 1
                anterior = grup
                if not 0 <= quina < len(jornades):
                    raise FormatDesconegut(
                        "Al calendari hi ha més blocs d'encontres que jornades amb data."
                    )
                numero, quan = jornades[quina]
                sortida.extend(
                    EncontreDeCalendari(numero, quan, grup, local, visitant)
                    for local, visitant in parelles
                )
    if not es_calendari or not sortida:
        raise FormatDesconegut("No és un calendari de la Lliga Nacional.")
    return sortida


def desa_calendari(conn, encontres: list[EncontreDeCalendari], divisio: str, temporada: str) -> int:
    """Desa els encontres del calendari de les jornades que encara no tenen resultat.

    Van a `nacional_encontres` sense punts, que és com es reconeix un encontre per
    jugar. Una jornada que ja té el seu PDF de resultats no es toca: allà mana el
    resultat, i `desa_jornada` ja en reemplaça el que hi hagués del calendari.
    Torna quants encontres ha desat.
    """
    if divisio not in DIVISIONS:
        raise ValueError(f"Divisió desconeguda: {divisio!r}. Ha de ser una de {DIVISIONS}.")
    jugades = {
        fila[0]
        for fila in conn.execute(
            "SELECT DISTINCT jornada FROM nacional_encontres "
            "WHERE temporada = ? AND divisio = ? AND punts_local IS NOT NULL",
            (temporada, divisio),
        )
    }
    desats = 0
    for jornada in sorted({e.jornada for e in encontres} - jugades):
        conn.execute(
            "DELETE FROM nacional_encontres WHERE temporada = ? AND divisio = ? AND jornada = ?",
            (temporada, divisio, jornada),
        )
        ordres: dict[str, int] = {}
        for e in encontres:
            if e.jornada != jornada:
                continue
            ordres[e.grup] = ordres.get(e.grup, 0) + 1
            conn.execute(
                "INSERT INTO nacional_encontres (temporada, divisio, grup, jornada, ordre, data, "
                "local, visitant) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    temporada,
                    divisio,
                    e.grup,
                    jornada,
                    ordres[e.grup],
                    e.data.isoformat() if e.data else None,
                    e.local,
                    e.visitant,
                ),
            )
            desats += 1
    conn.commit()
    return desats
