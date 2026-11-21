"""Lector de les partides dels PDF de fases de la web vella de la RFEB."""

from pathlib import Path

from fcbillar.rfeb_fases_pdf import (
    _costat_per_costat,
    _fila_per_jugador,
    _jocs_de_serie,
    _parelles,
    prova_i_fase,
)


def test_parelles_amb_les_entrades_a_la_linia():
    linies = [
        "CAR ENT PROM S.M.",
        "65 RUBÉN FERNÁNDEZ BERMEJO MAD 40 0,889 3",
        "16 JOSEBA ESCRIBANO BLANCO VASC 37 0,822 4",
    ]
    (p,), fora = _parelles(linies, "Fase final")
    assert fora == 0
    assert (p.jugador_a, p.caramboles_a, p.entrades, p.caramboles_b, p.serie_b) == (
        "RUBÉN FERNÁNDEZ BERMEJO",
        40,
        45,
        37,
        4,
    )
    assert (p.equip_a, p.equip_b, p.punts_a) == ("MAD", "VASC", 2)


def test_parelles_amb_els_numeros_en_linies_soltes():
    # 2013: la segona fila no porta les caramboles; van, amb les entrades, sols.
    linies = [
        "CAR PROM S.M.",
        "6 33 XAVIER YESTE DE PABLO CAT 40 ENT 1,290 8",
        "31",
        "35",
        "16 CARLOS CRESPO ALCALÁ BAL 1,129 8",
    ]
    (p,), _ = _parelles(linies, "Fase final")
    assert (p.caramboles_a, p.entrades, p.caramboles_b) == (40, 31, 35)


def test_un_bloc_amb_una_linia_de_menys_no_aparella_res():
    linies = [
        "CAR ENT PROM S.M.",
        "65 RUBÉN FERNÁNDEZ BERMEJO MAD 40 0,889 3",
        "16 JOSEBA ESCRIBANO BLANCO VASC 37 0,822 4",
        "19 JOSÉ M. GÓMEZ BRAVO VAL 32 0,727 3",
    ]
    assert _parelles(linies, "Fase final") == ([], 1)


def test_jocs_de_serie():
    (p,) = _jocs_de_serie(
        ["BANDA Antonio Gutiérrez Castro 100 94 Armando Moreno Cortés en 19"], "Fase final"
    )
    assert (p.modalitat, p.caramboles_a, p.caramboles_b, p.entrades) == ("banda", 100, 94, 19)


def test_prova_i_fase():
    assert prova_i_fase(Path("noticias2017/res_ce_3b_ff.pdf")) == (
        "noticias2017/res_ce_3b",
        "Fase final",
    )
    assert prova_i_fase(Path("noticias2019/res_ce_jds_fp_vic.pdf")) == (
        "noticias2019/res_ce_jds",
        "Fase prèvia",
    )
    assert prova_i_fase(Path("noticias2017/res_ce_3b.pdf")) is None


def test_dues_partides_costat_per_costat_amb_les_entrades_al_mig():
    # Final de banda 2014 (noticias2013/res_ce_banda_ff.pdf).
    linies = [
        "CUARTOS DE FINAL",
        "CAR ENT PROM SM CAR ENT PROM SM",
        "Raul Cuenca 120 10,00 32 Joan Espinasa 125 6,25 19",
        "12 20",
        "Jordi Garriga 125 10,42 27 Carmelo Garcés 54 2,70 26",
        "NOMBRE FED CAR ENT PROM PTOS Carmelo Garcés 65 13,00 38",
    ]
    partides, descartats = _costat_per_costat(linies, "Fase final")
    assert descartats == 0
    assert [
        (p.jugador_a, p.caramboles_a, p.jugador_b, p.caramboles_b, p.entrades) for p in partides
    ] == [
        ("Raul Cuenca", 120, "Jordi Garriga", 125, 12),
        ("Joan Espinasa", 125, "Carmelo Garcés", 54, 20),
    ]
    assert (partides[0].punts_a, partides[0].punts_b) == (0, 2)


def test_una_fila_per_jugador_amb_l_arbitre_entremig():
    # Quadre 47/2 2015-16 (noticias2015/res_ce_47-2_ff.pdf).
    linies = [
        "ESTEVE MATA 250 4 62,500 199 2 1",
        "9:00 1 PERE LLUMÀ",
        "MIQUEL PLANDOLIT 8 4 2,000 3 0 1",
    ]
    (p,), _ = _fila_per_jugador(linies, "Fase final")
    assert (p.jugador_a, p.caramboles_a, p.serie_a, p.jugador_b, p.caramboles_b, p.entrades) == (
        "Esteve Mata",
        250,
        199,
        "Miquel Plandolit",
        8,
        4,
    )


def test_dues_partides_per_linia_amb_la_federacio():
    # Quadre 47/2 2012-13 (noticias/resultados_ce_47_2_ff.pdf).
    linies = [
        "JUGADOR Caramb. Entr. Prom. SM Puntos JUGADOR Caramb. Entr. Prom. SM Puntos",
        "Esteve Mata Cat 250 7 35,714 125 2 J. Albert Tornero Val 250 14 17,857 105 2",
        "Jordi Garriga Cat 14 7 2 10 0 Joan Espinasa Cat 238 14 17 57 0",
    ]
    partides, _ = _fila_per_jugador(linies, "Fase final")
    assert [
        (p.jugador_a, p.equip_a, p.caramboles_a, p.caramboles_b, p.jugador_b, p.entrades)
        for p in partides
    ] == [
        ("Esteve Mata", "CAT", 250, 14, "Jordi Garriga", 7),
        ("J. Albert Tornero", "VAL", 250, 238, "Joan Espinasa", 14),
    ]


def test_fila_amb_els_punts_davant_i_la_classificacio_al_costat():
    # Tres bandes sub-17 2014-15 (noticias2014/res_ce_3b_s17_fp.pdf).
    linies = [
        "2 DAVID FIOL CAT 2 18 50 0,360 3",
        "Jugadores Fed Ptos Car Ent P.Gral SM Clas 3 JOSE R. PASCUAL VAL 0 9 50 0,180 1",
        "1 MARIO MERCADER MUR 4 59 88 0,670 5 1º 1 MARIO MERCADER MUR 2 29 50 0,580 3",
        "2 DAVID FIOL CAT 2 33 88 0,375 4 2º 3 JOSE R. PASCUAL VAL 0 16 50 0,320 2",
    ]
    partides, _ = _fila_per_jugador(linies, "Fase prèvia")
    assert [
        (p.jugador_a, p.caramboles_a, p.caramboles_b, p.jugador_b, p.entrades) for p in partides
    ] == [
        ("David Fiol", 18, 9, "Jose R. Pascual", 50),
        ("Mario Mercader", 29, 16, "Jose R. Pascual", 50),
    ]
