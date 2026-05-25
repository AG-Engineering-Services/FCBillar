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
        form_absent = page.query_selector(LOGIN_FORM_SELECTOR) is None
        url_ok = "/login" not in page.url
        if form_absent and url_ok:
            confirmed_streak += 1
            if confirmed_streak >= LOGIN_STABLE_ABSENT_TICKS:
                return True
        else:
            confirmed_streak = 0
        time.sleep(LOGIN_POLL_INTERVAL_SEC)
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
