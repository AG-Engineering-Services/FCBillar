"""Client Playwright amb sessió persistent, caché de HTML a disc i rate limiting."""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from fcbillar.config import Settings, get_settings

log = logging.getLogger(__name__)


class NoSessionError(RuntimeError):
    """Es llença quan es vol scrapejar però no hi ha sessió desada."""


class ScraperClient:
    """Wrapper de Playwright: obre context amb sessió persistida i descarrega URLs amb caché."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._last_request_ts: float = 0.0

    # ---------------- context manager ----------------

    def __enter__(self) -> ScraperClient:
        self._start(require_session=True)
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @contextmanager
    def interactive(self, headless: bool = False) -> Iterator[Page]:
        """Obre un navegador per a login (captcha). No exigeix sessió prèvia.

        `headless=True` el fa servir el login automàtic (OCR del captcha), que
        no necessita finestra visible.
        """
        self._start(require_session=False, headless=headless)
        try:
            yield self.page
        finally:
            self.close()

    # ---------------- core lifecycle ----------------

    def _start(self, *, require_session: bool, headless: bool | None = None) -> None:
        storage_state = self.settings.storage_state_path
        if require_session and not storage_state.exists():
            raise NoSessionError(
                f"No s'ha trobat sessió a {storage_state}. Executa primer `fcbillar login`."
            )
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.settings.headless if headless is None else headless
        )
        context_kwargs: dict = {
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            "locale": "ca-ES",
        }
        if storage_state.exists():
            context_kwargs["storage_state"] = str(storage_state)
        self._context = self._browser.new_context(**context_kwargs)
        self._page = self._context.new_page()

    def close(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._context = self._browser = self._pw = self._page = None

    def save_session(self) -> Path:
        if self._context is None:
            raise RuntimeError("Context no inicialitzat")
        path = self.settings.storage_state_path
        self._context.storage_state(path=str(path))
        log.info("Sessió desada a %s", path)
        return path

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Page no inicialitzada; entra al context primer")
        return self._page

    # ---------------- HTTP ----------------

    def _respect_rate_limit(self) -> None:
        delay = self.settings.request_delay_sec
        if delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_ts = time.monotonic()

    def _cache_path(self, url: str) -> Path:
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        # Inclou un fragment llegible per facilitar inspecció
        slug = url.replace("https://", "").replace("http://", "").replace("/", "_")[:80]
        return self.settings.cache_dir / f"{slug}__{h}.html"

    def fetch_html(self, url: str, *, use_cache: bool = True) -> str:
        """Descarrega HTML amb caché opcional a disc."""
        cache_file = self._cache_path(url)
        if use_cache and self.settings.cache_html and cache_file.exists():
            log.debug("CACHE HIT %s", url)
            return cache_file.read_text(encoding="utf-8")

        self._respect_rate_limit()
        log.info("GET %s", url)
        response = self.page.goto(url, wait_until="domcontentloaded")
        if response is None or response.status >= 400:
            status = response.status if response else "no-response"
            raise RuntimeError(f"Error HTTP {status} en {url}")
        # Espera oportunista a networkidle: les pàgines públiques tenen widgets
        # de Facebook/Twitter que mai s'estabilitzen, però el contingut útil ja
        # és al DOM en aquest punt. Si el timeout salta, continuem igualment.
        try:
            self.page.wait_for_load_state("networkidle", timeout=5_000)
        except PlaywrightTimeoutError:
            log.debug("networkidle no assolit en 5s a %s — continuant", url)
        html = self.page.content()

        if self.settings.cache_html:
            cache_file.write_text(html, encoding="utf-8")
        return html
