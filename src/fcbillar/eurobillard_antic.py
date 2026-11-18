"""Resultats d'abans del 2008 (i alguns campionats d'Europa) del web vell d'eurobillard.org.

El web vell de la CEB/UMB penjava els mateixos PDF de resultats que la UMB (llista
de jugadors, grups, rànquing final) a `/ausschreibung/upload/results/{id}/`. Ja no
existeix, però el Wayback Machine en guarda còpies. Es baixen a
`data/cache/eb_antic/{200000 + id}/` amb el mateix format que `umb_descarrega`, i es
carreguen amb `umb_carrega.carrega`. Una petició cada vegada, amb pausa.
"""

from __future__ import annotations

import html as _html
import json
import re
import time
from dataclasses import asdict
from pathlib import Path
from urllib.parse import quote, unquote

import httpx

from fcbillar.umb_descarrega import PAUSA, Esdeveniment, _client, porta_resultats

DESPLACAMENT = 200_000
CDX = "http://web.archive.org/cdx/search/cdx"
WAYBACK = "http://web.archive.org/web"
_RE_FITXER = re.compile(r"/ausschreibung/upload/results/(\d+)/([^?#]+\.pdf)$", re.I)
_RE_META = re.compile(
    r"Tournament:\s*(?P<nom>.*?)\s+Starts on:\s*(?P<ini>\d\d\.\d\d\.\d{4})\s+Ends on:\s*"
    r"(?P<fi>\d\d\.\d\d\.\d{4}).*?Place:\s*(?P<lloc>.*?)\s+(?:Material|Delegate|Hallo)",
    re.S,
)


def _get(c: httpx.Client, url: str, reintents: int = 4, maxim: float = 90) -> httpx.Response | None:
    """GET amb reintents i un límit de temps total: el Wayback a vegades va goteant bytes."""
    for i in range(reintents):
        try:
            inici = time.monotonic()
            with c.stream("GET", url) as r:
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                trossos = []
                for tros in r.iter_bytes():
                    trossos.append(tros)
                    if time.monotonic() - inici > maxim:
                        raise httpx.ReadTimeout("massa lent")
                r._content = b"".join(trossos)
                return r
        except httpx.HTTPError:
            time.sleep(5 * (i + 1))
    return None


def llista_fitxers(c: httpx.Client) -> dict[int, dict[str, str]]:
    """`{id: {nom del PDF: marca de temps de l'última còpia}}` de tot el que guarda el Wayback."""
    r = _get(
        c,
        f"{CDX}?url=www.eurobillard.org/ausschreibung/upload/results/&matchType=prefix"
        "&output=txt&fl=original,timestamp&filter=statuscode:200&limit=20000",
    )
    out: dict[int, dict[str, str]] = {}
    if r is None:
        return out
    for linia in r.text.splitlines():
        try:
            url, ts = linia.split(" ")
        except ValueError:
            continue
        m = _RE_FITXER.search(unquote(url))
        if m and porta_resultats(m.group(2)):
            fitxers = out.setdefault(int(m.group(1)), {})
            nom = m.group(2)
            if ts > fitxers.get(nom, ""):
                fitxers[nom] = ts
    return out


def llegeix_meta(id_: int, html: str) -> Esdeveniment | None:
    text = re.sub(r"(?is)<(style|script).*?</\1>|<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", _html.unescape(text))
    m = _RE_META.search(text)
    if not m:
        return None
    d, mm, a = m["ini"].split(".")
    d2, m2, a2 = m["fi"].split(".")
    return Esdeveniment(
        id=DESPLACAMENT + id_,
        nom=m["nom"].strip(),
        lloc=m["lloc"].strip(),
        inici=f"{a}-{mm}-{d}",
        fi=f"{a2}-{m2}-{d2}",
        descripcio="",
        font=f"http://www.eurobillard.org/ausschreibung/ausschreibung_detail.php?ID={id_}",
    )


def descarrega(cache: Path) -> tuple[list[Esdeveniment], list[str]]:
    """Baixa PDF i dades de cada prova. Torna les proves i els errors."""
    cache.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    evs: list[Esdeveniment] = []
    with _client() as c:
        llista = llista_fitxers(c)
        for id_, fitxers in sorted(llista.items()):
            time.sleep(PAUSA)
            detall = f"http://www.eurobillard.org/ausschreibung/ausschreibung_detail.php?ID={id_}"
            # «2020id_»: el Wayback serveix la còpia més propera a aquesta data, sense consultar el CDX.
            r = _get(c, f"{WAYBACK}/2020id_/{detall}")
            ev = llegeix_meta(id_, r.content.decode("latin-1")) if r else None
            if ev is None:
                errors.append(f"{id_}: sense pàgina de detall")
                continue
            ev.pdfs = sorted(fitxers)
            for nom, ts_f in sorted(fitxers.items()):
                dest = cache / str(ev.id) / nom
                if dest.exists() and dest.stat().st_size > 0:
                    continue
                url = f"{WAYBACK}/{ts_f}id_/http://www.eurobillard.org/ausschreibung/upload/results/{id_}/{quote(nom)}"
                time.sleep(PAUSA)
                r = _get(c, url)
                if r is None or not r.content.startswith(b"%PDF"):
                    errors.append(f"{id_}/{nom}")
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)
            evs.append(ev)
            # Es desa a cada prova: si s'atura, el que ja s'ha baixat es pot carregar.
            (cache / "esdeveniments.json").write_text(
                json.dumps([asdict(e) for e in evs], ensure_ascii=False, indent=1), encoding="utf-8"
            )
    return evs, errors
