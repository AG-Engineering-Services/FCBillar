"""El palmarès: qui ha estat campió, subcampió i tercer de cada campionat.

Dues fonts, dos formats, i cap dels dos pensat per ser llegit per una màquina:

- **RFEB** (`rfeb.org/medallero`): un PDF per modalitat i categoria, amb una taula
  de línies dibuixades i una fila per edició: `edició | any | mes | seu | ciutat |
  nre. de jugadors | ORO + mitjana | PLATA + mitjana | BRONCE + mitjana`. Els
  noms són els que va escriure qui va fer la taula («Joaquín Domingo», «A.
  Trapé», «Josep Mª Mas») i no porten federació. Al final de cada PDF hi ha un
  «medallero» resum per jugador, que aquí no es llegeix: és el mateix dit d'una
  altra manera.
- **CEB** (`eurobillard.org`, «Rolls of Honors»): un PDF per competició, amb el
  text d'una edició darrere l'altra: `77) Ankara (TR) (10.-13.4.2025) 40/50 Pts.`
  i, a sota, els tres primers: `1. Martin Horn (DE) 10:0 250/123 2,032 2,500 12`.
  Un tercer ex aequo surt amb un altre «3.». La línia sense número que ve
  després és el quart: no és medalla. Els noms porten el país entre parèntesis.

Es llegeix amb prudència: una cosa que no quadra es **diu**, no s'endevina. Cada
lectura torna un `Informe` amb les medalles, quantes edicions s'han vist i totes
les línies o files que no s'han pogut llegir. Una edició amb una fila que no es
pot assignar amb seguretat a un lloc del podi (per exemple, un segon nom a la
columna d'or) no desa cap medalla i queda anotada.

A la taula de la RFEB, una fila d'edició té la primera cel·la com a text (buit o
amb la xifra romana) i una fila de continuació -el segon tercer d'un ex aequo-
la té sense cel·la. Això és el que les distingeix, no la posició.

El nom de la competició i la categoria no surten del PDF sinó del seu nom de
fitxer (`_RFEB` i `_CEB`): és el que fa que una mateixa competició quedi igual
d'un any a l'altre.

- **FCB** (`fcbillar.cat`, «Històric Quadre d'Honor»): un PDF per temporada des
  del 1961-62, amb una taula `modalitat | categoria | campió | club | subcampió |
  club`. Només hi ha campió i subcampió. El club es desa a `lloc`. Les primeres
  temporades (fins al 1964-65) tenen algunes competicions en format de llista
  (`1r | jugador | club`). Es llegeixen les modalitats individuals de
  carambola; les lligues, els interclubs, el pool i el snooker no.
"""

from __future__ import annotations

import csv
import re
import sqlite3
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

FONT_RFEB = "rfeb"
FONT_CEB = "ceb"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
URL_RFEB = "https://rfeb.org/wp-content/uploads/2026/10/{}"
URL_CEB = "https://www.eurobillard.org/medias/rolls-of-honors/{}"

#: Fitxer -> (competició, categoria) de la RFEB.
_RFEB: dict[str, tuple[str, str]] = {
    "rfeb-medallero-absoluto-3b.pdf": ("Tres bandes", "absolut"),
    "rfeb-medallero-femenino-3b.pdf": ("Tres bandes", "femení"),
    "rfeb-medallero-sub17-3b.pdf": ("Tres bandes", "sub-17"),
    "rfeb-medallero-sub21-3b.pdf": ("Tres bandes", "sub-21"),
    "rfeb-medallero-sub25-3b.pdf": ("Tres bandes", "sub-25"),
    "rfeb-medallero-libre.pdf": ("Lliure", "absolut"),
    "rfeb-medallero-banda.pdf": ("Una banda", "absolut"),
    "rfeb-medallero-cuadro-47-1.pdf": ("Quadre 47/1", "absolut"),
    "rfeb-medallero-cuadro-71-2.pdf": ("Quadre 71/2", "absolut"),
    "rfeb-medallero-artistico.pdf": ("Artístic", "absolut"),
}

#: Fitxer -> (competició, categoria) del CEB. Els campionats per equips, els de
#: parelles i la Copa d'Europa de clubs no hi són: no tenen un jugador per lloc.
_CEB: dict[str, tuple[str, str]] = {
    "ec-3-cushion-2026-04-11.pdf": ("Campionat d'Europa tres bandes", "absolut"),
    "ec-3-cushion-ladies-2026-04-10.pdf": ("Campionat d'Europa tres bandes", "femení"),
    "ec-3-cushion-juniors-2026-08-26.pdf": ("Campionat d'Europa tres bandes", "júnior"),
    "ec-3-cushion-u25-2026-10-29.pdf": ("Campionat d'Europa tres bandes", "sub-25"),
    "ec-3cushion-youth-u17-2026-08-26.pdf": ("Campionat d'Europa tres bandes", "sub-17"),
    "st-ec-3cushion-youth-u17-2024-04-08.pdf": (
        "Campionat d'Europa tres bandes (taula petita)",
        "sub-17",
    ),
    "ec-1-cushion-2026-04-10.pdf": ("Campionat d'Europa una banda", "absolut"),
    "ec-artistique-2026-04-10.pdf": ("Campionat d'Europa artístic", "absolut"),
    "ec-cadre-47-1-2026-09-23.pdf": ("Campionat d'Europa quadre 45/1 i 47/1", "absolut"),
    "ec-cadre-47-2-2026-09-23.pdf": ("Campionat d'Europa quadre 45/2 i 47/2", "absolut"),
    "ec-cadre-71-2-2026-09-23.pdf": ("Campionat d'Europa quadre 71/2", "absolut"),
    "ec-libre.pdf": ("Campionat d'Europa lliure", "absolut"),
    "ec-libre-ladies.pdf": ("Campionat d'Europa lliure", "femení"),
    "st-ec-libre-ladies.pdf": ("Campionat d'Europa lliure (taula petita)", "femení"),
    "st-ec-libre-youth-u17.pdf": ("Campionat d'Europa lliure (taula petita)", "sub-17"),
    "ec-juniors-libre-2023-05-04.pdf": ("Campionat d'Europa lliure", "júnior"),
    "ec-juniors-cadre-47-2.pdf": ("Campionat d'Europa quadre 47/2", "júnior"),
    "ec-juniors-libre-and-cadre-47-2.pdf": ("Campionat d'Europa lliure i quadre 47/2", "júnior"),
    "ec-5-pins-juniors-2026-08-27.pdf": ("Campionat d'Europa 5 quilles", "júnior"),
    "ec-5-pins-ladies-2026-04-11.pdf": ("Campionat d'Europa 5 quilles", "femení"),
    "ec-5-pins-ladies-u21-2026-08-27.pdf": ("Campionat d'Europa 5 quilles", "femení sub-21"),
    # Un sol PDF amb dues competicions: es parteix per la capçalera de la secció.
    "ec-pins-and-5-pins-2026-04-10.pdf": ("", "absolut"),
    "ceb-grand-prix-three-cushion-2026-04-26.pdf": ("Grand Prix CEB tres bandes", "absolut"),
    "ceb-grand-prix-youth-three-cushion-2026-05-17.pdf": ("Grand Prix CEB tres bandes", "joves"),
    # Dues competicions, la Copa d'Europa femenina i el Grand Prix: per seccions.
    "ceb-ladies-cup-3-cushion-grand-prix-2026-09-11.pdf": ("", "femení"),
    "ceb-grand-prix-one-cushion-2023-05-15.pdf": ("Grand Prix CEB una banda", "absolut"),
    "ceb-grand-prix-cadre-47-2-2023-05-15.pdf": ("Grand Prix CEB quadre 47/2", "absolut"),
    "ceb-grand-prix-cadre-71-2-2023-05-15.pdf": ("Grand Prix CEB quadre 71/2", "absolut"),
    "ceb-grand-prix-artistique-2026-06-03.pdf": ("Grand Prix CEB artístic", "absolut"),
    "ceb-grand-prix-youth-5-pins-2023-05-15.pdf": ("Grand Prix CEB 5 quilles", "joves"),
    "european-ladies-cup-libre-mb-2023-05-15.pdf": (
        "Copa d'Europa femenina lliure (matchbillard)",
        "femení",
    ),
}

#: Per als PDF que mesclen competicions, que la numeració reinicia a cada una: la
#: línia de capçalera de la secció -> la competició que hi comença.
_SECCIONS_CEB = {
    "The European Championships - Pins": "Campionat d'Europa pins",
    "The European Championships - 5-Pins": "Campionat d'Europa 5 quilles",
    "European Ladies Cup - Three Cushion": "Copa d'Europa femenina tres bandes",
    "CEB Grand Prix Ladies - Three Cushion": "Grand Prix CEB tres bandes",
}


@dataclass(frozen=True)
class Medalla:
    font: str
    competicio: str
    categoria: str
    edicio: str  # la xifra romana, o el número d'ordre si el PDF no en porta
    any_edicio: int | None
    lloc: str | None
    posicio: int  # 1, 2 o 3 (el tercer ex aequo en surt dos cops)
    jugador: str  # tal com ho escriu la font
    pais: str | None = None
    mitjana: float | None = None


@dataclass
class Informe:
    fitxer: str
    font: str
    edicions: int = 0
    medalles: list[Medalla] = field(default_factory=list)
    #: El que no s'ha pogut llegir: `(on, què)`. Mai s'endevina.
    no_llegit: list[tuple[str, str]] = field(default_factory=list)
    #: Notes del PDF que no són una dada (p. ex. «fins aquí era el quadre 45/1»).
    notes: list[str] = field(default_factory=list)
    #: Línies sense número que no són medalla (el quart lloc dels PDF del CEB).
    sense_podi: int = 0

    def resum(self) -> str:
        return (
            f"{self.fitxer}: {self.edicions} edicions, {len(self.medalles)} medalles, "
            f"{len(self.no_llegit)} sense llegir"
        )


# ---------------------------------------------------------------------------
# RFEB
# ---------------------------------------------------------------------------

_ROMANA = re.compile(r"^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
#: La marca d'aigua «EN CONSTRUCCIÓN» del sub-21 cau trossejada dins de les cel·les
#: d'una edició sense dades (1988). No és cap nom.
_MARCA_AIGUA = {"EN", "CONSTRUC", "CIÓ", "N"}
_MITJANA = re.compile(r"^(\d+(?:,\d+)?)\s*%?$")


def _text(cel) -> str:
    t = re.sub(r"\s+", " ", cel).strip() if isinstance(cel, str) else ""
    return "" if t in _MARCA_AIGUA else t


def _mitjana_rfeb(cel) -> tuple[float | None, bool]:
    """`(mitjana, ok)`: «0,501» -> 0.501, «55,76%» -> 55.76, buit -> `(None, True)`."""
    t = _text(cel)
    if not t:
        return None, True
    m = _MITJANA.match(t)
    if not m:
        return None, False
    return float(m.group(1).replace(",", ".")), True


def _columnes_rfeb(taula: list[list]) -> dict[str, int] | None:
    """On és cada columna, segons la capçalera de la taula; `None` si no és d'edicions.

    El sub-21 té una columna més a la primera pàgina, i per això no es compten
    posicions: es busquen els rètols. La taula de resum de cada PDF no té «ORO».
    """
    if len(taula) < 2:
        return None
    cap = [_text(c).upper() for c in taula[0]]
    if not {"ORO", "PLATA", "BRONCE"} <= set(cap):
        return None
    sub = [_text(c).upper() for c in taula[1]]
    try:
        return {
            "edicio": 0,
            "any": sub.index("AÑO"),
            "mes": sub.index("MES"),
            "sede": sub.index("SEDE"),
            "ciutat": sub.index("CIUDAD"),
            "oro": cap.index("ORO"),
            "plata": cap.index("PLATA"),
            "bronce": cap.index("BRONCE"),
        }
    except ValueError:
        return None


def llegeix_rfeb(cami: str | Path) -> Informe:
    """Llegeix un PDF de «medallero» de la RFEB. Vegeu el mòdul."""
    import pdfplumber

    cami = Path(cami)
    competicio, categoria = _RFEB[cami.name]
    with pdfplumber.open(cami) as pdf:
        pagines = [pagina.extract_tables() for pagina in pdf.pages]
    return llegeix_taules_rfeb(pagines, competicio, categoria, cami.name)


def llegeix_taules_rfeb(
    pagines: list[list[list[list]]], competicio: str, categoria: str, fitxer: str = ""
) -> Informe:
    """El mateix, des de les taules de cada pàgina (és el que es prova)."""
    inf = Informe(fitxer=fitxer, font=FONT_RFEB)
    cols: dict[str, int] | None = None
    actual: dict | None = None

    def tanca() -> None:
        nonlocal actual
        if actual is None:
            return
        e = actual
        actual = None
        if e["ambigua"]:
            inf.no_llegit.append(
                (
                    f"edició {e['edicio']} ({e['any']})",
                    "dades dubtoses (més d'un nom a or o plata, o text superposat): no es desa",
                )
            )
            return
        for posicio, nom, mitjana in e["noms"]:
            inf.medalles.append(
                Medalla(
                    font=FONT_RFEB,
                    competicio=competicio,
                    categoria=categoria,
                    edicio=e["edicio"],
                    any_edicio=e["any"],
                    lloc=e["lloc"],
                    posicio=posicio,
                    jugador=nom,
                    mitjana=mitjana,
                )
            )

    for n_pag, taules in enumerate(pagines, 1):
        for taula in taules:
            nova = _columnes_rfeb(taula)
            if nova is not None:
                cols = nova
                # Les dues files de capçalera no porten dades.
                files = taula[2:]
            elif cols is not None and len(taula[0]) == max(cols.values()) + 1 + (
                1 if "sub-21" in categoria else 0
            ):
                files = taula
            else:
                # La taula de resum per jugador del final, o res que ens serveixi.
                continue
            for fila in files:
                on = f"p{n_pag}"
                if len(fila) <= max(cols.values()):
                    inf.no_llegit.append((on, f"fila curta {fila!r}"))
                    continue
                nomes_primera = _text(fila[0])
                resta = [_text(c) for c in fila[1:]]
                if (
                    fila[0] is not None
                    and nomes_primera
                    and not any(resta)
                    and not _ROMANA.fullmatch(nomes_primera)
                ):
                    inf.notes.append(nomes_primera)
                    continue
                if fila[0] is not None:
                    # Una edició nova.
                    tanca()
                    inf.edicions += 1
                    roman = nomes_primera
                    garbada = False
                    if roman and not _ROMANA.fullmatch(roman):
                        # Text d'una altra fila superposat: no es pot saber quina edició és.
                        inf.no_llegit.append((on, f"edició que no és romana: {roman!r}"))
                        garbada = True
                    any_txt = _text(fila[cols["any"]])
                    any_ed = int(any_txt) if re.fullmatch(r"\d{4}", any_txt) else None
                    if any_txt and any_ed is None:
                        inf.no_llegit.append((on, f"any il·legible {any_txt!r}"))
                        garbada = True
                    lloc = ", ".join(
                        x for x in (_text(fila[cols["sede"]]), _text(fila[cols["ciutat"]])) if x
                    )
                    actual = {
                        "edicio": roman or str(inf.edicions),
                        "any": any_ed,
                        "lloc": lloc or None,
                        "noms": [],
                        "ambigua": garbada,
                    }
                    extra = False
                else:
                    if actual is None:
                        inf.no_llegit.append((on, f"continuació sense edició {fila!r}"))
                        continue
                    extra = True
                    fora = [
                        i
                        for i, c in enumerate(fila)
                        if _text(c)
                        and i not in (cols["oro"], cols["plata"], cols["bronce"])
                        and i not in (cols["oro"] + 1, cols["plata"] + 1, cols["bronce"] + 1)
                    ]
                    if fora:
                        inf.no_llegit.append((on, f"continuació amb dades estranyes {fila!r}"))
                        actual["ambigua"] = True
                        continue
                for posicio, clau in ((1, "oro"), (2, "plata"), (3, "bronce")):
                    nom = _text(fila[cols[clau]])
                    mit_txt = fila[cols[clau] + 1] if cols[clau] + 1 < len(fila) else ""
                    if not nom:
                        if _text(mit_txt):
                            inf.no_llegit.append((on, f"mitjana sense nom {mit_txt!r}"))
                        continue
                    if re.search(r"\d", nom):
                        inf.no_llegit.append((on, f"nom amb xifres {nom!r}"))
                        actual["ambigua"] = True
                        continue
                    if extra and posicio != 3:
                        # Un segon nom a l'or o a la plata: no se sap de qui és.
                        actual["ambigua"] = True
                        continue
                    mitjana, ok = _mitjana_rfeb(mit_txt)
                    if not ok:
                        inf.no_llegit.append((on, f"mitjana il·legible {mit_txt!r}"))
                    actual["noms"].append((posicio, nom, mitjana))
    tanca()
    return inf


# ---------------------------------------------------------------------------
# CEB
# ---------------------------------------------------------------------------

#: Una edició: `77) Ankara (TR) (10.-13.4.2025) 40/50 Pts.`. Els Grand Prix antics no
#: la numeren, i a algun PDF falta el primer parèntesi de les dates. El país és el
#: codi tal com el posa el PDF («DE», però també «B», «Lux»).
_EDICIO_CEB = re.compile(r"^(?:(\d+)\)\s+)?(.+?)\s+\(([A-Za-z]{1,3})\)\s+\(?([^()]*\d{4})\)(.*)$")
#: Una línia que sembla una capçalera d'edició i no ho és per al lector: si el
#: podi que ve a sota s'assignés a l'edició anterior, quedaria mal posat.
_SEMBLA_EDICIO = re.compile(r"^(?:\d+|--)\)\s")
#: El parèntesi de tancament del país a vegades falta («(FR 16:0») als PDF.
_NOM_CEB = r"([^\d()/:?][^()\d]*?)\s+\(([A-Za-z]{1,3})\)?"
_PODI_CEB = re.compile(rf"^([123])\.?\s+{_NOM_CEB}(?:\s+(.*))?$")
_SENSE_NUMERO_CEB = re.compile(rf"^{_NOM_CEB}\s+(?:\d+:\d+|\?:\?)")
#: «Punts de partida, caramboles/entrades, mitjana general, millor partida, sèrie».
_ESTADISTICA = re.compile(r"^\d+:\d+(?:\s+\(?\d+:\d+\)?)?\s+\d+/\d+\s+(\d+,\d+)\s+")
#: Línies de capçalera, peu o text corregit que no són cap dada.
_SOROLL_CEB = re.compile(
    r"^(updated\b|©|Copyright\b|Dieter Haase|The European Champions\b|The European "
    r"(?:Championships|Tournament)\b|CEB Grand Prix|European Ladies Cup|Results of the "
    r"main tournaments|Matchpoints|\(Averages|- |The Winner|Winner\b|The Champions|"
    r"\(Picture Archive\)|\(Matchbillard\)|Unfortunately|in the avarage|the final matches|"
    r"documented\.|Sometimes|from the group|often is not|avarage|Coupe d|"
    r"\d+(?:st|nd|rd|th)\s|\"|\(Played|No more European|There were no more|From \d{4}\b|In cooperation|After \d{4})",
    re.I,
)


def llegeix_ceb(cami: str | Path) -> Informe:
    """Llegeix un PDF de «Rolls of Honors» del CEB. Vegeu el mòdul."""
    import pdfplumber

    cami = Path(cami)
    competicio, categoria = _CEB[cami.name]
    with pdfplumber.open(cami) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    return llegeix_text_ceb(text, competicio, categoria, cami.name)


def llegeix_text_ceb(text: str, competicio: str, categoria: str, fitxer: str = "") -> Informe:
    """El mateix, des del text del PDF (és el que es prova).

    Amb la competició buida, el PDF en porta més d'una i es parteix per les
    capçaleres de `_SECCIONS_CEB`.
    """
    inf = Informe(fitxer=fitxer, font=FONT_CEB)
    es_mixt = not competicio
    comp = competicio
    edicio: tuple[str, int | None, str] | None = None  # (número, any, lloc)
    perduda = False
    for n, linia in enumerate(text.splitlines(), 1):
        linia = linia.strip()
        if not linia:
            continue
        if es_mixt and linia in _SECCIONS_CEB:
            comp = _SECCIONS_CEB[linia]
            edicio = None
            continue
        if m := _EDICIO_CEB.match(linia):
            inf.edicions += 1
            anys = re.findall(r"\d{4}", m.group(4))
            edicio = (
                m.group(1) or str(inf.edicions),
                int(anys[-1]),
                f"{m.group(2)} ({m.group(3)})",
            )
            perduda = False
            continue
        if _SEMBLA_EDICIO.match(linia):
            # Una capçalera que no sabem llegir: el podi de sota no és de l'edició d'abans.
            inf.no_llegit.append((f"l{n}", linia))
            edicio = None
            perduda = True
            continue
        if _SOROLL_CEB.match(linia) or linia == "<<PAG>>":
            continue
        if edicio is None:
            if perduda:
                inf.no_llegit.append((f"l{n}", linia))
            # Si no, és abans de la primera edició: la galeria de campions.
            continue
        if m := _PODI_CEB.match(linia):
            posicio = int(m.group(1))
            nom = _neteja_nom(m.group(2))
            resta = m.group(4) or ""
            _desa_ceb(inf, comp, categoria, edicio, posicio, nom, m.group(3), resta)
            continue
        if _SENSE_NUMERO_CEB.match(linia):
            # El quart, que el PDF escriu sense número. No és medalla, encara que
            # tingui els mateixos punts que el tercer: el desempat el fa tercer a un.
            inf.sense_podi += 1
            continue
        if re.match(r"^[4-9]\.\s", linia):
            continue
        inf.no_llegit.append((f"l{n}", linia))
    return inf


def _neteja_nom(nom: str) -> str:
    return re.sub(r"\s+", " ", nom).strip()


def _desa_ceb(
    inf: Informe,
    competicio: str,
    categoria: str,
    edicio: tuple[str, int | None, str],
    posicio: int,
    nom: str,
    pais: str,
    resta: str,
) -> None:
    mitjana = None
    if m := _ESTADISTICA.match(resta.strip()):
        mitjana = float(m.group(1).replace(",", "."))
    inf.medalles.append(
        Medalla(
            font=FONT_CEB,
            competicio=competicio,
            categoria=categoria,
            edicio=edicio[0],
            any_edicio=edicio[1],
            lloc=edicio[2],
            posicio=posicio,
            jugador=nom,
            pais=pais,
            mitjana=mitjana,
        )
    )


# ---------------------------------------------------------------------------
# Descàrrega i base de dades local
# ---------------------------------------------------------------------------


def baixa(
    arrel: str | Path, forca: bool = False, pausa: float = 1.5, log=lambda msg: None
) -> list[str]:
    """Baixa els PDF que es llegeixen a `arrel/rfeb` i `arrel/ceb`.

    Els que ja hi són no es tornen a baixar si no és amb `forca`. Una pausa entre
    peticions, com ha de ser amb un servidor aliè. Retorna els fitxers que han
    fallat, perquè una pàgina que no respon no ha de parar la resta.
    """
    arrel = Path(arrel)
    fallats = []
    peticions = [(FONT_RFEB, n, URL_RFEB.format(n)) for n in _RFEB] + [
        (FONT_CEB, n, URL_CEB.format(n)) for n in _CEB
    ]
    for font, nom, url in peticions:
        desti = arrel / font / nom
        if desti.exists() and not forca:
            continue
        desti.parent.mkdir(parents=True, exist_ok=True)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                dades = r.read()
            if not dades.startswith(b"%PDF"):
                raise ValueError("no és un PDF")
            desti.write_bytes(dades)
            log(f"baixat {font}/{nom}")
        except Exception as e:  # qualsevol error de xarxa o de format
            fallats.append(f"{font}/{nom}: {e}")
        time.sleep(pausa)
    return fallats


# ---------------------------------------------------------------------------
# FCB: Quadre d'Honor
# ---------------------------------------------------------------------------

FONT_FCB = "fcb"

#: Modalitat del PDF → competició. Les que no hi són (lligues, interclubs,
#: copa, pool, snooker) no es llegeixen.
_MODALITATS_FCB = [
    (r"^LLIURE$", "Lliure"),
    (r"^TRES BANDES$", "Tres bandes"),
    (r"^QUADRE 47/2$", "Quadre 47/2"),
    (r"^QUADRE 71/2$", "Quadre 71/2"),
    (r"^QUADRE 47/1$", "Quadre 47/1"),
    (r"^BANDA$", "Banda"),
    (r"^ART[IÍ]STIC[O]?$", "Artístic"),
    (r"^(CHAP[OÓ]|XAP[OÓ])$", "Chapó"),
    (r"^5 QUILLES$", "5 quilles"),
    (r"^5 QUILLES BIATHL[OÓ]$|^([IVX]+ )?BIATHL[OÓ]$", "Biatló"),
    (r"^TROFEU CLAUDIO PUIGVERT$", "Trofeu Claudio Puigvert"),
]
_RE_TEMPORADA_FCB = re.compile(r"(\d{4})-(\d{4})")


def _competicio_fcb(text: str) -> str | None:
    for patro, nom in _MODALITATS_FCB:
        if re.match(patro, text.strip(), re.I):
            return nom
    return None


def _categoria_fcb(text: str) -> str:
    t = " ".join(text.split()).replace("ª", "a")
    if not t:
        return "absolut"
    if re.fullmatch(r"j[uú]nior", t, re.I):
        return "júnior"
    if re.fullmatch(r"(ct\.? )?catalunya|absolut", t, re.I):
        return "absolut"
    if t.lower() == "honor":
        return "honor"
    if t.lower() in {"femení", "juvenil"}:
        return t.lower()
    return t  # «1a», «2a A»…


def _jugador_fcb(text: str) -> str | None:
    t = " ".join(text.split())
    if not t or "NO JUGAT" in t.upper() or "DESERT" in t.upper() or "/" in t:
        return None  # sense campió, o una parella
    return t


def llegeix_fcb(cami: str | Path) -> Informe:
    """Les medalles (campió i subcampió) d'un PDF del Quadre d'Honor de la FCB."""
    import pdfplumber

    cami = Path(cami)
    inf = Informe(fitxer=cami.name, font=FONT_FCB)
    m = _RE_TEMPORADA_FCB.search(cami.stem)
    if not m:
        inf.no_llegit.append(("fitxer", "sense temporada al nom"))
        return inf
    edicio = f"{m.group(1)}-{m.group(2)[2:]}"
    any_fi = int(m.group(2))
    with pdfplumber.open(str(cami)) as pdf:
        taules = [t for pg in pdf.pages for t in pg.extract_tables()]
    vistes: set[tuple[str, str]] = set()
    for taula in taules:
        modalitat: str | None = None
        competicio: str | None = None
        categoria_llista = "absolut"
        for fila in taula:
            cel = [" ".join((c or "").split()) for c in fila]
            while len(cel) not in (4, 6) and len(cel) > 4 and not cel[-1]:
                cel.pop()  # una columna buida de més al final
            if not any(cel) or cel[0] == "MODALITAT" or cel[0].upper().startswith("QUADRE D'HONOR"):
                continue
            if cel[0]:
                modalitat = cel[0]
                competicio = _competicio_fcb(modalitat)
            if competicio is None:
                continue
            if len(cel) == 6:
                categoria = _categoria_fcb(cel[1])
                vistes.add((competicio, categoria))
                for posicio, nom, club in ((1, cel[2], cel[3]), (2, cel[4], cel[5])):
                    jugador = _jugador_fcb(nom)
                    if jugador:
                        inf.medalles.append(
                            Medalla(FONT_FCB, competicio, categoria, edicio, any_fi, club or None, posicio, jugador)
                        )
            elif len(cel) == 4:
                # Format de llista (1961-1965): «1r | jugador | club».
                if cel[1].upper().startswith("CLASSIF"):
                    continue
                pos = {"1r": 1, "2n": 2, "3r": 3}.get(cel[1].lower())
                jugador = _jugador_fcb(cel[2])
                if pos is None:
                    inf.no_llegit.append((edicio, " | ".join(cel)))
                    continue
                vistes.add((competicio, categoria_llista))
                if jugador:
                    inf.medalles.append(
                        Medalla(FONT_FCB, competicio, categoria_llista, edicio, any_fi, cel[3] or None, pos, jugador)
                    )
            else:
                inf.no_llegit.append((edicio, " | ".join(cel)))
    inf.edicions = len(vistes)
    return inf


def llegeix_carpeta(arrel: str | Path) -> list[Informe]:
    """Llegeix tots els PDF coneguts de `arrel/rfeb` i `arrel/ceb`, i tots els de `arrel/fcb`."""
    arrel = Path(arrel)
    informes = []
    for font, noms, lector in (
        (FONT_RFEB, _RFEB, llegeix_rfeb),
        (FONT_CEB, _CEB, llegeix_ceb),
    ):
        for nom in noms:
            cami = arrel / font / nom
            if cami.exists():
                informes.append(lector(cami))
    for cami in sorted((arrel / FONT_FCB).glob("*.pdf")):
        informes.append(llegeix_fcb(cami))
    return informes


def desa(conn: sqlite3.Connection, informes: list[Informe]) -> int:
    """Desa les medalles de cada font i competició, reemplaçant el que hi havia.

    S'esborra per (font, competició, categoria) i no per fitxer: un PDF que es
    torna a llegir no deixa res de la lectura anterior, i un que no hi és no
    toca el dels altres.
    """
    n = 0
    ambits = {(m.font, m.competicio, m.categoria) for i in informes for m in i.medalles}
    with conn:
        for ambit in ambits:
            conn.execute(
                "DELETE FROM palmares_medalles WHERE font=? AND competicio=? AND categoria=?",
                ambit,
            )
        for inf in informes:
            for m in inf.medalles:
                conn.execute(
                    "INSERT OR REPLACE INTO palmares_medalles (font, competicio, categoria, "
                    "edicio, any_edicio, lloc, posicio, jugador, pais, mitjana) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        m.font,
                        m.competicio,
                        m.categoria,
                        m.edicio,
                        m.any_edicio,
                        m.lloc,
                        m.posicio,
                        m.jugador,
                        m.pais,
                        m.mitjana,
                    ),
                )
                n += 1
    return n


def jugadors_per_candidats(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """`(nom, competició, font)` dels noms del palmarès que poden ser de la fitxa catalana.

    De la RFEB, tots (no porten federació). Del CEB, només els de país ES: un
    jugador que no és espanyol no és al cens. Els noms que són una inicial i un
    cognom («A. Trapé») s'hi inclouen igualment: el criteri dels candidats ja
    els descarta, que amb un sol cognom i una inicial no es proposa res.
    """
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='palmares_medalles'"
    ).fetchone():
        return []
    return [
        (nom, comp, font)
        for nom, comp, font in conn.execute(
            "SELECT jugador, CASE WHEN font = 'fcb' THEN MAX(lloc) ELSE MIN(competicio) END, font "
            "FROM palmares_medalles "
            "WHERE font IN ('rfeb', 'fcb') OR (font = 'ceb' AND pais = 'ES') "
            "GROUP BY jugador, font ORDER BY jugador"
        )
    ]


def afegeix_candidats(trobats, cami: str | Path) -> tuple[int, int]:
    """Afegeix els candidats nous al CSV **al final**, sense tocar l'ordre de res.

    `escriu_candidats` reordena tot el fitxer (els validats primer, per nom) i un
    CSV de centenars de files canvia de dalt a baix a cada execució; aquí només
    s'hi afegeixen files. El `validat` queda buit: el lligam només val quan algú
    hi posa «si».
    """
    cami = Path(cami)
    text = cami.read_bytes().decode("utf-8")
    lector = csv.DictReader(text.splitlines())
    camps = lector.fieldnames or []
    vistos = {(r["jugador_rfeb"], r["fcb_id"]) for r in lector}
    nous = []
    for c in trobats:
        if (c.rfeb.nom, c.cens.fcb_id) in vistos:
            continue
        vistos.add((c.rfeb.nom, c.cens.fcb_id))
        nous.append(
            {
                "validat": "",
                "jugador_rfeb": c.rfeb.nom,
                "equip_rfeb": c.rfeb.equip,
                "divisio": c.rfeb.divisio,
                "fcb_id": c.cens.fcb_id,
                "nom_cens": c.cens.nom,
                "club_cens": c.cens.club,
                "motiu": c.motiu,
            }
        )
    if nous:
        eol = "\r\n" if "\r\n" in text else "\n"
        with cami.open("a", encoding="utf-8", newline="") as f:
            if text and not text.endswith("\n"):
                f.write(eol)
            csv.DictWriter(f, fieldnames=camps, restval="", lineterminator=eol).writerows(nous)
    return len(vistos) - len(nous), len(nous)
