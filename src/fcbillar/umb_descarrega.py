"""Descoberta i descàrrega dels resultats oficials de la UMB (umb-carom.org).

El web és Blazor però cada pàgina `/events/{id}` ja porta renderitzats l'esdeveniment
(JSON-LD) i els enllaços als PDF de `files.umb-carom.org/Uploads/Results/{id}/`.
Es baixa tot a `data/cache/umb/{id}/`, en sèrie i amb pausa: és un web d'una
federació, no una API.
"""

from __future__ import annotations

import html as _html
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote

import httpx

BASE = "https://www.umb-carom.org"  # l'apex té el certificat d'un altre nom
UA = "fcbillar-resultats/1.0 (lectura puntual de resultats publics)"
PAUSA = 1.0
_RE_PDF = re.compile(r'https?://files\.umb-carom\.org/Uploads/Results/(\d+)/([^"<>]+?\.pdf)', re.I)
# El servidor escapa el «+» com a `&#x2B;`.
_RE_LD = re.compile(r'<script type="application/ld(?:\+|&#x2B;)json">(.*?)</script>', re.S)


# El que no porta resultats: horaris, entrenaments, sorteig i classificacions de grup
# (que ja surten de la taula de partides i de la classificació final).
_RE_NO_RESULTATS = re.compile(
    r"(?i)time ?table|training|groups?[ _-]*ranking|rank_pdf|^[A-Z]?[._ ]*groups?\.pdf$|poster"
)


def porta_resultats(nom: str) -> bool:
    return not _RE_NO_RESULTATS.search(nom)


@dataclass
class Esdeveniment:
    id: int
    nom: str
    lloc: str
    inici: str | None
    fi: str | None
    descripcio: str
    pdfs: list[str] = field(default_factory=list)
    font: str = ""  # només a la CEB: la pàgina de l'esdeveniment


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": UA}, timeout=60, follow_redirects=True)


def _get(c: httpx.Client, url: str, reintents: int = 3) -> httpx.Response | None:
    """GET amb reintents; None si el servidor diu 404 o no hi ha manera."""
    for i in range(reintents):
        try:
            r = c.get(url)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r
        except httpx.HTTPError:
            if i == reintents - 1:
                return None
            time.sleep(2 * (i + 1))
    return None


def llegeix_esdeveniment(id_: int, html: str) -> Esdeveniment | None:
    """L'esdeveniment d'una pàgina, o None si no n'és cap (id inexistent)."""
    ld = None
    for bloc in _RE_LD.findall(html):
        try:
            d = json.loads(bloc)
        except ValueError:
            continue
        if d.get("@type") == "SportsEvent":
            ld = d
            break
    if ld is None:
        return None
    pdfs = sorted(
        {
            _html.unescape(unquote(m.group(2)))
            for m in _RE_PDF.finditer(html)
            if int(m.group(1)) == id_
        }
    )
    return Esdeveniment(
        id=id_,
        nom=ld.get("name", ""),
        lloc=(ld.get("location") or {}).get("name", ""),
        inici=ld.get("startDate"),
        fi=ld.get("endDate"),
        descripcio=ld.get("description", ""),
        pdfs=pdfs,
    )


def descobreix(cache: Path, maxim: int = 450, buit_final: int = 25) -> list[Esdeveniment]:
    """Recorre els ids 1..maxim i desa `esdeveniments.json`.

    Passat l'últim id amb dades, s'atura després de `buit_final` ids seguits sense res.
    """
    cache.mkdir(parents=True, exist_ok=True)
    trobats: list[Esdeveniment] = []
    sense = 0
    with _client() as c:
        for i in range(1, maxim + 1):
            r = _get(c, f"{BASE}/events/{i}")
            ev = llegeix_esdeveniment(i, r.text) if r else None
            if ev:
                trobats.append(ev)
                sense = 0
            else:
                sense += 1
                if sense >= buit_final and i > 300:
                    break
            time.sleep(PAUSA)
    (cache / "esdeveniments.json").write_text(
        json.dumps([asdict(e) for e in trobats], ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return trobats


def carrega_esdeveniments(cache: Path) -> list[Esdeveniment]:
    f = cache / "esdeveniments.json"
    if not f.exists():
        return []
    return [Esdeveniment(**d) for d in json.loads(f.read_text(encoding="utf-8"))]


def descarrega(cache: Path, esdeveniments: list[Esdeveniment]) -> tuple[int, int, list[str]]:
    """Baixa els PDF que falten. Retorna (nous, ja_hi_eren, errors)."""
    nous = existents = 0
    errors: list[str] = []
    with _client() as c:
        for ev in esdeveniments:
            for nom in sorted({_html.unescape(n) for n in ev.pdfs if porta_resultats(n)}):
                dest = cache / str(ev.id) / nom
                if dest.exists() and dest.stat().st_size > 0:
                    existents += 1
                    continue
                url = f"https://files.umb-carom.org/Uploads/Results/{ev.id}/{quote(nom)}"
                r = _get(c, url)
                time.sleep(PAUSA)
                if r is None or not r.content.startswith(b"%PDF"):
                    errors.append(f"{ev.id}/{nom}")
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)
                nous += 1
    return nous, existents, errors
