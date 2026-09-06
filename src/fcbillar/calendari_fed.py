"""Calendari esportiu federatiu en PDF → esdeveniments per setmana.

Font actual: **RFEB** (`https://rfeb.org/cal_rfeb_XXYY.pdf`). La FCB publica el seu
més tard cada any; el model deixa lloc a una segona font (`font='FCB'`) sense tocar
res més.

## Com és el PDF

Una graella A4 horitzontal (una pàgina per trimestre, 4 en total). Cada **setmana**
ocupa TRES files —dilluns, dissabte i diumenge—, i cada **columna** és una
combinació de disciplina/àmbit/tipus:

```
                     CARAMBOLA                        │  POOL   │ SNOOKER
        NACIONAL              │    INTERNACIONAL       │ NAC·INT │ NAC·INT
 TRES BANDAS │ JOCS DE SÈRIE… │                       │         │
 EQ  │  IND  │  EQ   │  IND   │   EQ    │    IND      │         │
```

Dins d'una cel·la (setmana x columna) hi ha fins a tres línies de text, una per
fila de dia. N'hi ha de dos patrons:

- **amb seu** — les línies 1-2 són el nom de la competició i la 3a la localitat:
  `CTO. DE ESPAÑA` / `CUADRO 47/2` / `Cervera (LÉRIDA)`.
- **repartida per dies** — no hi ha localitat i les línies 2-3 diuen què es juga
  cada dia: `LIGA NACIONAL 3 BANDAS` / `HONOR J1` (ds) / `1ª-2ª DIV. J1` (dg).

`_es_seu()` distingeix els dos casos mirant l'última línia. Les línies crues es
desen sempre a `raw` per poder auditar la interpretació.

## Com se'n treuen les dates

El PDF no escriu l'any i el mes els posa com a lletres verticals al marge. En
comptes de llegir-les, es busca **quin dilluns de sortida fa quadrar els 159
números de dia de cop**: amb 53 setmanes és una comprovació prou forta perquè no
hi hagi ambigüitat, i falla clarament si el format canvia.

## Revisions

La RFEB va publicant versions del mateix fitxer («CALENDARIO V.1 actualizado a
28/07/2026»). `fetch_pdf()` retorna també l'`ETag`/`Last-Modified` per poder
saltar-se la feina quan no ha canviat res, i `sha256` identifica el contingut.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import re
from dataclasses import dataclass, field
from itertools import pairwise

# --- Fonts -----------------------------------------------------------------

FONT_RFEB = "RFEB"
FONT_FCB = "FCB"


def rfeb_url(temporada_inici: int) -> str:
    """URL del calendari de la RFEB per a la temporada que comença l'any donat.

    Temporada 2026/2027 → `cal_rfeb_2627.pdf`. Sense el `?v=N` que fa servir el
    web de la RFEB: és només un trencacaus de memòria cau del navegador i el
    fitxer és sempre el mateix camí.
    """
    return f"https://rfeb.org/cal_rfeb_{temporada_inici % 100:02d}{(temporada_inici + 1) % 100:02d}.pdf"


def temporada_actual(avui: dt.date | None = None) -> int:
    """Any en què comença la temporada esportiva vigent (canvi de temporada l'1 d'agost)."""
    avui = avui or dt.date.today()
    return avui.year if avui.month >= 8 else avui.year - 1


# --- Columnes de la graella -------------------------------------------------


@dataclass(frozen=True)
class Columna:
    """Semàntica d'una columna fulla de la graella, d'esquerra a dreta."""

    disciplina: str  # carambola | pool | snooker
    ambit: str  # nacional | internacional | mixt
    grup: str | None  # subgrup de modalitats (només carambola nacional)
    tipus: str | None  # equips | individual


TRES_BANDES = "Tres bandes"
JOCS_SERIE = "Jocs de sèrie, artístic i 5 quilles"

# L'ordre és el del PDF i és part del contracte: si el nombre de columnes fulla
# que es detecta no és exactament aquest, el parser peta (millor fallar fort que
# assignar malament una competició a "equips" o a "internacional").
COLUMNES: tuple[Columna, ...] = (
    Columna("carambola", "nacional", TRES_BANDES, "equips"),
    Columna("carambola", "nacional", TRES_BANDES, "individual"),
    Columna("carambola", "nacional", JOCS_SERIE, "equips"),
    Columna("carambola", "nacional", JOCS_SERIE, "individual"),
    Columna("carambola", "internacional", None, "equips"),
    Columna("carambola", "internacional", None, "individual"),
    Columna("pool", "nacional", None, None),
    Columna("pool", "internacional", None, None),
    # El snooker no separa nacional d'internacional: una sola columna per als dos.
    Columna("snooker", "mixt", None, None),
)


# --- Model ------------------------------------------------------------------


@dataclass
class Esdeveniment:
    """Una cel·la de la graella: què es juga una setmana en una columna."""

    font: str
    temporada: str  # '2026/2027'
    setmana: dt.date  # dilluns de la setmana (clau d'agrupació)
    data_inici: dt.date  # primer dia amb text (normalment el dissabte)
    data_fi: dt.date  # últim dia amb text (normalment el diumenge)
    disciplina: str
    ambit: str
    grup: str | None
    tipus: str | None
    titol: str
    seu: str | None
    dissabte: str | None  # només al patró "repartida per dies"
    diumenge: str | None
    col_span: int  # >1 = cel·la fusionada (NADAL, SETMANA SANTA)
    raw: str  # les línies crues, una per ratlla

    def clau(self) -> tuple:
        """Clau natural, per detectar altes/baixes/canvis entre revisions."""
        return (
            self.font,
            self.temporada,
            self.setmana,
            self.disciplina,
            self.ambit,
            self.grup or "",
            self.tipus or "",
        )


@dataclass
class Calendari:
    font: str
    temporada: str
    versio: str | None  # 'V.1'
    data_versio: dt.date | None  # data del "actualizado a …"
    sha256: str
    esdeveniments: list[Esdeveniment] = field(default_factory=list)


# --- Heurístiques de text ---------------------------------------------------

# Paraules que delaten que una línia és competició/modalitat i NO una localitat.
# Cal-hi perquè moltes seus s'escriuen en majúscules i sense parèntesi
# (`ZARAGOZA`, `MADRID`, `VALLADOLID`) igual que les modalitats (`TRES BANDAS`).
_NO_SEU = (
    "LIGA",
    "HONOR",
    "DIV.",
    "PLAYOFF",
    "COPA",
    "CTO",
    "CAMPEONATO",
    "TROFEO",
    "GRAN PREMIO",
    "GRAND PRIX",
    "OPEN",
    "TOUR",
    "MUNDO",
    "MUNDIAL",
    "EUROPA",
    "WORLD",
    "CHAMPIONSHIP",
    "BANDA",
    "QUILLAS",
    "ARTISTIC",
    "ARTÍSTIC",
    "LIBRE",
    "CUADRO",
    "SERIE",
    "CLASICOS",
    "CLÁSICOS",
    "SNOOKER",
    "POOL",
    "BALL",
    "EQUIPOS",
    "CLUBES",
    "CLUBS",
    "PRIMERA",
    "SEGUNDA",
    "MASC",
    "FEM",
    "JUNIOR",
    "SENIOR",
    "SUB-",
    "SS.NN",
    "SS.AA",
    "GAMES",
    "NEXTGEN",
    "EUROYOUTH",
    "WPA",
    "CEB",
    "PREDATOR",
    "LONGONI",
    "NAVIDAD",
    "SEMANA SANTA",
    "AÑO NUEVO",
)
_JORNADA = re.compile(r"\bJ\s?\d+\b|\d+[ªº]")


def _es_seu(text: str) -> bool:
    """Diu si una línia és la localitat del bloc (i no part del nom o un dia)."""
    if "(" in text:  # 'Cervera (LÉRIDA)', 'Assen (NED)', '(KOREA)'
        return True
    if text.startswith("Sede"):  # 'Sede R.F.E.B'
        return True
    if text == "?":  # seu per determinar
        return True
    u = text.upper()
    if _JORNADA.search(text) or any(k in u for k in _NO_SEU):
        return False
    # Resta: topònim escrit sol, en majúscules ('ZARAGOZA') o capitalitzat.
    return not any(c.isdigit() for c in text)


# --- Parser -----------------------------------------------------------------

_RE_TEMPORADA = re.compile(r"TEMPORADA\s+(\d{4})\s*/\s*(\d{4})")
# La RFEB no escriu la versió sempre igual: la V.1 del juliol de 2026 anava amb
# majúscula i la v.1.2 de l'agost amb minúscula. Sense IGNORECASE la revisió
# entrava sense versió ni data, i la capçalera del web seguia atribuint les
# dades a la revisió anterior.
_RE_VERSIO = re.compile(
    r"CALENDARIO\s+(V\.[\d.]+)\s+actualizado\s+a\s+(\d{1,2})\s*/(\d{1,2})/(\d{4})",
    re.IGNORECASE,
)

_MIN_AMPLE_COLUMNA = 50.0  # pt; descarta les columnes estretes dels marges
_TOL_FILA = 7.0  # pt; distància màxima entre el centre d'una paraula i la seva fila
_GAP_CELLA = 10.0  # pt; separació horitzontal que ja no és un espai entre paraules


def _boundaries(pdf) -> list[float]:
    """Línies verticals estructurals de la graella (unió de totes les pàgines)."""
    xs: set[float] = set()
    for page in pdf.pages:
        for e in page.edges:
            if e["orientation"] == "v" and (e["y1"] - e["y0"]) >= 80:
                xs.add(round(e["x0"], 1))
    out: list[float] = []
    for x in sorted(xs):
        if not out or x - out[-1] > 2.5:
            out.append(x)
    return out


def _columnes_x(pdf) -> list[tuple[float, float]]:
    """Rangs x de les columnes de contingut, validats contra `COLUMNES`."""
    bounds = _boundaries(pdf)
    cols = [(a, b) for a, b in pairwise(bounds) if b - a >= _MIN_AMPLE_COLUMNA]
    if len(cols) != len(COLUMNES):
        raise ValueError(
            f"El PDF té {len(cols)} columnes de contingut i se n'esperaven "
            f"{len(COLUMNES)}: la RFEB ha canviat el format del calendari i cal "
            f"revisar COLUMNES a calendari_fed.py. Rangs detectats: {cols}"
        )
    return cols


def _files(page, x_marques: float) -> list[tuple[float, str, int]]:
    """Files de dia d'una pàgina: (top, 'L'|'S'|'D', número de dia)."""
    marques = [w for w in page.extract_words() if w["x0"] > 30 and w["x1"] <= x_marques]
    bandes: list[tuple[float, list]] = []
    for w in sorted(marques, key=lambda w: w["top"]):
        if bandes and w["top"] - bandes[-1][0] < 6:
            bandes[-1][1].append(w)
        else:
            bandes.append((w["top"], [w]))
    out = []
    for top, ws in bandes:
        ws.sort(key=lambda w: w["x0"])
        # A la mateixa banda hi ha la lletra del dia i, a la dreta, el número.
        lletra = "".join(w["text"] for w in ws if len(w["text"]) == 1 and w["text"].isalpha())
        numero = "".join(w["text"] for w in ws if w["text"].isdigit())
        if lletra in ("L", "S", "D") and numero.isdigit():
            out.append((top, lletra, int(numero)))
    return out


def _dates(files: list[tuple[str, int]], any_inici: int) -> list[dt.date]:
    """Assigna dates reals a les files provant tots els dilluns d'arrencada.

    Es valida el patró L/S/D i, després, que TOTS els números de dia quadrin amb
    una única graella dilluns→(dissabte, diumenge). Si no hi ha exactament un
    candidat, el format ha canviat i val més petar que endevinar.
    """
    if len(files) % 3 != 0:
        raise ValueError(f"El PDF té {len(files)} files de dia i no és múltiple de 3.")
    for i, (dow, _) in enumerate(files):
        if dow != "LSD"[i % 3]:
            raise ValueError(
                f"Fila {i} és '{dow}' i s'esperava '{'LSD'[i % 3]}': el PDF ja no "
                f"segueix el patró dilluns/dissabte/diumenge."
            )

    def graella(dilluns: dt.date) -> list[dt.date]:
        return [
            dilluns + dt.timedelta(days=7 * (i // 3) + (0, 5, 6)[i % 3]) for i in range(len(files))
        ]

    candidats = []
    d = dt.date(any_inici, 7, 1)
    d += dt.timedelta(days=(0 - d.weekday()) % 7)  # primer dilluns de juliol
    while d <= dt.date(any_inici, 10, 15):
        dates = graella(d)
        if all(dates[i].day == files[i][1] for i in range(len(files))):
            candidats.append(dates)
        d += dt.timedelta(days=7)
    if len(candidats) != 1:
        raise ValueError(
            f"No s'ha pogut situar el calendari a l'any {any_inici}: "
            f"{len(candidats)} dilluns d'arrencada quadren amb els números de dia."
        )
    return candidats[0]


def parse_calendari(
    pdf_bytes: bytes, font: str = FONT_RFEB, versio: str | None = None
) -> Calendari:
    """Llegeix el PDF del calendari federatiu i en treu els esdeveniments.

    Cada federació té la seva graella: `parse_calendari_fcb` per a la catalana i
    la resta d'aquesta funció per a l'estatal.
    """
    if font == FONT_FCB:
        return parse_calendari_fcb(pdf_bytes, versio=versio)

    import pdfplumber

    sha = hashlib.sha256(pdf_bytes).hexdigest()
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        cols_x = _columnes_x(pdf)
        x_marques = cols_x[0][0]

        capcalera = pdf.pages[0].extract_text() or ""
        m = _RE_TEMPORADA.search(capcalera)
        if not m:
            raise ValueError("No s'ha trobat «TEMPORADA aaaa/aaaa» a la primera pàgina.")
        temporada, any_inici = f"{m.group(1)}/{m.group(2)}", int(m.group(1))
        versio = data_versio = None
        if mv := _RE_VERSIO.search(capcalera):
            versio = mv.group(1)
            data_versio = dt.date(int(mv.group(4)), int(mv.group(3)), int(mv.group(2)))

        # Files de totes les pàgines, en ordre, amb el text repartit per columnes.
        files: list[tuple[str, int]] = []
        # cel·les[fila] = llista de (x0, x1, text) — un element per bloc de text
        celles: list[list[tuple[float, float, str]]] = []
        for page in pdf.pages:
            page_files = _files(page, x_marques)
            base = len(files)
            files.extend((dow, dia) for _, dow, dia in page_files)
            celles.extend([] for _ in page_files)
            tops = [t for t, _, _ in page_files]
            if not tops:
                continue
            per_fila: dict[int, list] = {}
            for w in page.extract_words():
                cx = (w["x0"] + w["x1"]) / 2
                if cx < cols_x[0][0] or cx > cols_x[-1][1]:
                    continue
                centre = (w["top"] + w["bottom"]) / 2
                j = min(range(len(tops)), key=lambda k: abs(tops[k] + 5 - centre))
                if abs(tops[j] + 5 - centre) <= _TOL_FILA:
                    per_fila.setdefault(j, []).append(w)
            for j, ws in per_fila.items():
                ws.sort(key=lambda w: w["x0"])
                blocs, actual = [], [ws[0]]
                for a, b in pairwise(ws):
                    if b["x0"] - a["x1"] > _GAP_CELLA:
                        blocs.append(actual)
                        actual = [b]
                    else:
                        actual.append(b)
                blocs.append(actual)
                celles[base + j] = [
                    (bl[0]["x0"], bl[-1]["x1"], " ".join(w["text"] for w in bl)) for bl in blocs
                ]

    dates = _dates(files, any_inici)

    # Reagrupa: setmana x columna -> les fins a 3 línies del bloc. Un bloc que
    # travessa columnes (NADAL, SETMANA SANTA) va a la pseudocolumna 'tot'.
    blocs: dict[tuple[int, int | str], list[tuple[dt.date, str]]] = {}
    spans: dict[tuple[int, int | str], int] = {}
    for i, cel in enumerate(celles):
        setmana = i // 3
        for x0, x1, text in cel:
            toca = [k for k, (a, b) in enumerate(cols_x) if x0 < b and x1 > a]
            if not toca:
                continue
            clau: tuple[int, int | str]
            if len(toca) == 1:
                clau = (setmana, toca[0])
            else:
                # Cel·la fusionada: una única entrada per a tota la disciplina.
                disciplines = {COLUMNES[k].disciplina for k in toca}
                clau = (setmana, "tot:" + "/".join(sorted(disciplines)))
            blocs.setdefault(clau, []).append((dates[i], text))
            spans[clau] = max(spans.get(clau, 0), len(toca))

    out: list[Esdeveniment] = []
    for (setmana, col), linies in sorted(blocs.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        dilluns = dates[setmana * 3]
        seu = None
        cos = list(linies)
        if len(cos) >= 1 and _es_seu(cos[-1][1]):
            seu = None if cos[-1][1] == "?" else cos[-1][1]
            cos = cos[:-1]
        dissabte = diumenge = None
        if not cos:  # bloc que només tenia la localitat
            titol = seu or ""
            seu = None
        elif seu is None and len(cos) > 1:
            # Patró "repartida per dies" (LIGA NACIONAL): sense localitat, la línia
            # del dilluns és la capçalera i les del cap de setmana diuen què es juga
            # cada dia. Es reparteix per la data real de cada línia, no per l'ordre,
            # perquè hi ha setmanes on només es juga un dels dos dies.
            per_dia = {d.weekday(): t for d, t in cos}
            dissabte, diumenge = per_dia.get(5), per_dia.get(6)
            capcalera = [t for d, t in cos if d.weekday() == 0]
            titol = " · ".join(capcalera) if capcalera else cos[0][1]
        else:
            titol = " · ".join(t for _, t in cos)
        if isinstance(col, str):  # cel·la fusionada
            disciplina = col.removeprefix("tot:").split("/")[0]
            ambit, grup, tipus = "tot", None, None
        else:
            c = COLUMNES[col]
            disciplina, ambit, grup, tipus = c.disciplina, c.ambit, c.grup, c.tipus
        out.append(
            Esdeveniment(
                font=font,
                temporada=temporada,
                setmana=dilluns,
                data_inici=min(d for d, _ in linies),
                data_fi=max(d for d, _ in linies),
                disciplina=disciplina,
                ambit=ambit,
                grup=grup,
                tipus=tipus,
                titol=titol,
                seu=seu,
                dissabte=dissabte,
                diumenge=diumenge,
                col_span=spans[(setmana, col)],
                raw="\n".join(f"{d.isoformat()} {t}" for d, t in linies),
            )
        )
    return Calendari(
        font=font,
        temporada=temporada,
        versio=versio,
        data_versio=data_versio,
        sha256=sha,
        esdeveniments=out,
    )


# --- Descàrrega -------------------------------------------------------------


def _ssl_context_relaxat():
    """Context TLS que accepta grups Diffie-Hellman curts.

    rfeb.org negocia un grup DH per sota del que l'OpenSSL modern accepta al
    nivell de seguretat 2 (`DH_KEY_TOO_SMALL`), i per tant la descàrrega falla amb
    la configuració per defecte. Baixar el nivell a 1 NOMÉS per a aquesta petició
    és acceptable: és un PDF públic, no hi viatja cap credencial i el contingut es
    verifica igualment pel sha256 que se'n desa.
    """
    import ssl

    ctx = ssl.create_default_context()
    ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    return ctx


def fetch_pdf(url: str, etag: str | None = None) -> tuple[bytes | None, str | None, str | None]:
    """Baixa el PDF. Retorna (bytes, etag, last_modified); bytes=None si 304.

    Amb `etag` fa una petició condicional: si la RFEB no ha tocat el fitxer torna
    304 i ens estalviem tornar-lo a parsejar. És el que fa útil passar-hi cada dia.
    """
    import ssl

    import httpx

    headers = {"If-None-Match": etag} if etag else {}
    try:
        r = httpx.get(url, headers=headers, follow_redirects=True, timeout=60.0)
    except (httpx.ConnectError, ssl.SSLError) as exc:
        if "DH_KEY_TOO_SMALL" not in str(exc):
            raise
        r = httpx.get(
            url,
            headers=headers,
            follow_redirects=True,
            timeout=60.0,
            verify=_ssl_context_relaxat(),
        )
    if r.status_code == 304:
        return None, etag, None
    r.raise_for_status()
    return r.content, r.headers.get("ETag"), r.headers.get("Last-Modified")


# --- Font FCB: descobriment del PDF ----------------------------------------
#
# La FCB no publica el calendari a cap ruta previsible: el desa al magatzem
# estàtic `/media/{temporada}/CALENDARIS/` amb el número de versió DINS el nom del
# fitxer («CALENDARI FCB 2025-26 V-9.pdf» — ja van per la novena revisió de la
# 25/26). Endevinar el nom no serveix; el que sí que és estable és que l'enllaç al
# PDF vigent surt al **layout de totes les pàgines** de fcbillar.cat, així que es
# descobreix llegint qualsevol pàgina.
#
# Mentre la FCB no el penja al seu web, el calendari pot arribar per una altra via
# (un PDF compartit); per això `ingest_calendari` accepta `pdf_bytes` i `url`
# solts. El descobriment de sota segueix servint per saber quan el publiquen.

#: El web nou desa els documents amb el gestor de fitxers del WordPress:
#:     /download/{id_categoria}/{categoria}/{id_fitxer}/{nom}.pdf
#: El nom porta la temporada i la versió, que és tot el que en necessitem.
_RE_DESCARREGA_CAL = re.compile(
    r"https?://[^\"'\s<>]*/download/\d+/[^/]*calendari[^/]*/\d+/([^\"'\s<>]+\.pdf)",
    re.IGNORECASE,
)
#: El setembre de 2026 la federació va publicar els calendaris de cada grup de
#: la lliga, i tenen «calendari» al camí de descàrrega igual que aquest: sortien
#: aquí barrejats amb el calendari esportiu de la temporada, que no és el
#: mateix document ni de bon tros. Els llegeix `calendari_lliga.descobreix_grups`.
_RE_CAL_DE_GRUP = re.compile(r"calendari-lliga-", re.IGNORECASE)

_RE_TEMPORADA_FITXER = re.compile(r"(\d{4})[-_](\d{2,4})")
_RE_VERSIO_FITXER = re.compile(r"\bV[-_ ]?(\d+)", re.IGNORECASE)

FCB_BASE = "https://fcbillar.cat"
#: Sitemap de Yoast amb una pàgina per document publicat. Substitueix el llistat
#: paginat del web antic: aquí hi són tots d'una tirada, i cada pàgina de
#: document porta l'enllaç directe al PDF.
FCB_SITEMAP_DOCS = f"{FCB_BASE}/wpfd_file-sitemap.xml"


@dataclass
class CalendariFCB:
    """PDF de calendari de la FCB detectat al web."""

    temporada: str  # '2025/2026', derivada del camí /media/2025-2026/
    versio: str | None  # 'V-9', del nom del fitxer
    url: str
    nom_fitxer: str


def descobreix_fcb(html: str | None = None) -> list[CalendariFCB]:
    """Troba els PDF de calendari que la FCB té publicats.

    Amb el web nou ja no serveix mirar la portada: els documents viuen al gestor
    de fitxers del WordPress i no s'enllacen des del layout. El camí fiable és
    el sitemap de documents, que en llista un per pàgina, i entrar a les que
    parlen de calendari per treure'n l'enllaç al PDF.

    Amb `html` es mira un sol document ja baixat, que és el que fan els tests.
    Retorna la llista ordenada per temporada i versió, de més nova a més antiga.
    """
    from urllib.parse import unquote

    pagines = [html] if html is not None else _pagines_de_calendari()

    vistos: dict[str, CalendariFCB] = {}
    for pagina in pagines:
        for m in _RE_DESCARREGA_CAL.finditer(pagina):
            url, fitxer = m.group(0), unquote(m.group(1))
            if _RE_CAL_DE_GRUP.match(fitxer):
                continue  # el calendari d'un grup de lliga, que va per un altre camí
            mt = _RE_TEMPORADA_FITXER.search(fitxer)
            if mt is None:
                continue  # sense temporada al nom no el sabem col·locar
            a, b = mt.group(1), mt.group(2)
            if len(b) == 2:  # «2026-27» -> «2026/2027»
                b = a[:2] + b
            mv = _RE_VERSIO_FITXER.search(fitxer)
            vistos[url] = CalendariFCB(
                temporada=f"{a}/{b}",
                versio=f"V-{mv.group(1)}" if mv else None,
                url=url,
                nom_fitxer=fitxer,
            )

    def ordre(c: CalendariFCB) -> tuple:
        n = _RE_VERSIO_FITXER.search(c.versio or "")
        return (c.temporada, int(n.group(1)) if n else -1)

    return sorted(vistos.values(), key=ordre, reverse=True)


def _pagines_de_calendari() -> list[str]:
    """Les pàgines de document del web que parlen del calendari de la temporada.

    Els calendaris de grup de la lliga també diuen «calendari» a l'adreça i
    n'hi ha dotze: baixar-los per llençar-los després són dotze peticions cada
    nit per no res. Els llegeix `calendari_lliga.descobreix_grups`.
    """
    import httpx

    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        sitemap = client.get(FCB_SITEMAP_DOCS).text
        enllacos = [
            u
            for u in re.findall(r"<loc>([^<]+)</loc>", sitemap)
            if "calendari" in u.lower() and not _RE_CAL_DE_GRUP.search(u)
        ]
        return [client.get(u).text for u in enllacos]


def registra_fcb(db_path, html: str | None = None) -> dict:
    """Apunta a `calendari_versions` quins calendaris de la FCB hi ha publicats.

    NO en parseja els esdeveniments —d'això se n'encarrega `ingest_calendari` amb
    `font='FCB'`—: aquí només es deixa constància de quina revisió hi ha penjada i
    on, que és el que permet adonar-se que la federació n'ha tret una de nova.
    """
    from fcbillar.db.migrations import ensure_schema

    conn = ensure_schema(db_path)
    trobats = descobreix_fcb(html)
    nous = 0
    for c in trobats:
        pdf, etag, last_mod = fetch_pdf(c.url)
        assert pdf is not None
        sha = hashlib.sha256(pdf).hexdigest()
        ja = conn.execute(
            "SELECT id FROM calendari_versions WHERE font = ? AND temporada = ? AND sha256 = ?",
            (FONT_FCB, c.temporada, sha),
        ).fetchone()
        if ja:
            conn.execute(
                "UPDATE calendari_versions SET etag = COALESCE(?, etag), url = ?, "
                "last_checked_at = datetime('now') WHERE id = ?",
                (etag, c.url, ja[0]),
            )
            continue
        # `data_versio`: la FCB no escriu la data de revisió dins el PDF, així que
        # es pren el Last-Modified del servidor, que és quan la van penjar.
        data_versio = None
        if last_mod:
            try:
                from email.utils import parsedate_to_datetime

                data_versio = parsedate_to_datetime(last_mod).date().isoformat()
            except (TypeError, ValueError):
                data_versio = None
        conn.execute(
            "INSERT INTO calendari_versions (font, temporada, versio, data_versio, sha256, "
            "etag, last_modified, url, n_events, n_canvis) VALUES (?,?,?,?,?,?,?,?,0,0)",
            (FONT_FCB, c.temporada, c.versio, data_versio, sha, etag, last_mod, c.url),
        )
        nous += 1
    return {"trobats": len(trobats), "nous": nous, "calendaris": trobats}


# --- Font FCB: parser de la graella -----------------------------------------
#
# La graella catalana no s'assembla gens a la de la RFEB i té parser propi.
#
# ## Com és el PDF
#
# A4 horitzontal, quatre pàgines. Les DUES PRIMERES són el calendari; les altres
# dues són els annexos de distàncies i reglament (no tenen files de dia i el
# parser les descarta sol). La graella és:
#
#   - Una fila per DIA de competició —«29-ago. SAB», «30-ago. DOM»— de 8,9pt, i
#     no una per setmana com la RFEB. Dins d'una fila hi caben dues línies de text.
#   - Columna DATA + 11 columnes de contingut de 55,1pt, partides en dos blocs per
#     la capçalera: «CALENDARI F.C.B.» (les 6 primeres) i «CALENDARI
#     R.F.E.B.-C.E.B.-U.M.B.» (les 5 últimes).
#
# ## Què se n'ingesta i què no
#
# NOMÉS la meitat catalana. La dreta ja entra —i millor— per la font RFEB:
# ingestar-la també duplicaria cada competició estatal a la pestanya, i amb el
# text retallat d'una còpia de segona mà. En queden fora els campionats catalans
# de pool i snooker, que la FCB escriu a la columna de pool de la meitat estatal.
#
# ## Carrils, no categories
#
# Les columnes de la meitat catalana funcionen com a CARRILS: quan una setmana hi
# ha més actes que columnes, la FCB els escriu a la del costat si és buida (el
# 19-9 hi ha una pre-prèvia a la columna de finals). Per això els carrils agrupen
# columnes i el que diu de què va un acte és el seu TEXT, no la columna on ha
# acabat.
#
# ## Sense seu
#
# A diferència de la RFEB, aquí no se'n separa la localitat: a la columna d'opens
# el que sembla una seu sol ser part del nom del torneig («Pre-prèvies III Open
# Costa» + «Daurada», «…XIII Open Les» + «Santes de Mataró»). Partir-ho trencaria
# més noms dels que endreçaria, i el text sencer ja es llegeix bé.

AMBIT_CATALA = "catala"

_MESOS_FCB = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}
_DIES_FCB = {"LUN": 0, "MAR": 1, "MIE": 2, "JUE": 3, "VIE": 4, "SAB": 5, "DOM": 6}


@dataclass(frozen=True)
class CarrilFCB:
    """Un bloc de columnes de la meitat catalana de la graella."""

    columnes: tuple[int, ...]  # índexs de columna de contingut, base 0
    etiqueta: str  # títol quan la setmana es reparteix per dies
    grup: str
    tipus: str


CARRILS_FCB: tuple[CarrilFCB, ...] = (
    CarrilFCB((0,), "Lligues catalanes", "Lligues catalanes i Copa Catalana", "equips"),
    CarrilFCB((1, 2, 3, 4), "Campionats de Catalunya", "Campionats de Catalunya", "individual"),
    CarrilFCB((5,), "Opens catalans", "Opens catalans", "individual"),
)
# Columnes que cobreixen els carrils: ha de quadrar amb l'amplada que la capçalera
# «CALENDARI F.C.B.» diu que ocupa, o el mapatge s'ha desplaçat.
_N_COL_FCB = sum(len(c.columnes) for c in CARRILS_FCB)

_RE_FILA_FCB = re.compile(r"^(\d{1,2})-(\w{3})\.?\s*(\w{3})$")
_RE_TEMPORADA_FCB = re.compile(r"TEMPORADA\s+(\d{4})\s*/\s*(\d{2,4})")
_RE_CAPCALERA_FCB = re.compile(r"CALENDARI\s+F\.?C\.?B\.?", re.IGNORECASE)
_RE_DATA_META = re.compile(r"D:(\d{4})(\d{2})(\d{2})")

# Un acte propi es reconeix perquè es diu a si mateix què és. Serveix per destriar
# les dues línies d'una cel·la que continua al diumenge («Final Quadre 47/2» +
# «3ª Div.») del cas on dissabte i diumenge es juguen coses diferents
# («2ª jornada LL3B» dissabte, «1a jornada 4M» diumenge).
_RE_ACTE_FCB = re.compile(
    r"jornada|prèvi|previ|final|open|copa|campionat|cto\b|torneig|fase|"
    r"qualificaci|promoci|play\s*-?\s*off|biathló|reunió",
    re.IGNORECASE,
)
_FESTIUS_FCB = ("NADAL", "SETMANA SANTA", "CAP D'ANY")

_TOL_LINIA_FCB = 1.5  # pt; dos caràcters són de la mateixa línia de text
_ESPAI_FCB = 0.4  # pt; separació entre caràcters que ja no és dins d'una paraula
_GAP_CELLA_FCB = 5.0  # pt; separació entre paraules que ja és un canvi de cel·la
# Marge per damunt de la data amb què encara es considera de la mateixa fila (el
# text de la cel·la puja fins a 2,5pt per sobre del rètol del dia) i alçada útil
# de la fila (la segona ratlla baixa fins a 4,9pt per sota). Entremig hi ha prou
# folgança: les files fan 8,9pt.
_PUJADA_FILA_FCB = 2.7
_ALCADA_FILA_FCB = 6.0


def _linies_fcb(page) -> list[tuple[float, list[tuple[float, float, str]]]]:
    """Línies de text de la pàgina, cadascuna partida en cel·les: (top, blocs).

    Es reconstrueix a partir dels CARÀCTERS i no de `extract_words()`: dins d'una
    fila de 8,9pt hi caben dues ratlles separades per 3,3pt, i l'agrupació per
    defecte de pdfplumber, que tolera 3pt de desnivell, les barreja i deixa les
    paraules de les dues esmicolades lletra a lletra.
    """
    linies: list[tuple[float, list]] = []
    for c in sorted(page.chars, key=lambda c: (c["top"], c["x0"])):
        if c["text"].isspace():
            continue  # el farciment de justificació; els espais es dedueixen dels buits
        if linies and c["top"] - linies[-1][0] <= _TOL_LINIA_FCB:
            linies[-1][1].append(c)
        else:
            linies.append((c["top"], [c]))

    out: list[tuple[float, list[tuple[float, float, str]]]] = []
    for top, chars in linies:
        chars.sort(key=lambda c: c["x0"])
        blocs: list[list] = [[chars[0]]]
        for a, b in pairwise(chars):
            blocs.append([b]) if b["x0"] - a["x1"] > _GAP_CELLA_FCB else blocs[-1].append(b)
        out.append((top, [(bl[0]["x0"], bl[-1]["x1"], _text_fcb(bl)) for bl in blocs]))
    return out


def _text_fcb(chars: list) -> str:
    """Text d'un bloc: els espais surten dels buits entre caràcters."""
    parts = [chars[0]["text"]]
    for a, b in pairwise(chars):
        if b["x0"] - a["x1"] > _ESPAI_FCB:
            parts.append(" ")
        parts.append(b["text"])
    return "".join(parts).strip()


def _columnes_fcb(pdf) -> list[float]:
    """Línies verticals de la graella, comunes a les pàgines de calendari."""
    xs: set[float] = set()
    for page in pdf.pages:
        for e in page.edges:
            if e["orientation"] == "v" and (e["y1"] - e["y0"]) >= 15:
                xs.add(round(e["x0"], 1))
    out: list[float] = []
    for x in sorted(xs):
        if not out or x - out[-1] > 2.5:
            out.append(x)
    return out


def _talla_meitat_fcb(page, xs: list[float]) -> int:
    """Quantes columnes de contingut ocupa el bloc «CALENDARI F.C.B.».

    Es dedueix del centre de la capçalera del bloc en comptes de fixar-lo: si la
    FCB hi afegeix o en treu una columna, això ho detecta en lloc d'assignar
    silenciosament els actes catalans al carril equivocat.
    """
    for _, blocs in _linies_fcb(page):
        # La capçalera del bloc de la dreta també comença per «CALENDARI»: el
        # rètol de cada meitat és un bloc de text sencer i prou.
        for x0, x1, text in blocs:
            if not _RE_CAPCALERA_FCB.match(text):
                continue
            centre = (x0 + x1) / 2
            n = min(range(2, len(xs)), key=lambda k: abs((xs[1] + xs[k]) / 2 - centre))
            if abs((xs[1] + xs[n]) / 2 - centre) > 8.0:
                break
            return n - 1
    raise ValueError(
        "No s'ha pogut situar la capçalera «CALENDARI F.C.B.»: el PDF de la "
        "federació catalana ha canviat de format."
    )


def _sense_accents(text: str) -> str:
    """En majúscules i sense accents: el PDF escriu tant «SAB» com «SÁB»."""
    import unicodedata

    despullat = unicodedata.normalize("NFKD", text)
    return "".join(c for c in despullat if not unicodedata.combining(c)).upper()


def _data_fcb(dia: int, mes: str, any_inici: int) -> dt.date:
    """Data real d'una fila. El PDF escriu el mes en castellà i no l'any: la
    temporada va d'agost a juliol, i això el determina sense ambigüitat."""
    m = _MESOS_FCB.get(mes.lower())
    if m is None:
        raise ValueError(f"Mes desconegut a la graella de la FCB: {mes!r}")
    return dt.date(any_inici if m >= 8 else any_inici + 1, m, dia)


def _cella_fcb(linies: list[tuple[dt.date, str]]) -> tuple[str, str | None, str | None]:
    """Text d'una cel·la: (tot junt, dissabte, diumenge).

    Les dues línies d'una cel·la solen ser un sol nom que no cabia en una ratlla;
    només quan la del diumenge s'anomena a si mateixa un acte és que la setmana es
    reparteix de debò entre els dos dies.
    """
    ds = [t for d, t in linies if d.weekday() == 5]
    dg = [t for d, t in linies if d.weekday() != 5]
    tot = " ".join(t for _, t in linies)
    if ds and dg and _RE_ACTE_FCB.search(" ".join(dg)):
        return tot, " ".join(ds), " ".join(dg)
    return tot, None, None


def parse_calendari_fcb(pdf_bytes: bytes, versio: str | None = None) -> Calendari:
    """Llegeix la meitat catalana del calendari de la FCB."""
    import pdfplumber

    sha = hashlib.sha256(pdf_bytes).hexdigest()
    # cel·les[(setmana, carril)][columna] = línies (data, text), en ordre de lectura
    celles: dict[tuple[dt.date, int], dict[int, list[tuple[dt.date, str]]]] = {}
    festius: list[tuple[dt.date, dt.date, str]] = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        capcalera = pdf.pages[0].extract_text() or ""
        m = _RE_TEMPORADA_FCB.search(capcalera)
        if not m:
            raise ValueError("No s'ha trobat «TEMPORADA aaaa/aa» al calendari de la FCB.")
        any_inici = int(m.group(1))
        fi = m.group(2)
        temporada = f"{any_inici}/{fi if len(fi) == 4 else str(any_inici + 1)[:2] + fi}"
        data_versio = None
        if md := _RE_DATA_META.match(str(pdf.metadata.get("CreationDate") or "")):
            data_versio = dt.date(int(md.group(1)), int(md.group(2)), int(md.group(3)))

        xs = _columnes_fcb(pdf)
        n_cat = _talla_meitat_fcb(pdf.pages[0], xs)
        if n_cat != _N_COL_FCB:
            raise ValueError(
                f"El bloc «CALENDARI F.C.B.» ocupa {n_cat} columnes i els carrils "
                f"en cobreixen {_N_COL_FCB}: cal revisar CARRILS_FCB."
            )
        de_carril = {c: i for i, car in enumerate(CARRILS_FCB) for c in car.columnes}

        for page in pdf.pages:
            linies = _linies_fcb(page)
            # Files de dia, del rètol de la columna DATA. Les pàgines d'annexos no
            # en tenen cap i queden fora soles.
            files: list[tuple[float, dt.date]] = []
            for top, blocs in linies:
                # El rètol («24-jul.» i «SÁB») va prou separat per caure en dos blocs.
                rotul = " ".join(b[2] for b in blocs if b[1] <= xs[1] + 1)
                if not (mf := _RE_FILA_FCB.match(rotul)):
                    continue
                data = _data_fcb(int(mf.group(1)), mf.group(2), any_inici)
                esperat = _DIES_FCB.get(_sense_accents(mf.group(3)))
                if esperat is None:
                    raise ValueError(f"Dia de la setmana desconegut: {mf.group(3)!r}")
                if data.weekday() != esperat:
                    raise ValueError(
                        f"La fila «{rotul}» cau en dia {data.weekday()} i el PDF "
                        f"diu {mf.group(3)}: l'any de la temporada no quadra."
                    )
                files.append((top, data))
            if not files:
                continue

            for top, blocs in linies:
                # Fila a què pertany la línia: l'última que comença per damunt seu,
                # amb el marge que el text de la cel·la puja sobre el rètol del dia.
                j = max(
                    (k for k, (t, _) in enumerate(files) if t <= top + _PUJADA_FILA_FCB),
                    default=None,
                )
                fora = j is None or top - files[j][0] > _ALCADA_FILA_FCB
                for x0, x1, text in blocs:
                    if x1 <= xs[1] + 1:
                        continue  # la columna DATA
                    if len(text) < 2:
                        # Caràcter solt en una cel·la que no en té cap més: el full
                        # d'Excel d'origen n'arrossega algun (una «a» perduda a la
                        # columna de prèvies el 6-9) i no vol dir res.
                        continue
                    if fora:
                        # Cap fila de dia: és el rètol d'un període sense competició,
                        # que ocupa les setmanes que la graella es salta.
                        anterior = files[j][1] if j is not None else None
                        seguent = next((d for t, d in files if t > top), None)
                        if anterior and seguent:
                            festius.append(
                                (
                                    anterior + dt.timedelta(days=1),
                                    seguent - dt.timedelta(days=1),
                                    text,
                                )
                            )
                        continue
                    # Columna amb què la cel·la solapa més: les fusionades («REUNIÓ
                    # DELEGATS ESPORTIUS», «SETMANA CATALANA») en travessen unes quantes.
                    col = max(
                        range(len(xs) - 2),
                        key=lambda k: min(x1, xs[k + 2]) - max(x0, xs[k + 1]),
                    )
                    if col not in de_carril:
                        continue  # meitat estatal: ja entra per la font RFEB
                    data = files[j][1]
                    setmana = data - dt.timedelta(days=data.weekday())
                    cel = celles.setdefault((setmana, de_carril[col]), {})
                    cel.setdefault(col, []).append((data, text))

    out: list[Esdeveniment] = []
    for (setmana, icar), per_columna in sorted(celles.items()):
        carril = CARRILS_FCB[icar]
        totes = [ln for c in sorted(per_columna) for ln in per_columna[c]]
        parts, ds_parts, dg_parts = [], [], []
        for c in sorted(per_columna):
            tot, ds, dg = _cella_fcb(per_columna[c])
            parts.append(tot)
            if ds or dg:
                ds_parts += [ds] if ds else []
                dg_parts += [dg] if dg else []
            elif per_columna[c][0][0].weekday() == 5:
                ds_parts.append(tot)
            else:
                dg_parts.append(tot)
        titol = " · ".join(parts)
        reparteix = any(_cella_fcb(v)[1] for v in per_columna.values())
        es_festiu = titol.upper().startswith(_FESTIUS_FCB)
        out.append(
            Esdeveniment(
                font=FONT_FCB,
                temporada=temporada,
                setmana=setmana,
                data_inici=min(d for d, _ in totes),
                data_fi=max(d for d, _ in totes),
                disciplina="carambola",
                ambit="tot" if es_festiu else AMBIT_CATALA,
                grup="" if es_festiu else carril.grup,
                tipus=None if es_festiu else carril.tipus,
                titol=carril.etiqueta if reparteix else titol,
                seu=None,
                dissabte=" · ".join(ds_parts) if reparteix else None,
                diumenge=" · ".join(dg_parts) if reparteix else None,
                col_span=len(per_columna),
                raw="\n".join(f"{d.isoformat()} {t}" for d, t in totes),
            )
        )

    # Nadal i companyia: no cauen en cap fila perquè la graella salta les setmanes
    # que no es juga. Van amb `ambit = 'tot'`, com els de la RFEB, i la web no els
    # llista: ja ho diu prou no havent-hi res aquelles setmanes.
    for inici, fi_f, text in festius:
        setmana = inici - dt.timedelta(days=inici.weekday())
        out.append(
            Esdeveniment(
                font=FONT_FCB,
                temporada=temporada,
                setmana=setmana,
                data_inici=inici,
                data_fi=fi_f,
                disciplina="carambola",
                ambit="tot",
                grup="",
                tipus=None,
                titol=text,
                seu=None,
                dissabte=None,
                diumenge=None,
                col_span=len(CARRILS_FCB),
                raw=f"{inici.isoformat()}/{fi_f.isoformat()} {text}",
            )
        )

    out.sort(key=lambda e: (e.setmana, e.grup))
    return Calendari(
        font=FONT_FCB,
        temporada=temporada,
        versio=versio,
        data_versio=data_versio,
        sha256=sha,
        esdeveniments=out,
    )


# --- Comparació entre revisions --------------------------------------------


@dataclass
class Canvi:
    tipus_canvi: str  # alta | baixa | modificacio
    setmana: dt.date
    disciplina: str
    ambit: str
    grup: str | None
    tipus: str | None
    abans: str | None
    despres: str | None


def resum(e: Esdeveniment) -> str:
    """Resum d'una línia d'un esdeveniment (per als diffs i els informes)."""
    parts = [e.titol]
    if e.dissabte:
        parts.append(f"ds: {e.dissabte}")
    if e.diumenge:
        parts.append(f"dg: {e.diumenge}")
    if e.seu:
        parts.append(f"@ {e.seu}")
    return " · ".join(p for p in parts if p)


def diff(abans: list[Esdeveniment], despres: list[Esdeveniment]) -> list[Canvi]:
    """Altes, baixes i modificacions entre dues revisions del mateix calendari."""
    a = {e.clau(): e for e in abans}
    b = {e.clau(): e for e in despres}
    canvis: list[Canvi] = []
    for clau in sorted(set(a) | set(b), key=lambda k: (k[2], k[3], k[4], k[5], k[6])):
        vell, nou = a.get(clau), b.get(clau)
        ref = nou or vell
        assert ref is not None
        if vell is None:
            tipus_canvi, txt_a, txt_b = "alta", None, resum(nou)  # type: ignore[arg-type]
        elif nou is None:
            tipus_canvi, txt_a, txt_b = "baixa", resum(vell), None
        elif resum(vell) != resum(nou):
            tipus_canvi, txt_a, txt_b = "modificacio", resum(vell), resum(nou)
        else:
            continue
        canvis.append(
            Canvi(
                tipus_canvi=tipus_canvi,
                setmana=ref.setmana,
                disciplina=ref.disciplina,
                ambit=ref.ambit,
                grup=ref.grup,
                tipus=ref.tipus,
                abans=txt_a,
                despres=txt_b,
            )
        )
    return canvis


# --- Ingesta a SQLite -------------------------------------------------------

_CAMPS = (
    "font, temporada, setmana, disciplina, ambit, grup, tipus, data_inici, data_fi, "
    "titol, seu, dissabte, diumenge, col_span, raw"
)


def _llegeix_events(conn, font: str, temporada: str) -> list[Esdeveniment]:
    """Els esdeveniments que ja hi ha desats, per poder-los comparar amb els nous."""
    rows = conn.execute(
        f"SELECT {_CAMPS} FROM calendari_events WHERE font = ? AND temporada = ?",
        (font, temporada),
    ).fetchall()
    return [
        Esdeveniment(
            font=r[0],
            temporada=r[1],
            setmana=dt.date.fromisoformat(r[2]),
            disciplina=r[3],
            ambit=r[4],
            grup=r[5] or None,
            tipus=r[6] or None,
            data_inici=dt.date.fromisoformat(r[7]),
            data_fi=dt.date.fromisoformat(r[8]),
            titol=r[9],
            seu=r[10],
            dissabte=r[11],
            diumenge=r[12],
            col_span=r[13],
            raw=r[14],
        )
        for r in rows
    ]


def _marca_comprovacio(conn, url: str | None = None, sha256: str | None = None) -> None:
    """Deixa constància que s'ha comprovat el PDF, hi hagi canvis o no."""
    if sha256:
        conn.execute(
            "UPDATE calendari_versions SET last_checked_at = datetime('now') WHERE sha256 = ?",
            (sha256,),
        )
    elif url:
        conn.execute(
            "UPDATE calendari_versions SET last_checked_at = datetime('now') WHERE url = ?",
            (url,),
        )


def ingest_calendari(
    db_path,
    url: str | None = None,
    font: str = FONT_RFEB,
    force: bool = False,
    pdf_bytes: bytes | None = None,
    versio: str | None = None,
) -> dict:
    """Baixa (o rep) el PDF del calendari federatiu, el parseja i el desa.

    Idempotent i pensat per passar-hi cada dia: si la RFEB no ha tocat el fitxer
    (304 per ETag, o mateix sha256) no fa res i ho diu. Quan sí que ha canviat,
    desa la revisió nova, hi apunta el diff contra l'anterior i reemplaça els
    esdeveniments de la temporada.
    """
    from fcbillar.db.migrations import ensure_schema

    conn = ensure_schema(db_path)
    if pdf_bytes is None:
        url = url or rfeb_url(temporada_actual())
        # L'ETag es busca per URL: cada temporada és un fitxer diferent i barrejar-los
        # faria enviar l'ETag d'un altre recurs a la petició condicional.
        etag_previ = conn.execute(
            "SELECT etag FROM calendari_versions WHERE url = ? AND etag IS NOT NULL "
            "ORDER BY id DESC LIMIT 1",
            (url,),
        ).fetchone()
        pdf_bytes, etag, last_mod = fetch_pdf(
            url, None if force else (etag_previ[0] if etag_previ else None)
        )
        if pdf_bytes is None:
            _marca_comprovacio(conn, url=url)
            return {"estat": "sense-canvis", "motiu": "304 Not Modified", "url": url}
    else:
        etag = last_mod = None

    cal = parse_calendari(pdf_bytes, font=font, versio=versio)
    ja_hi_es = conn.execute(
        "SELECT id FROM calendari_versions WHERE font = ? AND temporada = ? AND sha256 = ?",
        (font, cal.temporada, cal.sha256),
    ).fetchone()
    if ja_hi_es and not force:
        conn.execute(
            "UPDATE calendari_versions SET etag = COALESCE(?, etag), "
            "last_modified = COALESCE(?, last_modified), url = COALESCE(?, url), "
            "last_checked_at = datetime('now') WHERE id = ?",
            (etag, last_mod, url, ja_hi_es[0]),
        )
        return {
            "estat": "sense-canvis",
            "motiu": "mateix sha256",
            "temporada": cal.temporada,
            "versio": cal.versio,
            "url": url,
        }

    canvis = diff(_llegeix_events(conn, font, cal.temporada), cal.esdeveniments)
    cur = conn.execute(
        "INSERT INTO calendari_versions "
        "(font, temporada, versio, data_versio, sha256, etag, last_modified, url, "
        " n_events, n_canvis) VALUES (?,?,?,?,?,?,?,?,?,?) "
        # En conflicte s'omple el que no sabíem i es deixa el que ja sabíem. Si
        # només es refresqués l'etag, una revisió desada abans que el parser en
        # sabés llegir la versió es quedaria sense versió per sempre, i la
        # capçalera del web seguiria atribuint les dades a la revisió anterior.
        # El COALESCE va al revés del que sembla: mana el valor NOU, i el vell
        # només si el nou és nul.
        "ON CONFLICT(font, temporada, sha256) DO UPDATE SET "
        "  versio = COALESCE(excluded.versio, calendari_versions.versio), "
        "  data_versio = COALESCE(excluded.data_versio, calendari_versions.data_versio), "
        "  etag = COALESCE(excluded.etag, calendari_versions.etag), "
        "  last_modified = COALESCE(excluded.last_modified, calendari_versions.last_modified), "
        "  url = COALESCE(excluded.url, calendari_versions.url), "
        "  n_events = excluded.n_events, n_canvis = excluded.n_canvis, "
        "  ingested_at = datetime('now'), last_checked_at = datetime('now')",
        (
            font,
            cal.temporada,
            cal.versio,
            cal.data_versio.isoformat() if cal.data_versio else None,
            cal.sha256,
            etag,
            last_mod,
            url,
            len(cal.esdeveniments),
            len(canvis),
        ),
    )
    versio_id = (
        cur.lastrowid
        or conn.execute(
            "SELECT id FROM calendari_versions WHERE font = ? AND temporada = ? AND sha256 = ?",
            (font, cal.temporada, cal.sha256),
        ).fetchone()[0]
    )
    conn.execute("DELETE FROM calendari_canvis WHERE versio_id = ?", (versio_id,))
    conn.executemany(
        "INSERT INTO calendari_canvis (versio_id, tipus_canvi, setmana, disciplina, "
        "ambit, grup, tipus, abans, despres) VALUES (?,?,?,?,?,?,?,?,?)",
        [
            (
                versio_id,
                c.tipus_canvi,
                c.setmana.isoformat(),
                c.disciplina,
                c.ambit,
                c.grup,
                c.tipus,
                c.abans,
                c.despres,
            )
            for c in canvis
        ],
    )

    # Reemplaça la temporada sencera: així les baixes (competicions que la RFEB
    # ha tret d'una revisió a l'altra) desapareixen de debò.
    conn.execute(
        "DELETE FROM calendari_events WHERE font = ? AND temporada = ?", (font, cal.temporada)
    )
    conn.executemany(
        f"INSERT INTO calendari_events ({_CAMPS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                e.font,
                e.temporada,
                e.setmana.isoformat(),
                e.disciplina,
                e.ambit,
                e.grup or "",
                e.tipus or "",
                e.data_inici.isoformat(),
                e.data_fi.isoformat(),
                e.titol,
                e.seu,
                e.dissabte,
                e.diumenge,
                e.col_span,
                e.raw,
            )
            for e in cal.esdeveniments
        ],
    )
    return {
        "estat": "actualitzat",
        "temporada": cal.temporada,
        "versio": cal.versio,
        "data_versio": cal.data_versio.isoformat() if cal.data_versio else None,
        "n_events": len(cal.esdeveniments),
        "n_canvis": len(canvis),
        "canvis": canvis,
        "url": url,
    }
