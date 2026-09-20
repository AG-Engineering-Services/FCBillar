"""El sorteig d'una fase del campionat individual, en PDF: grups, jugadors i clubs.

Abans de cada ronda del campionat de Catalunya la federació penja un PDF amb el
sorteig: quins grups hi ha, on es juguen, qui hi juga i **amb quin club**.

## Per què fa falta

Perquè és l'única font que diu el club amb què cadascú juga el **campionat
individual** d'aquesta temporada. Les pàgines del portal no el diuen enlloc: ni
la de divisions, ni la de fases, ni la de grups, ni la de participants; i
`individuals/inscripcions/{torneig}` del campionat de tres bandes 2026-27 està
buida («0 registres»).

I el club de l'individual **no** és el de la lliga. Un jugador pot anar fitxat a
la lliga per un club i jugar l'individual pel seu; i pot anar fitxat a la lliga
de tres bandes per un club i a la de 4 Modalitats per un altre. Al sorteig de la
prèvia d'Honor de 2026-27, MORENO CORTÉS juga l'individual per LLEIDA i PARERAS
MÉNDEZ per GRANOLLERS, i no és el que diria la plantilla de cap dels dos.

## Com és el PDF

**Dues columnes**, i això no es pot ignorar: llegit per línies, cada línia
barreja un jugador del grup de l'esquerra amb un del grup de la dreta, i els
clubs es creuen. La columna es reconeix per la coordenada `x`, no pel text.

```
Grup I (Granollers)                    Grup J (Matadepera)
MAS CANADELL, JOSEP Mª   GRANOLLERS    JIMÉNEZ GALERA, SERGI    GRANOLLERS
BENITEZ REINA, PAU       MATARÓ        PÉREZ ANDREU, ALEJANDRO  MATADEPERA
```

El club de cada fila comença sempre a la mateixa `x` dins de la seva columna —196
i 468 en aquell fitxer—, i el nom del jugador l'ocupa tot el que hi ha a
l'esquerra. Aquella `x` no es pot escriure al codi, perquè canvia de fitxer a
fitxer (175/436 al de 2a divisió), i per tant es *deduix*: és la que es repeteix
a totes les files de jugador de la columna.

El text entre parèntesis del títol d'un grup és el club que **acull** el grup, no
el de cap jugador. És el mateix parany que als PDF de rànquing: la seu no és el
club.

## La regla de classificació, que hi és escrita

Cada PDF diu qui passa de ronda, i no sempre és el mateix:

- «Es classificaran per a la final els dos primers de cada grup.» (Honor, prèvia)
- «…els primers de cada grup i els set millors segons.» (1a, pre-prèvia)
- «…el primer de cada grup i els quatre millors segons.» (2a, pre-prèvia)

Es desa tal com està escrita i no s'interpreta. Interessa perquè «els set millors
segons» vol dir que els segons s'han de poder comparar entre grups, que és el que
fa `individuals.ranquing_fase`.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

#: Marge en punts per repartir les paraules entre cel·les. Ample: una paraula que
#: comenci una mica abans de l'ancoratge ha de caure a la seva cel·la.
_MARGE_X = 6.0

#: Marge per dir que una paraula comença JUSTAMENT en una ancoratge. Estret a
#: posta: les files de jugador hi comencen exactes, i l'única cosa que ha
#: d'absorbir és l'arrodoniment. Amb sis punts, una línia del peu de pàgina del
#: sorteig de 1a («degudament@26 uniformats@115 és@194…») passava per jugador,
#: perquè 26 és a sis punts de 20 i 194 a dos de 196.
_MARGE_ANCORA = 2.5

#: Un títol de grup: «Grup I (Granollers)», «Grup A (Sant Adrià)».
_RE_GRUP = re.compile(r"^Grup\s+([A-ZÀ-Ú0-9]+)\s*(?:\(([^)]*)\))?\s*$", re.IGNORECASE)

#: La línia que diu qui passa de ronda.
_RE_REGLA = re.compile(r"^Es\s+classificar", re.IGNORECASE)

#: «DATA: 19 de setembre (16 hores) 40 caramboles / 50 entrades»
_RE_DISTANCIA = re.compile(r"(\d+)\s+caramboles\s*/\s*(\d+)\s+entrades", re.IGNORECASE)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", s)


@dataclass(frozen=True)
class JugadorSortejat:
    """Un jugador d'un grup, amb el club amb què hi juga."""

    jugador: str  # 'COGNOMS, NOM', tal com l'escriu la federació
    club: str  # tal com el PDF l'escriu: sovint sense prefix ('GRANOLLERS')
    grup: str  # 'I', 'A'…
    #: El club que acull el grup. NO és el club de cap jugador.
    seu: str | None = None


@dataclass
class SorteigFase:
    """El sorteig sencer d'una fase."""

    titol: str  # 'Pre-Prèvies 3 bandes 1a Divisió'
    #: Qui passa de ronda, tal com ho escriu la federació. `None` si no ho diu.
    regla: str | None = None
    caramboles: int | None = None
    entrades: int | None = None
    jugadors: list[JugadorSortejat] = field(default_factory=list)

    @property
    def grups(self) -> dict[str, list[JugadorSortejat]]:
        out: dict[str, list[JugadorSortejat]] = defaultdict(list)
        for j in self.jugadors:
            out[j.grup].append(j)
        return dict(out)


def _linies(page) -> list[list[dict]]:
    """Les paraules de la pàgina agrupades per línia, d'esquerra a dreta."""
    per_top: dict[int, list[dict]] = defaultdict(list)
    for w in page.extract_words():
        per_top[round(w["top"])].append(w)
    return [sorted(per_top[t], key=lambda w: w["x0"]) for t in sorted(per_top)]


def _text(paraules: list[dict]) -> str:
    return " ".join(w["text"] for w in paraules).strip()


def _blocs(fila: list[dict], buit: float = 14.0) -> list[list[dict]]:
    """Parteix una línia allà on hi ha un buit gros. Per als títols de grup.

    Serveix per a les línies de títol, on els dos grups estan separats per mig
    full. **No** serveix per a les files de jugador: el nom pot arribar a tocar
    el club («ANGARITA CRISTANCHO, ALEXANDER MONT-ROIG», vuit punts de
    separació) i llavors el buit no es veu. Aquelles es parteixen per `x` fixa,
    vegeu `_ancoratges`.
    """
    if not fila:
        return []
    out: list[list[dict]] = [[fila[0]]]
    for w in fila[1:]:
        if w["x0"] - out[-1][-1]["x1"] > buit:
            out.append([w])
        else:
            out[-1].append(w)
    return out


def _ancoratges(files: list[list[dict]]) -> list[float]:
    """Les `x` on comencen les cel·les d'una fila de jugador.

    El PDF dibuixa cada fila com quatre cel·les a `x` fixes —nom i club de la
    columna esquerra, nom i club de la dreta— i aquelles `x` són les mateixes a
    totes les files del fitxer, però canvien d'un fitxer a l'altre: (20, 176,
    304, 451) al sorteig d'Honor i (19, 175, 258, 436) al de 2a divisió. Per això
    es dedueixen i no s'escriuen al codi.

    Es reconeixen perquè es repeteixen: una `x` que surt a la meitat de les files
    és una cel·la, i una que surt a una fila sola és una paraula qualsevol del
    mig d'un nom. Amb un sol grup a la dreta buit —quan el nombre de grups és
    senar— les dues `x` de la dreta surten a menys files, i per això el llindar
    és baix.
    """
    if not files:
        return []
    compte = Counter(round(w["x0"]) for fila in files for w in fila)
    llindar = max(2, int(len(files) * 0.4))
    return sorted(float(x) for x, n in compte.items() if n >= llindar)


def _comenca(fila: list[dict], x: float) -> bool:
    """Hi ha alguna paraula que comenci justament en aquesta `x`?"""
    return any(abs(w["x0"] - x) <= _MARGE_ANCORA for w in fila)


def _cel_les(fila: list[dict], ancoratges: list[float]) -> list[str]:
    """El text de cada cel·la de la fila, una per ancoratge (buida si no n'hi ha)."""
    out = [""] * len(ancoratges)
    for k, x in enumerate(ancoratges):
        fi = ancoratges[k + 1] if k + 1 < len(ancoratges) else float("inf")
        dins = [w for w in fila if x - _MARGE_X <= w["x0"] < fi - _MARGE_X]
        out[k] = _text(dins)
    return out


def llegeix(pdf_path: str | Path) -> SorteigFase:
    """Llegeix el PDF del sorteig d'una fase."""
    import pdfplumber

    out = SorteigFase(titol="")
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages):
            files = _linies(page)
            if not files:
                continue
            if i == 0:
                out.titol = _text(files[0])
                for fila in files[:6]:
                    text = _text(fila)
                    if out.regla is None and _RE_REGLA.match(text):
                        out.regla = text
                    m = _RE_DISTANCIA.search(text)
                    if m and out.caramboles is None:
                        out.caramboles, out.entrades = int(m.group(1)), int(m.group(2))
            out.jugadors.extend(_llegeix_pagina(files))
    return out


def _titols(fila: list[dict]) -> list[tuple[float, str, str | None]]:
    """Els títols de grup d'una línia: `(centre, nom, seu)`, d'esquerra a dreta."""
    out = []
    for bloc in _blocs(fila):
        m = _RE_GRUP.match(_text(bloc))
        if m is None:
            return []  # una línia amb res més que títols, o no és de títols
        centre = (bloc[0]["x0"] + bloc[-1]["x1"]) / 2
        out.append((centre, m.group(1).upper(), (m.group(2) or "").strip() or None))
    return out


def _llegeix_pagina(files: list[list[dict]]) -> list[JugadorSortejat]:
    """Els jugadors d'una pàgina: títols de grup i, a sota, dues columnes de files."""
    titols = {k: t for k, fila in enumerate(files) if (t := _titols(fila))}
    if not titols:
        return []
    primer = min(titols)
    cos = [fila for k, fila in enumerate(files) if k > primer and k not in titols]
    ancoratges = _ancoratges(cos)
    if len(ancoratges) < 2:
        return []
    # Quatre ancoratges = dues columnes; la frontera és entre el club de
    # l'esquerra i el nom de la dreta. Dos = una columna sola.
    n_columnes = 2 if len(ancoratges) >= 4 else 1
    # La frontera entre columnes: entre el club de l'esquerra i el nom de la
    # dreta. Serveix per saber de quina columna és cada títol de grup, que va
    # centrat i per tant no cau a cap ancoratge.
    frontera = (ancoratges[1] + ancoratges[2]) / 2 if n_columnes == 2 else float("inf")

    out: list[JugadorSortejat] = []
    for k in sorted(titols):
        # Les files d'aquest bloc: de sota el títol fins al títol següent.
        seguents = [x for x in titols if x > k]
        fi = min(seguents) if seguents else len(files)
        del_grup = [files[x] for x in range(k + 1, fi) if x not in titols]
        for centre, nom_grup, seu in titols[k]:
            n_col = 0 if centre < frontera else 1
            if n_col >= n_columnes:
                continue
            i_nom, i_club = 2 * n_col, 2 * n_col + 1
            for fila in del_grup:
                # Es parteix amb TOTS els ancoratges: si es passés només els dos
                # de la columna, l'últim s'estendria fins al final del full i el
                # club de l'esquerra s'enduria la columna de la dreta sencera.
                # Una fila de jugador COMENÇA a les dues ancoratges de la seva
                # columna: hi ha una paraula justament on va el nom i una altra
                # justament on va el club. No n'hi ha prou amb que les dues
                # cel·les tinguin text: el peu de pàgina —vestimenta, horaris,
                # l'avís de l'entrenament— travessa el full de banda a banda i
                # n'omple totes quatre. D'aquí sortien dotze jugadors inventats
                # al sorteig d'Honor.
                if not (_comenca(fila, ancoratges[i_nom]) and _comenca(fila, ancoratges[i_club])):
                    continue
                cel_les = _cel_les(fila, ancoratges)
                if not cel_les[i_nom] or not cel_les[i_club]:
                    continue
                out.append(
                    JugadorSortejat(
                        jugador=cel_les[i_nom],
                        club=cel_les[i_club],
                        grup=nom_grup,
                        seu=seu,
                    )
                )
    return out


# --------------------------- descobriment al WordPress ---------------------------

WEB = "https://fcbillar.cat"
#: Sitemap de Yoast amb una pàgina per document publicat.
SITEMAP = f"{WEB}/wpfd_file-sitemap.xml"

#: Els PDF del campionat individual viuen a una categoria `individuals-…` del
#: gestor de fitxers; els dels opens, a `opens`. És l'única cosa que els
#: distingeix de manera fiable: pel nom del fitxer no es pot, perquè n'hi ha que
#: es diuen «grups-previa-open-…» i n'hi ha que es diuen «previes-3-bandes-…».
_RE_PDF_INDIVIDUAL = re.compile(
    r"https://fcbillar\.cat/download/\d+/(individuals-[a-z0-9-]+)/\d+/([^\"'<> ]+\.pdf)"
)

#: La modalitat, del nom de la categoria del gestor de fitxers.
_MODALITAT_DE_CATEGORIA = {
    "individuals-tres-bandes": "Tres bandes",
    "individuals-lliure": "Lliure",
    "individuals-banda": "Banda",
    "individuals-quadre-47-2": "Quadre 47/2",
    "individuals-quadre-71-2": "Quadre 71/2",
}


@dataclass(frozen=True)
class SorteigPublicat:
    """Un PDF de sorteig publicat al web, abans de baixar-lo."""

    url: str
    nom_fitxer: str
    categoria: str  # 'individuals-tres-bandes'
    modalitat: str  # 'Tres bandes'


def descobreix(client=None) -> list[SorteigPublicat]:
    """Els PDF de sorteig de fase del campionat individual publicats al web.

    Es va pel sitemap i s'entra a les pàgines que parlen de prèvies o de grups.
    De cada pàgina s'agafen només els PDF d'una categoria `individuals-…`: la
    pàgina també enllaça el calendari de la temporada des de la barra lateral, i
    els sortejos dels opens són a la categoria `opens`.
    """
    import httpx

    propi = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=60.0)
    try:
        sitemap = client.get(SITEMAP).text
        pagines = [
            u
            for u in re.findall(r"<loc>([^<]+)</loc>", sitemap)
            if re.search(r"previ|grups", u, re.IGNORECASE)
        ]
        vistos: dict[str, SorteigPublicat] = {}
        for pagina in pagines:
            for m in _RE_PDF_INDIVIDUAL.finditer(client.get(pagina).text):
                categoria = m.group(1)
                vistos[m.group(0)] = SorteigPublicat(
                    url=m.group(0),
                    nom_fitxer=m.group(2),
                    categoria=categoria,
                    modalitat=_MODALITAT_DE_CATEGORIA.get(categoria, ""),
                )
        return sorted(vistos.values(), key=lambda s: s.nom_fitxer)
    finally:
        if propi:
            client.close()

# --------------------------- quants se'n classifiquen ---------------------------

#: Els nombres escrits amb lletra que surten a les regles. La federació no passa
#: de deu, però costa el mateix tenir-los tots.
_NOMBRES = {
    "un": 1, "una": 1, "dos": 2, "dues": 2, "tres": 3, "quatre": 4, "cinc": 5,
    "sis": 6, "set": 7, "vuit": 8, "nou": 9, "deu": 10, "onze": 11, "dotze": 12,
    "tretze": 13, "catorze": 14, "quinze": 15, "setze": 16,
}

#: Les posicions dins d'un grup, escrites com les escriu la regla.
_POSICIONS = {"primer": 1, "primers": 1, "segon": 2, "segons": 2, "tercer": 3, "tercers": 3,
              "quart": 4, "quarts": 4}

#: «els dos primers de cada grup», «el primer de cada grup», «els primers de cada grup».
_RE_PER_GRUP = re.compile(
    r"\b(?:els?|les)\s+(?:(\w+)\s+)?(primers?|segons?|tercers?)\s+de\s+cada\s+grup",
    re.IGNORECASE,
)

#: «els set millors segons», «els quatre millors tercers».
_RE_MILLORS = re.compile(
    r"\b(?:els?|les)\s+(\w+)\s+millors\s+(primers?|segons?|tercers?|quarts?)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Classificats:
    """Quants passen de ronda, segons la regla escrita al PDF.

    `per_grup` són els que passen de cada grup i `millors` els que s'agafen a
    banda d'entre els que han quedat a la posició `posicio_millors` del seu grup.
    De «els primers de cada grup i els set millors segons» en surt
    `per_grup=1, millors=7, posicio_millors=2`.

    És la raó de ser del rànquing de fase: sense un ordre entre grups, «els set
    millors segons» no es pot resoldre.
    """

    per_grup: int
    millors: int = 0
    posicio_millors: int | None = None

    def places(self, n_grups: int) -> int:
        """Quantes places hi ha, amb aquest nombre de grups.

        La pre-prèvia de 1a de 2026-27 té 11 grups i la regla «els primers de
        cada grup i els set millors segons»: 11 + 7 = 18. La de 2a té 14 grups i
        «el primer de cada grup i els quatre millors segons»: 14 + 4 = 18. La
        prèvia d'Honor té 4 grups i «els dos primers»: 8. Les tres xifres quadren
        amb el que diu la federació.
        """
        return self.per_grup * n_grups + self.millors


def classificats(regla: str | None) -> Classificats | None:
    """Llegeix la regla d'un PDF de sorteig. `None` si no se'n surt.

    No s'inventa res: una regla que no encaixi amb cap dels dos patrons torna
    `None`, i llavors la fase no ensenya cap tall. Val més no dir res que dir un
    nombre de places que ningú no ha escrit.
    """
    if not regla:
        return None
    m = _RE_PER_GRUP.search(regla)
    if m is None:
        return None
    quants = _NOMBRES.get((m.group(1) or "").lower(), 1) if m.group(1) else 1
    # «els dos primers» = dos de cada grup. «els primers» = un de cada grup.
    per_grup = quants
    millors, posicio = 0, None
    mm = _RE_MILLORS.search(regla)
    if mm is not None:
        millors = _NOMBRES.get(mm.group(1).lower(), 0)
        posicio = _POSICIONS.get(mm.group(2).lower())
    return Classificats(per_grup=per_grup, millors=millors, posicio_millors=posicio)


def _norm_titol(s: str) -> str:
    """Per casar el títol d'un PDF amb el nom d'una divisió i d'una fase.

    Treu accents, puja a majúscules i **iguala el plural**: la federació titula
    el PDF «Pre-Prèvies 3 bandes 1a Divisió» i la fase al portal es diu
    «PRE-PRÈVIA». Sense això no casen mai.
    """
    t = unicodedata.normalize("NFKD", (s or "").upper())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^A-Z0-9]+", " ", t)
    t = re.sub(r"\bPREVIES\b", "PREVIA", t)
    t = re.sub(r"\bDIVISIONS\b", "DIVISIO", t)
    return f" {t.strip()} "


def casa_amb_fase(titol: str, divisio_nom: str, fase_nom: str) -> bool:
    """El títol d'un PDF de sorteig parla d'aquesta divisió i d'aquesta fase?

    Es demana que el títol contingui les dues coses. «Pre-Prèvies 3 bandes 1a
    Divisió» casa amb la divisió «1a DIVISIÓ» i la fase «PRE-PRÈVIA», i no amb la
    fase «PRÈVIA» d'aquella mateixa divisió, perquè «PRE-PREVIA» i «PREVIA» es
    comparen com a paraules senceres.
    """
    t = _norm_titol(titol)
    div = _norm_titol(divisio_nom).strip()
    fase = _norm_titol(fase_nom).strip()
    if not div or not fase:
        return False
    return div in t and f" {fase} " in t
