"""D'on surt el PDF del rànquing oficial d'opens, i que no es perdi pel camí.

La URL era una constant que apuntava a `/media/{temporada}/COMPETICIO/OPENS/…`
del web vell. Va morir amb el canvi de web de l'agost de 2026 i ningú no se'n va
assabentar: `publish_open_ranking` embolcalla l'aplicació del rànquing oficial
en un `try/except` que, si falla, només marca la ronda com a provisional. El web
va estar ensenyant el rànquing calculat en comptes de l'oficial.

Ara es busca al sitemap de documents. I qui la baixa la torna, perquè qui la
parseja l'ha de saber: `source_url` va a la resposta de l'API.
"""

from __future__ import annotations

import pytest

from fcb_opens.scraper import official_pdf as op


@pytest.fixture
def cau(tmp_path, monkeypatch):
    """Memòria cau buida i cap sortida a la xarxa que no sigui volguda."""
    monkeypatch.setattr(
        op, "descobreix_ranquing_oficial", lambda *_a, **_k: "https://x.test/r-25-26.pdf"
    )
    return tmp_path


def _resposta(cos: bytes):
    class R:
        content = cos

        def raise_for_status(self) -> None:
            return None

    return R()


def test_torna_la_url_que_ha_fet_servir(cau, monkeypatch) -> None:
    """Sense això el cridador passa `source_url=None` i l'API peta."""
    import httpx

    monkeypatch.setattr(httpx, "get", lambda *_a, **_k: _resposta(b"%PDF-1"))
    cos, url = op.fetch_official_ranking_pdf(cache_dir=cau)
    assert cos == b"%PDF-1"
    assert url == "https://x.test/r-25-26.pdf"


def test_la_url_donada_mana_sobre_la_descoberta(cau, monkeypatch) -> None:
    import httpx

    monkeypatch.setattr(httpx, "get", lambda *_a, **_k: _resposta(b"%PDF-2"))
    _cos, url = op.fetch_official_ranking_pdf(url="https://y.test/altre.pdf", cache_dir=cau)
    assert url == "https://y.test/altre.pdf"


def test_nomes_memoria_cau_no_surt_a_buscar_la_url(cau, monkeypatch) -> None:
    """`use_cache_only` promet no tocar la xarxa, i descobrir-la seria tocar-la.

    El nom del fitxer de la memòria cau surt del hash de la URL, o sigui que
    sense saber-la no es pot ni trobar. Per això la darrera que ha funcionat es
    recorda al costat.
    """
    import httpx

    def esclata(*_a, **_k):
        raise AssertionError("no s'hi pot sortir, a la xarxa")

    monkeypatch.setattr(httpx, "get", lambda *_a, **_k: _resposta(b"%PDF-3"))
    op.fetch_official_ranking_pdf(cache_dir=cau)  # baixada normal: la recorda

    monkeypatch.setattr(op, "descobreix_ranquing_oficial", esclata)
    monkeypatch.setattr(httpx, "get", esclata)
    cos, url = op.fetch_official_ranking_pdf(cache_dir=cau, use_cache_only=True)
    assert cos == b"%PDF-3"
    assert url == "https://x.test/r-25-26.pdf"


def test_sense_res_recordat_ho_diu_en_comptes_de_sortir(cau, monkeypatch) -> None:
    def esclata(*_a, **_k):
        raise AssertionError("no s'hi pot sortir, a la xarxa")

    monkeypatch.setattr(op, "descobreix_ranquing_oficial", esclata)
    with pytest.raises(FileNotFoundError, match="memòria cau"):
        op.fetch_official_ranking_pdf(cache_dir=cau, use_cache_only=True)
