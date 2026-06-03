"""Login interactiu a la intranet de fcbillar.cat.

Per la presència de captcha, NO automatitzem el login. La filosofia:

1. Obrim navegador visible.
2. (Opcional) pre-omplim usuari/contrasenya si tenim credencials a .env.
3. L'usuari resol el captcha i clica "Accedir".
4. L'usuari confirma manualment (prem ENTER) que veu el panell de jugador.
5. Validem que el form de login ja no és al DOM i desem `storage_state.json`.

La sessió té validesa fins que la federació la fa caducar; quan això passi,
torna a executar `fcbillar login`.
"""

from __future__ import annotations

import logging
import time

from rich.console import Console

from fcbillar.config import Settings, get_settings
from fcbillar.scraper.client import ScraperClient

log = logging.getLogger(__name__)
console = Console()

# Selector del formulari de login. Mentre existeixi al DOM, NO estem autenticats:
# l'intranet renderitza el form tant a /ca/login com a /ca/jugador per a usuaris no logats.
LOGIN_FORM_SELECTOR = "#formloguinacion"
LOGIN_OVERALL_TIMEOUT_SEC = 5 * 60  # temps total disponible per resoldre el captcha
LOGIN_POLL_INTERVAL_SEC = 1.0  # cada quan comprovem si el form encara hi és
LOGIN_STABLE_ABSENT_TICKS = 3  # form absent N ticks consecutius => login confirmat


def interactive_login(settings: Settings | None = None) -> bool:
    """Executa el login interactiu i desa la sessió. Retorna True si s'ha desat sessió."""
    settings = settings or get_settings()
    # /ca/login retorna 404; el form de login es renderitza directament a /ca/jugador
    # quan no estàs autenticat (i la mateixa URL serveix el dashboard quan ho estàs).
    login_url = f"{settings.base_url.rstrip('/')}/ca/jugador"

    console.print(
        "\n[bold cyan]Login a la intranet de fcbillar.cat[/]\n"
        "S'obrirà una finestra de navegador (Chromium). Has de:\n"
        "  1. Verificar usuari i contrasenya (pre-omplerts si els has posat al .env)\n"
        "  2. Resoldre el captcha\n"
        "  3. Clicar 'Accedir' i esperar al teu panell de jugador\n"
        f"Espero fins a {LOGIN_OVERALL_TIMEOUT_SEC // 60} minuts a que el form de login "
        "es mantingui absent (no només transitoriàment durant la navegació).\n"
    )

    client = ScraperClient(settings)
    with client.interactive() as page:
        page.goto(login_url, wait_until="domcontentloaded")

        if settings.has_credentials:
            _try_prefill(page, settings.user, settings.password.get_secret_value())

        console.print(f"[dim]URL inicial:[/] {page.url}")
        console.print("[yellow]Completa el login al navegador (botó 'Accedir')...[/]")

        if not _wait_for_login_confirmed(page):
            console.print(
                f"[red]Temps esgotat o login no confirmat. URL actual: {page.url}.[/]"
            )
            return False

        client.save_session()
        console.print(f"[green]OK Login confirmat. URL actual: {page.url}[/]")
        console.print(f"[green]OK Sessió desada a {settings.storage_state_path}[/]")
        return True


def _wait_for_login_confirmed(page) -> bool:
    """Espera login confirmat: form absent + URL fora de /login durant N ticks.

    Una navegació pot deixar el form transitòriament absent encara que la
    destinació final no sigui autenticada. Exigim que ambdues condicions
    es mantinguin estables durant LOGIN_STABLE_ABSENT_TICKS ticks consecutius
    perquè el resultat sigui fiable.
    """
    deadline = time.monotonic() + LOGIN_OVERALL_TIMEOUT_SEC
    confirmed_streak = 0
    while time.monotonic() < deadline:
        # El query_selector pot petar amb "Execution context was destroyed"
        # si la pàgina està navegant just en aquest instant (típic durant el
        # login). No és un error real: ho tractem com a "estat indeterminat"
        # i reintentem al següent tick.
        try:
            form_absent = page.query_selector(LOGIN_FORM_SELECTOR) is None
            url_ok = "/login" not in page.url
        except Exception:  # noqa: BLE001 — navegació en curs; reintenta
            confirmed_streak = 0
            time.sleep(LOGIN_POLL_INTERVAL_SEC)
            continue
        if form_absent and url_ok:
            confirmed_streak += 1
            if confirmed_streak >= LOGIN_STABLE_ABSENT_TICKS:
                return True
        else:
            confirmed_streak = 0
        time.sleep(LOGIN_POLL_INTERVAL_SEC)
    return False


CAPTCHA_IMG_SELECTOR = "#formloguinacion img"
SUBMIT_SELECTOR = "#formloguinacion [type='submit']"
AUTO_LOGIN_MAX_ATTEMPTS = 8


def _configure_tesseract() -> bool:
    """Point pytesseract at the tesseract binary. Returns False if not found."""
    import os
    import shutil

    import pytesseract

    found = shutil.which("tesseract")
    if not found:
        for cand in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ):
            if os.path.exists(cand):
                found = cand
                break
    if not found:
        return False
    pytesseract.pytesseract.tesseract_cmd = found
    return True


_CAPTCHA_WHITELIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _ocr_captcha(png_bytes: bytes) -> str:
    """OCR the fcbillar captcha to its 4-char code (best effort).

    The captcha is outlined letters over a noisy red/yellow flame texture, which
    defeats naive thresholding. We isolate the dark letter ink (grayscale < 60),
    upscale, despeckle with a median filter (kills isolated flame specks while
    keeping connected strokes) and crop to the central band where the letters
    live, then try a few Tesseract page-segmentation modes and keep the cleanest
    4-character read. NOTE: reliability is limited; the caller retries with fresh
    captchas. See login --auto for the retry loop.
    """
    import io
    import re

    import pytesseract
    from PIL import Image, ImageFilter, ImageOps

    rgb = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    w, h = rgb.size
    black = rgb.convert("L").point(lambda p: 255 if p < 60 else 0)
    big = black.resize((w * 6, h * 6), Image.NEAREST)
    for _ in range(3):
        big = big.filter(ImageFilter.MedianFilter(5))
    bw, bh = big.size
    big = big.crop((0, int(bh * 0.18), bw, int(bh * 0.86)))
    ocr_in = ImageOps.invert(big)

    candidates: list[str] = []
    for psm in (7, 8, 6):
        raw = pytesseract.image_to_string(
            ocr_in, config=f"--psm {psm} -c tessedit_char_whitelist={_CAPTCHA_WHITELIST}"
        )
        cleaned = re.sub(r"[^A-Z0-9]", "", raw.upper())
        if cleaned:
            candidates.append(cleaned)
    # Prefer an exactly-4-char read; otherwise the longest candidate.
    for c in candidates:
        if len(c) == 4:
            return c
    return max(candidates, key=len) if candidates else ""


def _anthropic_key() -> str | None:
    """ANTHROPIC_API_KEY from the environment, or from the project .env file."""
    import os

    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key.strip()
    # Convenience: read it from the repo .env if present (not FCB_-prefixed, so
    # pydantic-settings doesn't pick it up).
    from pathlib import Path

    env = Path(__file__).resolve().parents[2] / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY"):
                _, _, val = line.partition("=")
                return val.strip().strip('"').strip("'") or None
    return None


def _vision_captcha(png_bytes: bytes, api_key: str) -> str:
    """Read the captcha with a vision model (Claude) — reliable on the noisy
    flame captcha that defeats Tesseract. Returns the cleaned 4-char code."""
    import base64
    import re

    import httpx

    b64 = base64.standard_b64encode(png_bytes).decode("ascii")
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 16,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Aquesta imatge és un CAPTCHA de 4 caràcters "
                                "alfanumèrics. Respon NOMÉS amb els 4 caràcters "
                                "(majúscules), sense cap altre text."
                            ),
                        },
                    ],
                }
            ],
        },
        timeout=30,
    )
    resp.raise_for_status()
    txt = "".join(
        b.get("text", "") for b in resp.json().get("content", []) if b.get("type") == "text"
    )
    return re.sub(r"[^A-Z0-9]", "", txt.upper())[:4]


def _login_succeeded(page, *, settle_sec: float = 4.0) -> bool:
    """Quick success check after submitting: login form gone + URL not /login."""
    deadline = time.monotonic() + settle_sec
    streak = 0
    while time.monotonic() < deadline:
        try:
            ok = page.query_selector(LOGIN_FORM_SELECTOR) is None and "/login" not in page.url
        except Exception:  # noqa: BLE001 — navigation in progress
            ok = False
        streak = streak + 1 if ok else 0
        if streak >= 2:
            return True
        time.sleep(LOGIN_POLL_INTERVAL_SEC)
    return False


def automated_login(
    settings: Settings | None = None, *, max_attempts: int = AUTO_LOGIN_MAX_ATTEMPTS
) -> bool:
    """Headless login solving the captcha via local OCR (Tesseract).

    Requires credentials in the environment (FCB_USER / FCB_PASSWORD) and the
    Tesseract binary installed. Retries with a fresh captcha on each failure
    (the captcha refreshes for free), since OCR isn't 100% reliable. The saved
    session persists, so this only needs to succeed when the session expires.
    """
    settings = settings or get_settings()
    if not settings.has_credentials:
        console.print(
            "[red]Login automàtic: falten credencials. Posa FCB_USER i FCB_PASSWORD al .env.[/]"
        )
        return False
    ok_tess = _configure_tesseract()
    api_key = _anthropic_key()
    if not ok_tess and not api_key:
        console.print(
            "[red]Cal Tesseract (winget install UB-Mannheim.TesseractOCR) o una "
            "ANTHROPIC_API_KEY per resoldre el captcha.[/]"
        )
        return False
    console.print(
        f"[dim]Captcha: OCR={'sí' if ok_tess else 'no'}, visió={'sí' if api_key else 'no'}.[/]"
    )

    login_url = f"{settings.base_url.rstrip('/')}/ca/jugador"
    user = settings.user
    password = settings.password.get_secret_value()

    client = ScraperClient(settings)
    with client.interactive(headless=True) as page:
        for attempt in range(1, max_attempts + 1):
            try:
                page.goto(login_url, wait_until="domcontentloaded")
                if page.query_selector(LOGIN_FORM_SELECTOR) is None:
                    # Ja autenticats (sessió encara vàlida): res a fer.
                    client.save_session()
                    console.print("[green]OK Ja hi havia sessió vàlida.[/]")
                    return True
                page.fill("#email", user)
                page.fill("#password", password)
                captcha_el = page.query_selector(CAPTCHA_IMG_SELECTOR)
                if captcha_el is None:
                    console.print("[yellow]No s'ha trobat la imatge del captcha; reintento.[/]")
                    continue
                png = captcha_el.screenshot()
                # OCR el primer intent (gratis); visió a partir del 2n (fiable)
                # o sempre si no hi ha Tesseract.
                use_vision = api_key is not None and (attempt > 1 or not ok_tess)
                if use_vision:
                    try:
                        code = _vision_captcha(png, api_key)
                        method = "visió"
                    except Exception as exc:  # noqa: BLE001
                        log.warning("Visió captcha fallida: %s", exc)
                        code = _ocr_captcha(png) if ok_tess else ""
                        method = "ocr(fallback)"
                else:
                    code = _ocr_captcha(png)
                    method = "ocr"
                log.info("Intent %d (%s): captcha → '%s'", attempt, method, code)
                if len(code) != 4:
                    console.print(
                        f"[dim]Intent {attempt} ({method}): '{code}' (≠4 car.), reintento.[/]"
                    )
                    continue
                page.fill("#validator", code)
                el = page.query_selector(SUBMIT_SELECTOR)
                if el is not None:
                    el.click()
                else:
                    page.keyboard.press("Enter")
                if _login_succeeded(page):
                    client.save_session()
                    console.print(
                        f"[green]OK Login automàtic confirmat a l'intent {attempt}. "
                        f"Sessió desada a {settings.storage_state_path}[/]"
                    )
                    return True
                console.print(f"[dim]Intent {attempt}: captcha '{code}' rebutjat, reintento.[/]")
            except Exception as exc:  # noqa: BLE001 — reintenta amb captcha nou
                log.warning("Intent %d fallat: %s", attempt, exc)
                continue
    console.print(f"[red]Login automàtic fallit després de {max_attempts} intents.[/]")
    return False


def _try_prefill(page, user: str, password: str) -> None:
    """Intenta pre-omplir camps de login amb selectors habituals. Fallar és OK: l'usuari els pot omplir."""
    candidates_user = [
        "input[name='username']",
        "input[name='user']",
        "input[name='email']",
        "input[type='text']",
    ]
    candidates_pass = [
        "input[name='password']",
        "input[name='passwd']",
        "input[type='password']",
    ]
    for sel in candidates_user:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.fill(user)
                log.info("Pre-omplert camp d'usuari amb selector %s", sel)
                break
        except Exception:
            continue
    for sel in candidates_pass:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.fill(password)
                log.info("Pre-omplerta contrasenya amb selector %s", sel)
                break
        except Exception:
            continue
