"""El seguiment d'opens en directe, contra les pàgines del web nou de la federació.

De l'agost a l'octubre de 2026 `fcb_opens/scraper/open_live.py` va seguir buscant
el marcatge del web vell (`a.button`, `div.row.padded`) i les rutes velles
(`partidesgrups`, `partideseliminatoria`). Contra el portal nou no en treia res:
nom «UNKNOWN» i zero fases. I com que un open sense fases se saltava en silenci,
`publish-live-opens` deia «live_opens=0, errors=0» cada cap de setmana amb el job
en verd, i dos opens es van jugar sense seguiment.

Totes les pàgines d'aquí són còpies de les de debò, baixades el 8 d'octubre de
2026: l'Open Banda Granollers (219) sencer, que és petit, i retalls d'altres
torneigs per als casos que aquell no té.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fcb_opens.scraper import open_live as ol
from fcb_opens.scraper.horaris_pdf import parse_horaris_pdf
from fcb_opens.snapshot_live import _state_payload

FIXTURES = Path(__file__).parent / "fixtures" / "nou"


def pagina(nom: str) -> str:
    return (FIXTURES / nom).read_text(encoding="utf-8")


def fitxer_de(url: str) -> str:
    """El nom del fixture d'una adreça del portal: la ruta amb guions baixos."""
    cami = url.split("/frontend/", 1)[1].strip("/")
    return re.sub(r"[^A-Za-z0-9]+", "_", cami) + ".html"


@pytest.fixture
def portal(monkeypatch):
    """`fetch` servit dels fixtures. Una pàgina que no hi és fa fallar la prova."""
    demanades: list[str] = []
    canvis: dict[str, str] = {}

    def fetch(url: str, **_k) -> str:
        demanades.append(url)
        nom = fitxer_de(url)
        if nom in canvis:
            return canvis[nom]
        return pagina(nom)

    monkeypatch.setattr(ol, "fetch", fetch)
    return type("Portal", (), {"demanades": demanades, "canvis": canvis})()


# --------------------------------------------------------------------------- #
# Llistat
# --------------------------------------------------------------------------- #


def test_el_llistat_porta_l_estat_de_cada_torneig() -> None:
    entrades = {
        e.division_id: e
        for e in ol.parse_individuals_llistat(pagina("individuals_llistat_2026_10.html"))
    }
    assert entrades[219].name == "OPEN BANDA GRANOLLERS"
    assert entrades[219].estat == "Activa"
    assert entrades[220].estat == "Inscripció"


def test_un_llistat_sense_taula_no_es_un_llistat_buit(monkeypatch) -> None:
    """Sense la taula de torneigs no es pot dir «no hi ha cap open»."""
    monkeypatch.setattr(
        ol, "fetch", lambda url, **_k: "<html><body><p>Manteniment</p></body></html>"
    )
    with pytest.raises(ol.EstructuraInesperada):
        ol.fetch_individuals_llistat()


# --------------------------------------------------------------------------- #
# Divisió i fases
# --------------------------------------------------------------------------- #


def test_la_pagina_de_l_open_dona_el_nom_i_la_divisio() -> None:
    estructura = ol.parse_division_page(pagina("individuals_divisions_219.html"), 219)
    assert estructura.name == "OPEN BANDA GRANOLLERS"
    assert estructura.phase_id == 461


def test_una_pagina_del_web_vell_ja_no_torna_unknown() -> None:
    """Abans en sortia «UNKNOWN» i cap fase, i ningú no se n'assabentava."""
    vella = '<section class="three fourths padded"><h2>OPEN TRES BANDES SANTS</h2></section>'
    with pytest.raises(ol.EstructuraInesperada):
        ol.parse_division_page(vella, 206)


def test_les_fases_de_grups_i_les_eliminatories() -> None:
    fases = ol.parse_fases_page(pagina("individuals_fases_219_461.html"))
    assert [(f.label, f.kind, f.date) for f in fases] == [
        ("PRÈVIA", "group", "2026-09-20"),
        ("VUITENS", "group", "2026-09-26"),
        ("QUARTS", "ko", "2026-09-26"),
        ("SEMIFINALS", "ko", "2026-09-27"),
        ("FINAL", "ko", "2026-09-27"),
    ]
    assert fases[0].url.endswith("/individuals/grups/219/461/811")
    assert fases[2].url.endswith("/individuals/partides-eliminatories/219/461/1190")


def test_un_open_sense_sorteig_no_te_fases_i_no_es_cap_error() -> None:
    """Les dues taules hi són, buides: és «encara no hi ha res», no «no ho sé llegir»."""
    assert ol.parse_fases_page(pagina("individuals_fases_218_453.html")) == ()


def test_si_la_federacio_reanomena_una_ruta_salta() -> None:
    """El que va passar l'agost de 2026, a l'inrevés: una ruta que no es reconeix."""
    html = pagina("individuals_fases_219_461.html").replace(
        "partides-eliminatories", "eliminatories-partides"
    )
    with pytest.raises(ol.EstructuraInesperada, match="no reconec"):
        ol.parse_fases_page(html)


def test_una_pagina_de_fases_sense_cap_taula_salta() -> None:
    with pytest.raises(ol.EstructuraInesperada):
        ol.parse_fases_page("<html><body><div class='row box info'></div></body></html>")


# --------------------------------------------------------------------------- #
# Grups
# --------------------------------------------------------------------------- #


def test_els_grups_d_una_fase_amb_seu_dia_i_jugadors() -> None:
    grups = ol.parse_grups_page(pagina("individuals_grups_219_461_812.html"))
    assert [g.label for g in grups] == [f"Grup {x}" for x in "ABCDEF"]
    a = grups[0]
    assert a.venue == "B.C.GRANOLLERS"
    assert a.date == "2026-09-26"
    assert a.url.endswith("/individuals/partides-grup/219/461/812/5293")
    assert [s.player_name for s in a.standings] == [
        "BERENGUERAS COSTA, F. XAVIER",
        "BERENGUERAS COSTA, JORDI",
        "ESPINASA SÁNCHEZ, JOAN",
    ]


def test_grup_en_majuscules_es_el_mateix_grup() -> None:
    """La prèvia de Granollers el diu «GRUP G»; ha de comptar com a grup de debò."""
    (grup,) = ol.parse_grups_page(pagina("individuals_grups_219_461_811.html"))
    assert grup.label == "Grup G"
    assert ol._is_regular_group(grup.label)


def test_els_reservats_surten_amb_la_seva_etiqueta() -> None:
    grups = ol.parse_grups_page(pagina("individuals_grups_211_447_801.html"))
    assert grups[-1].label == "RESERVATS"
    assert len(grups) == 17
    # La taula de participants de la fase no els llista: només els 48 dels
    # setze grups. Els caps de sèrie surten de la pàgina del seu «grup».
    assert grups[-1].standings == ()
    assert sum(len(g.standings) for g in grups) == 48


def test_classificacio_i_partides_d_un_grup() -> None:
    grup = ol.parse_group_page(
        pagina("individuals_partides_grup_219_461_812_5293.html"), "Grup A", "u"
    )
    assert [(s.player_name, s.punts, s.mitjana) for s in grup.standings] == [
        ("ESPINASA SÁNCHEZ, JOAN", 4, 4.6875),
        ("BERENGUERAS COSTA, F. XAVIER", 2, 1.7105),
        ("BERENGUERAS COSTA, JORDI", 0, 0.5926),
    ]
    # El web nou no escriu el club del jugador enlloc: buit, no inventat.
    assert {s.club for s in grup.standings} == {""}
    primera = grup.matches[0]
    assert (primera.player_a, primera.player_b) == (
        "BERENGUERAS COSTA, F. XAVIER",
        "BERENGUERAS COSTA, JORDI",
    )
    assert (primera.caramboles_a, primera.caramboles_b, primera.entrades) == (55, 15, 30)
    assert (primera.serie_major_a, primera.serie_major_b) == (10, 3)
    assert primera.arbitre == "Manuel Garcia"
    # Els punts de partida no hi són: es dedueixen de les caramboles.
    assert (primera.punts_a, primera.punts_b) == (2, 0)
    assert all(m.is_played for m in grup.matches)


def test_una_partida_pendent_no_es_un_resultat() -> None:
    """El que es veu mentre es juga: partides acabades i una que encara no."""
    grup = ol.parse_group_page(
        pagina("individuals_partides_grup_216_455_815_5303.html"), "Grup A", "u"
    )
    pendent = grup.matches[0]
    assert pendent.estat == "Pendent"
    assert not pendent.is_played
    assert not ol._is_decided(pendent)
    assert pendent.entrades is None
    assert [m.is_played for m in grup.matches] == [False, True, True]
    payload = _state_payload(
        ol.OpenLiveState(
            structure=ol.OpenStructure(1, "OPEN X", 1, ()),
            phases=[ol.PhaseDetail(ref=ol.PhaseRef("PRÈVIA", "group", ""), groups=(grup,))],
        ),
        "ara",
    )
    assert payload["phases"][0]["is_active"] is True
    assert payload["phases"][0]["groups"][0]["matches"][0]["estat"] == "Pendent"


def test_les_incompareixences_d_un_grup_es_reparteixen_per_la_classificacio() -> None:
    """Tres partides «Finalitzada» amb tot a zero i una classificació 4-0-0.

    Qui té els quatre punts ha guanyat les seves dues; la tercera no la va
    guanyar ningú (cap dels dos s'hi va presentar) i es queda 0-0, però tancada.
    """
    grup = ol.parse_group_page(
        pagina("individuals_partides_grup_219_461_811_5292.html"), "Grup G", "u"
    )
    resultats = {(m.player_a, m.player_b): (m.punts_a, m.punts_b) for m in grup.matches}
    assert resultats == {
        ("BERENGUERAS COSTA, JORDI", "PARERA FERNÁNDEZ, VALERIÀ"): (2, 0),
        ("BERENGUERAS COSTA, JORDI", "PRETEL PÉREZ, JOSÉ"): (2, 0),
        ("PARERA FERNÁNDEZ, VALERIÀ", "PRETEL PÉREZ, JOSÉ"): (0, 0),
    }
    assert not any(m.is_played for m in grup.matches)
    assert all(ol._is_decided(m) for m in grup.matches)
    assert ol._is_walkover(grup.matches[0])


def test_una_pagina_de_grup_sense_cap_taula_salta() -> None:
    with pytest.raises(ol.EstructuraInesperada):
        ol.parse_group_page("<div id='classificacio'><div>JUGADOR</div></div>", "Grup A", "u")


# --------------------------------------------------------------------------- #
# Eliminatòries
# --------------------------------------------------------------------------- #


def test_una_ronda_eliminatoria() -> None:
    quarts = ol.parse_ko_page(pagina("individuals_partides_eliminatories_219_461_1190.html"))
    assert len(quarts) == 4
    assert [ol._ko_winner(m) for m in quarts] == [
        "ESPINASA SÁNCHEZ, JOAN",
        "ARNAU FONT, RICARD",
        "MORENO CORTÉS, ARMAND",
        "GASSÓ CHUMILLAS, JORDI",
    ]


def test_un_empat_a_caramboles_el_desfa_la_taula_de_punts() -> None:
    """Semifinal 100-100 en 28 entrades: les caramboles no diuen qui passa.

    El web vell ho escrivia a «Observacions», que ja no existeix. El nou porta
    una segona taula amb els punts de cada jugador de la ronda.
    """
    semis = ol.parse_ko_page(pagina("individuals_partides_eliminatories_219_461_1191.html"))
    empat = next(m for m in semis if m.caramboles_a == m.caramboles_b)
    assert (empat.player_a, empat.player_b) == ("ARNAU FONT, RICARD", "MORENO CORTÉS, ARMAND")
    assert (empat.punts_a, empat.punts_b) == (2, 0)
    assert ol._ko_winner(empat) == "ARNAU FONT, RICARD"


def test_una_eliminatoria_sense_taula_de_partides_salta() -> None:
    with pytest.raises(ol.EstructuraInesperada):
        ol.parse_ko_page("<html><body>No hi ha registres disponibles</body></html>")


# --------------------------------------------------------------------------- #
# Open acabat o en joc
# --------------------------------------------------------------------------- #


def test_l_enllac_de_classificacio_hi_es_sempre_i_no_vol_dir_res() -> None:
    """Al web vell l'enllaç sortia quan l'open s'acabava. Ara hi és des del primer dia."""
    url = ol.parse_final_classification_url(pagina("individuals_divisions_219.html"))
    assert url.endswith("/individuals/divisio-classificacio-final/219/461")


def test_un_open_es_tancat_quan_la_classificacio_te_files() -> None:
    assert ol.parse_has_final_classification(
        pagina("individuals_divisio_classificacio_final_219_461.html")
    )
    # «No s'ha creat la classificació»: la taula hi és amb una sola fila de text.
    assert not ol.parse_has_final_classification(
        pagina("individuals_divisio_classificacio_final_216_454.html")
    )


def test_fetch_has_final_classification_entra_a_la_classificacio(portal) -> None:
    assert ol.fetch_has_final_classification(219) is True
    assert any("divisio-classificacio-final/219/461" in u for u in portal.demanades)


# --------------------------------------------------------------------------- #
# L'open sencer
# --------------------------------------------------------------------------- #


def test_l_open_banda_granollers_sencer(portal) -> None:
    estat = ol.fetch_live_state(219)

    assert estat.structure.name == "OPEN BANDA GRANOLLERS"
    assert estat.last_date == "2026-09-27"
    assert [(p.ref.label, p.ref.kind) for p in estat.phases] == [
        ("PRÈVIA", "group"),
        ("VUITENS", "group"),
        ("QUARTS", "ko"),
        ("SEMIFINALS", "ko"),
        ("FINAL", "ko"),
    ]
    assert [len(p.groups) for p in estat.phases] == [1, 6, 0, 0, 0]
    assert [len(p.ko_matches) for p in estat.phases] == [0, 0, 4, 2, 1]
    assert sum(len(g.matches) for p in estat.phases for g in p.groups) == 21

    payload = _state_payload(estat, "2026-10-08T00:00:00+00:00")
    assert payload["name"] == "OPEN BANDA GRANOLLERS"
    assert not any(p["is_active"] for p in payload["phases"])
    grup = payload["phases"][1]["groups"][0]
    assert grup["label"] == "Grup A"
    assert grup["venue"] == "B.C.GRANOLLERS"
    assert grup["date"] == "2026-09-26"
    # El podi, que és el que publica la federació a la classificació oficial.
    podi = [(r["position"], r["player_name"]) for r in payload["classification"][:2]]
    assert podi == [(1, "ESPINASA SÁNCHEZ, JOAN"), (2, "ARNAU FONT, RICARD")]


def test_si_una_pagina_de_l_open_ha_canviat_no_torna_un_open_buit(portal) -> None:
    """El cas de l'octubre de 2026: abans tornava zero fases i semblava que no hi havia res."""
    portal.canvis["individuals_fases_219_461.html"] = (
        '<section class="three fourths padded">'
        '<a class="button" href="/ca/individuals/partidesgrups/219/461/811">PRÈVIA</a>'
        "</section>"
    )
    with pytest.raises(ol.EstructuraInesperada):
        ol.fetch_live_state(219)


# --------------------------------------------------------------------------- #
# Documents: rànquing inicial, horaris, grups
# --------------------------------------------------------------------------- #

SITEMAP = (FIXTURES / "wp_sitemap_documents_2026_10.xml").read_text(encoding="utf-8")


def test_els_documents_d_opens_surten_del_sitemap() -> None:
    docs = ol.parse_opens_docs(SITEMAP)
    slugs = {d.slug for d in docs}
    assert "horaris-open-banda-b-c-granollers" in slugs
    assert "2627-openlliurepuntatac-ranquinginicial" in slugs
    # Els rànquings del circuit i el reglament parlen d'opens però no són de cap open.
    assert not any(s.startswith(("ranquing-catala", "ranquing-opens", "reglament")) for s in slugs)
    horaris = next(d for d in docs if d.slug == "horaris-open-banda-b-c-granollers")
    assert horaris.title == "HORARIS OPEN BANDA B C GRANOLLERS"
    assert horaris.date == "14/09/2026"
    assert horaris.view_url == "https://fcbillar.cat/wpfd_file/horaris-open-banda-b-c-granollers/"


def test_cada_open_troba_els_seus_documents_i_no_els_d_un_altre() -> None:
    docs = ol.parse_opens_docs(SITEMAP)
    banda = {d.slug for d in ol.filter_docs_for_division(docs, 219, "OPEN BANDA GRANOLLERS")}
    lliure = {d.slug for d in ol.filter_docs_for_division(docs, 217, "OPEN LLIURE PUNT D'ATAC")}
    assert "ranking-inicial-open-banda-b-c-granollers" in banda
    assert "horaris-open-banda-b-c-granollers" in banda
    # La federació els posa nom com vol: «…openlliurepuntatac…» i «…punt-datac».
    assert "2627-openlliurepuntatac-horaris" in lliure
    assert "convocatoria-open-lliure-punt-datac" in lliure
    assert not banda & lliure
    # Un open que encara no té cap document no n'agafa de cap altre: «SANT
    # ADRIA» i «SANTS» comparteixen quatre lletres.
    assert ol.filter_docs_for_division(docs, 0, "OPEN TRES BANDES SANT ADRIA") == ()
    # I un de tres bandes al mateix club no es queda els del de banda.
    assert ol.filter_docs_for_division(docs, 0, "OPEN TRES BANDES GRANOLLERS") == ()


def test_quin_document_es_el_ranquing_inicial() -> None:
    docs = {d.slug: d for d in ol.parse_opens_docs(SITEMAP)}
    assert ol.doc_parla_de(
        docs["ranking-inicial-open-banda-b-c-granollers"], "RANQUING INICIAL", "RANKING INICIAL"
    )
    assert ol.doc_parla_de(
        docs["2627-openlliurepuntatac-ranquinginicial"], "RANQUING INICIAL", "RANKING INICIAL"
    )
    assert not ol.doc_parla_de(docs["2627-openlliurepuntatac-horaris"], "RANQUING INICIAL")


def test_el_pdf_d_un_document_no_es_el_calendari_de_la_capcalera() -> None:
    """Retall de la pàgina de debò: hi ha dos PDF i el primer no és el bo."""
    html = """
    <a href="https://fcbillar.cat/download/36/calendari/232324/calendari-fcb-2026-27-v-2.pdf">Calendari</a>
    <a href="https://fcbillar.cat/download/33/opens/232492/horaris-open-banda-b-c-granollers.pdf">Descarrega</a>
    """
    assert ol.parse_doc_pdf_url(html, "horaris-open-banda-b-c-granollers") == (
        "https://fcbillar.cat/download/33/opens/232492/horaris-open-banda-b-c-granollers.pdf"
    )
    # Encara que el fitxer no es digui com la pàgina.
    assert ol.parse_doc_pdf_url(html, "un-altre-nom").endswith("granollers.pdf")
    assert ol.parse_doc_pdf_url("<p>res</p>") is None


def test_els_horaris_d_un_bloc_de_dos_dies() -> None:
    """Els PDF de la 2026-27 posen «04-05/09/2026» al bloc que dura dos dies.

    Abans aquella data no es reconeixia i els grups del bloc heretaven la del
    bloc de sobre: els vuitens del Punt d'Atac sortien el 30 d'agost.
    """
    horaris = parse_horaris_pdf(FIXTURES / "horaris_open_lliure_punt_atac_2627.pdf")
    assert horaris["M"]["date"] == "2026-08-29"
    assert horaris["G"]["date"] == "2026-08-30"
    # Divendres a la tarda…
    assert horaris["D"]["date"] == "2026-09-04"
    assert horaris["D"]["matches"][0] == {"type": "2-3", "time": "15:30"}
    # …i dissabte al matí: l'hora torna enrere i és l'endemà.
    assert horaris["A"]["date"] == "2026-09-05"
    assert horaris["A"]["matches"][0] == {"type": "2-3", "time": "09:30"}
    assert horaris["A"]["billar"] == 1
    assert horaris["C"]["billar"] == 3
