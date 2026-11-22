"""La llista de captures de Wayback de la web vella de la RFEB (sense xarxa)."""

from __future__ import annotations

from fcbillar.rfeb_wayback import llegeix_cdx, ruta_local


def test_la_ruta_local_no_porta_ni_domini_ni_consulta_ni_espais():
    assert ruta_local("http://www.rfeb.org:80/0HOME/PDF/CE-Msc%20Sub.pdf?v=2") == (
        "0HOME/PDF/CE-Msc_Sub.pdf"
    )
    assert ruta_local("https://rfeb.org/noticias2015/res_ce_3b.pdf") == "noticias2015/res_ce_3b.pdf"


def test_de_cada_fitxer_nomes_la_captura_mes_nova_que_va_respondre_200():
    cdx = "\n".join(
        [
            "20110101000000 http://www.rfeb.org/0HOME/PDF/a.pdf application/pdf 200",
            "20120101000000 http://rfeb.org:80/0HOME/PDF/a.pdf application/pdf 200",
            "20130101000000 http://rfeb.org/0HOME/PDF/a.pdf application/pdf 404",
            "20100101000000 http://rfeb.org/0HOME/PDF/b.pdf application/pdf 200",
            "brossa",
        ]
    )
    caps = llegeix_cdx(cdx)
    assert [(c.marca, ruta_local(c.url)) for c in caps] == [
        ("20120101000000", "0HOME/PDF/a.pdf"),
        ("20100101000000", "0HOME/PDF/b.pdf"),
    ]
