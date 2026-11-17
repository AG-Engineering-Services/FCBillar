"""Descarrega i desa les partides de la CEB, la UMB i la RFEB.

Tot el que es baixa queda a `data/cache/externes/<font>/`: tornar a passar no
torna a demanar res a ningú, llevat que es demani `refresca`. Les tres webs són
petites i no són nostres; es va a poc a poc (`ESPERA_S` entre peticions).
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path

import httpx

from fcbillar.externes import ceb, rfeb, umb
from fcbillar.externes.desat import desa
from fcbillar.externes.model import Resultat

log = logging.getLogger(__name__)

USER_AGENT = "FCBillar/2.0 (seguiment de jugadors federats; contacte via fcbillar.cat)"
ESPERA_S = 0.5

Avis = Callable[[str], None]


class Descarregador:
    """GET amb còpia a disc i una pausa entre peticions."""

    def __init__(self, arrel: Path, refresca: bool = False) -> None:
        self.arrel = arrel
        self.refresca = refresca
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True
        )
        self._darrera = 0.0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Descarregador:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def bytes(self, url: str, desti: Path) -> bytes | None:
        """El contingut d'`url`, de la còpia a `desti` si n'hi ha. None si és un 404."""
        if desti.exists() and not self.refresca:
            return desti.read_bytes()
        espera = ESPERA_S - (time.monotonic() - self._darrera)
        if espera > 0:
            time.sleep(espera)
        self._darrera = time.monotonic()
        r = self._client.get(url)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        desti.parent.mkdir(parents=True, exist_ok=True)
        desti.write_bytes(r.content)
        return r.content


def _desa(conn, resultat: Resultat, avisa: Avis) -> None:
    e = resultat.esdeveniment
    partides, totals = desa(conn, resultat)
    que = f"{partides} partides" if partides else f"{totals} jugadors"
    avisa(f"  {e.font} {e.id}: {e.nom} ({e.temporada or 'sense temporada'}) · {que}")


# --- CEB ------------------------------------------------------------------------


def ingesta_ceb(conn, ids: Iterable[int], d: Descarregador, avisa: Avis = log.info) -> int:
    """Europeus de la CEB amb partides. Retorna quants se n'han desat.

    Els Mundials i les Copes del Món que surten al calendari de la CEB no es
    desen d'aquí: la font bona és la UMB, i així no surten dos cops.
    """
    desats = 0
    for id_ in ids:
        cos = d.bytes(ceb.URL_ESDEVENIMENT.format(id=id_), d.arrel / "ceb" / f"{id_}.html")
        if cos is None:
            continue
        try:
            resultat = ceb.llegeix_esdeveniment(cos.decode("utf-8", errors="replace"), id_)
        except ceb.SensePartides:
            continue
        if resultat.esdeveniment.tipus != "europeu":
            continue
        _desa(conn, resultat, avisa)
        desats += 1
    return desats


# --- UMB ------------------------------------------------------------------------


def ingesta_umb(conn, ids: Iterable[int], d: Descarregador, avisa: Avis = log.info) -> int:
    """Mundials i Copes del Món de la UMB. Retorna quants se n'han desat."""
    desats = 0
    for id_ in ids:
        cos = d.bytes(umb.URL_ESDEVENIMENT.format(id=id_), d.arrel / "umb" / str(id_) / "event.html")
        if cos is None:
            continue
        pagina = cos.decode("utf-8", errors="replace")
        try:
            esdeveniment = umb.llegeix_esdeveniment(pagina, id_)
        except umb.SensePartides:
            continue
        partides = []
        for fitxer in umb.fitxers_de_resultats(pagina):
            url = umb.URL_FITXERS.format(id=id_) + fitxer.replace(" ", "%20")
            pdf = d.bytes(url, d.arrel / "umb" / str(id_) / fitxer)
            if pdf is None:
                continue
            cami = d.arrel / "umb" / str(id_) / fitxer
            try:
                text = umb.text_del_pdf(cami)
            except Exception as exc:  # PDF trencat: se salta aquell fitxer, no l'esdeveniment
                avisa(f"  umb {id_}: {fitxer} no s'ha pogut obrir ({exc})")
                continue
            partides += umb.llegeix_text(text, umb.fase_del_fitxer(fitxer), len(partides) + 1)
        if not partides:
            avisa(f"  umb {id_}: {esdeveniment.nom} — cap partida llegible, no es desa")
            continue
        _desa(conn, Resultat(esdeveniment=esdeveniment, partides=partides), avisa)
        desats += 1
    return desats


# --- RFEB -----------------------------------------------------------------------

#: Del que penjava la RFEB a `noticiasAAAA/`, només els de carambola.
_RE_FORA = re.compile(
    r"pool|snooker|b8|b9|b10|b14|heyball|black|artistic|art_|5q|quillas|equipos|ssaa|jds|chapolin",
    re.IGNORECASE,
)


def _captures_wayback(carpeta: str, d: Descarregador) -> dict[str, str]:
    """`{nom del fitxer: url de la còpia més nova}` dels PDF de resultats d'una carpeta."""
    url = (
        "https://web.archive.org/cdx/search/cdx?url=rfeb.org/"
        f"{carpeta}/*&output=json&fl=original,timestamp,statuscode&limit=5000"
    )
    cos = d.bytes(url, d.arrel / "rfeb" / carpeta / "_cdx.json")
    if not cos:
        return {}
    files = json.loads(cos)[1:]
    millors: dict[str, tuple[str, str]] = {}
    for original, segell, estat in files:
        nom = original.rsplit("/", 1)[-1]
        if estat != "200" or not nom.lower().endswith(".pdf"):
            continue
        if nom not in millors or segell > millors[nom][0]:
            millors[nom] = (segell, original)
    return {
        nom: f"https://web.archive.org/web/{segell}id_/{original}"
        for nom, (segell, original) in millors.items()
    }


def ingesta_rfeb(conn, anys: Iterable[int], d: Descarregador, avisa: Avis = log.info) -> int:
    """Classificacions finals dels Campionats d'Espanya i Grans Premis, de Wayback."""
    desats = 0
    for any_ in anys:
        carpeta = f"noticias{any_}"
        for nom, url in sorted(_captures_wayback(carpeta, d).items()):
            if not rfeb.es_classificacio_final(nom) or _RE_FORA.search(nom):
                continue
            modalitat, _, _ = rfeb.descriu_fitxer(nom)
            if modalitat is None:
                continue
            cami = d.arrel / "rfeb" / carpeta / nom
            if d.bytes(url, cami) is None:
                continue
            try:
                text = umb.text_del_pdf(cami)
                resultat = rfeb.llegeix_classificacio(
                    text,
                    f"{carpeta}/{Path(nom).stem}",
                    nom,
                    url=f"https://rfeb.org/{carpeta}/{nom}",
                    temporada=f"{any_}-{any_ + 1}",
                )
            except rfeb.SenseClassificacio as exc:
                avisa(f"  rfeb {carpeta}/{nom}: {exc}")
                continue
            except Exception as exc:  # PDF trencat
                avisa(f"  rfeb {carpeta}/{nom}: no s'ha pogut obrir ({exc})")
                continue
            _desa(conn, resultat, avisa)
            desats += 1
    return desats
