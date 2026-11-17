"""Lectors de la CEB, la UMB i la RFEB, el desat a `ext_*` i els candidats a fitxa."""

from datetime import date
from pathlib import Path

import pytest

from fcbillar.db.migrations import ensure_schema
from fcbillar.externes import ceb, rfeb, umb
from fcbillar.externes.desat import desa
from fcbillar.externes.fitxes import JugadorExtern, nom_de_pila_primer, proposa
from fcbillar.externes.model import Esdeveniment, modalitat_de, tipus_de
from fcbillar.nacional_fitxes import JugadorCens

FIXTURES = Path(__file__).parent / "fixtures"


# --- model ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "modalitat"),
    [
        ("3-Cushion", "3B"),
        ("World Championship One Cushion CERVERA", "BANDA"),
        ("Free Game", "LLIURE"),
        ("Cadre 47/2", "47/2"),
        ("Balkline 71/2", "71/2"),
        ("Cadre 47/1", "47/1"),
        ("BILLAR A TRES BANDAS", "3B"),
        ("Artistic", None),
        ("5 Pins", None),
    ],
)
def test_modalitat(text, modalitat):
    assert modalitat_de(text) == modalitat


def test_tipus_nomes_mundials_europeus_i_copes():
    assert tipus_de("World Cup 3-Cushion PORTO") == "copa_mon"
    assert tipus_de("World Championship Ladies 3-Cushion") == "mundial"
    assert tipus_de("European Championship 3-Cushion U25") == "europeu"
    assert tipus_de("PREDATOR Grand Prix 3-Cushion Ladies") is None
    assert tipus_de("Coupe d'Europe 3-Cushion - Qualification") is None


def test_temporada_canvia_l_u_d_agost():
    e = Esdeveniment("umb", "1", "x", "3B", "internacional", "mundial", date(2025, 7, 31))
    assert e.temporada == "2024-2025"
    e = Esdeveniment("umb", "1", "x", "3B", "internacional", "mundial", date(2025, 8, 1))
    assert e.temporada == "2025-2026"


# --- CEB ------------------------------------------------------------------------


def _ceb():
    return ceb.llegeix_esdeveniment(
        (FIXTURES / "ceb_event_559.html").read_text(encoding="utf-8"), 559
    )


def test_ceb_esdeveniment():
    e = _ceb().esdeveniment
    assert (e.nom, e.modalitat, e.tipus) == ("European Championship 3-Cushion U25", "3B", "europeu")
    assert (e.data_inici, e.data_fi) == (date(2026, 10, 16), date(2026, 10, 18))
    assert e.temporada == "2026-2027"


def test_ceb_totes_les_partides_de_grups_a_final():
    partides = _ceb().partides
    assert len(partides) == 39
    assert [p.fase for p in partides].count("Qualifications") == 24
    final = partides[-1]
    assert (final.fase, final.jugador1, final.jugador2) == ("Final", "KRISTIANSEN Daniel", "IBRAIMOV Amir")
    assert (final.caramboles1, final.caramboles2, final.entrades1) == (27, 40, 24)
    assert (final.serie1, final.serie2, final.punts1, final.punts2) == (8, 5, 0, 2)


def test_ceb_pais_de_la_llista_de_jugadors():
    primera = _ceb().partides[0]
    assert (primera.jugador1, primera.nacio1, primera.nacio2) == ("BOLLANSEE Toon", "BEL", "PRT")


def test_ceb_sense_disciplina_de_carambola():
    with pytest.raises(ceb.SensePartides):
        ceb.llegeix_esdeveniment(
            '<title>European Championship Artistic</title><div class="field col-xs">Discipline</div>'
            '<div class="value col-xs">Artistic</div>',
            1,
        )


# --- UMB ------------------------------------------------------------------------

GRUPS_PROGRAMA_NOU = """PORTO WORLD CUP 2025 (PT)
29 June - 05 July 2025
Pre-Pre-Pre-Qual Groups
Group MatchPlayers T-Car T-Inn Avg MP 1stHR 2ndHR
BLAUWBLOMMEHenk 30 53 0.566 2 3 2
ESCUDEIROJose 18 53 0.339 0 2 2
A LALANNEPatrice 21 54 0.388 0 3 2
ESCUDEIROJose 30 54 0.555 2 5 2
LALANNEPatrice 19 45 0.422 0 3 2
BLAUWBLOMMEHenk 30 45 0.666 2 3 2
Players Nat T-Car T-Inn G.Avg MP 1stHR 2ndHR Place
BLAUWBLOMMEHenk BE 60 98 0.612 4 3 3 1
ESCUDEIROJose PT 48 107 0.448 2 5 2 2
LALANNEPatrice FR 40 99 0.404 0 3 3 3
"""

ELIMINATORIES_PROGRAMA_NOU = """PORTO WORLD CUP 2025 (PT)
Main Tournament - Semi_Final
MatchPlayers Nat T-Car T-Inn Penality Avg MP HR
CHOMyungWoo KR 50 22 0 2.272 2 9
SALMANGokhan TR 24 21 0 1.142 0 7
Main Tournament - Final
MatchPlayers Nat T-Car T-Inn Penality Avg MP HR
CHOMyungWoo KR 50 23 0 2.173 2 8
BURYJeremy FR 34 23 0 1.478 0 6
"""

#: 2008: tres sets, i el total al final.
GRUPS_AMB_SETS = """SLUISKIL WORLD CUP / GRAND PRIX
Group Match players S1-Car S1-Inn S2-Car S2-Inn S3-Car S3-Inn T-car T-Inn Av MP Sets HR
A MANCINI Giorgio 15 14 15 7 30 21 1,428 2 2 6
BLAUWBLOMME Henk 8 13 10 7 18 20 0,900 0 -2 7
Players Nat T-Car T-Inn Gen-Av MP Ba-Sets HR Place
MANCINI Giorgio IT 66 57 1,157 2 1 6 1
BLAUWBLOMME Henk BE 48 52 0,923 2 0 7 2
"""

#: 2013: penalització i caramboles repetides.
ELIMINATORIES_2013 = """Match players Nat T-Car T-Inn Penalty T-car T-Inn Av MP HR
ZANETTI Marco IT 40 31 40 31 1,290 2 6
GARZON Cesar CO 33 31 S5-Inn 33 31 1,064 0 5
"""


def test_umb_grups_nom_enganxat_i_pais_del_resum():
    partides = umb.llegeix_text(GRUPS_PROGRAMA_NOU, "PPPQ")
    assert len(partides) == 3
    p = partides[0]
    assert (p.jugador1, p.nacio1, p.caramboles1, p.entrades1, p.serie1, p.punts1) == (
        "BLAUWBLOMME Henk",
        "BE",
        30,
        53,
        3,
        2,
    )
    assert (p.jugador2, p.nacio2, p.caramboles2) == ("ESCUDEIRO Jose", "PT", 18)
    # La lletra del grup surt a la tercera línia però val per a tot el grup.
    assert {x.grup for x in partides} == {"A"}


def test_umb_semifinal_i_final_al_mateix_pdf():
    partides = umb.llegeix_text(ELIMINATORIES_PROGRAMA_NOU, "Semi Final Final")
    assert [(p.fase, p.jugador1, p.jugador2) for p in partides] == [
        ("Semi Final", "CHO MyungWoo", "SALMAN Gokhan"),
        ("Final", "CHO MyungWoo", "BURY Jeremy"),
    ]
    assert (partides[1].caramboles1, partides[1].entrades1, partides[1].serie1) == (50, 23, 8)


def test_umb_sets_el_total_es_el_que_dona_la_mitjana():
    p = umb.llegeix_text(GRUPS_AMB_SETS, "Q")[0]
    assert (p.caramboles1, p.entrades1, p.serie1, p.punts1) == (30, 21, 6, 2)
    assert (p.caramboles2, p.entrades2, p.serie2) == (18, 20, 7)
    assert (p.nacio1, p.nacio2) == ("IT", "BE")


def test_umb_penalitzacio_que_no_es_un_nombre():
    [p] = umb.llegeix_text(ELIMINATORIES_2013, "1/16")
    assert (p.jugador1, p.caramboles1, p.entrades1, p.punts1) == ("ZANETTI Marco", 40, 31, 2)
    assert (p.jugador2, p.caramboles2, p.entrades2, p.serie2) == ("GARZON Cesar", 33, 31, 5)


def test_umb_linia_solta_no_desaparella_les_seguents():
    text = ELIMINATORIES_2013.replace(
        "ZANETTI", "SOLT Jugador XX 12 50 12 50 0,240 0 2\nZANETTI"
    )
    [p] = umb.llegeix_text(text, "1/16")
    assert (p.jugador1, p.jugador2) == ("ZANETTI Marco", "GARZON Cesar")


def test_umb_quins_pdf_porten_partides():
    pagina = " ".join(
        f'href="https://files.umb-carom.org/Uploads/Results/320/{n}"'
        for n in [
            "A. Players List.pdf",
            "B. Groups.pdf",
            "C. Time Table.pdf",
            "J. GroupResults_Q.pdf",
            "K. Groups_Ranking_Q.pdf",
            "O. MTResults_Rank_8.pdf",
            "V. FinalRanking.pdf",
        ]
    )
    assert umb.fitxers_de_resultats(pagina) == ["J. GroupResults_Q.pdf", "O. MTResults_Rank_8.pdf"]
    pagina_2013 = 'href="Uploads/Results/50/J. Q-Groups_PDF.pdf" href="Uploads/Results/50/K. Q-Rank_PDF.pdf" href="Uploads/Results/50/L. MT 1_16.pdf"'
    assert umb.fitxers_de_resultats(pagina_2013) == ["J. Q-Groups_PDF.pdf", "L. MT 1_16.pdf"]


def test_umb_fase_del_fitxer():
    assert umb.fase_del_fitxer("J. GroupResults_Q.pdf") == "Q"
    assert umb.fase_del_fitxer("D. PPPQ-Groups_PDF.pdf") == "PPPQ"
    assert umb.fase_del_fitxer("M. MT 1_8.pdf") == "1/8"


# --- RFEB -----------------------------------------------------------------------

CE_3B = """XCI CAMPEONATO DE ESPAÑA
DE BILLAR A TRES BANDAS
CARTAGENA, DEL 18 AL 26 DE ENERO DE 2025
CLASIFICACIÓN FINAL
# RONDA NOMBRE FED J G E P CAR. ENT. PROM. PTOS.
1 FF Carlos Anguita Díaz MUR 5 4 1 0 200 139 1,439 180
4 3 FF Marcos Morales Otero MAD 4 3 0 1 145 122 1,189 155
53 PQ-2º Per Kofoed AND 10 8 1 1 232 284 0,817 58
"""

CE_47_2 = """LXXV CAMPEONATO DE ESPAÑA
CUADRO 47/2
ALMUSSAFES (VALENCIA), DEL 17 AL 19 DE ABRIL DE 2015
CLASIFICACIÓN FINAL
NOMBRE FED CAR ENT PROM
1 Raúl Cuenca Monrabal Val 1272 41 31,02
30 Armando Moreno Cortés Cat NO PRESENTADO 0
"""

#: Sense línia de lloc i dates (era una imatge) i amb sèrie major.
CE_3B_2017 = """CLASIFICACIÓN FINAL
# NOMBRE FED J G E P CAR. ENT. PROM. S.M. PTOS.
1 Rubén Legazpi Martín Mad 5 5 0 0 200 114 1,754 11 180
"""


def test_rfeb_3b_amb_partides_guanyades_i_perdudes():
    r = rfeb.llegeix_classificacio(CE_3B, "noticias2024/res_ce_3b", "res_ce_3b.pdf")
    e = r.esdeveniment
    assert (e.modalitat, e.tipus, e.ambit, e.data_inici) == (
        "3B",
        "campionat_espanya",
        "espanya",
        date(2025, 1, 18),
    )
    assert e.temporada == "2024-2025"
    assert [t.jugador for t in r.totals] == ["Carlos Anguita Díaz", "Marcos Morales Otero", "Per Kofoed"]
    t = r.totals[0]
    assert (t.federacio, t.jugades, t.guanyades, t.empatades, t.perdudes) == ("MUR", 5, 4, 1, 0)
    assert (t.caramboles, t.entrades, t.serie) == (200, 139, None)


def test_rfeb_quadre_nomes_caramboles_i_entrades():
    r = rfeb.llegeix_classificacio(CE_47_2, "noticias2014/res_ce_c47-2", "res_ce_c47-2.pdf")
    assert r.esdeveniment.modalitat == "47/2"
    assert len(r.totals) == 1  # el no presentat no hi és
    t = r.totals[0]
    assert (t.jugador, t.caramboles, t.entrades, t.jugades) == ("Raúl Cuenca Monrabal", 1272, 41, None)


def test_rfeb_sense_dates_la_temporada_es_la_de_la_carpeta():
    r = rfeb.llegeix_classificacio(
        CE_3B_2017, "noticias2017/res_ce_3b", "res_ce_3b.pdf", temporada="2017-2018"
    )
    assert r.esdeveniment.data_inici is None
    assert r.esdeveniment.temporada == "2017-2018"
    assert r.totals[0].serie == 11


def test_rfeb_quins_fitxers_son_classificacio_final():
    assert rfeb.es_classificacio_final("res_ce_3b.pdf")
    assert rfeb.es_classificacio_final("res_ce_3b_s21.pdf")
    assert rfeb.es_classificacio_final("res_gpe_3b_palma.pdf")
    assert not rfeb.es_classificacio_final("res_ce_3b_ff.pdf")
    assert not rfeb.es_classificacio_final("res_gpe_3b_llinars_r16.pdf")
    assert not rfeb.es_classificacio_final("des_ce_3b.pdf")
    assert rfeb.descriu_fitxer("res_ce_3b_s21.pdf") == ("3B", "sub-21", "campionat_espanya")


# --- desat ----------------------------------------------------------------------


def test_desar_dues_vegades_no_duplica(tmp_path):
    conn = ensure_schema(tmp_path / "t.db")
    resultat = _ceb()
    desa(conn, resultat)
    desa(conn, resultat)
    assert conn.execute("SELECT COUNT(*) FROM ext_partides").fetchone()[0] == 39
    assert conn.execute("SELECT COUNT(*) FROM ext_esdeveniments").fetchone()[0] == 1
    r = rfeb.llegeix_classificacio(CE_3B, "noticias2024/res_ce_3b", "res_ce_3b.pdf")
    desa(conn, r)
    desa(conn, r)
    assert conn.execute("SELECT COUNT(*) FROM ext_totals").fetchone()[0] == 3


# --- candidats a fitxa ----------------------------------------------------------


def test_nom_de_pila_primer():
    assert nom_de_pila_primer("JIMENEZ Sergio") == "Sergio JIMENEZ"
    assert nom_de_pila_primer("MAS CANADELL José Mª") == "José Mª MAS CANADELL"


def test_candidats_nomes_espanyols_i_inequivocs():
    cens = [
        JugadorCens("1", "JIMÉNEZ GALERA, SERGIO", "C.B. X"),
        JugadorCens("2", "MAS CANADELL, JOSEP Mª", "C.B. Y"),
    ]
    trobats = proposa(
        [
            JugadorExtern("umb", "JIMENEZ Sergio", "ES"),
            JugadorExtern("ceb", "JIMENEZ Sergio", "MEX"),
            JugadorExtern("rfeb", "José Mª Mas Canadell", "EXT"),
        ],
        cens,
    )
    assert [(j.font, c.fcb_id) for j, c, _ in trobats] == [("umb", "1"), ("rfeb", "2")]
