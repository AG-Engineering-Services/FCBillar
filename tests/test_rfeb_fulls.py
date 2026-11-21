"""Lector de les partides dels fulls de Google de la RFEB."""

from datetime import date

from fcbillar.rfeb_fulls import fase_de_pestanya, fitxer_pestanya, llegeix_actes, llegeix_parelles


def _f(*cels: str) -> list[str]:
    return list(cels)


def test_actes_play_off_dues_actes_per_fila_i_equip_de_cada_bloc():
    files = [
        _f("", "FECHA", "31/05/2025", "", "", "HORA", "10:00", "", "FECHA", "01/06/2025"),
        _f("", "EQUIPO", "", "PARC", "PARC", "", "", "", "EQUIPO", "", "PARC", "PARC"),
        _f("", "CHEF AMADEO GANDÍA", "", "6", "2", "", "", "", "C.B. VALLADOLID", "", "2", "6"),
        _f("", "NOMBRE", "", "", "", "", "", "", "NOMBRE"),
        _f(
            "1",
            "FRANCISCO GOMARIZ",
            "5",
            "31",
            "34",
            "40",
            "11",
            "JOSE A. CAMACHO",
            "1",
            "SALVADOR DIEZ",
            "6",
            "31",
            "28",
            "40",
            "10",
            "ANTONIO HERNANDEZ",
        ),
        # Els totals de l'encontre no són cap partida.
        _f("", "", "", "142", "", "170", "119"),
    ]
    a, b = llegeix_actes(files, "Grups")
    assert (a.jugador_a, a.caramboles_a, a.entrades, a.caramboles_b, a.jugador_b) == (
        "FRANCISCO GOMARIZ",
        31,
        34,
        40,
        "JOSE A. CAMACHO",
    )
    assert (a.serie_a, a.serie_b, a.punts_a, a.punts_b) == (5, 11, 0, 2)
    assert (a.equip_a, a.data) == ("CHEF AMADEO GANDÍA", date(2025, 5, 31))
    assert (b.equip_a, b.data, b.ordre) == ("C.B. VALLADOLID", date(2025, 6, 1), 2)


def test_actes_amb_els_dos_equips_a_la_capcalera_i_grup():
    files = [
        _f("12.00 HORAS GRUPO C"),
        _f("", "ANDALUCIA", "2", "6", "0", "2", "", "NAVARRA"),
        _f("", "JAIME S. FARACO", "5", "40", "33", "25", "4", "ALEJANDRO PEREZ", "1"),
    ]
    (p,) = llegeix_actes(files, "Grups")
    assert (p.equip_a, p.equip_b, p.punts_a) == ("ANDALUCIA", "NAVARRA", 2)


def test_actes_amb_mitjanes_i_modalitat():
    files = [
        _f("", "BANDA", "J. FELGUERA", "7", "2,240", "56", "25", "100", "4,000", "15", "R. ARNAU"),
        # Una mitjana que no quadra amb caramboles/entrades: no és una partida.
        _f("", "BANDA", "X. ALTRE", "7", "2,100", "56", "25", "100", "4,000", "15", "Y. ALTRE"),
    ]
    (p,) = llegeix_actes(files, "Divendres")
    assert (p.modalitat, p.caramboles_a, p.caramboles_b, p.entrades, p.serie_b) == (
        "banda",
        56,
        100,
        25,
        15,
    )


def test_parelles_del_grup_sota_la_classificacio_i_sense_les_no_jugades():
    files = [
        _f("", "1", "Martí López", "Cat", "4", "", "30", "51", "0,588", "3"),
        # La classificació té la mateixa forma: no s'ha de llegir.
        _f("", "2", "Sergio Marquina", "Cat", "2", "", "9", "51", "0,176", "1"),
        _f("RESULTADOS PARTIDOS DEL GRUPO"),
        _f("", "2", "Sergio Marquina", "", "2", "", "5", "30", "", "0,167", "", "1"),
        _f("", "3", "Sham Saeed", "", "0", "", "1", "30", "", "0,033", "", "1"),
        _f("", "2", "Javier Izquierdo", "", "2"),
        _f("", "3", "Agustín Ferrán", "", "0"),
        _f("", "1", "Martí López", "", "2", "", "15", "21", "", "0,714", "", "3"),
        # La segona fila no repeteix les entrades.
        _f("", "4", "Sergio Marquina", "", "0", "", "4", "", "", "0,190", "", "1"),
    ]
    a, b = llegeix_parelles(files, "Grups", "A")
    assert (a.jugador_a, a.caramboles_a, a.punts_a, a.jugador_b, a.caramboles_b) == (
        "Sergio Marquina",
        5,
        2,
        "Sham Saeed",
        1,
    )
    assert (b.jugador_a, b.entrades, b.caramboles_b, b.serie_a, b.grup) == (
        "Martí López",
        21,
        4,
        3,
        "A",
    )


def test_parelles_amb_la_fase_a_la_fila_i_els_punts_darrere():
    files = [
        _f("Clasif.", "Jugadores", "Federación", "", "CAR", "ENT", "PRO", "SM", "Ptos", "GAN"),
        _f(
            "", "Jesús García Andujar", "", "", "15", "28", "0,536", "2", "0", "0", "0", "1", "PPPQ"
        ),
        _f(
            "",
            "Alejandro Pérez Andreu",
            "",
            "",
            "30",
            "28",
            "1,071",
            "6",
            "2",
            "1",
            "0",
            "0",
            "PPPQ",
        ),
        _f("SEMI", "#N/A", "#N/A", "", "", "", "", "", "0", "0", "0", "1"),
    ]
    (p,) = llegeix_parelles(files, "Acumulado Partidos")
    assert (p.fase, p.punts_a, p.punts_b, p.serie_b) == ("PPPQ", 0, 2, 6)


def test_pestanyes():
    assert fase_de_pestanya("GRUPO B") == ("Grups", "B")
    assert fase_de_pestanya("ACTAS FASE FINAL") == ("Fase final", "")
    assert fitxer_pestanya("PARTIDOS SÁBADO") == "PARTIDOS_SABADO.csv"
