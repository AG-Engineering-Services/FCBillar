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


def test_no_toca_un_host_que_nomes_hi_comenci() -> None:
    """`www.fcbillar.cat.exemple.com` és d'algú altre.

    Amb un `replace` de text pla també se li treia el `www.`, i això és enviar
    la petició a un lloc que no és el que demanava qui crida.
    """
    u = "https://www.fcbillar.cat.exemple.com/x"
    assert normalitza(u) == u


def test_respecta_el_port() -> None:
    assert normalitza("https://www.fcbillar.cat:8443/x") == "https://fcbillar.cat:8443/x"


def test_el_host_pelat_sense_cami() -> None:
    assert normalitza("https://www.fcbillar.cat") == "https://fcbillar.cat"


def test_no_toca_el_www_que_surt_al_mig_del_cami() -> None:
    u = "https://fcbillar.cat/media/www.fcbillar.cat.pdf"
    assert normalitza(u) == u


def test_no_toca_un_altre_domini_encara_que_el_porti_al_cami() -> None:
    u = "https://exemple.com/?redirect=https://www.fcbillar.cat/x"
    assert normalitza(u) == u
