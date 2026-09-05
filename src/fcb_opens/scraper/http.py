"""Minimal HTTP client with a local file cache.

The FCB website is stable and rate-unlimited in practice, but we still
cache responses to disk so that:
  - Re-running scripts during development doesn't hammer the server.
  - Tests can run offline against fixtures.
  - We have raw HTML snapshots to debug parser regressions.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "fcb_opens"
USER_AGENT = "fcb-opens/0.1 (+personal tool for billiards group management)"
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_TTL_S = 3600  # 1 hour


def normalitza(url: str) -> str:
    """Treu el `www.` de fcbillar.cat.

    El seu certificat no cobreix `www.fcbillar.cat` —«Hostname mismatch»— i la
    petició no arriba a sortir: peta abans de connectar. Al domini pelat el
    mateix contingut es serveix bé.

    Es fa aquí i no a les constants de cada mòdul perquè n'hi ha cinc, i perquè
    el dia que ho arreglin només s'ha de treure d'un lloc. No és cosa nostra:
    és una configuració seva que porta trencada des d'almenys el setembre de
    2026, i cada nit se'ns enduia el pas d'opens de la reingesta.
    """
    return url.replace("://www.fcbillar.cat", "://fcbillar.cat")


def _cache_path(url: str, cache_dir: Path) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return cache_dir / f"{digest}.html"


def fetch_binary(
    url: str,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    cache_ttl_s: int = DEFAULT_TTL_S,
    force: bool = False,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    suffix: str = ".bin",
) -> bytes:
    """Fetch a URL and return its raw bytes, using a local file cache.

    Same semantics as `fetch()` but for binary content (PDFs, images).
    The suffix controls the cache file extension so .pdf files are easy
    to inspect with a viewer directly from the cache dir.
    """
    import httpx

    url = normalitza(url)
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    cache_file = cache_dir / f"{digest}{suffix}"

    if not force and cache_file.exists():
        age_s = time.time() - cache_file.stat().st_mtime
        if age_s < cache_ttl_s:
            return cache_file.read_bytes()

    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout_s,
        follow_redirects=True,
    )
    response.raise_for_status()
    body = response.content
    cache_file.write_bytes(body)
    return body


def fetch(
    url: str,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    cache_ttl_s: int = DEFAULT_TTL_S,
    force: bool = False,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> str:
    """Fetch a URL and return its text body, using a local file cache.

    Args:
        url: absolute URL to fetch.
        cache_dir: directory where responses are persisted.
        cache_ttl_s: a cached response older than this is refetched.
        force: if True, ignore the cache and always refetch.
        timeout_s: request timeout.

    Returns:
        Response body as text.

    Raises:
        httpx.HTTPError: on network or 4xx/5xx errors.
    """
    # Lazy import: the parser modules import this file but only the
    # networked commands actually need httpx. Keeping the import inside
    # fetch() lets tests and pure-parsing workflows run without it.
    import httpx

    url = normalitza(url)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = _cache_path(url, cache_dir)

    if not force and cache_file.exists():
        age_s = time.time() - cache_file.stat().st_mtime
        if age_s < cache_ttl_s:
            return cache_file.read_text(encoding="utf-8")

    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout_s,
        follow_redirects=True,
    )
    response.raise_for_status()
    body = response.text
    cache_file.write_text(body, encoding="utf-8")
    return body
