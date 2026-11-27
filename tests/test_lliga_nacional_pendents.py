"""Formats de la Lliga Nacional que encara no es llegien (2020-21 i la temporada en curs).

- Unes quantes jornades de cop, cadascuna a les seves pàgines: Primera, Honor i
  Segona 2020-2023.
- Partides no presentades, encontres sense jugar i encontres adjudicats per
  alineació indeguda.
- Segona 2026-27: jornada 3 dels grups B i C en un sol PDF.
"""

from datetime import date
from pathlib import Path

import pytest

from fcbillar import lliga_nacional as LN

NACIONAL = Path(__file__).parent / "fixtures" / "nacional"


def _parelles(grup: LN.GrupDeJornada) -> list[tuple[str, str]]:
    return [(e.local, e.visitant) for e in grup.encontres]


def test_primera_2021_concentracio_amb_una_pagina_per_jornada():
    js = LN.llegeix_jornades_concentrades(NACIONAL / "liga_nal_1a_j1a4_2021.pdf")
    assert [(j.numero, j.data) for j in js] == [(1, date(2021, 3, 14)), (2, date(2021, 3, 14))]
    assert [len(j.grups[0].encontres) for j in js] == [4, 4]
    e = js[0].grups[0].encontres[0]
    assert (e.local, e.punts_local, e.punts_visitant, e.visitant) == (
        "C.B. BAEZA",
        6,
        2,
        "C.B. JPR CALLOSA",
    )
    assert len(e.partides) == 4
    # La classificació del final del PDF és de la darrera jornada, no de la primera.
    assert js[0].grups[0].classificacio == []
    assert len(js[1].grups[0].classificacio) == 8


def test_honor_2021_una_jornada_a_dues_pagines_i_equip_que_descansa():
    js = LN.llegeix_jornades_concentrades(NACIONAL / "liga_nal_h_j1a5_2021.pdf")
    assert [j.numero for j in js] == [1, 2]
    # Cinc encontres per jornada: la meitat és a cada pàgina, i «DESCANSA» no compta.
    assert [len(j.grups[0].encontres) for j in js] == [5, 5]
    assert "C.B. PAIPORTA" not in {x for p in _parelles(js[0].grups[0]) for x in p}
    # Les millors sèries del final són «de las jornadas»: de cap en concret.
    assert all(j.millors_series == [] for j in js)


def test_honor_2022_concentracio_amb_la_jornada_a_dalt_de_cada_pagina():
    js = LN.llegeix_jornades_concentrades(NACIONAL / "liga_nal_h_j7a9_2122.pdf")
    assert [j.numero for j in js] == [7, 8, 9]
    assert all(len(j.grups[0].encontres) == 5 for j in js)
    assert len(js[2].grups[0].classificacio) == 10


def test_segona_2021_concentracio_de_jornades_amb_la_classificacio_a_cada_una():
    js = LN.llegeix_jornades_concentrades(NACIONAL / "liga_nal_2b_j7a10_2021.pdf")
    assert [(j.numero, j.grups[0].grup) for j in js] == [(7, "B"), (8, "B")]
    assert js[0].grups[0].encontres[0].local == "C.C.R. CHAPELA"
    assert all(len(j.grups[0].classificacio) == 5 for j in js)


def test_un_pdf_sense_cap_jornada_a_dalt_de_les_pagines_no_es_llegeix():
    # Un PDF de classificació de jugadors no porta «JORNADA n» enlloc.
    with pytest.raises(LN.FormatDesconegut):
        LN.llegeix_jornades_concentrades(NACIONAL / "liga_nal_1_cjug_2627.pdf")


def test_honor_partida_no_presentada_no_es_desa():
    j = LN.llegeix_jornada(NACIONAL / "liga_nal_h_j5_1920.pdf")
    ateneo = next(e for e in j.grups[0].encontres if e.local == "C.B. ATENEO MERC.")
    assert (ateneo.punts_local, ateneo.punts_visitant) == (6, 2)
    # La quarta partida no es va jugar: les caramboles són les de les tres que sí.
    assert len(ateneo.partides) == 3
    assert ateneo.caramboles_local == sum(p.caramboles_local for p in ateneo.partides) == 111
    assert "Juan L. Torner Alama" not in {p.jugador_local for p in ateneo.partides}


def test_honor_encontre_adjudicat_per_alineacio_indeguda_no_es_desa():
    # Kalima-Rivas - Vallecas (8-0) i l'altra parella tenen només els noms dels
    # jugadors alineats, sense caramboles ni totals.
    j = LN.llegeix_jornada(NACIONAL / "liga_nal_h_j11_1819.pdf")
    equips = {x for p in _parelles(j.grups[0]) for x in p}
    assert "C.B. VALLECAS" not in equips and "C.B. KALIMA-RIVAS" not in equips
    assert len(j.grups[0].encontres) == 3


def test_honor_encontres_suspesos_no_es_desen():
    j = LN.llegeix_jornada(NACIONAL / "liga_nal_h_j12_2526.pdf")
    assert _parelles(j.grups[0]) == [
        ("C.B. MÓSTOLES", "MADRID E. NACIONAL"),
        ("DS PREDATOR CARTAGENA", "INVIKTCUES GRANOLLERS"),
    ]


def test_segona_equip_retirat_amb_files_de_zeros():
    # Olotí no juga: el seu encontre surt amb «0 0 0» i «8 0 0 0 0», sense noms.
    j = LN.llegeix_jornada(NACIONAL / "liga_nal_2c_j3_2021.pdf")
    [grup] = j.grups
    assert grup.grup == "C"
    assert _parelles(grup) == [
        ("C.B. MOLLET", "C.B. BARCELONA"),
        ("ABACÓ C.B.", "C.B. SANT ADRIÁ"),
    ]
    assert len(grup.classificacio) == 6


def test_segona_2026_jornada_3_dels_grups_b_i_c():
    j = LN.llegeix_jornada(NACIONAL / "liga_nal_2bc_j3_2627.pdf")
    assert (j.numero, j.data) == (3, date(2026, 10, 24))
    assert [(g.grup, len(g.encontres), len(g.classificacio)) for g in j.grups] == [
        ("B", 3, 6),
        ("C", 3, 6),
    ]
    murcia = j.grups[0].encontres[0]
    assert (murcia.local, murcia.punts_local, murcia.punts_visitant) == ('C.B. MURCIA "B"', 6, 2)
    # «Francisco Ruiz Puerta 0 0 0»: sense rival, no es va jugar.
    assert len(murcia.partides) == 3
    assert murcia.caramboles_local == 85 and murcia.entrades == 143


def test_primera_encontre_sense_partides_per_alineacio_indeguda():
    # Kalima-Rivas - Burguillos (8-0) surt només amb el resultat i el rètol.
    j = LN.llegeix_jornada(NACIONAL / "liga_nal_1_j11_2223.pdf")
    assert ("C.B. KALIMA-RIVAS", "C.B. BURGUILLOS") not in _parelles(j.grups[0])
    assert len(j.grups[0].encontres) == 3


def test_primera_partida_no_presentada_en_un_encontre_de_dos_columnes():
    j = LN.llegeix_jornada(NACIONAL / "liga_nal_1_j12_2324.pdf")
    assert [len(g.encontres) for g in j.grups] == [4, 4]
    # L'encontre Barcelona - Vallecas té una partida menys.
    assert sorted(len(e.partides) for g in j.grups for e in g.encontres) == [3] + [4] * 7


def test_primera_2021_equip_que_no_es_presenta_no_es_desa():
    # Palma «B» - Vallecas (8-0): les quatre partides surten «Nom 0 0 en 0», sense
    # visitant, i una línia «NO PRESENTADO». L'encontre no es va jugar.
    j = LN.llegeix_jornada(NACIONAL / "liga_nal_1b_j7_2021.pdf")
    assert [(e.local, e.visitant) for e in j.grups[0].encontres] == [
        ("C.B. GETAFE", "CÍRC. A. NUMANCIA"),
        ("DS MATADEPERA C.", "C.B. GRANOLLERS"),
    ]


def test_primera_2021_la_partida_no_presentada_no_te_visitant_que_es_digui_no_presentado():
    j = LN.llegeix_jornada(NACIONAL / "liga_nal_1b_j12_2021.pdf")
    numancia = j.grups[0].encontres[1]
    assert len(numancia.partides) == 3
    assert "NO PRESENTADO" not in {p.jugador_visitant for p in numancia.partides}
