"""Lector de les partides dels PDF de fases de la web vella de la RFEB."""

from pathlib import Path

from fcbillar.rfeb_fases_pdf import _jocs_de_serie, _parelles, prova_i_fase


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
