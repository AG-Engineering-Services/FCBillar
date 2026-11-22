"""Classificacions finals dels campionats individuals de carambola de la RFEB.

Els PDF són de la web vella de la RFEB (una carpeta `noticiasAAAA` per any, que ja
no hi és i se'n recuperen les còpies de Wayback Machine). Cada campionat, gran
premi o open en penja un amb la classificació final: una taula d'una línia per
jugador, amb la capçalera que li va tocar aquell any.

Les capçaleres no són sempre les mateixes (`# NOMBRE FED J G E P CAR. ENT. PROM.
S.M. PTOS.`, `# RONDA NOMBRE FED J G E P CAR. ENT. PROM. PTOS.`, `Clasif. Jugadores
Federación T-Car. T.Entr. Prom. Gral. Ptos.`…). Per això el lector no sap cap
format: llegeix la capçalera, hi assigna a cada columna el que vol dir, i desa
els números de cada fila segons aquest ordre.

No s'endevina res. Una fila amb més o menys números que la capçalera, una
federació que no és al vocabulari o una línia que comença amb número i no és
fila fan fallar el fitxer sencer amb `FormatDesconegut`: més val no tenir una
prova que tenir-ne una amb la meitat dels jugadors desplaçats.

Només es desa la classificació FINAL. Les fases parcials (`_fp`, `_ff`…) es
descarten quan hi ha el fitxer principal de la mateixa prova.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from fcbillar.lliga_nacional import FormatDesconegut


class SenseTaula(FormatDesconegut):
    """El PDF no porta cap taula de classificació de jugadors que sapiguem llegir."""


# ---------------------------------------------------------------- capçalera

#: Etiqueta de la capçalera (en minúscula) → columna que té al darrere.
#: `None` vol dir que la columna no porta cap número que desem.
_NUMERIQUES = {
    "j": "jugades",
    "p.j.": "jugades",
    "jug": "jugades",
    "jug.": "jugades",
    "g": "guanyades",
    "p.g.": "guanyades",
    "gan": "guanyades",
    "e": "empatades",
    "p.e.": "empatades",
    "emp": "empatades",
    "p": "perdudes",
    "p.p.": "perdudes",
    "perd": "perdudes",
    "car": "caramboles",
    "car.": "caramboles",
    "caramb.": "caramboles",
    "carambolas": "caramboles",
    "t-car.": "caramboles",
    "t.car.": "caramboles",
    "ent": "entrades",
    "ent.": "entrades",
    "entr.": "entrades",
    "entrad.": "entrades",
    "entradas": "entrades",
    "t.entr.": "entrades",
    "prom": "mitjana",
    "prom.": "mitjana",
    "pro.": "mitjana",
    "promedio": "mitjana",
    "p.gral": "mitjana",
    "pr.gral.": "mitjana",
    "s.m.": "serie_major",
    "s.m": "serie_major",
    "sm": "serie_major",
    "ptos": "punts",
    "ptos.": "punts",
    "puntos": "punts",
}
_POSICIO = {"#", "nº", "nº.", "n°", "pos.", "clasif.", "clasif"}
_RONDA = {"ronda"}
_NOM = {"nombre", "jugador", "jugadores", "apellidos"}
_FED = {"fed", "fed.", "federación", "federeción", "comunidad", "c.a.", "país"}
#: La posició repetida al final de la fila («1º»): no porta cap dada nova.
_RANG_FINAL = {"cls", "clas", "clasificacion"}
_COLUMNES_NUMERIQUES = (
    "jugades",
    "guanyades",
    "empatades",
    "perdudes",
    "caramboles",
    "entrades",
    "mitjana",
    "serie_major",
    "punts",
)


@dataclass(frozen=True)
class Capcalera:
    """Què vol dir cada columna d'una taula, tal com la diu la seva capçalera."""

    etiquetes: tuple[str, ...]
    posicio_davant: bool
    rang_final: bool
    ronda: bool
    fed: bool
    #: Les columnes numèriques, per ordre de la capçalera.
    numeriques: tuple[str, ...]


def _minuscula(token: str) -> str:
    return token.lower()


def _tokens_de_capcalera(linia: str) -> list[str] | None:
    """Les etiquetes de la línia ja unides, o `None` si no és una capçalera."""
    brut = [_minuscula(t) for t in linia.split()]
    out: list[str] = []
    i = 0
    while i < len(brut):
        t = brut[i]
        seguent = brut[i + 1] if i + 1 < len(brut) else ""
        # «Prom. Gral.», «S M»: dues paraules, una sola columna.
        if t in {"prom.", "prom"} and seguent in {"gral.", "gral"}:
            out.append("prom.")
            i += 2
            continue
        if t == "s" and seguent == "m":
            out.append("sm")
            i += 2
            continue
        if t in {"gral.", "gral"} and out and out[-1] == "prom.":
            i += 1
            continue
        if (
            t in _NUMERIQUES
            or t in _POSICIO
            or t in _RONDA
            or t in _NOM
            or t in _FED
            or t in _RANG_FINAL
        ):
            out.append(t)
        else:
            return None
        i += 1
    return out


def llegeix_capcalera(linia: str) -> Capcalera | None:
    """La capçalera d'una taula de classificació, o `None` si la línia no ho és.

    Una línia és capçalera només si TOTES les seves paraules són etiquetes
    conegudes: una línia de dades que s'hi ha enganxat, com els `Jugadores Fed …
    Clas 3 ALFONSO GIL MUR…` de les fases de grups, no ho és.
    """
    tokens = _tokens_de_capcalera(linia)
    if not tokens:
        return None
    numeriques = tuple(_NUMERIQUES[t] for t in tokens if t in _NUMERIQUES)
    if "caramboles" not in numeriques or "entrades" not in numeriques:
        return None
    if len(set(numeriques)) != len(numeriques):
        return None
    return Capcalera(
        etiquetes=tuple(tokens),
        posicio_davant=tokens[0] in _POSICIO,
        rang_final=tokens[-1] in _RANG_FINAL or (len(tokens) > 1 and tokens[-1] in _POSICIO),
        ronda="ronda" in tokens,
        fed=any(t in _FED for t in tokens),
        numeriques=numeriques,
    )


# --------------------------------------------------------------- federacions


def _sense_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _clau_fed(text: str) -> str:
    """`Com.Valenciana`, `COM. VALENCIANA` i `com valenciana` són la mateixa clau."""
    return re.sub(r"[^A-Z0-9]", "", _sense_accents(text).upper())


_FEDERACIONS = {
    "CAT": ("CAT", "CATALANA", "CATALUNA", "CATALUNYA"),
    "VAL": (
        "VAL",
        "VALENCIANA",
        "VALEN",
        "COMVALENCIANA",
        "COMUNIDADVALENCIANA",
        "VALENCIA",
    ),
    "MAD": ("MAD", "MADRID", "MADRILENA", "MADRILEÑA"),
    "AND": ("AND", "ANDALUZA", "ANDALUCIA"),
    "MUR": ("MUR", "MURC", "MURCIA", "MURCIANA", "RDEMURCIA"),
    "BAL": ("BAL", "BALEAR", "BALEARES"),
    "GAL": ("GAL", "GALICIA", "GALLEGA"),
    "CLE": ("CLE", "LEO", "CLEO", "CLEON", "CYL", "CASTILLAYLEON"),
    "NAV": ("NAV", "NAVARRA"),
    "CLM": ("CLM", "CMAN", "CASTILLALAMANCHA", "CASTILLALAMA"),
    "VASC": ("VASC", "VAASC", "VASCA", "PAISVASCO", "VAS"),
    "AST": ("AST", "ASTURIAS", "ASTURIANA"),
    "ARAG": ("ARAG", "ARA", "ARG", "ARAGONESA", "ARAGON"),
    "EXT": ("EXT", "EXTR", "EXTREMADURA", "EXTREMENA"),
    "CANT": ("CANT", "CANTABRIA", "CANTABRA"),
    "PORT": ("PORT",),
    "RIO": ("RIO", "RIOJA", "LARIOJA", "RIOJANA"),
    "CAN": ("CAN", "CANARIAS", "CANARIA"),
}
_FED_PER_CLAU = {_clau_fed(v): sigla for sigla, vs in _FEDERACIONS.items() for v in vs}
_FEDS_LLARGUES = sorted((k for k in _FED_PER_CLAU if len(k) >= 7), key=len, reverse=True)


def normalitza_fed(text: str) -> str | None:
    """`Catalana`, `Cat` i `(CAT)` → `CAT`. `None` si no és cap federació coneguda."""
    return _FED_PER_CLAU.get(_clau_fed(text.strip("()")))


# ---------------------------------------------------------------------- files

_RE_POSICIO = re.compile(r"^(\d+)\s*[ºª°]?(?:\s+|$)")
_RE_RANG = re.compile(r"^\d+\s*[ºª°]?$")
#: La ronda fins a la qual ha arribat el jugador: FF, Q, PQ-2º, PPQ-3º, PPPQ…
#: («F. Prev.» són dues paraules i es tracta a part).
_RE_RONDA = re.compile(r"^(?:FF|FP(?:-\d[ºª°])?|P{0,5}Q(?:\*|-?\d[ºª°]?)?)$")
#: A les taules sense posició, la fase a què ha arribat: F, 1/2, 1/4, P2…
_RE_FASE = re.compile(r"^(?:F|\d/\d{1,2}|P\d)$")
_RE_ENTER = re.compile(r"^-?\d+$")
_RE_DECIMAL = re.compile(r"^-?\d+[.,]\d+$")
_NO_JUGA = {
    "INCOMPARECENCIA",
    "RETIRADO",
    "RETIRADA",
    "PENDIENTE",
    "ABANDONO",
    "JUSTIFICADO",
    "WO",
    "NP",
}


@dataclass(frozen=True)
class Fila:
    posicio: int
    jugador: str
    fed: str | None = None
    ronda: str | None = None
    #: La posició que comparteix amb un altre jugador, quan el PDF la diu.
    posicio_empat: int | None = None
    jugades: int | None = None
    guanyades: int | None = None
    empatades: int | None = None
    perdudes: int | None = None
    caramboles: int | None = None
    entrades: int | None = None
    mitjana: float | None = None
    serie_major: int | None = None
    punts: int | None = None


def _desdobla(linia: str) -> str:
    """Una línia on cada lletra surt dues vegades («CCaatt») torna a ser una de sola.

    Alguns PDF tenen la línia escrita dues vegades una sobre l'altra i
    l'extracció en treu cada caràcter duplicat. Només es desfà si TOTES les
    paraules de la línia són així; una paraula sola amb lletres dobles («Aaron»,
    «Anna») no es toca.
    """
    tokens = linia.split()
    if len(tokens) < 3:
        return linia
    out: list[str] = []
    for t in tokens:
        if len(t) % 2 == 0 and t[0::2] == t[1::2]:
            out.append(t[0::2])
            continue
        # «1166º»: el «º» pot haver sortit una sola vegada.
        cua = t[-1] if t[-1] in "ºª°" else ""
        cos = t[: len(t) - len(cua)]
        if not cua or not cos or len(cos) % 2 or cos[0::2] != cos[1::2]:
            return linia
        out.append(cos[0::2] + cua)
    return " ".join(out)


def _desdobla_nom(nom: str) -> str:
    """«JJoosséé AAllbbeerrtt TToorrnneerroo» torna a ser «José Albert Tornero».

    A `_desdobla` només es desfà la línia sencera; hi ha files on només el nom va
    escrit dues vegades i els números no. Només es toca si TOTES les paraules del
    nom (en són almenys dues) tenen cada lletra repetida.
    """
    tokens = nom.split()
    if len(tokens) < 2 or not all(len(t) % 2 == 0 and t[0::2] == t[1::2] for t in tokens):
        return nom
    return " ".join(t[0::2] for t in tokens)


def _es_enter(text: str) -> bool:
    return bool(_RE_ENTER.match(text))


def _numero(text: str, columna: str) -> int | float | None:
    if text == "-" and columna == "serie_major":
        return None
    if columna == "mitjana":
        if _RE_DECIMAL.match(text) or _RE_ENTER.match(text):
            return float(text.replace(",", "."))
    elif _RE_ENTER.match(text):
        return int(text)
    raise ValueError(text)


def _clau_paraula(token: str) -> str:
    return re.sub(r"[^A-Z]", "", _sense_accents(token).upper())


def _comenca_no_juga(tokens: list[str]) -> int | None:
    """On comença «NO PRESENTADO», «INCOMPARECENCIA …», «W.O.»…, o `None`."""
    for i, t in enumerate(tokens):
        k = _clau_paraula(t)
        if k in _NO_JUGA and i >= 2:
            return i
        no_presentat = i >= 2 and i + 1 < len(tokens) and k == "NO"
        if no_presentat and _clau_paraula(tokens[i + 1]).startswith("PRESENTAD"):
            return i
    return None


def llegeix_fila(linia: str, cap: Capcalera) -> Fila:
    """Una fila de la taula segons la seva capçalera. `FormatDesconegut` si no quadra."""
    linia = _desdobla(linia.strip())
    # «(*)»: la crida a una nota al peu, que no és cap dada.
    resta = re.sub(r"\s*\(\*+\)\s*$", "", linia)
    posicio: int | None = None
    m = _RE_POSICIO.match(resta)
    if m:
        posicio = int(m.group(1))
        resta = resta[m.end() :]
    tokens = resta.split()

    rang: int | None = None
    if cap.rang_final:
        if not tokens or not _RE_RANG.match(tokens[-1]):
            raise FormatDesconegut(f"Fila sense la posició del final: {linia!r}")
        rang = int(re.sub(r"\D", "", tokens[-1]))
        tokens = tokens[:-1]
    if posicio is None:
        posicio = rang
    if posicio is None:
        raise FormatDesconegut(f"Fila sense posició: {linia!r}")

    fase: str | None = None
    if not m and tokens and _RE_FASE.match(tokens[0]):
        fase, tokens = tokens[0], tokens[1:]

    # Qui no ha jugat no porta números: una frase («INCOMPARECENCIA JUSTIFICADA»)
    # i, de vegades, els punts de penalització.
    on = _comenca_no_juga(tokens)
    if on is not None:
        return _fila_que_no_juga(posicio, tokens, on, cap, linia, fase)

    # Un nom sense cap número: també és algú que no ha jugat.
    if not any(re.search(r"\d", t) for t in tokens):
        return _fila_de_text(posicio, tokens, {}, cap, linia, fase, juga=False)

    n = len(cap.numeriques)
    intents = [tokens]
    # El sub-17 repeteix la posició al final sense dir-ho a la capçalera.
    if (
        not cap.rang_final
        and cap.fed
        and tokens
        and _es_enter(tokens[-1])
        and int(tokens[-1]) == posicio
    ):
        intents.append(tokens[:-1])
    llegides: list[Fila] = []
    motius: list[str] = []
    for ts in intents:
        try:
            llegides.append(_fila_de_tokens(posicio, ts, n, cap, linia, fase))
        except FormatDesconegut as e:
            motius.append(str(e))
    if len(llegides) == 1:
        return llegides[0]
    if not llegides:
        raise FormatDesconegut(motius[0])
    raise FormatDesconegut(f"Fila ambigua (la posició del final és o no és una dada): {linia!r}")


def _fila_de_tokens(
    posicio: int, tokens: list[str], n: int, cap: Capcalera, linia: str, fase: str | None
) -> Fila:
    if len(tokens) <= n:
        raise FormatDesconegut(f"Fila amb menys de {n} números ({len(tokens)} paraules): {linia!r}")
    cru = tokens[-n:]
    valors: dict[str, int | float | None] = {}
    for col, t in zip(cap.numeriques, cru, strict=True):
        try:
            valors[col] = _numero(t, col)
        except ValueError:
            raise FormatDesconegut(
                f"Fila amb «{t}» on hi va «{col}» (capçalera {' '.join(cap.etiquetes)}): {linia!r}"
            ) from None
    return _fila_de_text(posicio, tokens[:-n], valors, cap, linia, fase)


def _fila_que_no_juga(
    posicio: int, tokens: list[str], on: int, cap: Capcalera, linia: str, fase: str | None
) -> Fila:
    davant, frase = tokens[:on], tokens[on:]
    # Els zeros d'abans de la frase («0 0 0 0 W.O.») no diuen res.
    while davant and davant[-1] == "0":
        davant = davant[:-1]
    valors: dict[str, int | float] = {}
    if frase and _es_enter(frase[-1]):
        if "punts" in cap.numeriques:
            valors["punts"] = int(frase[-1])
        frase = frase[:-1]
    if any(re.search(r"\d", t) for t in frase):
        raise FormatDesconegut(f"Fila amb números a dins de «{' '.join(frase)}»: {linia!r}")
    return _fila_de_text(posicio, davant, valors, cap, linia, fase, juga=False)


def _fila_de_text(
    posicio: int,
    text: list[str],
    valors: dict[str, int | float],
    cap: Capcalera,
    linia: str,
    fase: str | None,
    *,
    juga: bool = True,
) -> Fila:
    empat: int | None = None
    if text and text[0].isdigit() and len(text) > 1:
        empat = int(text[0])
        text = text[1:]
    ronda: str | None = fase
    if cap.ronda:
        # «F. Prev.» són dues paraules.
        if text[:2] == ["F.", "Prev."]:
            ronda, text = "F. Prev.", text[2:]
        elif text and _RE_RONDA.match(text[0]):
            ronda, text = text[0], text[1:]
        elif juga:
            raise FormatDesconegut(f"Fila sense ronda: {linia!r}")

    fed: str | None = None
    if cap.fed:
        fed, text = _treu_fed(text, linia)
    elif text and re.fullmatch(r"\(\w+\)", text[-1]):
        # Sense columna de federació, de vegades va entre parèntesis al nom.
        fed = normalitza_fed(text[-1])
        if fed is None:
            raise FormatDesconegut(f"Federació desconeguda {text[-1]!r}: {linia!r}")
        text = text[:-1]
    # «DAVID ZAPATA (23)»: un número entre parèntesis darrere del nom, que no diu res.
    while text and re.fullmatch(r"\(\d+\)", text[-1]):
        text = text[:-1]
    nom = _desdobla_nom(" ".join(text).strip())
    if not nom:
        raise FormatDesconegut(f"Fila sense nom: {linia!r}")
    return Fila(
        posicio=posicio,
        jugador=nom,
        fed=fed,
        ronda=ronda,
        posicio_empat=empat,
        jugades=valors.get("jugades"),  # type: ignore[arg-type]
        guanyades=valors.get("guanyades"),  # type: ignore[arg-type]
        empatades=valors.get("empatades"),  # type: ignore[arg-type]
        perdudes=valors.get("perdudes"),  # type: ignore[arg-type]
        caramboles=valors.get("caramboles"),  # type: ignore[arg-type]
        entrades=valors.get("entrades"),  # type: ignore[arg-type]
        mitjana=valors.get("mitjana"),  # type: ignore[arg-type]
        serie_major=valors.get("serie_major"),  # type: ignore[arg-type]
        punts=valors.get("punts"),  # type: ignore[arg-type]
    )


_RE_FED_ENGANXADA = re.compile(r"^(.+?[a-zñáéíóúü.])([A-ZÁÉÍÓÚ][a-záéíóú]{1,4})$")


def _treu_fed(text: list[str], linia: str) -> tuple[str, list[str]]:
    """La federació del final del text, la més llarga que sigui al vocabulari."""
    for n in (4, 3, 2, 1):
        if len(text) > n:
            fed = normalitza_fed("".join(text[-n:]))
            if fed:
                return fed, text[:-n]
    # «BermejoMad»: el PDF a vegades s'ha menjat l'espai entre el cognom i la federació.
    if text:
        m = _RE_FED_ENGANXADA.match(text[-1])
        if m and (fed := normalitza_fed(m.group(2))):
            return fed, [*text[:-1], m.group(1)]
        # «MISIUKONISVALENCIANA»: en majúscules no hi ha límit de paraula, però
        # les formes llargues («VALENCIANA») no són mai el final d'un cognom.
        clau = _clau_fed(text[-1])
        for llarga in _FEDS_LLARGUES:
            if clau.endswith(llarga) and len(clau) > len(llarga) + 1:
                tall = len(text[-1]) - len(llarga)
                return _FED_PER_CLAU[llarga], [*text[:-1], text[-1][:tall]]
    raise FormatDesconegut(f"Federació desconeguda al final de «{' '.join(text)}»: {linia!r}")


# --------------------------------------------------------------------- taula

_TITOL_FINAL = re.compile(r"CLASS?IFICACION(?: FINAL| GENERAL)?(?: DEL TORNEO)?", re.IGNORECASE)


def _es_titol_de_final(linia: str) -> bool:
    """«CLASIFICACIÓN FINAL» (o sense «FINAL»), però no la d'un grup, ni provisional."""
    net = _sense_accents(linia).strip()
    # «C L A S I F I C A C I Ó N»: les lletres separades.
    if re.fullmatch(r"(?:[A-Za-z] ){5,}[A-Za-z]", net):
        net = net.replace(" ", "")
    return _TITOL_FINAL.fullmatch(net) is not None


@dataclass(frozen=True)
class Taula:
    capcalera: Capcalera
    files: list[Fila]
    #: Les línies d'abans de la capçalera de la primera pàgina, per al títol.
    previ: list[str] = field(default_factory=list)


def _linies(pagina: str) -> list[str]:
    return [_desdobla(x.strip()) for x in pagina.split("\n") if x.strip()]


def llegeix_taula(pagines: list[str]) -> Taula:
    """La taula de la classificació final, de totes les pàgines que la porten.

    La primera capçalera que té al davant un títol de classificació final (o que
    comença amb «Clasif.», la del sub-17, que no en porta) és la taula. Una
    pàgina següent només hi pertany si comença amb la mateixa capçalera: les de
    fases de grups que venen després en tenen una altra, o cap.
    """
    llistes = [_linies(p) for p in pagines]
    inici: tuple[int, int] | None = None
    cap: Capcalera | None = None
    for p, linies in enumerate(llistes):
        for i, linia in enumerate(linies):
            c = llegeix_capcalera(linia)
            if c is None:
                continue
            davant = linies[max(0, i - 3) : i]
            es_la_del_sub17 = c.posicio_davant and c.etiquetes[0] == "clasif."
            if es_la_del_sub17 or any(_es_titol_de_final(x) for x in davant):
                inici, cap = (p, i), c
                break
        if cap:
            break
    if inici is None or cap is None:
        raise SenseTaula("No trobo cap taula de classificació final de jugadors amb capçalera.")

    p0, i0 = inici
    previ = llistes[p0][:i0]
    try:
        files = _files_de(llistes, p0, i0, cap)
    except FormatDesconegut as e:
        if not cap.fed or not str(e).startswith("Federació desconeguda"):
            raise
        # Hi ha taules on la columna de federació és buida a totes les files
        # («C.A.» del sub-15). Només es dóna per bona si a cap fila el nom
        # acaba en una federació: si no, és una fila malament, no una columna buida.
        cap = replace(cap, fed=False)
        files = _files_de(llistes, p0, i0, cap)
        for f in files:
            try:
                _treu_fed(f.jugador.split(), f.jugador)
            except FormatDesconegut:
                continue
            raise e from None
    return Taula(cap, files, previ)


def _files_de(llistes: list[list[str]], p0: int, i0: int, cap: Capcalera) -> list[Fila]:
    files: list[Fila] = []
    for p in range(p0, len(llistes)):
        linies = llistes[p]
        if p == p0:
            comenca = i0 + 1
        else:
            # La pàgina continua la taula només si en repeteix la capçalera.
            pos = next(
                (
                    k
                    for k, x in enumerate(linies[:6])
                    if (c := llegeix_capcalera(x)) and c.etiquetes == cap.etiquetes
                ),
                None,
            )
            if pos is None:
                break
            comenca = pos + 1
        acabada = False
        for linia in linies[comenca:]:
            veredicte = _es_fila(linia, cap)
            if veredicte is None:
                acabada = True
                break
            if veredicte:
                files.append(llegeix_fila(linia, cap))
        if acabada:
            break
    if not files:
        raise FormatDesconegut("La taula no té cap fila.")
    vistes: set[tuple[int, str]] = set()
    for f in files:
        if (f.posicio, f.jugador) in vistes:
            raise FormatDesconegut(f"«{f.jugador}» surt dues vegades a la posició {f.posicio}.")
        vistes.add((f.posicio, f.jugador))
    return files


def _es_fila(linia: str, cap: Capcalera) -> bool | None:
    """`True` si és una fila, `False` si s'ha d'ignorar, `None` si la taula s'ha acabat.

    Una fila porta nom: una línia de només números és el total del peu de la
    taula, i la taula s'ha acabat. Una línia que comença amb número i no és ni
    una cosa ni l'altra sí que és un error, i ho diu `llegeix_fila`.
    """
    if "#" in linia or not re.search(r"[A-Za-zÀ-ÿ]", linia):
        # A les taules amb la posició al final, un número solt entre dues files
        # és brossa del PDF que no porta cap dada.
        if cap.rang_final and re.fullmatch(r"\d{1,3}", linia):
            return False
        return None
    if _RE_POSICIO.match(linia):
        return True
    tokens = linia.split()
    if cap.rang_final and _RE_RANG.match(tokens[-1]):
        return True
    return None


# ------------------------------------------------------------ metadades

_MESOS = {
    "enero": 1,
    "ene": 1,
    "febrero": 2,
    "feb": 2,
    "marzo": 3,
    "mar": 3,
    "abril": 4,
    "abr": 4,
    "mayo": 5,
    "may": 5,
    "junio": 6,
    "jun": 6,
    "julio": 7,
    "jul": 7,
    "agosto": 8,
    "ago": 8,
    "septiembre": 9,
    "setiembre": 9,
    "sep": 9,
    "sept": 9,
    "octubre": 10,
    "oct": 10,
    "noviembre": 11,
    "nov": 11,
    "diciembre": 12,
    "dic": 12,
}
_MES = r"(" + "|".join(sorted(_MESOS, key=len, reverse=True)) + r")\.?"
_ANY = r"(\d{4}|\d\.\d{3})"
#: «del 1 al 6 de Julio de 2014», «3 y 4 DE FEBRERO DE 2018», «12-15 ENERO 2017»,
#: «del 26 Oct. al 01 de Noviembre 2015», «DEL 31 DE ENERO AL 3 DE FEBRERO DE 2013».
_RE_DATA_RANG = re.compile(
    rf"(?<![\d/])(?:del\s+)?(\d{{1,2}})(?:\s+(?:de\s+)?{_MES})?\s*(?:y|al|a|-)\s*(\d{{1,2}})"
    rf"\s+(?:de\s+)?{_MES}\s*(?:de\s+)?{_ANY}",
    re.IGNORECASE,
)
#: Una llista de dies d'un sol mes: «19, 20 y 21 ENERO 2018», «24-25-26 FEB.2017».
_RE_DATA_LLISTA = re.compile(
    rf"(?<![\d/])(\d{{1,2}}(?:\s*(?:,|-|y|al|a)\s*\d{{1,2}}){{2,}})\s+(?:de\s+)?{_MES}\s*"
    rf"(?:de\s+)?{_ANY}",
    re.IGNORECASE,
)
_RE_DATA_UNICA = re.compile(
    rf"(?<![\d/])(\d{{1,2}})\s+(?:de\s+)?{_MES}\s*(?:de\s+)?{_ANY}", re.IGNORECASE
)


def _any(text: str) -> int:
    return int(text.replace(".", ""))


def _data(d: int, mes: str, any_: int) -> date | None:
    try:
        return date(any_, _MESOS[mes.lower()], d)
    except ValueError:
        return None


#: Una línia que parla d'una fase o d'un grup dóna la data d'aquesta fase, no la del campionat.
_RE_NO_ES_LA_DATA = re.compile(r"GRUP|FASE|RONDA|CALIFICACI|CLASS?IFICACI", re.IGNORECASE)
_RE_MES_I_ANY = re.compile(rf"^\W*{_MES}\W*(\d{{4}})\W*$", re.IGNORECASE)


def _dates_de_linia(linia: str) -> tuple[date, date, str | None] | None:
    """(inici, fi, lloc) si la línia diu uns dies concrets d'un mes i un any."""
    m = _RE_DATA_LLISTA.search(linia)
    if m:
        dies, mes, a = m.groups()
        nums = [int(d) for d in re.findall(r"\d+", dies)]
        ini, fi = _data(nums[0], mes, _any(a)), _data(nums[-1], mes, _any(a))
        if ini and fi and ini <= fi:
            return ini, fi, _lloc(linia[: m.start()])
        return None
    m = _RE_DATA_RANG.search(linia)
    if m:
        d1, m1, d2, m2, a = m.groups()
        fi = _data(int(d2), m2, _any(a))
        ini = _data(int(d1), m1 or m2, _any(a))
        if ini and fi:
            if ini > fi:
                # «del 30 de Diciembre al 2 de Enero de 2025»
                ini = _data(int(d1), m1 or m2, _any(a) - 1)
            if ini and ini <= fi:
                return ini, fi, _lloc(linia[: m.start()])
        return None
    m = _RE_DATA_UNICA.search(linia)
    if m:
        d1, m1, a = m.groups()
        dia = _data(int(d1), m1, _any(a))
        if dia:
            return dia, dia, _lloc(linia[: m.start()])
    return None


def cerca_dates(linies: list[str]) -> tuple[date, date, str | None] | None:
    """(inici, fi, lloc) de la primera línia que diu quan s'ha jugat."""
    for linia in linies:
        if _RE_NO_ES_LA_DATA.search(_sense_accents(linia)):
            continue
        trobat = _dates_de_linia(linia)
        if trobat:
            return trobat
    return None


_DIES_SETMANA = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
}
#: «SABADO 17 DE OCTUBRE»: el dia de la setmana, sense any.
_RE_DIA_SETMANA = re.compile(
    rf"(?<![A-Za-z])(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\s+"
    rf"(\d{{1,2}})\s+(?:de\s+)?{_MES}(?![a-z])",
    re.IGNORECASE,
)


def data_amb_dia_de_la_setmana(linia: str, temporada: str) -> date | None:
    """«VIERNES 16 DE OCTUBRE» dins la temporada `2015-2016`: el dia del 2015.

    L'any no hi és, però el dia de la setmana el confirma: només es dóna per bona
    la data de la temporada que cau en aquell dia de la setmana. Si no hi cau, no
    es diu res.
    """
    m = _RE_DIA_SETMANA.search(linia)
    if not m:
        return None
    dia_setmana, d, mes = m.groups()
    inici = int(temporada[:4])
    mes_num = _MESOS[mes.lower()]
    dia = _data(int(d), mes, inici if mes_num >= 8 else inici + 1)
    clau = _sense_accents(dia_setmana).lower()
    if dia is None or dia.weekday() != _DIES_SETMANA[clau]:
        return None
    return dia


def dates_de_fases(linies: list[str], temporada: str) -> list[tuple[date, date]]:
    """Els dies que diuen les línies d'una capçalera de fase («GRUPOS 12-15 ENERO 2017»).

    A diferència de `cerca_dates`, aquí una línia de grups o de fase final SÍ és
    bona: és el tros del campionat que ella cobreix.
    """
    out: list[tuple[date, date]] = []
    for linia in linies:
        trobat = _dates_de_linia(linia)
        if trobat:
            out.append((trobat[0], trobat[1]))
            continue
        dia = data_amb_dia_de_la_setmana(linia, temporada)
        if dia:
            out.append((dia, dia))
    return out


def cerca_mes_i_any(linies: list[str]) -> date | None:
    """«DIC. 2021»: un mes sense dia, només per saber a quina temporada és."""
    for linia in linies:
        m = _RE_MES_I_ANY.match(linia)
        if m:
            return _data(1, m.group(1), int(m.group(2)))
    return None


def _lloc(abans: str) -> str | None:
    lloc = re.sub(r"^\W*FECHA\W*", "", abans.strip(), flags=re.IGNORECASE)
    lloc = re.sub(r"[\s,;:\-\u2013]+$", "", lloc)
    lloc = re.sub(r"[\s,]*\bdel?$", "", lloc, flags=re.IGNORECASE).strip(" ,")
    lloc = re.sub(r"[\s,;:\-\u2013]+$", "", lloc)
    # Un lloc és un nom, no una frase ni un número.
    if not lloc or re.search(r"\d", lloc) or len(lloc) > 60:
        return None
    if lloc.isupper():
        lloc = lloc.title()
    return lloc


def temporada_de(dia: date) -> str:
    """`2014-2015` per a un dia entre l'1 d'agost del 2014 i el 31 de juliol del 2015."""
    inici = dia.year if dia.month >= 8 else dia.year - 1
    return f"{inici}-{inici + 1}"


def temporada_de_carpeta(carpeta: str) -> str:
    """`noticias2015` és la temporada 2015-2016; `noticias`, sense any, la 2012-2013."""
    m = re.search(r"(\d{4})$", carpeta)
    inici = int(m.group(1)) if m else 2012
    return f"{inici}-{inici + 1}"


#: «CE-Msc-3B-Sb17-Res-290910», «Inscritos_CE_3B-080612»: el dia (ddmmaa) al final del nom.
_RE_DATA_AL_NOM = re.compile(r"(?:^|[-_])(\d{2})(\d{2})(\d{2})(?:$|[-_])")


def data_del_nom(nom: str) -> date | None:
    """El dia que porta el nom d'un fitxer de la web vella, escrit ddmmaa.

    És el dia en què es va penjar el resultat, no el que comença el campionat:
    serveix per saber a quina temporada és i res més.
    """
    for m in _RE_DATA_AL_NOM.finditer(nom):
        dia, mes, any_ = (int(g) for g in m.groups())
        try:
            return date(2000 + any_, mes, dia)
        except ValueError:
            continue
    return None


def temporada_sense_data(carpeta: str, nom: str) -> str:
    """La temporada d'un PDF que no diu quan es va jugar.

    A `noticiasAAAA` la diu la carpeta. A qualsevol altra carpeta (`0HOME/PDF`,
    on hi ha de tots els anys barrejats) només la pot dir el dia que porta el nom
    del fitxer; si no en porta, no s'endevina: `FormatDesconegut`.
    """
    if re.fullmatch(r"noticias(\d{4})?", carpeta.rsplit("/", 1)[-1]):
        return temporada_de_carpeta(carpeta)
    dia = data_del_nom(nom)
    if dia is None:
        raise FormatDesconegut(
            f"«{carpeta}/{nom}» no diu la temporada: ni la carpeta, ni el PDF, ni el nom porten data."
        )
    return temporada_de(dia)


# ------------------------------------------------- modalitat, categoria, tipus

_MODALITATS = (
    (
        "3b",
        re.compile(r"(?<![a-z0-9])3b(?![a-z0-9])|tres\s*bandas|3\s*bandas|bilbao", re.IGNORECASE),
    ),
    ("47_2", re.compile(r"47[-_/]2|c47|cuadro\s*47", re.IGNORECASE)),
    ("71_2", re.compile(r"71[-_/]2|c71|cuadro\s*71", re.IGNORECASE)),
    ("5q", re.compile(r"5\s*quillas|(?<![a-z0-9])5q(?![a-z0-9])|cinco\s*quillas", re.IGNORECASE)),
    ("artistic", re.compile(r"art[ií]stico|(?<![a-z])art(?![a-z])", re.IGNORECASE)),
    ("lliure", re.compile(r"(?<![a-z])lib(?:re)?(?![a-z])", re.IGNORECASE)),
    ("banda", re.compile(r"(?<![a-z])banda(?![a-z])", re.IGNORECASE)),
)
_CATEGORIES = (
    ("femeni", re.compile(r"(?<![a-z])fem(?:enin[oa])?(?![a-z])", re.IGNORECASE)),
    (
        "sub15",
        re.compile(
            r"sub[-'.\s]*15|(?<![a-z])sb[-'.\s]*15(?![0-9])|(?<![a-z0-9])s15(?![a-z0-9])",
            re.IGNORECASE,
        ),
    ),
    (
        "sub17",
        re.compile(
            r"sub[-'.\s]*17|(?<![a-z])sb[-'.\s]*17(?![0-9])|(?<![a-z0-9])s17(?![a-z0-9])",
            re.IGNORECASE,
        ),
    ),
    (
        "sub21",
        re.compile(
            r"sub[-'.\s]*21|(?<![a-z])sb[-'.\s]*21(?![0-9])|(?<![a-z0-9])s21(?![a-z0-9])",
            re.IGNORECASE,
        ),
    ),
    (
        "sub25",
        re.compile(
            r"sub[-'.\s]*25|(?<![a-z])sb[-'.\s]*25(?![0-9])|(?<![a-z0-9])s25(?![a-z0-9])",
            re.IGNORECASE,
        ),
    ),
    ("infantil", re.compile(r"infantil(?:es)?|(?<![a-z])inf(?![a-z])", re.IGNORECASE)),
    ("junior", re.compile(r"j[uú]nior(?:es)?|(?<![a-z])jr(?![a-z])", re.IGNORECASE)),
    ("senior", re.compile(r"s[eé]nior(?:es)?", re.IGNORECASE)),
)


def _primer(opcions, *textos: str) -> str | None:
    """La primera opció que surt, mirant els textos per ordre (primer el nom del fitxer)."""
    for text in textos:
        for valor, regex in opcions:
            if regex.search(text):
                return valor
    return None


def tipus_de(nom: str, titol: str) -> str:
    """`ce` (Campionat d'Espanya), `gpe` (Gran Premi d'Espanya) o `altres` (opens)."""
    tokens = set(re.split(r"[_\-]", nom.lower()))
    if tokens & {"gpe"} or any(re.fullmatch(r"gp\d*", t) for t in tokens):
        return "gpe"
    if tokens & {"ce", "ceu", "cm"}:
        return "ce"
    if re.search(r"gran\s+premio", titol, re.IGNORECASE):
        return "gpe"
    if re.search(r"campeonato\s+de\s+espa", titol, re.IGNORECASE):
        return "ce"
    return "altres"


@dataclass(frozen=True)
class Metadades:
    modalitat: str
    categoria: str
    tipus: str


def metadades_de(nom: str, titol: str) -> Metadades:
    """Modalitat, categoria i tipus: del nom del fitxer, i si no del títol del PDF."""
    modalitat = _primer(_MODALITATS, nom, titol)
    if modalitat is None:
        raise FormatDesconegut(f"No sé la modalitat de «{nom}» ({titol[:60]!r}).")
    categoria = _primer(_CATEGORIES, nom, titol) or "absolut"
    return Metadades(modalitat, categoria, tipus_de(nom, titol))


_NOM_MODALITAT = {
    "3b": "tres bandes",
    "banda": "banda",
    "lliure": "lliure",
    "47_2": "quadre 47/2",
    "71_2": "quadre 71/2",
    "artistic": "artístic",
    "5q": "cinc quilles",
}
_NOM_TIPUS = {"ce": "Campionat d'Espanya", "gpe": "Gran Premi d'Espanya", "altres": "Prova"}


_RE_DIA_I_MES = re.compile(rf"(?<!\d)\d{{1,2}}\s+(?:de\s+)?{_MES}(?![a-z])", re.IGNORECASE)


def _parla_de_dates(linia: str) -> bool:
    return cerca_dates([linia]) is not None or bool(_RE_DIA_I_MES.search(linia))


def _es_linia_de_titol(linia: str) -> bool:
    """Una línia del títol té alguna paraula de debò i no és una data ni una fase."""
    return (
        bool(re.search(r"[A-Za-zÀ-ÿ']{4,}", linia))
        and not _parla_de_dates(linia)
        and not _RE_NO_ES_LA_DATA.search(_sense_accents(linia))
    )


def titol_de(linies: list[str], meta: Metadades, nom: str, temporada: str) -> str:
    """El títol que diu el PDF, o un de construït si no en diu cap."""
    titol: list[str] = []
    for linia in linies:
        if re.search(r"CLASS?IFICACI", _sense_accents(linia), re.I) or _parla_de_dates(linia):
            break
        if _es_linia_de_titol(linia):
            titol.append(linia)
    text = re.sub(r"\s+", " ", " ".join(titol[:3])).strip()
    if len(text) >= 12:
        return text
    base = f"{_NOM_TIPUS[meta.tipus]} de {_NOM_MODALITAT[meta.modalitat]}"
    if meta.categoria != "absolut":
        base += f" {meta.categoria}"
    if meta.tipus == "ce":
        return f"{base} {temporada}"
    return f"{base} ({nom})"


# --------------------------------------------------------------------- prova


@dataclass(frozen=True)
class Prova:
    id: str
    temporada: str
    modalitat: str
    categoria: str
    tipus: str
    titol: str
    lloc: str | None
    data_inici: str | None
    data_fi: str | None
    font: str
    files: list[Fila]

    def signatura(self) -> tuple:
        """El que fa que dues proves siguin la mateixa: modalitat, categoria i les files."""
        return (
            self.modalitat,
            self.categoria,
            tuple((f.posicio, _clau_fed(f.jugador), f.caramboles, f.entrades) for f in self.files),
        )


def _capcalera_del_document(pagines: list[str]) -> list[str]:
    """Les primeres línies de la primera pàgina, fins que comença la taula o un grup."""
    out: list[str] = []
    for linia in _linies(pagines[0])[:10] if pagines else []:
        if llegeix_capcalera(linia) or re.search(r"GRUPO|PARTIDOS", linia):
            break
        out.append(linia)
    return out


#: Quants dies com a màxim pot durar un campionat: més que això vol dir que les
#: dates de les fases són de coses diferents i no se'n treu cap.
_MAX_DIES_DE_PROVA = 14

#: Els sufixos dels fitxers de fase d'una prova (`_fp`, `_ff`, `_prov`…).
_RE_FASE_GERMANA = re.compile(r"_(?:fp|ff|fc|q|pq|prov|all|cuad)(?:_[a-z]+)?$")


def es_fase_de(nom_prova: str, nom_fitxer: str) -> bool:
    """`res_ce_3b_s17_fp` és una fase de `res_ce_3b_s17`, però `res_ce_3b_s15` no."""
    if not nom_fitxer.startswith(nom_prova + "_"):
        return False
    m = _RE_FASE_GERMANA.search(nom_fitxer[len(nom_prova) :])
    return m is not None and m.start() == 0


def _dates_del_campionat(
    pagines: list[str], germanes: list[list[str]], temporada: str
) -> tuple[date, date] | None:
    """Els dies del campionat segons les capçaleres de les fases, quan el PDF principal no en té.

    Es mira el principi de la primera pàgina del PDF i de cada fase germana: el
    primer dia és el de la primera fase (grups) i l'últim el de la darrera (fase
    final). Només es dona per bo si tot cap en el que pot durar un campionat; unes
    dates que no hi caben són de coses diferents.
    """
    capcaleres = [_linies(pagines[0])[:10] if pagines else [], *germanes]
    dates: list[tuple[date, date]] = []
    for linies in capcaleres:
        dates += dates_de_fases(linies, temporada)
    if not dates:
        return None
    ini = min(d[0] for d in dates)
    fi = max(d[1] for d in dates)
    if (fi - ini).days > _MAX_DIES_DE_PROVA:
        return None
    return ini, fi


def prova_de_pagines(
    pagines: list[str],
    carpeta: str,
    nom: str,
    germanes: list[list[str]] | None = None,
) -> Prova:
    """La prova d'un PDF ja llegit a text (separat de pdfplumber per provar-ho).

    `germanes` són les primeres línies dels PDF de fase de la mateixa prova
    (`_fp`, `_ff`…): molts campionats no diuen quan es van jugar al PDF de la
    classificació, però sí a la capçalera de les fases.
    """
    taula = llegeix_taula(pagines)
    # El títol i la data són a sobre de la taula; si la taula és a la segona
    # pàgina, a dalt de la primera.
    context = taula.previ or _capcalera_del_document(pagines)
    meta = metadades_de(nom, " ".join(context[:3]))
    dates = cerca_dates(context) or cerca_dates(_capcalera_del_document(pagines))
    mes = None if dates else cerca_mes_i_any(context)
    if dates:
        ini, fi, lloc = dates
        temporada = temporada_de(ini)
        data_inici, data_fi = ini.isoformat(), fi.isoformat()
    else:
        temporada = temporada_de(mes) if mes else temporada_sense_data(carpeta, nom)
        data_inici = data_fi = lloc = None
        de_fases = _dates_del_campionat(pagines, germanes or [], temporada)
        if de_fases:
            temporada = temporada_de(de_fases[0])
            data_inici, data_fi = de_fases[0].isoformat(), de_fases[1].isoformat()
    return Prova(
        id=f"{carpeta}/{nom}",
        temporada=temporada,
        modalitat=meta.modalitat,
        categoria=meta.categoria,
        tipus=meta.tipus,
        titol=titol_de(context, meta, nom, temporada),
        lloc=lloc,
        data_inici=data_inici,
        data_fi=data_fi,
        font=f"https://rfeb.org/{carpeta}/{nom}.pdf",
        files=taula.files,
    )


def llegeix_prova(cami: Path, arrel: Path) -> Prova:
    """La classificació final d'un PDF. `FormatDesconegut` si no se'n pot treure."""
    import pdfplumber

    carpeta = cami.parent.relative_to(arrel).as_posix()
    with pdfplumber.open(str(cami)) as pdf:
        pagines = [p.extract_text() or "" for p in pdf.pages]
    germanes: list[list[str]] = []
    for fase in sorted(cami.parent.glob(f"{cami.stem}_*.pdf")):
        if not es_fase_de(cami.stem, fase.stem):
            continue
        try:
            with pdfplumber.open(str(fase)) as pdf:
                germanes.append(_linies(pdf.pages[0].extract_text() or "")[:10])
        except Exception:
            # Una fase malmesa només es queda sense dates; la prova no en depèn.
            continue
    return prova_de_pagines(pagines, carpeta, cami.stem, germanes)
