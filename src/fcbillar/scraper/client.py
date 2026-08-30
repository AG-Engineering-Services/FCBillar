"""Client HTTP per al web de la FCB: caché a disc, ritme i reintents.

Fins a l'agost de 2026 aquí hi havia un navegador Playwright sencer, perquè el
rànquing i les partides de cada jugador vivien darrere d'un login amb captcha:
calia obrir Chromium, resoldre'l a mà i desar `storage_state.json`.

Amb el web nou **totes les pàgines que ingerim són públiques**, així que n'hi ha
prou amb `httpx`. Això treu de sobre el navegador, la sessió que caducava i la
finestra setmanal amb l'usuari al davant — i permet que la ingesta corri sencera
al núvol.

La interfície (`fetch_html`, `settings`, gestor de context) és la mateixa que
tenia el client de Playwright, perquè la resta del codi no se n'ha d'assabentar.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

import httpx

from fcbillar.config import Settings, get_settings

log = logging.getLogger(__name__)

# El portal és petit i el mantenen ells: identifiquem-nos i no l'atabalem.
USER_AGENT = "FCBillar/2.0 (seguiment de jugadors federats; contacte via fcbillar.cat)"

REINTENTS = 3
ESPERA_REINTENT_S = 2.0


class ErrorPortal(RuntimeError):
    """El portal ha respost amb un codi d'error després de tots els reintents.

    Porta l'`estat` perquè qui crida pugui distingir el que és nostre (404: id
    inexistent, se salta) del que és seu (500: pàgina trencada, s'apunta i es
    reprova un altre dia).
    """

    def __init__(self, url: str, estat: int) -> None:
        super().__init__(f"HTTP {estat} a {url}")
        self.url = url
        self.estat = estat


class ScraperClient:
    """Descarrega pàgines de la FCB amb caché a disc i límit de ritme."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: httpx.Client | None = None
        self._last_request_ts: float = 0.0

    # ---------------- cicle de vida ----------------

    def __enter__(self) -> ScraperClient:
        self._obre()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _obre(self) -> None:
        if self._client is None:
            self._client = httpx.Client(
                headers={"User-Agent": USER_AGENT, "Accept-Language": "ca-ES,ca;q=0.9"},
                follow_redirects=True,
                timeout=60.0,
            )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # ---------------- HTTP ----------------

    def _respecta_ritme(self) -> None:
        delay = self.settings.request_delay_sec
        if delay <= 0:
            return
        passat = time.monotonic() - self._last_request_ts
        if passat < delay:
            time.sleep(delay - passat)
        self._last_request_ts = time.monotonic()

    def _cache_path(self, url: str) -> Path:
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        # Un tros llegible al nom facilita inspeccionar la caché a mà.
        slug = url.replace("https://", "").replace("http://", "")
        slug = slug.replace("/", "_").replace("?", "_").replace("&", "_")[:80]
        return self.settings.cache_dir / f"{slug}__{h}.html"

    def fetch_html(self, url: str, *, use_cache: bool = True) -> str:
        """Descarrega una pàgina, amb caché a disc opcional."""
        cache_file = self._cache_path(url)
        if use_cache and self.settings.cache_html and cache_file.exists():
            log.debug("CACHE HIT %s", url)
            return cache_file.read_text(encoding="utf-8")

        self._obre()
        assert self._client is not None

        ultim_estat = 0
        for intent in range(1, REINTENTS + 1):
            self._respecta_ritme()
            log.info("GET %s%s", url, f" (intent {intent})" if intent > 1 else "")
            try:
                r = self._client.get(url)
            except httpx.HTTPError as e:
                log.warning("Xarxa KO a %s: %s", url, e)
                ultim_estat = 0
                time.sleep(ESPERA_REINTENT_S * intent)
                continue

            if r.status_code == 200:
                html = r.text
                if self.settings.cache_html:
                    cache_file.write_text(html, encoding="utf-8")
                return html

            ultim_estat = r.status_code
            # Un 404 és definitiu: l'id no existeix i reprovar-ho no el crearà.
            if r.status_code == 404:
                break
            time.sleep(ESPERA_REINTENT_S * intent)

        raise ErrorPortal(url, ultim_estat)
