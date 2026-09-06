"""Trobar els calendaris de grup que la federació té penjats.

La federació no els enllaça des de cap pantalla: viuen al gestor de fitxers del
WordPress i l'únic lloc on hi són tots és el sitemap de documents. I no és una
comoditat, és l'única font: el setembre de 2026, amb els dotze grups de la
26/27 ja publicats, `intranet.fcbillar.cat/frontend/lligues/grups/38/…` responia
500 i la pàgina de divisions no tenia ni un enllaç.

Les fixtures són captures del web del 6 de setembre de 2026, el dia que els van
publicar.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fcbillar.calendari_lliga import CalendariPublicat, descobreix_grups, slugs_de_grup, url_del_pdf

FIXTURES = Path(__file__).parent / "fixtures" / "nou"
SITEMAP = (FIXTURES / "wp_sitemap_documents.xml").read_text(encoding="utf-8")
DOCUMENT = (FIXTURES / "wp_document_calendari_grup.html").read_text(encoding="utf-8")


# --------------------------- el sitemap ---------------------------


def test_hi_son_els_dotze_grups() -> None:
    """Honor, 1a, 2a i 3a amb dos grups cadascuna, i 4a amb quatre."""
    trobats = slugs_de_grup(SITEMAP)

    assert len(trobats) == 12
    assert {etiqueta for _, _, etiqueta in trobats} == {
        "honor grup A",
        "honor grup B",
        "primera grup A",
        "primera grup B",
        "segona grup A",
        "segona grup B",
        "tercera grup A",
        "tercera grup B",
        "quarta grup A",
        "quarta grup B",
        "quarta grup C",
        "quarta grup D",
    }


def test_la_temporada_surt_sencera() -> None:
    """A l'slug hi diu «2026-27» i aquí les temporades s'escriuen '2026/2027'."""
    assert {temporada for _, temporada, _ in slugs_de_grup(SITEMAP)} == {"2026/2027"}


def test_es_pot_demanar_una_temporada() -> None:
    assert len(slugs_de_grup(SITEMAP, "2026/2027")) == 12
    assert slugs_de_grup(SITEMAP, "2025/2026") == []


def test_no_s_hi_cola_res_mes() -> None:
    """Al sitemap hi ha reglaments, rànquings i el calendari esportiu de la FCB."""
    slugs = [slug for slug, _, _ in slugs_de_grup(SITEMAP)]

    assert all(s.startswith("calendari-lliga-tres-bandes-") for s in slugs)
    assert "calendari-fcb-2026-27-v-2" not in slugs


def test_un_sitemap_sense_calendaris_no_inventa_res() -> None:
    assert slugs_de_grup("<urlset><url><loc>https://fcbillar.cat/</loc></url></urlset>") == []


# --------------------------- la pàgina del document ---------------------------


def test_l_enllac_al_pdf_surt_de_la_pagina() -> None:
    url = url_del_pdf(DOCUMENT)

    assert url is not None
    assert url.endswith("calendari-lliga-tres-bandes-2026-27-honor-grup-a.pdf")
    assert url.startswith("https://fcbillar.cat/download/")


def test_no_s_agafa_el_calendari_esportiu_de_la_pagina() -> None:
    """La mateixa pàgina porta l'enllaç a `calendari-fcb-2026-27-v-2.pdf`.

    És el calendari de tota la temporada, un altre document: si se'l quedés,
    els dotze grups sortirien amb el mateix PDF.
    """
    assert "calendari-fcb" not in (url_del_pdf(DOCUMENT) or "")


def test_una_pagina_sense_pdf_no_menteix() -> None:
    assert url_del_pdf("<html><body>res</body></html>") is None


# --------------------------- les dues coses juntes ---------------------------


class _ClientDeProva:
    """Serveix el sitemap i, per a cada document, la pàgina que li toca."""

    def __init__(self, sitemap: str = SITEMAP) -> None:
        self.sitemap = sitemap
        self.demanats: list[str] = []

    def get(self, url: str):
        self.demanats.append(url)
        if url.endswith(".xml"):
            return _Resposta(self.sitemap)
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        return _Resposta(DOCUMENT.replace("honor-grup-a", slug.split("2026-27-")[-1]))


class _Resposta:
    def __init__(self, text: str) -> None:
        self.text = text


def test_descobreix_els_dotze() -> None:
    client = _ClientDeProva()

    trobats = descobreix_grups("2026/2027", client=client)

    assert len(trobats) == 12
    assert all(isinstance(c, CalendariPublicat) for c in trobats)
    assert len({c.url for c in trobats}) == 12, "cada grup ha de portar el seu PDF"


def test_es_demana_una_pagina_per_grup_i_prou() -> None:
    """Una petició pel sitemap i una per document: res de rastrejar el web."""
    client = _ClientDeProva()

    descobreix_grups("2026/2027", client=client)

    assert len(client.demanats) == 13
    assert client.demanats[0].endswith("wpfd_file-sitemap.xml")


def test_un_document_sense_pdf_no_atura_la_resta(caplog) -> None:
    """Si la federació penja la pàgina abans que el fitxer, els altres onze hi són."""

    class SenseElPrimer(_ClientDeProva):
        def get(self, url: str):
            if "honor-grup-a" in url:
                return _Resposta("<html>encara no</html>")
            return super().get(url)

    with caplog.at_level("WARNING"):
        trobats = descobreix_grups("2026/2027", client=SenseElPrimer())

    assert len(trobats) == 11
    assert "honor-grup-a" in caplog.text


# --------------------------- que no es barregi amb l'altre calendari ---------------------------


def test_els_grups_no_surten_al_calendari_esportiu() -> None:
    """`descobreix_fcb()` busca «calendari» al camí i els grups també en tenen.

    Fins que no es va filtrar, els dotze grups sortien a la llista del calendari
    esportiu de la temporada com si en fossin versions.
    """
    from fcbillar.calendari_fed import descobreix_fcb

    trobats = descobreix_fcb(DOCUMENT)

    assert [c.nom_fitxer for c in trobats] == ["calendari-fcb-2026-27-v-2.pdf"]


@pytest.mark.parametrize(
    "fitxer",
    [
        "calendari-lliga-tres-bandes-2026-27-honor-grup-a.pdf",
        "calendari-lliga-tres-bandes-2026-27-quarta-grup-d.pdf",
    ],
)
def test_cap_calendari_de_grup_passa_per_calendari_esportiu(fitxer: str) -> None:
    from fcbillar.calendari_fed import descobreix_fcb

    pagina = f'<a href="https://fcbillar.cat/download/10/calendari-lligues/1/{fitxer}">x</a>'

    assert descobreix_fcb(pagina) == []
