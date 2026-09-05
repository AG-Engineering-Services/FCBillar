"""El `www.` de fcbillar.cat es treu abans de sortir a la xarxa.

El seu certificat no cobreix `www.fcbillar.cat` —«Hostname mismatch»— i la
petició peta abans de connectar-se. Al domini pelat el mateix contingut es
serveix bé. La reingesta del núvol hi perdia el pas d'opens cada nit.
"""

from __future__ import annotations

from fcb_opens.scraper.http import normalitza


def test_treu_el_www_de_fcbillar() -> None:
    assert (
        normalitza("https://www.fcbillar.cat/ca/historial") == "https://fcbillar.cat/ca/historial"
    )


def test_el_domini_pelat_no_es_toca() -> None:
    assert normalitza("https://fcbillar.cat/ca/x") == "https://fcbillar.cat/ca/x"


def test_la_intranet_no_es_toca() -> None:
    """És un altre servidor i el seu certificat sí que és bo."""
    u = "https://intranet.fcbillar.cat/frontend/lligues/divisions/38"
    assert normalitza(u) == u


def test_no_toca_altres_dominis_que_hi_acabin() -> None:
    """`www.fcbillar.cat.exemple.com` no és el mateix lloc."""
    u = "https://www.fcbillar.cat.exemple.com/x"
    assert normalitza(u) == "https://fcbillar.cat.exemple.com/x"


def test_no_toca_el_www_que_surt_al_mig_del_cami() -> None:
    u = "https://fcbillar.cat/media/www.fcbillar.cat.pdf"
    assert normalitza(u) == u
