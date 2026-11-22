"""Classificacions finals dels campionats individuals de la RFEB.

Els PDF de `tests/fixtures/rfeb_individuals/` són còpies de la web vella, amb la
mateixa estructura de carpetes (`noticiasAAAA/`): un de cada capçalera principal.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from fcbillar.db.migrations import ensure_schema
from fcbillar.lliga_nacional import FormatDesconegut
from fcbillar.rfeb_individuals import (
    SenseTaula,
    llegeix_capcalera,
    llegeix_fila,
    llegeix_prova,
    llegeix_taula,
    normalitza_fed,
)
from fcbillar.rfeb_individuals_carrega import carrega, cobertura

ARREL = Path(__file__).parent / "fixtures" / "rfeb_individuals"


def prova(id_: str):
    return llegeix_prova(ARREL / f"{id_}.pdf", ARREL)


# ---------------------------------------------------------------- capçaleres


@pytest.mark.parametrize(
    ("linia", "numeriques"),
    [
        (
            "# NOMBRE FED J G E P CAR. ENT. PROM. S.M. PTOS.",
            (
                *("jugades", "guanyades", "empatades", "perdudes", "caramboles", "entrades"),
                *("mitjana", "serie_major", "punts"),
            ),
        ),
        ("# NOMBRE FED CAR ENT PROM", ("caramboles", "entrades", "mitjana")),
        ("# NOMBRE FED CAR ENT PROM Puntos", ("caramboles", "entrades", "mitjana", "punts")),
        (
            "Clasif. Jugadores Federación T-Car. T.Entr. Prom. Gral. Ptos.",
            ("caramboles", "entrades", "mitjana", "punts"),
        ),
        # La posició és al final: no és cap columna numèrica.
        (
            "JUGADORES C.A. Ptos Car Ent P.Gral SM Cls",
            ("punts", "caramboles", "entrades", "mitjana", "serie_major"),
        ),
    ],
)
def test_la_capcalera_dona_les_columnes_per_ordre(linia, numeriques):
    cap = llegeix_capcalera(linia)
    assert cap is not None
    assert cap.numeriques == numeriques


def test_una_linia_de_dades_enganxada_a_una_capcalera_no_es_capcalera():
    # Les fases de grups porten això: la capçalera i la primera fila a la mateixa línia.
    assert llegeix_capcalera("Jugadores Fed Ptos Car Ent P.Gral SM Clas 3 ANDY OSPINA MAD") is None


def test_la_ronda_i_la_federacio_son_a_la_capcalera():
    cap = llegeix_capcalera("# RONDA NOMBRE FED J G E P CAR. ENT. PROM. PTOS.")
    assert cap is not None
    assert cap.ronda
    assert cap.fed
    assert cap.posicio_davant


# ----------------------------------------------------------------- federacions


@pytest.mark.parametrize(
    ("text", "sigla"),
    [
        ("Cat", "CAT"),
        ("CAT", "CAT"),
        ("cat", "CAT"),
        ("Catalana", "CAT"),
        ("Valenciana", "VAL"),
        ("Com.Valenciana", "VAL"),
        ("(Mad)", "MAD"),
        ("C-Le", "CLE"),
        ("Vasc", "VASC"),
    ],
)
def test_la_federacio_es_normalitza_a_sigles(text, sigla):
    assert normalitza_fed(text) == sigla


def test_una_federacio_desconeguda_no_es_endevina():
    assert normalitza_fed("Atlantida") is None


# ----------------------------------------------------------------------- files

_CAP_3B = llegeix_capcalera("# NOMBRE FED J G E P CAR. ENT. PROM. S.M. PTOS.")
_CAP_RONDA = llegeix_capcalera("# RONDA NOMBRE FED J G E P CAR. ENT. PROM. PTOS.")


def test_una_fila_amb_tots_els_numeros():
    f = llegeix_fila("1 Daniel Sánchez Gálvez Cat 5 5 0 0 200 89 2,247 23 180", _CAP_3B)
    assert (f.posicio, f.jugador, f.fed) == (1, "Daniel Sánchez Gálvez", "CAT")
    assert (f.jugades, f.guanyades, f.empatades, f.perdudes) == (5, 5, 0, 0)
    assert (f.caramboles, f.entrades, f.mitjana) == (200, 89, 2.247)
    assert (f.serie_major, f.punts) == (23, 180)


def test_un_numero_de_mes_a_la_fila_es_un_error():
    with pytest.raises(FormatDesconegut):
        llegeix_fila("1 Daniel Sánchez Gálvez Cat 5 5 0 0 200 89 2,247 23 180 7", _CAP_3B)


def test_un_numero_de_menys_a_la_fila_es_un_error():
    with pytest.raises(FormatDesconegut):
        llegeix_fila("1 Daniel Sánchez Gálvez Cat 5 5 0 200 89 2,247 23 180", _CAP_3B)


def test_una_federacio_desconeguda_fa_fallar_la_fila():
    with pytest.raises(FormatDesconegut, match="Federació desconeguda"):
        llegeix_fila("1 Daniel Sánchez Gálvez Xyz 5 5 0 0 200 89 2,247 23 180", _CAP_3B)


def test_el_nom_enganxat_a_la_federacio_es_separa():
    f = llegeix_fila("2 Rubén Fernández BermejoMad 5 3 0 2 178 168 1,060 7 120", _CAP_3B)
    assert (f.jugador, f.fed) == ("Rubén Fernández Bermejo", "MAD")


def test_el_numero_solt_abans_de_la_ronda_es_la_posicio_compartida():
    f = llegeix_fila("4 3 FF Xavier Yeste de Pablo CAT 8 7 0 1 283 178 1,590 155", _CAP_RONDA)
    assert (f.posicio, f.posicio_empat, f.ronda, f.jugador) == (4, 3, "FF", "Xavier Yeste de Pablo")


def test_qui_no_es_presenta_no_porta_numeros():
    f = llegeix_fila("125 Roberto Casado Bertschy MAD NO PRESENTADO 0", _CAP_RONDA)
    assert (f.jugador, f.fed, f.punts) == ("Roberto Casado Bertschy", "MAD", 0)
    assert f.caramboles is None
    assert f.jugades is None


def test_la_linia_escrita_dues_vegades_es_desdobla():
    f = llegeix_fila(
        "9944 XXaavviieerr DDííeezz AAyyzzaa CCaatt 11 00 00 11 1155 4488 00,,331133 33 2255",
        _CAP_3B,
    )
    assert (f.posicio, f.jugador, f.fed, f.caramboles, f.punts) == (
        94,
        "Xavier Díez Ayza",
        "CAT",
        15,
        25,
    )


# ----------------------------------------------------------------------- taula


def test_una_taula_s_acaba_a_la_primera_linia_sense_posicio():
    taula = llegeix_taula(
        [
            "CLASIFICACIÓN FINAL\n"
            "# NOMBRE FED CAR ENT PROM\n"
            "1 Raúl Cuenca Monrabal Val 1350 39 34,62\n"
            "2 Pere Lluma Vergara Cat 361 85 4,25\n"
            "Promedio General del Campeonato: 0,245\n"
            "3 Això ja no és de la taula Cat 1 1 1,00"
        ]
    )
    assert [f.jugador for f in taula.files] == ["Raúl Cuenca Monrabal", "Pere Lluma Vergara"]


def test_la_taula_continua_a_la_pagina_seguent_si_en_repeteix_la_capcalera():
    cap = "CLASIFICACIÓN FINAL\n# NOMBRE FED CAR ENT PROM\n"
    taula = llegeix_taula(
        [
            cap + "1 Raúl Cuenca Monrabal Val 1350 39 34,62",
            cap + "2 Pere Lluma Vergara Cat 361 85 4,25",
            "GRUPOS\n3 Aquesta pàgina ja és d'una altra taula Cat 1 1 1,00",
        ]
    )
    assert [f.posicio for f in taula.files] == [1, 2]


def test_una_fila_que_no_quadra_a_la_segona_pagina_fa_fallar_tot_el_fitxer():
    cap = "CLASIFICACIÓN FINAL\n# NOMBRE FED CAR ENT PROM\n"
    with pytest.raises(FormatDesconegut):
        llegeix_taula(
            [cap + "1 Raúl Cuenca Monrabal Val 1350 39 34,62", cap + "2 Pere Lluma Cat 361 85"]
        )


def test_el_pdf_sense_taula_es_diu_sense_taula():
    with pytest.raises(SenseTaula):
        llegeix_taula(["CLASIFICACIÓN FINAL\nNº SELECCIÓN CAR. ENT. PROM\n1 MADRID 599 478 1,253"])


def test_el_total_del_peu_no_es_una_fila():
    taula = llegeix_taula(
        [
            "CLASIFICACIÓN FINAL\n# NOMBRE FED CAR ENT PROM\n"
            "1 Raúl Cuenca Monrabal Val 1350 39 34,62\n"
            "6359 1670"
        ]
    )
    assert len(taula.files) == 1


# --------------------------------------------------- PDF reals, un per capçalera


def test_3b_amb_serie_major_i_punts_2015_2017():
    p = prova("noticias2016/res_gpe_3b_llinars")
    assert (p.modalitat, p.categoria, p.tipus, p.temporada) == ("3b", "absolut", "gpe", "2016-2017")
    assert p.font == "https://rfeb.org/noticias2016/res_gpe_3b_llinars.pdf"
    assert len(p.files) == 88
    primer = p.files[0]
    assert (primer.jugador, primer.fed, primer.caramboles, primer.entrades) == (
        "Ricardo García Alarcón",
        "CAT",
        200,
        157,
    )
    assert (primer.mitjana, primer.serie_major, primer.punts) == (1.274, 8, 180)
    # Dos jugadors empaten al tercer lloc: el segon porta «4 3».
    assert [(f.posicio, f.posicio_empat) for f in p.files if f.posicio_empat] == [(4, 3)]


def test_3b_amb_ronda_2018_2025():
    p = prova("noticias2019/res_ce_3b")
    assert (p.modalitat, p.categoria, p.tipus, p.temporada) == ("3b", "absolut", "ce", "2019-2020")
    assert len(p.files) == 127
    assert p.files[0].ronda == "FF"
    assert (p.files[0].caramboles, p.files[0].punts) == (200, 180)
    sense_jugar = [f for f in p.files if f.caramboles is None]
    assert sense_jugar
    assert all(f.fed for f in sense_jugar)
    assert {"FF", "Q"} <= {f.ronda for f in p.files}


def test_banda_amb_punts_i_dates_del_pdf():
    p = prova("noticias2016/res_ce_banda")
    assert (p.modalitat, p.categoria, p.tipus) == ("banda", "absolut", "ce")
    assert (p.lloc, p.data_inici, p.data_fi) == ("Paiporta (Valencia)", "2017-02-10", "2017-02-12")
    assert p.temporada == "2016-2017"
    assert len(p.files) == 28
    primer = p.files[0]
    assert (primer.jugador, primer.fed, primer.caramboles, primer.entrades) == (
        "Raúl Cuenca Monrabal",
        "VAL",
        675,
        97,
    )
    assert (primer.mitjana, primer.punts) == (6.96, 100)
    assert primer.jugades is None


def test_quadre_sense_punts():
    p = prova("noticias2015/res_ce_47-2")
    assert (p.modalitat, p.tipus, p.temporada) == ("47_2", "ce", "2015-2016")
    assert (p.lloc, p.data_inici) == ("Vic (Barcelona)", "2016-04-01")
    assert len(p.files) == 20
    assert p.files[0].punts is None
    assert p.files[0].mitjana == 34.62


def test_quadre_amb_la_columna_puntos():
    p = prova("noticias2018/res_ce_71-2")
    assert (p.modalitat, p.temporada) == ("71_2", "2018-2019")
    assert (p.files[0].caramboles, p.files[0].punts) == (700, 100)


def test_sub17_amb_la_federacio_escrita_sencera():
    p = prova("noticias2020/res_ce_3b_s17")
    assert (p.modalitat, p.categoria, p.tipus) == ("3b", "sub17", "ce")
    assert len(p.files) == 13
    assert (p.files[0].jugador, p.files[0].fed) == ("DANIEL SAINZ", "VAL")
    assert {f.fed for f in p.files} <= {"VAL", "MAD", "MUR", "CAT", "BAL", "ARAG", "AND"}


def test_femeni_sense_columna_de_nom_a_la_capcalera():
    p = prova("noticias2019/res_ce_3b_fem")
    assert (p.modalitat, p.categoria) == ("3b", "femeni")
    assert len(p.files) == 13
    assert p.files[0].jugador == "Estela Cardoso San Millán"
    # Una jugadora que no es va presentar: surt a la taula sense números.
    assert p.files[-1].caramboles is None


def test_sub21_amb_la_posicio_al_final_i_la_fase():
    p = prova("noticias2024/res_ce_3b_s21")
    assert (p.categoria, p.temporada) == ("sub21", "2024-2025")
    assert len(p.files) == 19
    assert (p.files[0].posicio, p.files[0].ronda, p.files[0].jugador) == (1, "F", "MARCOS MORALES")
    assert p.files[0].punts == 10
    assert [f.posicio for f in p.files] == sorted(f.posicio for f in p.files)


# ------------------------------------------------------------------ la càrrega


@pytest.fixture
def conn(tmp_path):
    c = ensure_schema(tmp_path / "rfeb.db")
    yield c
    c.close()


def _copia(arrel: Path, *ids: str, origen: str | None = None) -> None:
    for id_ in ids:
        desti = arrel / f"{id_}.pdf"
        desti.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ARREL / f"{origen or id_}.pdf", desti)


def _comptes(conn: sqlite3.Connection) -> tuple[int, int]:
    return (
        conn.execute("SELECT COUNT(*) FROM rfeb_proves").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM rfeb_classificacions").fetchone()[0],
    )


def test_carregar_dues_vegades_no_duplica_res(conn, tmp_path):
    _copia(tmp_path / "pdf", "noticias2016/res_ce_banda", "noticias2015/res_ce_47-2")
    res = carrega(conn, tmp_path / "pdf")
    assert [r.estat for r in res] == ["desat", "desat"]
    primer = _comptes(conn)
    assert primer == (2, 28 + 20)

    carrega(conn, tmp_path / "pdf")
    assert _comptes(conn) == primer
    # Les files tornen a ser úniques.
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM (SELECT 1 FROM rfeb_classificacions "
            "GROUP BY prova_id, posicio, jugador HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        == 0
    )


def test_tornar_a_carregar_reemplaca_les_files(conn, tmp_path):
    _copia(tmp_path / "pdf", "noticias2016/res_ce_banda")
    carrega(conn, tmp_path / "pdf")
    conn.execute("UPDATE rfeb_classificacions SET caramboles = 1 WHERE posicio = 1")
    conn.execute(
        "INSERT INTO rfeb_classificacions (prova_id, posicio, jugador) VALUES (?, 99, 'x')",
        ("noticias2016/res_ce_banda",),
    )
    carrega(conn, tmp_path / "pdf")
    assert (
        conn.execute("SELECT caramboles FROM rfeb_classificacions WHERE posicio = 1").fetchone()[0]
        == 675
    )
    assert _comptes(conn)[1] == 28


def test_la_mateixa_prova_a_dos_fitxers_es_desa_un_cop(conn, tmp_path):
    # El CE de Madrid del 2013 és a `noticias/` i a `noticias2013/` amb noms diferents.
    pdf = tmp_path / "pdf"
    _copia(pdf, "noticias/resultados_ce_banda", origen="noticias2016/res_ce_banda")
    _copia(pdf, "noticias2013/resultados_ce_banda_2013", origen="noticias2016/res_ce_banda")
    res = {r.fitxer: r for r in carrega(conn, pdf)}
    assert res["noticias/resultados_ce_banda"].estat == "desat"
    duplicat = res["noticias2013/resultados_ce_banda_2013"]
    assert duplicat.estat == "saltat"
    assert "duplicat" in duplicat.motiu
    assert duplicat.detall == "noticias/resultados_ce_banda"
    assert _comptes(conn) == (1, 28)


def test_dues_proves_diferents_de_la_mateixa_modalitat_no_son_duplicats(conn, tmp_path):
    pdf = tmp_path / "pdf"
    _copia(pdf, "noticias2016/res_ce_banda")
    _copia(pdf, "noticias2018/res_ce_71-2")
    _copia(pdf, "noticias2015/res_ce_47-2")
    carrega(conn, pdf)
    assert _comptes(conn)[0] == 3


def test_un_duplicat_desat_en_una_carrega_anterior_s_esborra(conn, tmp_path):
    pdf = tmp_path / "pdf"
    _copia(pdf, "noticias2013/resultados_ce_banda_2013", origen="noticias2016/res_ce_banda")
    carrega(conn, pdf)
    assert _comptes(conn)[0] == 1
    # Ara apareix l'altra còpia, que ordena abans: mana ella.
    _copia(pdf, "noticias/resultados_ce_banda", origen="noticias2016/res_ce_banda")
    carrega(conn, pdf)
    ids = [r[0] for r in conn.execute("SELECT id FROM rfeb_proves")]
    assert ids == ["noticias/resultados_ce_banda"]


def test_les_fases_parcials_no_es_carreguen_si_hi_ha_el_principal(conn, tmp_path):
    pdf = tmp_path / "pdf"
    _copia(pdf, "noticias2016/res_ce_banda")
    for sufix in ("fp", "ff"):
        (pdf / "noticias2016" / f"res_ce_banda_{sufix}.pdf").write_bytes(b"no cal ni obrir-lo")
    res = {r.fitxer: r for r in carrega(conn, pdf)}
    assert res["noticias2016/res_ce_banda_fp"].estat == "saltat"
    assert "parcial" in res["noticias2016/res_ce_banda_ff"].motiu
    assert _comptes(conn)[0] == 1


def test_una_fase_parcial_sense_principal_es_diu(conn, tmp_path):
    pdf = tmp_path / "pdf"
    (pdf / "noticias2018").mkdir(parents=True)
    (pdf / "noticias2018" / "res_3b_bilbao_ff.pdf").write_bytes(b"x")
    [r] = carrega(conn, pdf)
    assert r.estat == "saltat"
    assert "sense fitxer principal" in r.motiu
    assert _comptes(conn) == (0, 0)


def test_quadre_47_2_no_es_confon_amb_una_fase_parcial(conn, tmp_path):
    # `resultados_ce_47_2` acaba en «_2» però és el 47/2, no la ronda 2.
    pdf = tmp_path / "pdf"
    _copia(pdf, "noticias/resultados_ce_47_2", origen="noticias2015/res_ce_47-2")
    [r] = carrega(conn, pdf)
    assert r.estat == "desat"


def test_fora_d_abast_i_pdf_il_legible(conn, tmp_path):
    pdf = tmp_path / "pdf"
    (pdf / "noticias2019").mkdir(parents=True)
    (pdf / "noticias2019" / "res_ce_jds_ff.pdf").write_bytes(b"x")
    (pdf / "noticias2019" / "res_ce_3b_ssaa.pdf").write_bytes(b"x")
    (pdf / "noticias2019" / "res_ce_banda.pdf").write_bytes(b"no es un PDF")
    res = {r.fitxer: r for r in carrega(conn, pdf)}
    assert "equips" in res["noticias2019/res_ce_jds_ff"].motiu
    assert "seleccions" in res["noticias2019/res_ce_3b_ssaa"].motiu
    assert res["noticias2019/res_ce_banda"].estat == "error"
    assert "il·legible" in res["noticias2019/res_ce_banda"].motiu
    assert _comptes(conn) == (0, 0)


def test_cobertura_per_temporada_i_modalitat(conn, tmp_path):
    pdf = tmp_path / "pdf"
    _copia(pdf, "noticias2016/res_ce_banda", "noticias2015/res_ce_47-2", "noticias2018/res_ce_71-2")
    carrega(conn, pdf)
    assert cobertura(conn) == {
        "2015-2016": {"47_2": 1},
        "2016-2017": {"banda": 1},
        "2018-2019": {"71_2": 1},
    }


# ------------------------------------------------- dates que només diuen les fases

from datetime import date  # noqa: E402

from fcbillar.rfeb_individuals import (  # noqa: E402
    cerca_dates,
    data_amb_dia_de_la_setmana,
    dates_de_fases,
    es_fase_de,
    prova_de_pagines,
)

_TAULA_S17 = [
    "XXVII CAMPEONATO DE ESPAÑA SUB-17 DE\nBILLAR A TRES BANDAS\n"
    "CLASIFICACIÓN FINAL\n"
    "Clasif. Jugadores Federación T-Car. T.Entr. Pr.Gral. Ptos.\n"
    "1 SERGIO MARTÍNEZ Catalana 146 212 0,689 10\n"
    "2 LUIS MIRA Valenciana 146 201 0,726 8"
]


@pytest.mark.parametrize(
    "linia, esperat",
    [
        ("GRUPOS 19, 20 y 21 ENERO 2018", (date(2018, 1, 19), date(2018, 1, 21))),
        ("FASE FINAL 24-25-26 FEB.2017", (date(2017, 2, 24), date(2017, 2, 26))),
        ("GRUPOS FECHA: 04 al 06 Marzo 2016", (date(2016, 3, 4), date(2016, 3, 6))),
        ("GRUPOS 11 AL 14 DE JULIO 2019", (date(2019, 7, 11), date(2019, 7, 14))),
        ("GRUPOS 12 y 13 DICIEMBRE 2019", (date(2019, 12, 12), date(2019, 12, 13))),
    ],
)
def test_dates_de_les_capcaleres_de_fase(linia, esperat):
    assert dates_de_fases([linia], "2017-2018") == [esperat]


def test_una_linia_de_fase_no_es_la_data_del_campionat_sense_mirar_les_fases():
    # `cerca_dates` continua ignorant «GRUPOS»: una fase sola no és tot el campionat.
    assert cerca_dates(["GRUPOS 19, 20 y 21 ENERO 2018"]) is None
    # Un mes sense dia («DIC. 2022») no és una data.
    assert dates_de_fases(["DIC. 2022", "CLASIFICACIÓN DEL GRUPO FEB. 2022"], "2022-2023") == []


def test_el_dia_de_la_setmana_confirma_l_any_que_falta():
    assert data_amb_dia_de_la_setmana("SABADO 17 DE OCTUBRE", "2015-2016") == date(2015, 10, 17)
    assert data_amb_dia_de_la_setmana("DOMINGO 14 DE FEBRERO", "2015-2016") == date(2016, 2, 14)
    # El 17 d'octubre del 2016 no és dissabte: no s'endevina.
    assert data_amb_dia_de_la_setmana("SABADO 17 DE OCTUBRE", "2016-2017") is None


def test_les_dates_surten_de_les_fases_si_el_principal_no_en_diu_cap():
    p = prova_de_pagines(
        _TAULA_S17,
        "noticias2017",
        "res_ce_3b_s17",
        germanes=[["XXVII CAMPEONATO", "GRUPOS 19, 20 y 21 ENERO 2018", "GRUPO Partidos"]],
    )
    assert (p.data_inici, p.data_fi) == ("2018-01-19", "2018-01-21")
    assert p.temporada == "2017-2018"
    assert p.lloc is None


def test_les_dates_de_dues_fases_s_ajunten_de_la_primera_a_l_ultima():
    p = prova_de_pagines(
        _TAULA_S17,
        "noticias2016",
        "res_ce_3b_fem",
        germanes=[["GRUPOS 24-25-26 FEBRERO 2017"], ["FASE FINAL 26 y 27 FEB.2017"]],
    )
    assert (p.data_inici, p.data_fi) == ("2017-02-24", "2017-02-27")


def test_unes_dates_massa_separades_no_es_donen_per_bones():
    p = prova_de_pagines(
        _TAULA_S17,
        "noticias2017",
        "res_ce_3b_s17",
        germanes=[["GRUPOS 19, 20 y 21 ENERO 2018"], ["FASE FINAL 13-14-15 ABR.2018"]],
    )
    assert p.data_inici is None
    assert p.temporada == "2017-2018"


def test_nomes_les_fases_de_la_mateixa_prova_hi_compten():
    assert es_fase_de("res_ce_3b_s17", "res_ce_3b_s17_fp")
    assert es_fase_de("res_gpe_3b_llinars", "res_gpe_3b_llinars_prov")
    assert not es_fase_de("res_ce_3b", "res_ce_3b_s15")
    assert not es_fase_de("res_gpe_3b_madrid", "res_gpe_3b_madrid_fem")
