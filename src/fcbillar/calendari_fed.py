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
    "LIGA", "HONOR", "DIV.", "PLAYOFF", "COPA", "CTO", "CAMPEONATO", "TROFEO",
    "GRAN PREMIO", "GRAND PRIX", "OPEN", "TOUR", "MUNDO", "MUNDIAL", "EUROPA",
    "WORLD", "CHAMPIONSHIP", "BANDA", "QUILLAS", "ARTISTIC", "ARTÍSTIC", "LIBRE",
    "CUADRO", "SERIE", "CLASICOS", "CLÁSICOS", "SNOOKER", "POOL", "BALL",
    "EQUIPOS", "CLUBES", "CLUBS", "PRIMERA", "SEGUNDA", "MASC", "FEM", "JUNIOR",
    "SENIOR", "SUB-", "SS.NN", "SS.AA", "GAMES", "NEXTGEN", "EUROYOUTH", "WPA",
    "CEB", "PREDATOR", "LONGONI", "NAVIDAD", "SEMANA SANTA", "AÑO NUEVO",
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
_RE_VERSIO = re.compile(r"CALENDARIO\s+(V\.[\d.]+)\s+actualizado\s+a\s+(\d{1,2})\s*/(\d{1,2})/(\d{4})")

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


def parse_calendari(pdf_bytes: bytes, font: str = FONT_RFEB) -> Calendari:
    """Llegeix el PDF del calendari federatiu i en treu els esdeveniments."""
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
# `/media/2026-2027` encara respon 404: la FCB no ha publicat res de la temporada
# vinent. El codi de sota ho detecta i ho deixa apuntat sense fallar, de manera que
# el dia que el pengin la web ho pot dir i enllaçar-hi.
#
# GEOMETRIA DEL PDF DE LA FCB (mesurada sobre la 25/26 V-9, per si s'ha de
# parsejar el dia que publiquin la 26/27):
#   - A4 horitzontal, 4 pàgines, graella uniforme.
#   - Línies verticals a x = 51,2 · 89,4 i després cada 55,1pt fins a 750,5:
#     columna DATA + 12 columnes de contingut.
#   - Una fila per DIA (no per setmana com la RFEB): «13-sep. SAB», «14-sep. DOM»,
#     alçada ~8,9pt. Molt més fi que el calendari estatal.
#   - Blocs de columnes segons la capçalera: lligues catalanes (Honor/1ª/2ª/3ª | 4a),
#     campionats de Catalunya (prèvies | qualificació i finals), opens catalans,
#     lliga nacional, campionats d'Espanya, d'Europa, del Món i pool.
#   - Complica el parseig: cel·les fusionades horitzontalment i text ajustat que
#     s'entrellaça en llegir-lo per coordenada x; cal agrupar per `top` abans.

_RE_MEDIA_CAL = re.compile(
    r"/media/(\d{4}-\d{4})/CALENDARIS/([^\"'>]+?\.pdf)", re.IGNORECASE
)
_RE_VERSIO_FITXER = re.compile(r"\bV[-_ ]?(\d+)", re.IGNORECASE)
FCB_BASE = "https://www.fcbillar.cat"


@dataclass
class CalendariFCB:
    """PDF de calendari de la FCB detectat al web."""

    temporada: str  # '2025/2026', derivada del camí /media/2025-2026/
    versio: str | None  # 'V-9', del nom del fitxer
    url: str
    nom_fitxer: str


def descobreix_fcb(html: str | None = None) -> list[CalendariFCB]:
    """Troba els PDF de calendari de la FCB enllaçats al web (layout comú).

    Sense `html` es baixa la portada. Retorna la llista ordenada per temporada i
    versió, de més nova a més antiga.
    """
    from urllib.parse import unquote, urljoin

    if html is None:
        import httpx

        html = httpx.get(FCB_BASE + "/", follow_redirects=True, timeout=60.0).text

    vistos: dict[str, CalendariFCB] = {}
    for m in _RE_MEDIA_CAL.finditer(html):
        carpeta, fitxer = m.group(1), unquote(m.group(2))
        url = urljoin(FCB_BASE, m.group(0))
        mv = _RE_VERSIO_FITXER.search(fitxer)
        a, b = carpeta.split("-")
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


def registra_fcb(db_path, html: str | None = None) -> dict:
    """Apunta a `calendari_versions` quins calendaris de la FCB hi ha publicats.

    NO en parseja els esdeveniments: la graella de la FCB és diferent de la de la
    RFEB i el fitxer de la temporada vinent encara no existeix. El que sí que fa,
    i és el que interessa ara, és deixar constància de la versió vigent i la seva
    URL, de manera que la web pugui enllaçar el PDF oficial i avisar el dia que la
    federació publiqui la temporada nova.
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

    cal = parse_calendari(pdf_bytes, font=font)
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
        "ON CONFLICT(font, temporada, sha256) DO UPDATE SET "
        "  etag = COALESCE(excluded.etag, calendari_versions.etag), "
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
    versio_id = cur.lastrowid or conn.execute(
        "SELECT id FROM calendari_versions WHERE font = ? AND temporada = ? AND sha256 = ?",
        (font, cal.temporada, cal.sha256),
    ).fetchone()[0]
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
