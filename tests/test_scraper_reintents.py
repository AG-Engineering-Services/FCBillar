"""Quan el portal està caigut, no s'hi insisteix pàgina per pàgina.

Reintentar un 500 té sentit quan és un ensopec del servidor. Quan la secció
sencera està trencada no en té cap i surt caríssim: la reingesta del 5 de
setembre de 2026 va trobar 401 encontres amb 500 —1.203 respostes d'error contra
127 de bones— i, a tres intents amb espera creixent, hi va cremar prop de 87
minuts. El job es va cancel·lar als 90 sense haver acabat la ingesta.
"""

from __future__ import annotations

import httpx
import pytest

from fcbillar.scraper.client import (
    CINCS_PER_RENDIR_SE,
    REINTENTS,
    ErrorPortal,
    ScraperClient,
)


class _Resposta:
    def __init__(self, estat: int, text: str = "<html></html>") -> None:
        self.status_code = estat
        self.text = text


class _ClientFals:
    """Compta les peticions i respon el que se li digui."""

    def __init__(self, estats: list[int]) -> None:
        self.estats = estats
        self.urls: list[str] = []

    def get(self, url: str) -> _Resposta:
        self.urls.append(url)
        i = min(len(self.urls) - 1, len(self.estats) - 1)
        return _Resposta(self.estats[i])


@pytest.fixture
def client(tmp_path, monkeypatch):
    c = ScraperClient()
    c.settings.cache_html = False
    c.settings.cache_dir = tmp_path
    # Ni ritme ni esperes: aquí es compten peticions, no segons.
    monkeypatch.setattr(c, "_respecta_ritme", lambda: None)
    monkeypatch.setattr(c, "_obre", lambda: None)
    monkeypatch.setattr("fcbillar.scraper.client.time.sleep", lambda _s: None)
    return c


def _amb(client, estats: list[int]) -> _ClientFals:
    fals = _ClientFals(estats)
    client._client = fals
    return fals


def test_un_500_aillat_es_reintenta(client) -> None:
    """Pot ser un ensopec, i el segon intent encara el pot enxampar bé."""
    fals = _amb(client, [500, 500, 500])
    with pytest.raises(ErrorPortal) as e:
        client.fetch_html("https://x/1")
    assert len(fals.urls) == REINTENTS
    assert e.value.estat == 500


def test_un_404_no_es_reintenta_mai(client) -> None:
    """L'id no existeix, i reprovar-ho no el crearà."""
    fals = _amb(client, [404])
    with pytest.raises(ErrorPortal):
        client.fetch_html("https://x/1")
    assert len(fals.urls) == 1


def test_amb_el_portal_caigut_es_prova_un_sol_cop(client) -> None:
    """El cas del 5 de setembre: 401 encontres seguits amb 500."""
    fals = _amb(client, [500])
    for i in range(CINCS_PER_RENDIR_SE):
        with pytest.raises(ErrorPortal):
            client.fetch_html(f"https://x/{i}")
    fins_a_rendir_se = len(fals.urls)

    # A partir d'aquí, una petició per pàgina i no tres.
    for i in range(10):
        with pytest.raises(ErrorPortal):
            client.fetch_html(f"https://x/despres-{i}")
    assert len(fals.urls) - fins_a_rendir_se == 10


def test_una_pagina_bona_torna_a_donar_confiança(client) -> None:
    """Si el portal es recupera, es torna a insistir com sempre."""
    fals = _amb(client, [500])
    for i in range(CINCS_PER_RENDIR_SE):
        with pytest.raises(ErrorPortal):
            client.fetch_html(f"https://x/{i}")
    assert client._cincs_seguits >= CINCS_PER_RENDIR_SE

    fals.estats = [200]
    client.fetch_html("https://x/bona")
    assert client._cincs_seguits == 0

    fals.estats = [500]
    abans = len(fals.urls)
    with pytest.raises(ErrorPortal):
        client.fetch_html("https://x/altra")
    assert len(fals.urls) - abans == REINTENTS


def test_els_404_no_compten_com_a_portal_caigut(client) -> None:
    """Un id inexistent no diu res de com està el servidor."""
    fals = _amb(client, [404])
    for i in range(CINCS_PER_RENDIR_SE + 5):
        with pytest.raises(ErrorPortal):
            client.fetch_html(f"https://x/{i}")
    assert client._cincs_seguits == 0

    fals.estats = [500]
    abans = len(fals.urls)
    with pytest.raises(ErrorPortal):
        client.fetch_html("https://x/cinc-cents")
    assert len(fals.urls) - abans == REINTENTS


def test_un_error_de_xarxa_no_dispara_el_rendiment(client) -> None:
    """No és el portal dient que està trencat: és que no s'hi ha arribat."""

    class _Peta:
        def get(self, url):
            raise httpx.ConnectError("res")

    client._client = _Peta()
    with pytest.raises(ErrorPortal):
        client.fetch_html("https://x/1")
    assert client._cincs_seguits == 0
