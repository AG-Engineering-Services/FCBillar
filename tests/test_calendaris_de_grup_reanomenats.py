"""Un calendari de grup que la federació reanomena s'ha de veure, no perdre's.

Els calendaris de grup es troben al sitemap pel nom del document
(`calendari-lliga-tres-bandes-2026-27-honor-grup-a`), que algú escriu a mà al
WordPress. Si en canvien la forma, la comanda no en troba cap; i si només en
canvien un, n'ingereix onze i sembla que tot va bé.

I la temporada: la comanda duia «2026/2027» per defecte i la reingesta la crida
sense arguments. El setembre de 2027 hauria seguit demanant els de la temporada
anterior, que encara són al sitemap.
"""

from __future__ import annotations

from pathlib import Path

from fcbillar.calendari_lliga import (
    calendaris_sense_llegir,
    es_calendari_de_grup,
    slugs_de_grup,
    temporada_mes_nova,
)

FIXTURES = Path(__file__).parent / "fixtures" / "nou"
#: El sitemap del 8 d'octubre de 2026: els dotze grups de tres bandes i els
#: quatre calendaris de la Lliga de 4 Modalitats, que no es llegeixen a posta.
SITEMAP = (FIXTURES / "wp_sitemap_documents_2026_10.xml").read_text(encoding="utf-8")


def _sitemap(*slugs: str) -> str:
    return (
        "<urlset>"
        + "".join(f"<url><loc>https://fcbillar.cat/wpfd_file/{s}/</loc></url>" for s in slugs)
        + "</urlset>"
    )


def test_al_sitemap_de_debo_no_n_hi_ha_cap_sense_llegir() -> None:
    """Els de 4 Modalitats no compten: les seves dates venen de la intranet."""
    assert len(slugs_de_grup(SITEMAP)) == 12
    assert calendaris_sense_llegir(SITEMAP) == []


def test_un_de_reanomenat_surt_a_la_llista() -> None:
    reanomenat = SITEMAP.replace(
        "calendari-lliga-tres-bandes-2026-27-honor-grup-a", "calendari-lliga-3-bandes-26-27-honor-a"
    )

    assert len(slugs_de_grup(reanomenat)) == 11, "se n'ingeririen onze sense dir res"
    assert calendaris_sense_llegir(reanomenat) == ["calendari-lliga-3-bandes-26-27-honor-a"]


def test_si_els_reanomenen_tots_no_en_queda_cap_i_es_diu() -> None:
    tots = SITEMAP.replace("calendari-lliga-tres-bandes-", "calendari-lliga-tresbandes-")

    assert slugs_de_grup(tots) == []
    assert len(calendaris_sense_llegir(tots)) == 12


def test_el_calendari_esportiu_i_els_reglaments_no_s_hi_colen() -> None:
    """«calendari-fcb-…» és un altre document, i un reglament de lliga no és cap calendari."""
    slugs = _sitemap("calendari-fcb-2026-27-v-2", "reglament-lliga-catalana-3-bandes-26-27")

    assert calendaris_sense_llegir(slugs) == []


def test_es_reconeix_pel_mateix_criteri_que_es_descobreix() -> None:
    assert es_calendari_de_grup("calendari-lliga-tres-bandes-2026-27-quarta-grup-d")
    assert not es_calendari_de_grup("calendari-lliga-4modalitats-honor-26-27")
    assert not es_calendari_de_grup("calendari-fcb-2026-27-v-2")


def test_la_temporada_es_la_mes_nova_que_hi_ha_publicada() -> None:
    assert temporada_mes_nova(SITEMAP) == "2026/2027"


def test_l_any_que_ve_la_temporada_canvia_sola() -> None:
    """Amb els de la 2027-28 penjats al costat dels vells, s'ingereixen els nous."""
    amb_els_nous = _sitemap(
        "calendari-lliga-tres-bandes-2026-27-honor-grup-a",
        "calendari-lliga-tres-bandes-2027-28-honor-grup-a",
        "calendari-lliga-tres-bandes-2027-28-honor-grup-b",
    )

    assert temporada_mes_nova(amb_els_nous) == "2027/2028"
    assert len(slugs_de_grup(amb_els_nous, temporada_mes_nova(amb_els_nous))) == 2


def test_sense_cap_calendari_no_hi_ha_temporada() -> None:
    assert temporada_mes_nova(_sitemap("calendari-fcb-2026-27-v-2")) is None
