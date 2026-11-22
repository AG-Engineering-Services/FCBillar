"""El palmarès: lectura dels dos formats i desat a la BBDD local."""

from __future__ import annotations

import sqlite3

from fcbillar import palmares as P
from fcbillar.nacional_fitxes import Candidat, JugadorCens, JugadorRfeb

CAP = [
    ["EDICIÓN", "FECHA", None, "LUGAR", None, "Nº JUG.", "ORO", "PROM.", "PLATA", "PROM.", "BRONCE", "PROM."],
    [None, "AÑO", "MES", "SEDE", "CIUDAD", None, None, None, None, None, None, None],
]  # fmt: skip


def _fila(roman, any_, mes, sede, ciutat, n, oro="", m1="", plata="", m2="", bronze="", m3=""):
    return [roman, any_, mes, sede, ciutat, n, oro, m1, plata, m2, bronze, m3]


def _continuacio(bronze, m3=""):
    return [None] * 10 + [bronze, m3]


# ---------------------------------------------------------------------------
# RFEB
# ---------------------------------------------------------------------------


def test_rfeb_una_edicio_amb_els_tres_llocs_i_les_mitjanes():
    taula = [*CAP, 
        _fila(
            "VIII", "1940", "", "C.B. Colón", "Valencia", "4",
            "Joaquín Domingo", "0,501", "Claudio Puigvert", "0,539", "Antonio Cuscó", "0,409",
        ),
    ]  # fmt: skip
    inf = P.llegeix_taules_rfeb([[taula]], "Tres bandes", "absolut", "x.pdf")
    assert inf.edicions == 1
    assert inf.no_llegit == []
    assert [(m.posicio, m.jugador, m.mitjana) for m in inf.medalles] == [
        (1, "Joaquín Domingo", 0.501),
        (2, "Claudio Puigvert", 0.539),
        (3, "Antonio Cuscó", 0.409),
    ]
    m = inf.medalles[0]
    assert (m.font, m.edicio, m.any_edicio, m.lloc, m.pais) == (
        "rfeb",
        "VIII",
        1940,
        "C.B. Colón, Valencia",
        None,
    )


def test_rfeb_les_edicions_antigues_porten_nomes_el_campio():
    taula = [*CAP, _fila("I", "1929", "", "", "Barcelona", "", "Claudio Puigvert")]
    inf = P.llegeix_taules_rfeb([[taula]], "Tres bandes", "absolut")
    assert [(m.posicio, m.jugador, m.mitjana) for m in inf.medalles] == [
        (1, "Claudio Puigvert", None)
    ]


def test_rfeb_una_fila_sense_cel_la_es_un_segon_tercer():
    taula = [*CAP, 
        _fila("I", "2001", "Abril", "", "Lugo", "7", "A B", "0,4", "C D", "0,3", "E F", "0,3"),
        _continuacio("G H", "0,150"),
        _fila("II", "2002", "", "", "Cartagena", "7", "C D", "", "A B"),
    ]  # fmt: skip
    inf = P.llegeix_taules_rfeb([[taula]], "Tres bandes", "femení")
    assert inf.edicions == 2
    tercers = [m.jugador for m in inf.medalles if m.edicio == "I" and m.posicio == 3]
    assert tercers == ["E F", "G H"]
    assert inf.medalles[-1].jugador == "A B"  # el segon de l'edició II


def test_rfeb_un_segon_nom_a_l_or_no_es_desa_i_es_diu():
    ambigua = [None] * 6 + ["Juan Fontova", "0,617"] + [None] * 4
    taula = [*CAP, 
        _fila("XXVII", "1960", "", "", "Barcelona", "", "Joaquín Domingo", "0,876"),
        _fila("XXVIII", "1961", "", "", "Valencia", "8", "Claudio Nadal", "0,666", "", "", "A R", "0,661"),
        ambigua,
        _fila("XXIX", "1962", "", "", "La Coruña", "", "A R", "0,658"),
    ]  # fmt: skip
    inf = P.llegeix_taules_rfeb([[taula]], "Tres bandes", "absolut")
    assert {m.edicio for m in inf.medalles} == {"XXVII", "XXIX"}
    assert len(inf.no_llegit) == 1
    assert "XXVIII" in inf.no_llegit[0][0]


def test_rfeb_un_any_o_una_edicio_garbats_no_es_desen_i_es_diuen():
    taula = [*CAP, 
        _fila("XVII", "11998927", "", "", "Murcia", "20", "Raúl Hernández", "0,9"),
        _fila("XXIXI", "1990", "", "", "Valencia", "11", "David Zapata", "1,2"),
        _fila("XVIII", "1999", "", "", "Gandía", "", "Carlos Cortés"),
    ]  # fmt: skip
    inf = P.llegeix_taules_rfeb([[taula]], "Tres bandes", "sub-21")
    assert [m.jugador for m in inf.medalles] == ["Carlos Cortés"]
    assert inf.edicions == 3
    assert len(inf.no_llegit) >= 2


def test_rfeb_la_marca_d_aigua_i_les_notes_no_son_noms():
    taula = [*CAP, 
        _fila("VII", "1988", "", "", "", "", "EN", "CONSTRUC", "CIÓ", "N"),
        ["HASTA ESTE MOMENTO SE DISPUTABA EL CUADRO 45/1"] + [None] * 11,
        _fila("VIII", "1989", "", "", "", "", "A B"),
    ]  # fmt: skip
    inf = P.llegeix_taules_rfeb([[taula]], "Tres bandes", "sub-21")
    assert [m.jugador for m in inf.medalles] == ["A B"]
    assert inf.no_llegit == []
    assert inf.notes == ["HASTA ESTE MOMENTO SE DISPUTABA EL CUADRO 45/1"]


def test_rfeb_la_taula_de_resum_del_final_no_es_llegeix():
    resum = [["MEDALLERO", None, None], ["Claudio Puigvert", "12", "3"]]
    taula = [*CAP, _fila("I", "1929", "", "", "Barcelona", "", "A B")]
    inf = P.llegeix_taules_rfeb([[taula], [resum]], "Tres bandes", "absolut")
    assert [m.jugador for m in inf.medalles] == ["A B"]


def test_rfeb_les_edicions_sense_roman_porten_el_numero_d_ordre():
    taula = [*CAP, 
        _fila("", "1991", "Diciembre", "", "", "36", "Sergio Cantó", "0,527"),
        _fila("", "", "", "", "", "", "Sergio Cantó"),
    ]  # fmt: skip
    inf = P.llegeix_taules_rfeb([[taula]], "Tres bandes", "sub-17")
    assert [(m.edicio, m.any_edicio) for m in inf.medalles] == [("1", 1991), ("2", None)]


def test_rfeb_el_percentatge_de_l_artistic():
    taula = [*CAP, _fila("L", "2013", "", "", "Écija", "8", "Xavier Fonellosa", "64,69%")]
    inf = P.llegeix_taules_rfeb([[taula]], "Artístic", "absolut")
    assert inf.medalles[0].mitjana == 64.69


# ---------------------------------------------------------------------------
# CEB
# ---------------------------------------------------------------------------

CEB = """\
updated - 11.4.2026
The European Champions - Three Cushion Dieter Haase
A. Aeberhardt (CH) A. Lagache (FR) J. Domingo (ES)
<<PAG>>
The European Championships - Three Cushion
Results of the main tournaments
1) Amsterdam (NL) (25.-29.11.1932) 50 Pts.
1. Alfred Aeberhard (CH) 14:2 399/605 0,659 0,862 6
2. Hendrik Robijns (NL) 12:4 381/531 0,717 0,925 7
3. Claudio Puigvert (ES) 10:6 378/616 0,613 0,877 6
2) Angoulême (FR) (29.6.-2.7.1939) 50 Pts.
1. Alfred Lagache (FR 16:0 400/497 0,804 1,041 7
2. Arie Bos (NL) 14:2 377/528 0,714 0,862 7
3. Alfredo Ferraz (PT) 10:6 359/625 0,574 0,675 8
3. Jan Hendriks (NL)
Michel Dupont (BE) 8:6 311/443 0,702 1,020 8
3) Madrid (ES) (6.-10.5.1948) 50 Pts.
1. Joaquin Domingo (ES) ?:? ?/? ? ? ?
<<PAG>>
2. Roger Hanoun (FR) 14:2 384/464 0,827 1,219 6
Copyright by
"""


def test_ceb_edicions_podi_i_mitjana():
    inf = P.llegeix_text_ceb(CEB, "Campionat d'Europa tres bandes", "absolut", "ec.pdf")
    assert inf.edicions == 3
    assert inf.no_llegit == []
    primera = [m for m in inf.medalles if m.edicio == "1"]
    assert [(m.posicio, m.jugador, m.pais, m.mitjana) for m in primera] == [
        (1, "Alfred Aeberhard", "CH", 0.659),
        (2, "Hendrik Robijns", "NL", 0.717),
        (3, "Claudio Puigvert", "ES", 0.613),
    ]
    assert (primera[0].any_edicio, primera[0].lloc, primera[0].font) == (
        1932,
        "Amsterdam (NL)",
        "ceb",
    )


def test_ceb_el_parentesi_que_falta_i_el_tercer_ex_aequo_amb_numero():
    inf = P.llegeix_text_ceb(CEB, "X", "absolut")
    segona = [m for m in inf.medalles if m.edicio == "2"]
    assert segona[0].jugador == "Alfred Lagache" and segona[0].pais == "FR"
    assert [m.jugador for m in segona if m.posicio == 3] == ["Alfredo Ferraz", "Jan Hendriks"]
    assert segona[0].any_edicio == 1939


def test_ceb_la_linia_sense_numero_es_el_quart_i_no_es_medalla():
    inf = P.llegeix_text_ceb(CEB, "X", "absolut")
    assert "Michel Dupont" not in {m.jugador for m in inf.medalles}
    assert inf.sense_podi == 1


def test_ceb_una_estadistica_amb_interrogants_no_dona_mitjana_ni_error():
    inf = P.llegeix_text_ceb(CEB, "X", "absolut")
    domingo = next(m for m in inf.medalles if m.jugador == "Joaquin Domingo")
    assert domingo.mitjana is None
    assert domingo.pais == "ES"


def test_ceb_una_capcalera_il_legible_no_deixa_el_podi_a_l_edicio_d_abans():
    text = (
        "1) Roma (IT) (1.-2.3.1990) 50 Pts.\n"
        "1. A B (IT) 10:0\n"
        "2) Monte Carlo (Monaco) (29.-31.10.1999) 50 Pts.\n"
        "1. C D (IT) 10:0\n"
        "2. E F (IT) 8:2\n"
    )
    inf = P.llegeix_text_ceb(text, "X", "absolut")
    assert [m.jugador for m in inf.medalles] == ["A B"]
    assert len(inf.no_llegit) == 3


def test_ceb_els_grand_prix_antics_no_numeren_les_edicions():
    text = (
        "Hundige / Copenhague (DK) (15.-18.1.1987) Sets à 15 Pts.\n"
        "1. Dieter Müller (DE) 12:0 18:4 306/? ? ? ? 10\n"
        "Landau (DE) (21.-25.1.1987) Sets à 15 Pts.\n"
        "1. Hans-Jürgen Kühl (DE) 10:2 15:8 294/268 1,097 1,250 2,142 10\n"
    )
    inf = P.llegeix_text_ceb(text, "Grand Prix", "absolut")
    assert [(m.edicio, m.any_edicio, m.jugador) for m in inf.medalles] == [
        ("1", 1987, "Dieter Müller"),
        ("2", 1987, "Hans-Jürgen Kühl"),
    ]


def test_ceb_un_pdf_amb_dues_competicions_es_parteix_per_seccions():
    text = (
        "The European Championships - Pins\n"
        "1) Stockholm (SE) (12.-14.3.1976) 600 Pts.\n"
        "1. Lennart Blomdahl (SE) 13:1 4200/79 53,16 85,71 315\n"
        "The European Championships - 5-Pins\n"
        "1) Rimini (IT) (1.-2.3.1986) 600 Pts.\n"
        "1. Claudio Cifala (IT) 5:1\n"
    )
    inf = P.llegeix_text_ceb(text, "", "absolut")
    assert [(m.competicio, m.edicio) for m in inf.medalles] == [
        ("Campionat d'Europa pins", "1"),
        ("Campionat d'Europa 5 quilles", "1"),
    ]


# ---------------------------------------------------------------------------
# Base de dades local i candidats
# ---------------------------------------------------------------------------


def _bd():
    from importlib.resources import files

    conn = sqlite3.connect(":memory:")
    conn.executescript((files("fcbillar.db") / "schema.sql").read_text(encoding="utf-8"))
    return conn


def _medalla(**kw):
    base = dict(
        font="rfeb", competicio="Tres bandes", categoria="absolut", edicio="I", any_edicio=1929,
        lloc=None, posicio=1, jugador="A B",
    )  # fmt: skip
    return P.Medalla(**(base | kw))


def test_desa_reemplaca_per_competicio_i_no_toca_les_altres():
    conn = _bd()
    a = P.Informe("a.pdf", "rfeb", medalles=[_medalla(), _medalla(edicio="II", jugador="C D")])
    b = P.Informe("b.pdf", "rfeb", medalles=[_medalla(categoria="femení", jugador="E F")])
    assert P.desa(conn, [a, b]) == 3
    # Es torna a llegir només l'absolut, ara amb una medalla menys.
    assert P.desa(conn, [P.Informe("a.pdf", "rfeb", medalles=[_medalla()])]) == 1
    noms = sorted(r[0] for r in conn.execute("SELECT jugador FROM palmares_medalles"))
    assert noms == ["A B", "E F"]


def test_candidats_de_palmares_nomes_els_de_la_rfeb_i_els_espanyols_del_ceb():
    conn = _bd()
    medalles = [
        _medalla(jugador="Josep Mª Mas"),
        _medalla(font="ceb", jugador="Ivan Mayor", pais="ES", competicio="Europa"),
        _medalla(font="ceb", jugador="Martin Horn", pais="DE", competicio="Europa"),
    ]
    P.desa(conn, [P.Informe("x", "rfeb", medalles=medalles)])
    assert [n for n, _, _ in P.jugadors_per_candidats(conn)] == ["Ivan Mayor", "Josep Mª Mas"]


def test_afegeix_candidats_va_al_final_i_no_reordena_ni_canvia_els_finals_de_linia(tmp_path):
    cami = tmp_path / "fitxes.csv"
    cap = "validat,jugador_rfeb,equip_rfeb,divisio,fcb_id,nom_cens,club_cens,motiu\r\n"
    cami.write_bytes(
        (cap + 'si,Zeta Z,x,1,10,"Z, Z",,exacte\r\n,Alfa A,x,1,11,"A, A",,exacte\r\n').encode()
    )
    nou = Candidat(
        rfeb=JugadorRfeb(nom="Beta B", equip="Tres bandes", divisio="palmares"),
        cens=JugadorCens(fcb_id="12", nom="B B, BETA", club="C.B.X"),
        motiu="un cognom",
    )
    ja_hi_era = Candidat(
        rfeb=JugadorRfeb(nom="Alfa A", equip="y", divisio="palmares"),
        cens=JugadorCens(fcb_id="11", nom="A, A", club=""),
    )
    assert P.afegeix_candidats([ja_hi_era, nou], cami) == (2, 1)
    linies = cami.read_bytes().decode().split("\r\n")
    assert linies[1].startswith("si,Zeta Z") and linies[2].startswith(",Alfa A")
    assert linies[3] == ',Beta B,Tres bandes,palmares,12,"B B, BETA",C.B.X,un cognom'
    # Tornar-hi no duplica res.
    assert P.afegeix_candidats([nou], cami) == (3, 0)


def test_quadre_honor_fcb_pdf_real():
    from pathlib import Path

    from fcbillar.palmares import llegeix_fcb

    cami = Path(__file__).parents[1] / "fonts/palmares/fcb/quadrehonorfcb1985-1986.pdf"
    inf = llegeix_fcb(cami)
    assert inf.no_llegit == []
    tb = [(m.categoria, m.posicio, m.jugador, m.lloc) for m in inf.medalles if m.competicio == "Tres bandes"]
    assert ("1a", 1, "Claudio Nadal", "C.B. Barcelona") in tb
    assert ("2a", 1, "Ferran Rodríguez", "C.B. Banyoles") in tb
    assert all(m.edicio == "1985-86" and m.any_edicio == 1986 for m in inf.medalles)


def test_quadre_honor_fcb_llista_dins_taula_de_sis_columnes():
    """Al 1973-74 el Trofeu Claudio Puigvert és «1r | jugador | club | | »: un campió i un subcampió."""
    from pathlib import Path

    from fcbillar.palmares import llegeix_fcb

    cami = Path(__file__).parents[1] / "fonts/palmares/fcb/quadrehonorfcb1973-1974.pdf"
    inf = llegeix_fcb(cami)
    trofeu = sorted((m.categoria, m.posicio, m.jugador) for m in inf.medalles if m.competicio == "Trofeu Claudio Puigvert")
    assert trofeu == [("absolut", 1, "Pascual Peña"), ("absolut", 2, "Norman Solé")]
    copa = sorted((m.posicio, m.jugador) for m in inf.medalles if m.competicio == "Copa Presidente")
    assert copa == [(1, "Segundo Goméz"), (2, "Isidoro Mizrahi")]
    assert inf.no_llegit == []


def test_quadre_honor_fcb_celles_combinades():
    """2016-17: una sola cel·la «5 QUILLES / BIATHLÓ» per a dues files, una per modalitat.

    2015-16: dos GP femenins el mateix any (la segona categoria es numera).
    2012-13: «----------» vol dir que no hi ha subcampió.
    """
    from pathlib import Path

    from fcbillar.palmares import llegeix_fcb

    arrel = Path(__file__).parents[1] / "fonts/palmares/fcb"
    m16 = llegeix_fcb(arrel / "quadrehonorfcb2016-2017.pdf").medalles
    campio = {m.competicio: m.jugador for m in m16 if m.posicio == 1 and m.competicio in ("5 quilles", "Biatló")}
    assert campio == {"5 quilles": "Lino Brizzi", "Biatló": "Angel Viladomat Gonfaus"}

    m15 = llegeix_fcb(arrel / "quadrehonorfcb2015-2016.pdf").medalles
    gp = sorted((m.categoria, m.posicio, m.jugador) for m in m15 if m.categoria.startswith("GP"))
    assert gp == [
        ("GP Femení", 1, "Georgeta Anghel"),
        ("GP Femení", 2, "Mònica Planes Bravo"),
        ("GP Femení 2", 1, "Eva Julià Soldevila"),
        ("GP Femení 2", 2, "Mònica Planes Bravo"),
    ]

    m12 = llegeix_fcb(arrel / "quadrehonorfcb2012-2013.pdf").medalles
    assert not [m for m in m12 if not any(ch.isalpha() for ch in m.jugador)]
    assert ("Quadre 71/2", "2a", 1, "Alejandro López Balboa") in {(m.competicio, m.categoria, m.posicio, m.jugador) for m in m12}
