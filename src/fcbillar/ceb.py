"""Resultats dels campionats d'Europa de la CEB (eurobillard.org).

A diferència de la UMB, la CEB no penja PDF: cada pàgina d'esdeveniment porta
dins del HTML les pestanyes de jugadors, partides i classificació. Els mundials
de la llista de la CEB apunten als PDF de la UMB i no es llegeixen aquí.

Els ids es desen com `100000 + id de la CEB` perquè no xoquin amb els de la UMB.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, Tag

from fcbillar.umb import Classificat, Costat, Jugador, Llegit, Partida
from fcbillar.umb_descarrega import PAUSA, UA, Esdeveniment, _get

BASE = "https://www.eurobillard.org"
DESPLACAMENT = 100_000
#: Les temporades de la llista d'esdeveniments (2014-15 en endavant), pel seu codi.
TEMPORADES = [10, 11, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 13, 14]
#: Proves per equips o de clubs: no tenen resultats individuals.
_RE_EQUIPS = re.compile(r"(?i)team|coupe d.europe|euro-?league|assembly|club|biathlon|pentathlon")
_RE_FILA = re.compile(r"<tr><td>(\d\d-\d\d-\d{4})<br>(\d\d-\d\d-\d{4})</td>(.*?)</tr>", re.S)
_RE_ENLLAC = re.compile(r"<a href='(/events/([^']*?)-(\d+)\.html)'[^>]*>([^<]*)</a>")

# Els països que la CEB escriu amb tres lletres als grups.
_ISO3 = {
    "ESP": "ES", "CHE": "CH", "DEU": "DE", "NLD": "NL", "DNK": "DK", "GRE": "GR", "GRC": "GR",
    "FRA": "FR", "BEL": "BE", "ITA": "IT", "AUT": "AT", "SWE": "SE", "TUR": "TR", "PRT": "PT",
    "CZE": "CZ", "POL": "PL", "HUN": "HU", "FIN": "FI", "NOR": "NO", "GBR": "GB", "SVN": "SI",
}  # fmt: skip


def _nat(codi: str) -> str:
    return _ISO3.get(codi, codi)[:2]


def llegeix_llista(html: str) -> list[Esdeveniment]:
    """Els esdeveniments d'una temporada de la llista de la CEB."""
    out = []
    for inici, fi, resta in ((m[1], m[2], m[3]) for m in _RE_FILA.finditer(html)):
        e = _RE_ENLLAC.search(resta)
        if not e:  # un mundial: l'enllaç va a la UMB
            continue
        cel = re.findall(r"<td>(.*?)</td>", resta, re.S)
        lloc = re.sub(r"<[^>]+>|&nbsp;", "", cel[-1]).strip() if cel else ""
        d, m_, a = inici.split("-")
        d2, m2, a2 = fi.split("-")
        out.append(
            Esdeveniment(
                id=DESPLACAMENT + int(e.group(3)),
                nom=re.sub(r"\s+", " ", e.group(4)).strip(),
                lloc=lloc,
                inici=f"{a}-{m_}-{d}",
                fi=f"{a2}-{m2}-{d2}",
                descripcio="",
                pdfs=[],
                font=BASE + e.group(1),
            )
        )
    return out


def es_individual(ev: Esdeveniment) -> bool:
    return not _RE_EQUIPS.search(ev.nom)


def descobreix(cache: Path) -> list[Esdeveniment]:
    """Llista les temporades i baixa la pàgina de cada prova individual a `cache/{id}.html`."""
    cache.mkdir(parents=True, exist_ok=True)
    vistos: dict[int, Esdeveniment] = {}
    with httpx.Client(headers={"User-Agent": UA}, timeout=60, follow_redirects=True) as c:
        for s in TEMPORADES:
            r = _get(c, f"{BASE}/pages/events-29.html?event_season={s}&event_type=")
            time.sleep(PAUSA)
            if r is None:
                continue
            for e in llegeix_llista(r.text):
                if es_individual(e):
                    vistos.setdefault(e.id, e)
        for e in vistos.values():
            dest = cache / f"{e.id - DESPLACAMENT}.html"
            if dest.exists() and dest.stat().st_size > 0:
                continue
            r = _get(c, e.font.replace(" ", "%20"))
            time.sleep(PAUSA)
            if r is not None:
                dest.write_bytes(r.content)
    evs = sorted(vistos.values(), key=lambda e: e.id)
    (cache / "esdeveniments.json").write_text(
        json.dumps([asdict(e) for e in evs], ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return evs


def _caixes(tab: Tag) -> list[list[Tag]]:
    """Les files de dades d'una pestanya: els `div` de cada `box_ligne` que no és capçalera."""
    return [
        d.find_all("div", recursive=False)
        for d in tab.find_all("div", class_="box_ligne")
        if "box_titres" not in d.get("class", [])
    ]


def _parells(cel: Tag) -> list[str]:
    return [s.get_text(strip=True) for s in cel.find_all("span")]


def _nom_nat(text: str) -> tuple[str, str | None]:
    m = re.match(r"^(.*?)\s*\(([A-Z]{2,3})\)\s*$", text.strip())
    return (m.group(1).strip(), _nat(m.group(2))) if m else (text.strip(), None)


def llegeix_pagina(contingut: bytes) -> Llegit:
    """Jugadors, partides i classificació final d'una pàgina d'esdeveniment."""
    sopa = BeautifulSoup(contingut, "lxml")
    res = Llegit()
    tabs = {n: sopa.find("div", id=f"onglet_{n}") for n in (6, 8, 9)}

    nats: dict[str, str | None] = {}
    if tabs[6]:
        for c in _caixes(tabs[6]):
            if len(c) >= 2 and c[1].get_text(strip=True):
                nom, nat = _nom_nat(c[1].get_text(" ", strip=True))
                if nom:
                    nats[nom] = nat
    if tabs[9]:
        for c in _caixes(tabs[9]):
            t = [x.get_text(" ", strip=True) for x in c]
            if len(t) < 2 or not t[0].isdigit():
                continue
            nom, nat = _nom_nat(t[1])
            nats[nom] = nat or nats.get(nom)
            if len(t) < 8:  # eliminats a la fase prèvia: tenen lloc però no estadístiques
                res.classificacio.append(
                    Classificat(int(t[0]), nom, nat, None, None, None, None, None, None, None, None)
                )
                continue
            try:
                res.classificacio.append(
                    Classificat(
                        posicio=int(t[0]), jugador=nom, nacionalitat=nat, ronda=None,
                        punts=int(t[2]), mitjana=float(t[5]), mitjana_particular=float(t[7]) if t[7] else None,
                        serie1=int(t[6]), serie2=None, caramboles=int(t[3]), entrades=int(t[4]),
                    )
                )  # fmt: skip
            except ValueError:
                res.errors.append(f"classificació: fila que no quadra {t[:3]}")
    if tabs[8]:
        for c in _caixes(tabs[8]):
            if len(c) < 11:
                continue
            try:
                fase = c[3].get_text(strip=True)
                grup = c[4].get_text(strip=True)
                noms = [s.get_text(strip=True) for s in c[5].find_all("span")]
                mp, car, inn, avg, hr = (_parells(x) for x in c[6:11])
                if len(noms) != 2 or any(len(x) != 2 for x in (mp, car, inn, avg, hr)):
                    continue  # partida sense jugar o sense totes les dades
                costats = [
                    Costat(
                        jugador=noms[i], caramboles=int(car[i]), mitjana=float(avg[i]),
                        punts=int(mp[i]), serie=int(hr[i]), serie2=None, entrades=int(inn[i]),
                    )
                    for i in (0, 1)
                ]  # fmt: skip
            except (ValueError, IndexError) as e:
                res.errors.append(f"partida: {type(e).__name__}")
                continue
            res.partides.append(
                Partida(
                    fase=fase, grup=grup, ordre=len(res.partides) + 1, a=costats[0], b=costats[1]
                )
            )
    noms = {n for p in res.partides for n in (p.a.jugador, p.b.jugador)} | set(nats)
    res.jugadors = [Jugador(nom=n, nacionalitat=nats.get(n)) for n in sorted(noms)]
    return res
