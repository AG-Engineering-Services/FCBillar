"""Calendari oficial d'un grup de lliga, en PDF → encontres amb data.

La federació publica un PDF per grup («CALENDARI LLIGA TRES BANDES 2026-27
PRIMERA GRUP B») amb les catorze jornades i, per a cadascuna, la data i els
encontres. És l'única font que concreta **el dia** de cada jornada: el calendari
esportiu general que llegeix `calendari_fed.py` només diu quina setmana es juga,
i per això la graella federativa de la zona soci va per setmanes i no per dies.

I el 6 de setembre de 2026, quan van publicar de cop els dotze grups de la
26/27, va resultar ser l'única font de res: la intranet responia 500 a
`lligues/grups` i la pàgina de divisions no tenia ni un enllaç. `descobreix_grups()`
els busca al sitemap de documents del WordPress, que és l'únic lloc on hi són
tots —la federació no els enllaça des de cap pantalla.

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

I les columnes s'agrupen entre files **pel centre**, no per on comencen: el text
hi va centrat, o sigui que el principi es mou amb la llargada del nom de l'equip.
Fent-ho pel principi, la columna del visitant de la 1a divisió grup A ballava
25,9 punts —més que el llindar de columna—, es partia en dues i les files del mig
no cabien ni en una ni en l'altra. Pel centre, aquella mateixa columna balla 0,1.

Un forat així no s'assembla a un error: el que en surt continua sent un
calendari. Per això hi ha `problemes()`, que comprova el que ha de ser cert
sempre, i per això el comandament no desa res si algun grup no quadra.

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
from typing import NamedTuple

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
#: «1ª DIVISIÓ», i també «DIVISIÓ HONOR», que va al davant i no porta número.
#: Els noms que en surten —'1a'…'4a' i 'Honor'— són els de `categories.norm_divisio`,
#: que és el vocabulari de divisions de tot el projecte.
_RE_DIVISIO = re.compile(r"(?:(\d+)ª\s+DIVISIÓ|DIVISIÓ\s+(HONOR))")
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
    divisio: str  # 'Honor', '1a', '2a', '3a', '4a'
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


class Columna(NamedTuple):
    """Una columna d'una fila: on comença, on té el centre i què hi diu.

    Les dues coordenades no són intercanviables i cadascuna té la seva feina.
    El marge esquerre —la llista numerada d'equips— es reconeix per on
    **comença** la columna. Agrupar columnes entre files, en canvi, s'ha de fer
    pel **centre**: el text hi va centrat, o sigui que el punt on comença es mou
    amb la llargada del nom de l'equip i el centre no es mou gens.
    """

    esquerra: float
    centre: float
    text: str


def _columnes(fila: list[dict], *, nomes_dreta_de: float = 0.0) -> list[Columna]:
    """Parteix una fila allà on hi ha un salt horitzontal ample."""
    out: list[Columna] = []
    actual: list[dict] = []

    def tanca(paraules: list[dict]) -> None:
        out.append(
            Columna(
                esquerra=paraules[0]["x0"],
                centre=(paraules[0]["x0"] + paraules[-1]["x1"]) / 2,
                text=" ".join(w["text"] for w in paraules),
            )
        )

    for w in fila:
        if w["x0"] < nomes_dreta_de:
            continue
        if actual and w["x0"] - actual[-1]["x1"] > _SALT_COLUMNA:
            tanca(actual)
            actual = []
        actual.append(w)
    if actual:
        tanca(actual)
    return out


def _data_de(text: str) -> date | None:
    m = _RE_DATA.search(text)
    if m is None:
        return None
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))


def llegeix(pdf_path: str | Path | bytes) -> CalendariGrup:
    """Llegeix el PDF del calendari d'un grup, d'un fitxer o de la memòria.

    Els bytes hi són perquè baixant-los del web no cal escriure'ls enlloc: la
    ingesta en fa una dotzena seguits i no té cap motiu per deixar-los al disc.
    """
    import io

    import pdfplumber

    origen = io.BytesIO(pdf_path) if isinstance(pdf_path, bytes) else str(pdf_path)
    capcalera = {"temporada": "", "divisio": "", "grup": ""}
    encontres: list[Encontre] = []

    # Un bloc és una capçalera de jornades («1ª JORNADA … 8ª JORNADA») amb la
    # seva fila de dates i les files d'encontres que hi pengen. N'hi ha uns
    # quants per pàgina, o sigui que es tanca quan n'arriba un de nou.
    jornades: list[tuple[float, int]] = []
    dates: dict[int, date] = {}
    files: list[list[Columna]] = []

    def tanca_bloc() -> None:
        if jornades and dates and files:
            encontres.extend(_encontres_del_bloc(files, jornades, dates))
        files.clear()

    with pdfplumber.open(origen) as pdf:
        for pagina in pdf.pages:
            for fila in _files(pagina):
                text = " ".join(w["text"] for w in fila)
                _llegeix_capcalera(text, capcalera)

                if _RE_JORNADA.search(text):
                    tanca_bloc()
                    jornades = [
                        (c.centre, int(m.group(1)))
                        for c in _columnes(fila)
                        if (m := _RE_JORNADA.match(c.text))
                    ]
                    dates = {}
                    continue

                cols = _columnes(fila)

                # La fila de les dates ve just sota la capçalera.
                if jornades and not dates and any(_RE_DATA.search(c.text) for c in cols):
                    for c in cols:
                        d = _data_de(c.text)
                        j = _bloc_de(c.centre, jornades)
                        if d is not None and j is not None:
                            dates[j] = d
                    continue

                if jornades and dates:
                    files.append([c for c in cols if c.esquerra >= _MARGE_LLISTA])
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
        dest["divisio"] = f"{m.group(1)}a" if m.group(1) else "Honor"
    if not dest["grup"] and (m := _RE_GRUP.search(text)):
        dest["grup"] = m.group(1)


def _encontres_del_bloc(
    files: list[list[Columna]],
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

    Les columnes s'agrupen pel centre. Fent-ho pel punt on comencen, els noms
    d'equip llargs i els curts d'una mateixa columna quedaven a més de vint
    punts els uns dels altres, la columna es partia en dues i les files del mig
    no cabien ni en una ni en l'altra: desapareixien. A la 1a divisió grup A de
    la 26-27 això s'enduia vint dels cinquanta-sis encontres sense dir res.
    """
    posicions = sorted({c.centre for fila in files for c in fila})
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


def _text_a(fila: list[Columna], centre: float) -> str:
    """El text de la fila que cau a la columna centrada a `centre`."""
    for c in fila:
        if abs(c.centre - centre) <= _SALT_COLUMNA:
            return c.text
    return ""


_RE_NUM_LLISTA = re.compile(r"^\d+\s+")


def _neteja_equip(text: str) -> str:
    """Treu el número de la llista i normalitza els espais."""
    return re.sub(r"\s+", " ", _RE_NUM_LLISTA.sub("", text)).strip()


def _bloc_de(x: float, jornades: list[tuple[float, int]]) -> int | None:
    """A quina jornada pertany una columna que comença a `x`."""
    candidats = [(abs(x - xj), j) for xj, j in jornades]
    return min(candidats)[1] if candidats else None


def problemes(cal: CalendariGrup) -> list[str]:
    """Què no quadra d'un calendari llegit, dit en pla.

    El lector treballa per posició, i quan una columna no li acaba de quadrar no
    peta: es deixa files. Això no es veu enlloc —el que en surt continua sent un
    calendari, només que amb forats—, i un calendari amb forats publicat fa més
    mal que no tenir-ne cap: qui el mira no té cap manera de saber que li falta
    el seu encontre. Per això es comprova el que ha de ser cert sempre.

    A cada jornada hi juga tothom qui pot. Amb un nombre parell d'equips totes
    les jornades tenen els mateixos encontres; amb un nombre senar, també,
    perquè el que descansa va rodant. Una jornada amb menys encontres que una
    altra no és una jornada curta: és una fila que s'ha perdut.
    """
    fallen: list[str] = []
    if not cal.encontres:
        fallen.append("cap encontre")
        return fallen

    for camp in ("temporada", "divisio", "grup"):
        if not getattr(cal, camp):
            fallen.append(f"sense {camp}")

    per_jornada: dict[int, list[Encontre]] = collections.defaultdict(list)
    for e in cal.encontres:
        per_jornada[e.jornada].append(e)

    jornades = sorted(per_jornada)
    if jornades != list(range(1, len(jornades) + 1)):
        falten = sorted(set(range(1, max(jornades) + 1)) - set(jornades))
        fallen.append(f"jornades que falten: {falten}")

    compte = {j: len(enc) for j, enc in per_jornada.items()}
    if len(set(compte.values())) > 1:
        normal = collections.Counter(compte.values()).most_common(1)[0][0]
        curtes = {j: n for j, n in sorted(compte.items()) if n != normal}
        fallen.append(f"jornades amb {normal} encontres menys aquestes: {curtes}")

    # Un equip no pot jugar dos cops el mateix dia, i encara menys contra ell
    # mateix: si surt, dues columnes s'han aparellat malament.
    for j, enc in sorted(per_jornada.items()):
        for e in enc:
            if e.local == e.visitant:
                fallen.append(f"jornada {j}: {e.local} contra ell mateix")
        equips = [x for e in enc for x in (e.local, e.visitant)]
        repetits = sorted({x for x in equips if equips.count(x) > 1})
        if repetits:
            fallen.append(f"jornada {j}: {', '.join(repetits)} hi surt més d'un cop")

    return fallen


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
        encontres=tuple(replace(e, data=referencia.get(e.jornada, e.data)) for e in cal.encontres),
    )


# ======================================================================
# Descobriment: quins calendaris de grup té publicats la federació
# ======================================================================

#: Els PDF de calendari de grup tenen tots la mateixa forma d'slug al gestor de
#: fitxers del WordPress: `calendari-lliga-tres-bandes-2026-27-honor-grup-a`.
#: La divisió i el grup que s'hi llegeixen només serveixen per anomenar-los
#: abans de baixar-los; els bons són els de la capçalera del PDF.
_RE_SLUG_GRUP = re.compile(
    r"calendari-lliga-tres-bandes-(\d{4})-(\d{2,4})-([a-z]+)-grup-([a-z])\b",
    re.IGNORECASE,
)

#: L'enllaç directe al PDF dins la pàgina de document. La pàgina en porta dos
#: més que no volem —el CSS del connector i una URL d'`admin-ajax`—, i també
#: l'enllaç al calendari general de la temporada, que és d'una altra categoria.
_RE_DESCARREGA_GRUP = re.compile(
    r"https?://[^\"'\s<>]*/download/\d+/[^\"'\s<>]*/\d+/"
    r"(calendari-lliga-tres-bandes-[^\"'\s<>]+\.pdf)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CalendariPublicat:
    """Un PDF de calendari de grup que la federació té penjat."""

    temporada: str  # '2026/2027'
    etiqueta: str  # 'honor grup A', tal com ho diu l'slug
    url: str


def slugs_de_grup(sitemap: str, temporada: str | None = None) -> list[tuple[str, str, str]]:
    """(slug, temporada, etiqueta) de cada calendari de grup que hi ha al sitemap."""
    out: list[tuple[str, str, str]] = []
    for u in re.findall(r"<loc>([^<]+)</loc>", sitemap):
        m = _RE_SLUG_GRUP.search(u)
        if m is None:
            continue
        a, b = m.group(1), m.group(2)
        if len(b) == 2:  # «2026-27» → «2026/2027»
            b = a[:2] + b
        temp = f"{a}/{b}"
        if temporada and temp != temporada:
            continue
        out.append(
            (u.rstrip("/").rsplit("/", 1)[-1], temp, f"{m.group(3)} grup {m.group(4).upper()}")
        )
    return sorted(out)


def url_del_pdf(pagina: str) -> str | None:
    """L'enllaç directe al PDF dins una pàgina de document del WordPress."""
    m = _RE_DESCARREGA_GRUP.search(pagina)
    return m.group(0) if m else None


def descobreix_grups(temporada: str | None = None, *, client=None) -> list[CalendariPublicat]:
    """Els calendaris de grup publicats, trobats pel sitemap de documents.

    La federació no els enllaça des de cap pantalla: viuen al gestor de fitxers
    del WordPress i només el sitemap els llista. Cal entrar a la pàgina de cada
    document per treure'n l'enllaç al PDF, o sigui una petició per grup.

    És l'única font d'aquesta informació. El setembre de 2026, amb els dotze
    grups de la 26-27 ja publicats aquí, la intranet encara responia 500 a
    `lligues/grups` i la pàgina de divisions no tenia ni un enllaç.
    """
    import httpx

    from fcbillar.scraper.urls import web_sitemap_documents

    tanca = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=60.0)
    try:
        slugs = slugs_de_grup(client.get(web_sitemap_documents()).text, temporada)
        out: list[CalendariPublicat] = []
        for slug, temp, etiqueta in slugs:
            url = url_del_pdf(client.get(f"https://fcbillar.cat/wpfd_file/{slug}/").text)
            if url is None:
                log.warning("%s: la pàgina del document no porta l'enllaç al PDF", slug)
                continue
            out.append(CalendariPublicat(temporada=temp, etiqueta=etiqueta, url=url))
        return out
    finally:
        if tanca:
            client.close()


# ======================================================================
# Cap al calendari: files de `calendari_events` i fitxer .ics
# ======================================================================

#: Font pròpia, i no `FCB`, per dos motius. Un: `ingest_calendari` reemplaça la
#: temporada sencera d'una font, i amb `FCB` la propera ingesta del calendari
#: general s'enduria aquests encontres. Dos: la graella de la zona soci parteix
#: els títols de la font `FCB` pel punt volat, i aquí el punt volat separa la
#: jornada del grup i dels equips.
FONT = "FCB-LLIGA"

_CAMPS_EVENT = (
    "font, temporada, setmana, disciplina, ambit, grup, tipus, data_inici, data_fi, "
    "titol, seu, dissabte, diumenge, col_span, raw"
)


def _dilluns(d: date) -> date:
    from datetime import timedelta

    return d - timedelta(days=d.weekday())


def files_de_calendari(calendaris: list[CalendariGrup], club: str, temporada: str) -> list[tuple]:
    """Els encontres d'un club, en la forma que demana `calendari_events`.

    Només els del club: la graella és la de la zona soci, i el que hi vol veure
    el soci és quan juga el seu equip, no les 92 files de la lliga sencera.
    """
    files: list[tuple] = []
    for cal in calendaris:
        nostre = next((e for e in cal.equips if club in e), None)
        if nostre is None:
            continue
        lletra = lletra_equip(nostre)

        # Les jornades que l'equip NO juga també són informació: als grups de
        # set equips en descansa un cada jornada, i qui mira el calendari ha de
        # saber que aquell dissabte no hi ha partit, no que ens n'hem descuidat.
        per_jornada = {e.jornada: e for e in cal.de(nostre)}
        for jornada in sorted(cal.dates):
            e = per_jornada.get(jornada)
            data = e.data if e else cal.dates[jornada]
            cua = f"{e.local} - {e.visitant}" if e else "descansa"
            titol = f"Equip {lletra} · J{jornada} · {cal.divisio} {cal.grup} · {cua}"
            files.append(
                (
                    FONT,
                    temporada,
                    _dilluns(data).isoformat(),
                    "carambola",
                    "catala",
                    # La clau primària de la taula és (font, temporada, setmana,
                    # disciplina, àmbit, grup, tipus): està pensada per a una
                    # fila per cel·la setmanal. Amb un sol epígraf per als
                    # quatre equips, els quatre partits d'un dissabte xocarien.
                    # L'equip com a grup respecta la clau i alhora és el millor
                    # epígraf: tots comencen igual i queden junts.
                    f"Lliga Tres Bandes · Equip {lletra}",
                    "equips",
                    data.isoformat(),
                    data.isoformat(),
                    titol,
                    e.local if e else None,  # qui juga a casa és qui fa de seu
                    None,
                    None,
                    1,
                    f"{data.isoformat()} {titol}",
                )
            )
    # Per data i, dins del dia, per lletra d'equip: A, B, C i D. Funciona
    # perquè el títol ara comença per la lletra; abans començava per la jornada
    # i els ordenava per divisió, que és l'ordre estrany que es veia.
    return sorted(files, key=lambda f: (f[7], f[9]))


_RE_LLETRA = re.compile(r'"([A-Z])"\s*$')


def lletra_equip(nom: str) -> str:
    """La lletra d'un equip: 'C.B. BANYOLES "C"' -> 'C'.

    Els clubs amb un sol equip no en porten, i llavors és l'A.
    """
    m = _RE_LLETRA.search(nom.strip())
    return m.group(1) if m else "A"


class ResDesar(ValueError):
    """S'ha demanat de desar una llista buida damunt de dades que ja hi eren."""


def ingest(conn, calendaris: list[CalendariGrup], club: str, temporada: str) -> int:
    """Desa els encontres del club a `calendari_events`. Reemplaça els seus.

    No toca les files del calendari general —les de «1ª jornada LL3B»—, que
    diuen que la lliga sencera juga aquell dia i segueixen servint.

    El reemplaçament és destructiu, o sigui que una llista buida s'enduria el
    que ja hi havia. Passa amb un `--club` mal escrit. Per això no es desa mai
    el buit.
    """
    files = files_de_calendari(calendaris, club, temporada)
    if not files:
        raise ResDesar(
            "No hi ha res per desar. No esborro el que ja hi ha per posar-hi el buit: "
            "si el filtre no ha trobat ningú, el problema és el filtre, no les dades."
        )
    conn.execute("DELETE FROM calendari_events WHERE font = ? AND temporada = ?", (FONT, temporada))
    conn.executemany(
        f"INSERT INTO calendari_events ({_CAMPS_EVENT}) VALUES ({','.join('?' * 15)})",
        files,
    )
    conn.commit()
    return len(files)


def _escapa_ics(text: str) -> str:
    """Escapa un text per a un camp .ics (RFC 5545 §3.3.11).

    La barra primer: si no, escaparia les barres que acabem de posar.
    """
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics(calendaris: list[CalendariGrup], club: str, *, nom: str = "Billar") -> str:
    """Els encontres del club en un .ics per importar a un calendari.

    Són esdeveniments de DIA SENCER: la federació dona el dia de la jornada,
    però l'hora la posa cada club amb el contrari, i no la sabem. Posar-hi una
    hora inventada seria pitjor que no posar-n'hi cap.
    """
    from datetime import timedelta

    linies = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//FCBillar//Calendari de lliga//CA",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escapa_ics(nom)}",
    ]
    for cal in calendaris:
        for e in cal.encontres:
            if club not in e.local and club not in e.visitant:
                continue
            casa = club in e.local
            # L'identificador ha de ser estable: si es torna a importar, el
            # calendari ha d'actualitzar l'esdeveniment, no duplicar-lo.
            # Estable entre exportacions, i únic encara que s'exporti més d'un
            # club: si canviés, cada importació duplicaria els esdeveniments en
            # comptes d'actualitzar-los.
            uid = (
                f"lliga3b-{cal.temporada.replace('/', '')}"
                f"-{cal.divisio}{cal.grup}-j{e.jornada}"
                f"-{re.sub(r'[^a-z0-9]', '', club.lower())}@fcbillar"
            )
            linies += [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTART;VALUE=DATE:{e.data:%Y%m%d}",
                f"DTEND;VALUE=DATE:{e.data + timedelta(days=1):%Y%m%d}",
                f"SUMMARY:{_escapa_ics(f'{e.local} - {e.visitant}')}",
                f"LOCATION:{_escapa_ics(e.local if not casa else club)}",
                "DESCRIPTION:"
                + _escapa_ics(
                    f"Jornada {e.jornada} · {cal.divisio} divisió grup {cal.grup} · "
                    f"{'a casa' if casa else 'a fora'}"
                ),
                "TRANSP:TRANSPARENT",
                "END:VEVENT",
            ]
    linies.append("END:VCALENDAR")
    # L'RFC demana CRLF i línies de com a molt 75 octets.
    return "\r\n".join(pleg for ln in linies for pleg in _plega(ln)) + "\r\n"


def _plega(linia: str, limit: int = 73) -> list[str]:
    """Parteix una línia llarga com mana l'RFC 5545 §3.1.

    El tall es compta en OCTETS, no en caràcters: amb accents i punts volats,
    una línia que sembla curta pot passar-se. Les continuacions comencen amb un
    espai, que qui la llegeix torna a treure.
    """
    b = linia.encode("utf-8")
    if len(b) <= limit:
        return [linia]
    trossos: list[str] = []
    while b:
        tall = min(limit, len(b))
        # No partir un caràcter multibyte pel mig: si el byte del tall és una
        # continuació (10xxxxxx), enrere fins al principi del caràcter.
        while 0 < tall < len(b) and (b[tall] & 0xC0) == 0x80:
            tall -= 1
        trossos.append(b[:tall].decode("utf-8"))
        b = b[tall:]
        limit = 72  # les continuacions perden un octet per l'espai del davant
    return [trossos[0]] + [f" {t}" for t in trossos[1:]]


def desa_grups(conn, calendaris: list[CalendariGrup], temporada: str) -> int:
    """Desa el calendari SENCER de cada grup a `lliga_calendari`.

    `ingest` desa només els encontres del club, que és el que vol veure el soci
    al seu calendari. Això desa la resta: tots els equips del grup i tots els
    seus encontres.

    Serveix per ensenyar la temporada que comença amb la mateixa forma que una
    de jugada —la composició del grup i la graella de jornades— quan la
    federació encara no ha publicat la competició. Sense això, del setembre fins
    a la primera jornada no hi ha res a ensenyar: els encontres no disputats no
    porten identificador al seu web i no es poden ingerir.

    Es reemplaça grup a grup i no la temporada sencera: els PDF arriben d'un en
    un i tornar a ingerir-ne un no pot esborrar els altres.
    """
    if not calendaris:
        raise ResDesar(
            "Cap calendari de grup per desar. No esborro el que ja hi ha per posar-hi el buit."
        )
    n = 0
    for cal in calendaris:
        conn.execute(
            "DELETE FROM lliga_calendari WHERE temporada = ? AND divisio = ? AND grup = ?",
            (temporada, cal.divisio, cal.grup),
        )
        conn.executemany(
            "INSERT OR REPLACE INTO lliga_calendari "
            "(temporada, divisio, grup, jornada, data, local, visitant) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    temporada,
                    cal.divisio,
                    cal.grup,
                    e.jornada,
                    e.data.isoformat(),
                    e.local,
                    e.visitant,
                )
                for e in cal.encontres
            ],
        )
        n += len(cal.encontres)
    conn.commit()
    return n
