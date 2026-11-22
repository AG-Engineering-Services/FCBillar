"""Resultats de carambola de Kozoom, de les còpies que en guarda el Wayback Machine.

Kozoom publicava, de cada prova que retransmetia o seguia (copes del món,
campionats d'Europa i del món, grans premis, lligues nacionals…), la
classificació final i totes les partides. La web nova (`home.kozoom.com`) ja no
té aquestes pàgines, però el Wayback en conserva milers. Són la font que falta
per als campionats d'Europa agrupats des del 2023 —eurobillard.org només en
conserva l'horari— i per a les proves de la UMB que no tenen cap PDF.

De cada prova hi ha, a `www.kozoom.com/en/billiard-carom/results/{id}/`:

- `rankings.html`: la classificació final (posició, jugador, punts, entrades,
  mitjana, sèrie);
- `matches.html`: totes les partides, si la prova la tenia;
- i, des de cada jugador de la classificació,
  `players/{jugador}/matches.html?event_id={id}`: les seves partides en aquella
  prova. Quan no hi ha `matches.html`, les partides es reconstrueixen d'aquí.

Les partides porten, per a cada jugador, el país (la bandera), el club entre
parèntesis a les lligues, els punts o caramboles, les entrades, la mitjana i la
sèrie, i el guanyador marcat. Les partides a sets porten, a cada set, els punts
i les entrades de cada jugador.

Els noms van «Esteve MATA» i es desen a l'ordre de la UMB, «MATA Esteve», perquè
lliguin amb els de les altres fonts. Els ids de les proves es desen com
`300000 + id de Kozoom`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from bs4 import BeautifulSoup, Tag

from fcbillar.umb import Classificat, Costat, Jugador, Llegit, Partida, nom_umb

DESPLACAMENT = 300_000
BASE = "https://www.kozoom.com/en/billiard-carom"

#: «3-Cushion - World Cup - Hurghada (EGY) - 9/4/06 to 9/9/06»
_RE_TITOL = re.compile(
    r"^(?P<disc>.+?) - (?P<nom>.+?) - (?P<lloc>[^-]*?\((?P<pais>[A-Z]{3})\)|\s*\([A-Z]{3}\)) - "
    r"(?P<ini>\d{1,2}/\d{1,2}/\d{2})(?: to (?P<fi>\d{1,2}/\d{1,2}/\d{2}))?"
)
_RE_CLUB = re.compile(r"\s*\(([^()]*)\)\s*$")


@dataclass
class Titol:
    disciplina: str
    nom: str
    lloc: str
    inici: date | None
    fi: date | None


def _data(text: str | None) -> date | None:
    if not text:
        return None
    m, d, a = (int(x) for x in text.split("/"))
    # Kozoom hi té també l'històric dels europeus (1925, 1947…): cap prova és posterior al 2024.
    return date(2000 + a if a <= 24 else 1900 + a, m, d)


def llegeix_titol(text: str) -> Titol | None:
    """El títol d'una prova, del `<h3>` de la pàgina o del `<title>` sense el prefix."""
    text = re.sub(
        r"^(Carom Billiard|Results Carom Billiard|Matches Carom Billiard)\s*", "", text
    ).strip()
    text = re.sub(r"^(Ranking|Rankings|Matches)\s+", "", text)
    text = text.lstrip("- ").strip()
    text = re.sub(r"\s+-\s+Kozoom$", "", text)
    m = _RE_TITOL.match(text)
    if not m:
        return None
    return Titol(
        disciplina=m.group("disc").strip(),
        nom=m.group("nom").strip(),
        lloc=(m.group("lloc") or "").strip(),
        inici=_data(m.group("ini")),
        fi=_data(m.group("fi")) or _data(m.group("ini")),
    )


def _pais(p: Tag) -> str | None:
    img = p.find("img")
    if not img or not img.get("src"):
        return None
    m = re.search(r"/flags/([a-z]{2})\.png", img["src"])
    return m.group(1).upper() if m else None


def _jugador(p: Tag) -> tuple[str, str | None, str | None]:
    """(nom a l'ordre de la UMB, país, club) d'un `<p>` de jugador."""
    text = " ".join(p.get_text(" ").split())
    club = None
    if m := _RE_CLUB.search(text):
        club, text = m.group(1).strip(), text[: m.start()].strip()
    return nom_umb(text), _pais(p), club


def _num(text: str) -> float | None:
    text = text.strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _parells(td: Tag) -> list[Tag]:
    return td.find_all("p", recursive=False) or td.find_all("p")


def _guanya(p: Tag) -> bool:
    return p.find("strong") is not None


def llegeix_partides(html: str) -> tuple[Titol | None, list[Partida], list[Jugador]]:
    """Les partides d'una pàgina `matches.html` (de la prova o d'un jugador)."""
    sopa = BeautifulSoup(html, "lxml")
    titol = None
    # La taula de partides va després d'un <h3> amb el títol de la prova, tant a
    # la pàgina de la prova com a la d'un jugador.
    taula = next(
        (
            t
            for t in sopa.select("table.listing")
            if "stage"
            in " ".join(td.get_text(" ").lower() for td in t.select("thead td, thead th"))
        ),
        None,
    )
    if taula is None:
        return titol, [], []
    if (h3 := taula.find_previous("h3")) is not None:
        titol = llegeix_titol(h3.get_text(" ").strip())
    capcalera = [td.get_text(" ").strip().lower() for td in taula.select("thead td, thead th")]
    a_sets = any(c.startswith("set") for c in capcalera)
    partides: list[Partida] = []
    jugadors: dict[str, Jugador] = {}
    for tr in taula.select("tbody tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 3:
            continue
        fase = tds[0].get_text(" ").strip()
        pj = _parells(tds[1])
        if len(pj) != 2:
            continue
        (na, pa, _ca), (nb, pb, _cb) = _jugador(pj[0]), _jugador(pj[1])
        for n, p in ((na, pa), (nb, pb)):
            jugadors.setdefault(n, Jugador(n, p))
        cols = {capcalera[i]: tds[i] for i in range(min(len(capcalera), len(tds)))}
        if a_sets:
            costat = _costats_a_sets(tds, capcalera, na, nb)
        else:
            costat = _costats(cols, na, nb)
        if costat is None:
            continue
        a, b = costat
        partides.append(Partida(fase=fase, grup="", ordre=len(partides) + 1, a=a, b=b))
    return titol, partides, list(jugadors.values())


def _valors(td: Tag | None) -> list[float | None]:
    if td is None:
        return [None, None]
    ps = _parells(td)
    vals = [_num(p.get_text(" ")) for p in ps]
    return (vals + [None, None])[:2]


def _costats(cols: dict[str, Tag], na: str, nb: str) -> tuple[Costat, Costat] | None:
    punts = cols.get("points") or cols.get("pts")
    if punts is None:
        return None
    car = _valors(punts)
    ent = _valors(cols.get("innings") or cols.get("inn."))
    avg = _valors(cols.get("avg."))
    run = _valors(cols.get("run"))
    if car[0] is None or car[1] is None:
        return None
    guanya = [_guanya(p) for p in _parells(punts)] + [False, False]
    pa, pb = (
        (2, 0) if guanya[0] and not guanya[1] else (0, 2) if guanya[1] and not guanya[0] else (1, 1)
    )

    def costat(i: int, nom: str, punts_: int) -> Costat:
        e = int(ent[i]) if ent[i] is not None else 0
        c = int(car[i])
        m = avg[i] if avg[i] is not None else (round(c / e, 3) if e else 0.0)
        return Costat(
            jugador=nom,
            caramboles=c,
            mitjana=m,
            punts=punts_,
            serie=int(run[i]) if run[i] is not None else None,
            serie2=None,
            entrades=e,
        )

    return costat(0, na, pa), costat(1, nb, pb)


def _costats_a_sets(
    tds: list[Tag], capcalera: list[str], na: str, nb: str
) -> tuple[Costat, Costat] | None:
    """Una partida a sets: a cada set, els punts i (en petit) les entrades de cada jugador."""
    sets_a: list[tuple[int, int]] = []
    sets_b: list[tuple[int, int]] = []
    guanyats = [0, 0]
    avg: list[float | None] = [None, None]
    run: list[float | None] = [None, None]
    for i, nom_col in enumerate(capcalera):
        if i >= len(tds):
            break
        td = tds[i]
        if nom_col.startswith("set"):
            ps = _parells(td)
            if len(ps) != 2:
                continue
            fila = []
            for p in ps:
                petit = p.find("small")
                ent = _num(petit.get_text()) if petit else None
                if petit:
                    petit.extract()
                car = _num(p.get_text(" "))
                fila.append((car, ent, _guanya(p)))
            if any(x[0] is None for x in fila):
                continue
            sets_a.append((int(fila[0][0]), int(fila[0][1] or 0)))
            sets_b.append((int(fila[1][0]), int(fila[1][1] or 0)))
            if fila[0][2] and not fila[1][2]:
                guanyats[0] += 1
            elif fila[1][2] and not fila[0][2]:
                guanyats[1] += 1
        elif nom_col == "avg.":
            avg = _valors(td)
        elif nom_col == "run":
            run = _valors(td)
    if not sets_a:
        return None
    pa, pb = (
        (2, 0) if guanyats[0] > guanyats[1] else (0, 2) if guanyats[1] > guanyats[0] else (1, 1)
    )

    def costat(nom: str, sets: list[tuple[int, int]], i: int, punts: int) -> Costat:
        car = sum(c for c, _ in sets)
        ent = sum(e for _, e in sets)
        return Costat(
            jugador=nom,
            caramboles=car,
            mitjana=avg[i] if avg[i] is not None else (round(car / ent, 3) if ent else 0.0),
            punts=punts,
            serie=int(run[i]) if run[i] is not None else None,
            serie2=None,
            entrades=ent,
            sets=sets,
        )

    return costat(na, sets_a, 0, pa), costat(nb, sets_b, 1, pb)


def llegeix_classificacio(html: str) -> tuple[Titol | None, list[Classificat], list[Jugador]]:
    """La classificació final d'una pàgina `rankings.html`."""
    sopa = BeautifulSoup(html, "lxml")
    titol = None
    if t := sopa.find("title"):
        titol = llegeix_titol(t.get_text(" ").strip())
    taula = sopa.select_one("table.listing")
    if taula is None:
        return titol, [], []
    capcalera = [th.get_text(" ").strip().lower() for th in taula.select("thead th, thead td")]
    files: list[Classificat] = []
    jugadors: list[Jugador] = []
    for tr in taula.select("tbody tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) != len(capcalera):
            continue
        cols = {capcalera[i]: tds[i] for i in range(len(tds))}
        pos = _num(cols.get("rank").get_text()) if cols.get("rank") else None
        # La bandera pot ser a la mateixa cel·la que el nom o a una de pròpia (l'artístic).
        enllac = next((td for td in tds if td.find("a", href=re.compile(r"/players/"))), tds[1])
        nom, pais, _club = _jugador(enllac)
        pais = pais or next((_pais(td) for td in tds if _pais(td)), None)
        if pos is None or not nom:
            continue

        def val(*claus: str) -> float | None:
            for k in claus:
                if k in cols:
                    return _num(cols[k].get_text())
            return None

        car, ent, avg, run = val("pts", "points"), val("inn.", "innings"), val("avg."), val("run")
        files.append(
            Classificat(
                posicio=int(pos),
                jugador=nom,
                nacionalitat=pais,
                ronda=None,
                punts=None,
                mitjana=avg,
                mitjana_particular=None,
                serie1=int(run) if run is not None else None,
                serie2=None,
                caramboles=int(car) if car is not None else None,
                entrades=int(ent) if ent is not None else None,
            )
        )
        jugadors.append(Jugador(nom, pais))
    return titol, files, jugadors


def enllacos_jugadors(html: str, prova: int) -> list[str]:
    """Els enllaços `players/…/matches.html?event_id=…` d'una classificació."""
    return sorted(
        set(
            re.findall(
                rf'href="(/en/billiard-carom/players/[^"?]+/matches\.html\?event_id={prova})"', html
            )
        )
    )


def de_les_pagines_de_jugador(pagines: list[str]) -> Llegit:
    """Les partides d'una prova reconstruïdes de les pàgines de cada jugador.

    Cada partida surt a les pàgines dels dos jugadors: es queda una sola vegada.
    """
    vistes: set[tuple] = set()
    ll = Llegit()
    jugadors: dict[str, Jugador] = {}
    for html in pagines:
        _t, partides, js = llegeix_partides(html)
        for j in js:
            jugadors.setdefault(j.nom, j)
        for p in partides:
            clau = (
                p.fase,
                frozenset(
                    {
                        (p.a.jugador, p.a.caramboles, p.a.entrades),
                        (p.b.jugador, p.b.caramboles, p.b.entrades),
                    }
                ),
            )
            if clau in vistes:
                continue
            vistes.add(clau)
            p.ordre = len(ll.partides) + 1
            ll.partides.append(p)
    ll.jugadors = list(jugadors.values())
    return ll


def proves_del_jugador(html: str) -> list[tuple[int, str]]:
    """Totes les proves d'un jugador a Kozoom: el desplegable de la seva pàgina de partides."""
    sopa = BeautifulSoup(html, "lxml")
    sel = sopa.find("select", id="recherche_matches_event_id")
    if sel is None:
        return []
    return [
        (int(o["value"]), " ".join(o.get_text(" ").split()))
        for o in sel.find_all("option")
        if o.get("value", "").isdigit()
    ]
