from __future__ import annotations

from fcbillar import rfeb_antiga_partides as A


def test_dues_columnes_s_aparellen_per_separat():
    """Gijón 2008: dues partides per línia, cada columna és una ronda."""
    linies = [
        "Gijón , 7 a 13 de Julio 2008",
        "128 Ramón Antuña Ast 6 50 0,120 1 112 José Vila Soriano Cant 30 50 0,600 4",
        "136 Juan Secades Ast 36 50 0,720 4 Juan Secades Ast 38 50 0,760 6",
    ]
    partides, descartats = A.llegeix_jugadors(linies, "Fase prèvia")
    assert descartats == 0
    assert [
        (p.jugador_a, p.caramboles_a, p.caramboles_b, p.jugador_b, p.entrades) for p in partides
    ] == [
        ("Ramón Antuña", 6, 36, "Juan Secades", 50),
        ("José Vila Soriano", 30, 38, "Juan Secades", 50),
    ]


def test_ordinal_davant_i_entrades_que_han_de_quadrar():
    linies = [
        "OCTAVOS",
        "8º Francisco Unguetti Val 31 36 0,861 5",
        "9º José Mª Mas Cat 50 36 1,389 9",
        "1º Daniel Sánchez And 50 35 1,429 5",
        "16º Antonio Torres Sánchez Bal 32 35 0,914 7",
    ]
    partides, descartats = A.llegeix_jugadors(linies, "Fase final")
    assert descartats == 0
    assert [(p.jugador_a, p.equip_a, p.jugador_b, p.serie_b, p.punts_a) for p in partides] == [
        ("Francisco Unguetti", "Val", "José Mª Mas", 9, 0),
        ("Daniel Sánchez", "And", "Antonio Torres Sánchez", 7, 2),
    ]


def test_sense_entrades_les_treu_de_la_mitjana_i_aguanta_el_soroll_del_marge():
    """Campionat d'Espanya del 2010: la mitjana amb quatre decimals i lletres girades al marge."""
    linies = [
        "149 JOSÉ-JAVIER SÁEZ MUR 23 0,4600 5",
        "1 50",
        "144 GIOVANNI CANO SALINAS MUR 25 0,5000 4",
        "S R E O 147 JOAQUÍN TODO SERRA VAL 35 0,7000 4",
        "N H 4 50",
        "U 142 FERNANDO GARCÍA CAT 24 0,4800 3",
        "22 JOSÉ G. MONUERA VAL 40 P 0,9091 5",
        "11 JORGE CANTÓ ORTEGA VAL 40 G 0,9091 10",
    ]
    partides, descartats = A.llegeix_jugadors(linies, "Fase prèvia")
    assert descartats == 0
    assert [(p.jugador_a, p.jugador_b, p.entrades) for p in partides] == [
        ("José-Javier Sáez", "Giovanni Cano Salinas", 50),
        ("Joaquín Todo Serra", "Fernando García", 50),
        ("José G. Monuera", "Jorge Cantó Ortega", 44),
    ]


def test_linia_partida_en_tres_i_federacio_amb_guio():
    linies = [
        "135 ANTONIO-LUÍS GRAU MUR 24",
        "50",
        "0,4800 3",
        "O 90 JOSÉ FERNÁNDEZ C-LE 34 0,6800 5",
    ]
    partides, descartats = A.llegeix_jugadors(linies, "Fase prèvia")
    assert descartats == 0
    assert [(p.jugador_a, p.jugador_b, p.equip_b, p.entrades) for p in partides] == [
        ("Antonio-Luís Grau", "José Fernández", "C-LE", 50)
    ]


def test_entrades_que_no_quadren_no_s_aparellen():
    linies = [
        "1 PERE PUIG CAT 40 1,0000 5",  # 40 entrades
        "2 JOAN SERRA CAT 20 0,4000 3",  # 50 entrades: no és la seva partida
        "3 PAU VIDAL CAT 30 0,6000 4",  # 50 entrades
    ]
    partides, descartats = A.llegeix_jugadors(linies, "Fase prèvia")
    assert [(p.jugador_a, p.jugador_b) for p in partides] == [("Joan Serra", "Pau Vidal")]
    assert descartats == 1


def test_seleccions_amb_capcalera_selecc():
    linies = [
        "Selecciones del grupo B",
        "Selecc: CATALANA 8 0 EXTREMEÑA",
        "Jug 2 Car Car 0 Ent",
        "1 Sergio Jiménez 40 20 César Grillo en 37",
        "2 Gabriel Liébana 39 25 Javier Prieto en 50",
        "0,888 158 105 0,590 178",
    ]
    partides, descartats = A.llegeix_seleccions(linies, "Fase de grups", "B")
    assert descartats == 0
    assert [
        (
            p.jugador_a,
            p.equip_a,
            p.caramboles_a,
            p.caramboles_b,
            p.jugador_b,
            p.equip_b,
            p.entrades,
            p.grup,
        )
        for p in partides
    ] == [
        ("Sergio Jiménez", "CATALANA", 40, 20, "César Grillo", "EXTREMEÑA", 37, "B"),
        ("Gabriel Liébana", "CATALANA", 39, 25, "Javier Prieto", "EXTREMEÑA", 50, "B"),
    ]


def test_seleccions_dues_columnes_i_noms_de_dues_paraules():
    linies = [
        "1 VALENCIANA",
        "2 ANDALUZA",
        "3 CASTILLA LEÓN",
        "4 PAÍS VASCO",
        "VALENCIANA 8 0 PAÍS VASCO ANDALUZA 6 2 CASTILLA LEÓN",
        "Jug 2 Car Car 0 Ent Jug 2 Car Car 0 Ent",
        "1 Antonio Ortiz 40 29 Joseba Escribano en 39 1 Manuel González 40 25 Valentín Andaluz B. en 36",
    ]
    partides, descartats = A.llegeix_seleccions(linies, "Fase de grups", "B")
    assert descartats == 0
    assert [(p.equip_a, p.jugador_a, p.jugador_b, p.equip_b) for p in partides] == [
        ("VALENCIANA", "Antonio Ortiz", "Joseba Escribano", "PAÍS VASCO"),
        ("ANDALUZA", "Manuel González", "Valentín Andaluz B.", "CASTILLA LEÓN"),
    ]


def test_seleccions_capcalera_que_no_es_pot_partir_no_s_endevina():
    linies = [
        "NORD 8 0 SUD EST MOLT LLUNY 6 2 OEST",
        "1 Pere Puig 40 29 Joan Serra en 39 1 Pau Vidal 40 25 Jordi Pla en 36",
    ]
    partides, descartats = A.llegeix_seleccions(linies, "Fase de grups")
    assert partides == []
    assert descartats == 3
