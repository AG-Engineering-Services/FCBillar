"""Baixa de Wayback Machine els fitxers de la web vella de la RFEB.

La web de la RFEB d'abans del 2012 (`rfeb.org/0HOME/PDF/…`, `9Archivo/…`) i les
carpetes `noticiasAAAA` ja no existeixen; només en queden còpies a
web.archive.org. Aquí es llisten amb l'API CDX i es baixen d'una en una, amb
pausa entre peticions i sense enviar cap dada personal: l'agent és genèric.

Els fitxers es desen a `<destí>/<camí original>` (sense domini ni consulta),
que és l'estructura que esperen `rfeb-individuals` i `rfeb-fases`.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

CDX = "http://web.archive.org/cdx/search/cdx"
AGENT = "Mozilla/5.0 (compatible; research-script)"
#: Segons entre dues peticions. Wayback talla les connexions si se'n fan massa.
PAUSA = 2.0


@dataclass(frozen=True)
class Captura:
    marca: str  # AAAAMMDDhhmmss
    url: str
    tipus: str


def ruta_local(url: str) -> str:
    """`http://www.rfeb.org:80/0HOME/PDF/CE-Msc%20Sub.pdf?v=2` → `0HOME/PDF/CE-Msc_Sub.pdf`."""
    sense_domini = re.sub(r"^https?://(?:www\.)?rfeb\.org(?::\d+)?/", "", url)
    return sense_domini.split("?", 1)[0].replace("%20", "_")


def llegeix_cdx(text: str) -> list[Captura]:
    """Les captures d'una resposta CDX `fl=timestamp,original,mimetype,statuscode`.

    Només la més nova de cada fitxer, i només les que van respondre 200.
    """
    millors: dict[str, Captura] = {}
    for linia in text.splitlines():
        parts = linia.split()
        if len(parts) < 4 or parts[3] != "200":
            continue
        cap = Captura(parts[0], parts[1], parts[2])
        clau = ruta_local(cap.url)
        if clau not in millors or cap.marca > millors[clau].marca:
            millors[clau] = cap
    return sorted(millors.values(), key=lambda c: ruta_local(c.url))


def llista(patro: str = "rfeb.org/*") -> list[Captura]:
    """Totes les captures de `patro` (`rfeb.org/*`, `www.rfeb.org/0HOME/*`…)."""
    import httpx

    r = httpx.get(
        CDX,
        params={
            "url": patro,
            "output": "text",
            "fl": "timestamp,original,mimetype,statuscode",
            "filter": "statuscode:200",
            "collapse": "urlkey",
        },
        headers={"User-Agent": AGENT},
        timeout=300.0,
    )
    r.raise_for_status()
    return llegeix_cdx(r.text)


def baixa(captures: list[Captura], desti: Path, pausa: float = PAUSA) -> dict[str, str]:
    """Baixa les captures que encara no hi són. `{camí: «ok» o el motiu de l'error}`."""
    import httpx

    resultat: dict[str, str] = {}
    for cap in captures:
        cami = desti / ruta_local(cap.url)
        if cami.exists() and cami.stat().st_size:
            continue
        # `id_` demana el fitxer tal com era, sense el marc de Wayback.
        url = f"http://web.archive.org/web/{cap.marca}id_/{cap.url}"
        for intent in range(3):
            try:
                r = httpx.get(
                    url, headers={"User-Agent": AGENT}, follow_redirects=True, timeout=90.0
                )
                r.raise_for_status()
                cami.parent.mkdir(parents=True, exist_ok=True)
                cami.write_bytes(r.content)
                resultat[ruta_local(cap.url)] = "ok"
                break
            except httpx.HTTPError as exc:
                resultat[ruta_local(cap.url)] = f"{type(exc).__name__}"
                time.sleep(pausa * (intent + 1))
        time.sleep(pausa)
    return resultat
