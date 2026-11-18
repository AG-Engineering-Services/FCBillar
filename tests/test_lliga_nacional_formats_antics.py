"""Formats de la Lliga Nacional d'abans del 2023 que el lector no entenia.

- Honor 2016-17: la data en lletres («8 de octubre de 2016»).
- Segona 2016-17: dos grups per PDF i cada grup a dues columnes.
- Segona 2021-22: un equip amb número al nom («C.B. BAEZA 2»).
- Honor 2020-21 i 2021-22: unes quantes jornades de cop, per concentracions.
"""

from datetime import date
from pathlib import Path

from fcbillar.lliga_nacional import (
    RE_FITXER_CONCENTRAT,
    llegeix_jornada,
    llegeix_jornades_concentrades,
)
from fcbillar.nacional_historic import temporada_de_la_carpeta

NACIONAL = Path(__file__).parent / "fixtures" / "nacional"


def test_honor_amb_la_data_en_lletres():
    j = llegeix_jornada(NACIONAL / "liga_nal_h_j1_1617.pdf")
    assert (j.numero, j.data) == (1, date(2016, 10, 8))
    e = j.grups[0].encontres[0]
    assert (e.local, e.punts_local, e.punts_visitant, e.visitant) == (
        "C.B. VALENCIA",
        3,
        5,
        "CSNO. DE CARTAGENA",
    )
    assert len(e.partides) == 4


def test_segona_2016_dos_grups_a_dues_columnes():
    j = llegeix_jornada(NACIONAL / "liga_nal_2ab_j1_1617.pdf")
    assert j.data == date(2016, 10, 8)
    assert [(g.grup, len(g.encontres)) for g in j.grups] == [("A", 2), ("B", 2)]
    e = j.grups[0].encontres[0]
    assert (e.local, e.punts_local, e.punts_visitant, e.visitant) == (
        "GRUPOTOT C.B. SUECA",
        8,
        0,
        "C.B. KALIMA-RIVAS 'B'",
    )
    p = e.partides[0]
    assert (p.jugador_local, p.caramboles_local, p.caramboles_visitant, p.entrades) == (
        "Raúl Cuenca Monrabal",
        39,
        29,
        50,
    )
    # Les caramboles de l'encontre són la suma de les partides.
    assert e.caramboles_local == sum(x.caramboles_local for x in e.partides)


def test_segona_2021_equip_amb_numero_al_nom():
    j = llegeix_jornada(NACIONAL / "liga_nal_2_j1_2122.pdf")
    a = next(g for g in j.grups if g.grup == "A")
    e = a.encontres[0]
    assert (e.local, e.punts_local, e.punts_visitant, e.visitant) == (
        "C.B. LA PALMA",
        8,
        0,
        "C.B. BAEZA 2",
    )


def test_honor_2021_jornades_concentrades():
    fitxer = NACIONAL / "liga_nal_h_j10y11_2021.pdf"
    assert RE_FITXER_CONCENTRAT.search(fitxer.name)
    js = llegeix_jornades_concentrades(fitxer)
    assert [(j.numero, j.data) for j in js] == [(10, date(2021, 5, 22)), (11, date(2021, 5, 22))]
    # Cinc encontres per jornada (deu equips), sense els «DESCANSA».
    assert [len(j.grups[0].encontres) for j in js] == [5, 5]
    assert ("C.B. PAIPORTA", "C.B. VIC") in [
        (e.local, e.visitant) for e in js[0].grups[0].encontres
    ]
    assert ("C.B. PAIPORTA", "MADRID E. NACIONAL") in [
        (e.local, e.visitant) for e in js[1].grups[0].encontres
    ]


def test_la_temporada_de_la_carpeta_de_la_web_vella():
    assert temporada_de_la_carpeta(Path("x/noticias2016")) == "2016-2017"
    assert temporada_de_la_carpeta(Path("fonts/nacional/2025-2026")) is None
