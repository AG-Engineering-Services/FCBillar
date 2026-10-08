"""`publish-live-opens` ha de fallar fort quan no sap llegir un open.

El lector d'opens en directe es va trencar amb el web nou de la federació
(agost de 2026) i ningú no ho va veure fins a l'octubre: la publicació se saltava
en silenci l'open del qual no treia cap fase, tornava «live_opens=0, errors=0»,
la comanda sortia amb 0 i el workflow, que a més hi tenia un `|| true`, es
quedava en verd. Una sola execució de cap de setmana ho va dir 142 vegades.

Aquí es prova la publicació sencera contra les pàgines de debò de l'Open Banda
Granollers (219) i un núvol fals, i sobretot què passa quan una pàgina deixa de
tenir la forma esperada.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from fcb_opens.scraper import open_live as ol
from fcbillar import cloud_sync
from fcbillar.cli import app
from tests.test_open_live_web_nou import fitxer_de, pagina
from tests.test_publish_lliga_retirada import ClientFals, TaulaFalsa


class Taula(TaulaFalsa):
    """La taula falsa de sempre, amb els tres filtres que fa servir aquest camí."""

    def order(self, *_a, **_k) -> Taula:
        return self

    def lt(self, camp: str, valor) -> Taula:
        self._filtres.append(lambda f: f.get(camp) is not None and f.get(camp) < valor)
        return self

    @property
    def not_(self):
        pare = self

        class _No:
            def in_(self, camp: str, valors) -> Taula:
                conjunt = set(valors)
                pare._filtres.append(lambda f: f.get(camp) not in conjunt)
                return pare

        return _No()


class Client(ClientFals):
    def table(self, nom: str) -> Taula:
        return Taula(self._m, nom)


NO_CREADA = "individuals_divisio_classificacio_final_216_454.html"


@pytest.fixture
def entorn(monkeypatch):
    """El portal servit dels fixtures i un núvol a la memòria.

    L'Open Banda Granollers es va acabar el 27 de setembre. Per tenir-lo «en
    joc» se li serveix la classificació final d'un torneig que encara no la té,
    i es desactiva la caducitat (que el donaria per acabat per la data).
    """
    canvis: dict[str, str] = {
        "individuals_divisio_classificacio_final_219_461.html": pagina(NO_CREADA),
    }

    def fetch(url: str, **_k) -> str:
        nom = fitxer_de(url)
        return canvis[nom] if nom in canvis else pagina(nom)

    monkeypatch.setattr(ol, "fetch", fetch)
    monkeypatch.setattr(
        ol,
        "fetch_individuals_llistat",
        lambda **_k: (ol.CompetitionIndexEntry(219, "OPEN BANDA GRANOLLERS", 0, "Activa"),),
    )
    # Ni PDF ni projecció: aquí es prova la lectura del portal.
    monkeypatch.setattr(cloud_sync, "_autobuild_projection_payload", lambda *a, **k: None)
    monkeypatch.setattr(cloud_sync, "_open_schedule_by_group", lambda *a, **k: None)
    monkeypatch.setattr(cloud_sync, "_open_caducat", lambda state, avui: False)

    magatzem: dict[str, list[dict]] = {
        "open_live": [],
        "open_ranking": [],
        "players": [{"nom": "ESPINASA SÁNCHEZ, JOAN", "fcb_id": "211"}],
    }
    monkeypatch.setattr(cloud_sync, "get_client", lambda: Client(magatzem))
    return type("Entorn", (), {"magatzem": magatzem, "canvis": canvis})()


def test_un_open_en_joc_es_publica_amb_les_seves_fases(entorn) -> None:
    missatges: list[str] = []
    res = cloud_sync.publish_live_opens(lambda nivell, msg: missatges.append(msg))

    assert res["live_opens"] == 1
    assert res["errors"] == 0
    (fila,) = entorn.magatzem["open_live"]
    assert fila["fcb_division_id"] == 219
    assert fila["name"] == "OPEN BANDA GRANOLLERS"
    assert fila["modality"] == "Banda"
    payload = fila["payload_json"]
    assert [p["label"] for p in payload["phases"]] == [
        "PRÈVIA",
        "VUITENS",
        "QUARTS",
        "SEMIFINALS",
        "FINAL",
    ]
    grup = payload["phases"][1]["groups"][0]
    # El que llegeixen les aplicacions dels clubs (openLive.ts, upcomingOpens.ts).
    assert {"label", "venue", "standings"} <= set(grup)
    assert {"player_name", "club", "punts", "mitjana"} <= set(grup["standings"][0])
    assert payload["player_ids"] == {"ESPINASA SÁNCHEZ, JOAN": "211"}
    # El dia del portal viatja, però no es disfressa d'horari.
    assert grup["date"] == "2026-09-26"
    assert "schedule" not in grup
    assert any("5 fases, 7 grups, 28 partides" in m for m in missatges)


def test_un_open_tancat_no_es_publica_i_no_es_cap_error(entorn) -> None:
    """Avui: tots els opens del llistat ja tenen classificació final."""
    del entorn.canvis["individuals_divisio_classificacio_final_219_461.html"]
    entorn.magatzem["open_live"].append({"fcb_division_id": 219, "name": "OPEN BANDA GRANOLLERS"})

    res = cloud_sync.publish_live_opens()

    assert res["live_opens"] == 0
    assert res["errors"] == 0
    assert res["removed"] == 1, "un open acabat es retira del directe"
    assert entorn.magatzem["open_live"] == []


def test_la_pagina_de_fases_ha_canviat_es_un_error_i_no_zero_opens(entorn) -> None:
    """El cas de debò. Abans: `live_opens=0, errors=0`. Ara: error d'estructura."""
    entorn.canvis["individuals_fases_219_461.html"] = (
        '<section class="three fourths padded">'
        '<a class="button" href="/ca/individuals/partidesgrups/219/461/811">PRÈVIA</a>'
        "</section>"
    )
    # El que hi havia publicat d'una passada anterior, quan encara es llegia.
    entorn.magatzem["open_live"].append({"fcb_division_id": 219, "name": "OPEN BANDA GRANOLLERS"})
    avisos: list[str] = []

    res = cloud_sync.publish_live_opens(lambda nivell, msg: avisos.append(msg))

    assert res["live_opens"] == 0
    assert res["errors"] == 1
    assert res["errors_estructura"] == 1
    assert any("NO TÉ LA FORMA ESPERADA" in a for a in avisos)
    # No haver-lo pogut llegir no vol dir que s'hagi acabat: la fila s'hi queda.
    assert res["removed"] == 0
    assert [f["fcb_division_id"] for f in entorn.magatzem["open_live"]] == [219]


def test_una_ruta_reanomenada_dins_d_una_fase_tambe_es_un_error(entorn) -> None:
    entorn.canvis["individuals_grups_219_461_812.html"] = pagina(
        "individuals_grups_219_461_812.html"
    ).replace("partides-grup", "partidesgrups")

    res = cloud_sync.publish_live_opens()

    assert (res["live_opens"], res["errors"], res["errors_estructura"]) == (0, 1, 1)


def test_no_saber_si_esta_tancat_es_compta_i_es_publica_igualment(entorn) -> None:
    """Abans era un `except: pass`. Si la pàgina de classificació canvia, s'ha de saber."""
    entorn.canvis["individuals_divisio_classificacio_final_219_461.html"] = "<html></html>"

    res = cloud_sync.publish_live_opens()

    assert res["errors_estructura"] == 1
    assert res["live_opens"] == 1, "en el dubte l'open segueix en directe"


def test_un_open_actiu_sense_sorteig_s_avisa_pero_no_es_un_error(entorn) -> None:
    """Entre el tancament d'inscripcions i el sorteig la pàgina de fases és buida de debò."""
    entorn.canvis["individuals_fases_219_461.html"] = pagina("individuals_fases_218_453.html")
    avisos: list[str] = []

    res = cloud_sync.publish_live_opens(lambda nivell, msg: avisos.append(msg))

    assert (res["live_opens"], res["errors"], res["sense_fases"]) == (0, 0, 1)
    assert any("encara no té cap fase publicada" in a for a in avisos)


def test_el_llistat_illegible_es_un_error_d_estructura(entorn, monkeypatch) -> None:
    def peta(**_k):
        raise ol.EstructuraInesperada("llistat d'individuals: no hi ha la taula de torneigs")

    monkeypatch.setattr(ol, "fetch_individuals_llistat", peta)

    res = cloud_sync.publish_live_opens()

    assert (res["errors"], res["errors_estructura"]) == (1, 1)


def test_dry_run_no_escriu_ni_esborra_res(entorn) -> None:
    entorn.magatzem["open_live"].append({"fcb_division_id": 150, "name": "UN OPEN VELL"})

    res = cloud_sync.publish_live_opens(dry_run=True)

    assert res["live_opens"] == 1
    assert entorn.magatzem["open_live"] == [{"fcb_division_id": 150, "name": "UN OPEN VELL"}]


def test_la_prova_de_fum_llegeix_un_open_acabat(entorn) -> None:
    """`--inclou-tancats`: el lector es prova encara que no hi hagi cap open en joc."""
    del entorn.canvis["individuals_divisio_classificacio_final_219_461.html"]

    res = cloud_sync.publish_live_opens(dry_run=True, include_closed=True, max_opens=1)

    assert (res["live_opens"], res["errors"]) == (1, 0)
    assert entorn.magatzem["open_live"] == []


def test_un_open_que_la_federacio_no_tanca_mai_caduca() -> None:
    """Mataró, juliol de 2026: final jugada el 26 i la classificació no s'ha creat mai."""
    from datetime import date

    estat = ol.OpenLiveState(structure=ol.OpenStructure(211, "X", 447, ()), last_date="2026-07-26")
    assert not cloud_sync._open_caducat(estat, date(2026, 7, 26))
    assert not cloud_sync._open_caducat(estat, date(2026, 7, 29))
    assert cloud_sync._open_caducat(estat, date(2026, 7, 30))
    # Sense cap data no es pot dir que hagi caducat.
    estat.last_date = None
    assert not cloud_sync._open_caducat(estat, date(2026, 12, 1))


def test_els_reservats_sense_club_no_es_dupliquen() -> None:
    """El web nou no dona el club; la projecció (PDF) sí. Han de casar igualment.

    Amb el club dins de la clau cap reservat del viu no casava amb el seu de la
    projecció, i els setze caps de sèrie s'haurien afegit dues vegades.
    """
    estat = ol.OpenLiveState(
        structure=ol.OpenStructure(1, "OPEN TRES BANDES X", 1, ()),
        reservats=(
            ol.GroupStanding("GARCÍA ALARCÓN, RICARDO", "", 0, 0.0),
            ol.GroupStanding("MAS CANADELL, JOSEP Mª", "", 0, 0.0),
        ),
    )
    projeccio = [
        {
            "kind": "ko",
            "label": "Fase Final (K.O.)",
            "provisional_players": [
                {"name": "GARCIA ALARCÓN,RICARDO", "club": "C.B. SANTS", "source": "reservat"},
                {"name": "MAS CANADELL, JOSEP Mª", "club": "C.B. BANYOLES", "source": "reservat"},
                {"name": "PASTOR RIVAS, MANUEL", "club": "C.B. MOLLET", "source": "reservat"},
            ],
        }
    ]

    afegits = cloud_sync._complete_first_ko_reservats(estat, projeccio)

    assert afegits == 1
    assert [s.player_name for s in estat.reservats] == [
        "GARCÍA ALARCÓN, RICARDO",
        "MAS CANADELL, JOSEP Mª",
        "PASTOR RIVAS, MANUEL",
    ]


# --------------------------------------------------------------------------- #
# La comanda: amb quin codi surt
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("comptadors", "codi"),
    [
        ({"live_opens": 0, "errors": 0, "errors_estructura": 0}, 0),
        ({"live_opens": 2, "errors": 0, "errors_estructura": 0}, 0),
        ({"live_opens": 0, "errors": 1, "errors_estructura": 0}, 1),
        ({"live_opens": 1, "errors": 1, "errors_estructura": 1}, 3),
    ],
)
def test_la_comanda_surt_amb_error_quan_n_hi_ha(monkeypatch, comptadors, codi) -> None:
    """«Cap open en joc» surt amb 0; un error, mai. Abans sortia sempre amb 0."""
    monkeypatch.setattr(cloud_sync, "publish_live_opens", lambda **_k: comptadors)
    res = CliRunner().invoke(app, ["publish-live-opens"])
    assert res.exit_code == codi, res.output


def test_inclou_tancats_nomes_amb_dry_run(monkeypatch) -> None:
    """Publicar com a «en directe» un open acabat no s'ha de poder fer per error."""
    cridat: list[dict] = []
    monkeypatch.setattr(cloud_sync, "publish_live_opens", lambda **k: cridat.append(k) or {})
    res = CliRunner().invoke(app, ["publish-live-opens", "--inclou-tancats"])
    assert res.exit_code == 2
    assert cridat == []
