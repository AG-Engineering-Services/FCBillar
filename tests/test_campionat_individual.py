"""Divisions del campionat individual i quan li toca jugar a cadascú."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from fcbillar.campionat_individual import (
    FASES,
    FINAL,
    Fase,
    cites,
    fases_del_calendari,
    files_de_calendari,
)
from fcbillar.divisions_individual import Inscrit, llegeix, per_club
from fcbillar.scraper.parsers import parse_clubs_listing

FIXTURES = Path(__file__).parent / "fixtures"
PDF = FIXTURES / "divisions_3b_2627.pdf"

#: El cens oficial de clubs, tret de la mateixa pàgina de la federació que ja
#: tenim com a fixture. És el que fa servir aquest PDF, amb el seu espaiat.
#:
#: I dos que hi falten: el B.C.OLESA, que és un club de debò —juga a divisió
#: d'Honor— i no surt al llistat públic de la federació; i INDEPENDENT, que no
#: és cap club sinó els jugadors amb llicència pròpia.
CENS = [
    c.nom for c in parse_clubs_listing((FIXTURES / "nou" / "wp_clubs.html").read_text("utf-8"))
] + ["B.C.OLESA", "INDEPENDENT"]


@pytest.fixture(scope="module")
def inscrits():
    llegits, rebutjades = llegeix(PDF, CENS)
    assert rebutjades == [], f"línies sense interpretar: {rebutjades[:3]}"
    return llegits


def test_els_llegeix_tots(inscrits) -> None:
    assert len(inscrits) == 379


def test_reparteix_el_nom_del_club(inscrits) -> None:
    """El nom i el club porten tots dos espais: el tall no és trivial."""
    primer = inscrits[0]
    assert primer.divisio == "Honor"
    assert primer.posicio == 1
    assert primer.jugador == "MAS CANADELL, JOSEP Mª"
    assert primer.club == "B.C.GRANOLLERS"


def test_el_club_es_reconeix_amb_altres_espais(inscrits) -> None:
    """El mateix club, escrit diferent segons el document de la federació."""
    molins = next(i for i in inscrits if i.jugador.startswith("PERALES SANZ"))
    assert molins.club == "S.B.F.MOLINS"


def test_els_independents_no_es_perden(inscrits) -> None:
    """«INDEPENDENT» no és un club, però és el que la federació hi escriu."""
    assert any(i.club == "INDEPENDENT" for i in inscrits)


def test_l_ordinal_masculi_tambe_val(inscrits) -> None:
    """Dins del mateix PDF hi ha «5ª» i «5º»."""
    assert {i.divisio for i in inscrits} <= {"Honor", "1ª", "2ª", "3ª", "4ª", "5ª", "6ª"}
    assert sum(1 for i in inscrits if i.divisio == "5ª") == 52


def test_la_mitjana_provisional_es_marca(inscrits) -> None:
    provisionals = [i for i in inscrits if not i.definitiva]
    assert provisionals, "n'hi ha d'haver alguna de provisional"
    assert all(i.mitjana > 0 for i in provisionals)


def test_els_del_club_van_de_mes_alta_a_mes_baixa(inscrits) -> None:
    meus = per_club(inscrits, "BANYOLES")
    assert len(meus) == 12
    assert [i.divisio for i in meus] == [
        "1ª",
        "1ª",
        "1ª",
        "2ª",
        "2ª",
        "2ª",
        "3ª",
        "4ª",
        "6ª",
        "6ª",
        "6ª",
        "6ª",
    ]


# --------------------------- fases ---------------------------


def _conn_amb_calendari(files: list[tuple[str, str, str]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE calendari_events (font TEXT, temporada TEXT, data_inici TEXT,"
        " data_fi TEXT, titol TEXT)"
    )
    conn.executemany(
        "INSERT INTO calendari_events (font, temporada, data_inici, data_fi, titol)"
        " VALUES ('FCB', '2026/2027', ?, ?, ?)",
        files,
    )
    return conn


def test_llegeix_les_fases_encara_que_estiguin_mal_escrites() -> None:
    """La federació no les escriu dues vegades igual."""
    conn = _conn_amb_calendari(
        [
            (
                "2026-09-19",
                "2026-09-19",
                "Pre-Prèvia 3 Bandes 1ª Divisió · Prèvia 3 Bandes Div. Honor",
            ),
            ("2027-02-06", "2027-02-06", "Pre- Pre-Prèvia 3 B. 6ª Divisió"),
            ("2027-02-13", "2027-02-13", "Pre-Prèvia 3 Bandes 6ª Div."),
            ("2026-10-17", "2026-10-18", "FINAL 3Bandes 1ª Divisió"),
            ("2026-10-31", "2026-11-01", "FINAL 3Bandes Div. Honor"),
        ]
    )
    fases = fases_del_calendari(conn, "2026/2027")
    assert [f.fase for f in fases["Honor"]] == ["Prèvia", "Final"]
    assert [f.fase for f in fases["1ª"]] == ["Pre-prèvia", "Final"]
    assert [f.fase for f in fases["6ª"]] == ["Pre-pre-prèvia", "Pre-prèvia"]


def test_no_confon_una_altra_modalitat() -> None:
    conn = _conn_amb_calendari(
        [("2027-05-15", "2027-05-16", "Prèvia Lliure 2ª Divisió · Final Banda 3ª Div.")]
    )
    assert fases_del_calendari(conn, "2026/2027") == {}


def _inscrit(nom: str, divisio: str) -> Inscrit:
    return Inscrit(
        divisio=divisio, posicio=1, jugador=nom, club="C.B.BANYOLES", mitjana=0.5, definitiva=True
    )


FASES_2A = [
    Fase(
        "2ª", "Pre-prèvia", date(2026, 9, 19), date(2026, 9, 19), "Pre-Prèvia 3 Bandes 2ª Divisió"
    ),
    Fase("2ª", "Prèvia", date(2026, 10, 3), date(2026, 10, 4), "Prèvia 3 Bandes 2ª Divisió"),
    Fase("2ª", "Final", date(2026, 10, 17), date(2026, 10, 18), "FINAL 3Bandes 2ª Divisió"),
]


def test_nomes_hi_va_la_primera_fase() -> None:
    """Per jugar la prèvia s'ha de passar la pre-prèvia: encara no és una data seva."""
    resultat = cites([_inscrit("QUALSEVOL, U", "2ª")], {"2ª": FASES_2A})
    assert [c.fase.fase for c in resultat] == ["Pre-prèvia"]


def test_a_honor_la_primera_es_la_previa() -> None:
    """Honor no té pre-prèvia: la seva primera fase sí que és segura."""
    honor = [
        Fase("Honor", "Prèvia", date(2026, 9, 19), date(2026, 9, 19)),
        Fase("Honor", "Final", date(2026, 10, 31), date(2026, 11, 1)),
    ]
    resultat = cites([_inscrit("QUALSEVOL, U", "Honor")], {"Honor": honor})
    assert [c.fase.fase for c in resultat] == ["Prèvia"]


def test_la_final_no_hi_va_mai() -> None:
    nomes_final = [Fase("2ª", FINAL, date(2026, 10, 17), date(2026, 10, 18))]
    assert cites([_inscrit("QUALSEVOL, U", "2ª")], {"2ª": nomes_final}) == []


def test_la_fase_d_entrada_es_per_ordre_no_per_data() -> None:
    """Si la federació escriu una data equivocada, la fase segueix sent la mateixa.

    Primer s'ha de passar la pre-prèvia i després es juga la prèvia, encara que
    el calendari les hagi posades al revés. I ja hem vist que s'hi equivoquen.
    """
    desordenades = [
        Fase("2ª", "Prèvia", date(2026, 9, 5), date(2026, 9, 5), "Prèvia 3 Bandes 2ª Divisió"),
        Fase(
            "2ª",
            "Pre-prèvia",
            date(2026, 9, 19),
            date(2026, 9, 19),
            "Pre-Prèvia 3 Bandes 2ª Divisió",
        ),
    ]
    resultat = cites([_inscrit("QUALSEVOL, U", "2ª")], {"2ª": desordenades})
    assert [c.fase.fase for c in resultat] == ["Pre-prèvia"]


def test_els_jugadors_van_junts_a_la_fila_de_la_seva_fase() -> None:
    """Una fila per fase amb els nostres a dins, no una per jugador."""
    dos = cites(
        [_inscrit("UN, JUGADOR", "2ª"), _inscrit("ALTRE, U", "2ª")],
        {"2ª": FASES_2A},
    )
    files = files_de_calendari(dos, "2026/2027")
    assert len(files) == 1
    assert "UN, JUGADOR" in files[0][9] and "ALTRE, U" in files[0][9]
    # El separador no pot ser la coma: ja n'hi ha a «COGNOMS, NOM».
    assert " · " in files[0][9]
    # I `seu` porta el text de la fase tal com l'escriu la federació.
    assert files[0][10] == FASES_2A[0].text


def test_una_divisio_sense_fases_no_genera_cites() -> None:
    assert cites([_inscrit("QUALSEVOL, U", "3ª")], {"2ª": FASES_2A}) == []


def test_les_fases_estan_ordenades() -> None:
    assert FASES.index("Pre-pre-prèvia") < FASES.index("Pre-prèvia") < FASES.index("Prèvia")
    assert FASES.index("Prèvia") < FASES.index("Final")


def test_les_files_del_calendari_porten_la_setmana_del_dilluns() -> None:
    resultat = cites([_inscrit("QUALSEVOL, U", "2ª")], {"2ª": FASES_2A})
    files = files_de_calendari(resultat, "2026/2027")
    # 19/09/2026 és dissabte; el dilluns de la seva setmana és el 14.
    assert files[0][2] == "2026-09-14"
    assert files[0][7] == "2026-09-19"
    assert files[0][6] == "individual"
    # El grup és la fase: la clau primària de la taula és per setmana i grup, i
    # una divisió no té dues fases el mateix cap de setmana.
    assert "2ª" in files[0][5] and "Pre-prèvia" in files[0][5]


def test_qui_no_juga_les_classificatories_no_surt_al_calendari() -> None:
    """La federació publica qui s'ha inscrit, no qui hi anirà.

    Un jugador pot constar inscrit i no presentar-se a les prèvies, i posar-lo
    al calendari seria prometre una cita que no existeix. Això no se sap de cap
    font: ho diu el club, i per això va escrit al codi.
    """
    from fcbillar.campionat_individual import NO_JUGA_CLASSIFICATORIES

    exclos = next(iter(NO_JUGA_CLASSIFICATORIES))
    llista = cites([_inscrit(exclos, "2ª"), _inscrit("ALTRE, U", "2ª")], {"2ª": FASES_2A})

    assert [c.inscrit.jugador for c in llista] == ["ALTRE, U"]
