"""Resultats oficials de la UMB: lectura dels PDF, càrrega i lligams amb el cens.

Els PDF de `tests/fixtures/umb/{id}/` són només de resultats (cap adreça, telèfon
ni correu), amb l'id de l'esdeveniment de umb-carom.org com a carpeta: un del 2013
(noms amb espais, decimals amb coma), un del 2018 (noms enganxats, sense
identificador) i un del 2025.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fcbillar.db.migrations import ensure_schema
from fcbillar.nacional_fitxes import JugadorCens
from fcbillar.umb import (
    clau,
    es_equips,
    llegeix_equips,
    llegeix_jugadors,
    llegeix_partides,
    llegeix_prova,
    noms_de_la_llista_d_equips,
    separa_nom,
    text_sets,
)
from fcbillar.umb_carrega import carrega, disciplina_de, resum
from fcbillar.umb_descarrega import llegeix_esdeveniment
from fcbillar.umb_fitxes import (
    JugadorUmb,
    escriu_candidats,
    lligams_validats,
    nom_natural,
    proposa,
)

FIX = Path(__file__).parent / "fixtures" / "umb"


def test_noms_enganxats():
    assert separa_nom("KARAKURTBerkay") == "KARAKURT Berkay"
    assert separa_nom("TRANThanhLuc") == "TRAN Thanh Luc"
    assert separa_nom("JENSENBjornMikkel") == "JENSEN Bjorn Mikkel"
    assert separa_nom("D'AGATAAlessio") == "D'AGATA Alessio"
    assert separa_nom("ABU TAYEH Mashhour") == "ABU TAYEH Mashhour"
    assert clau("SIDHOMSameh") == clau("SIDHOM Sameh")
    assert clau("CAUDRON Frédéric") == clau("CAUDRONFrédéric")


def test_llista_de_jugadors_amb_id():
    text = (
        "Players List\n"
        "1 JASPERS Dick NL 1 428 0106 Main Tournament Confirmed\n"
        "15 PIEDRABUENA Pedro US 463 0 0122 Wildcard CPB\n"
        "26 LEGAZPI Ruben ES 21 137 0132\n"
        "21 ABU TAYEH Mashhour JO 77 31 1660\n"
    )
    js = llegeix_jugadors(text)
    assert [(j.nom, j.nacionalitat, j.umb_id) for j in js] == [
        ("JASPERS Dick", "NL", "0106"),
        ("PIEDRABUENA Pedro", "US", "0122"),
        ("LEGAZPI Ruben", "ES", "0132"),
        ("ABU TAYEH Mashhour", "JO", "1660"),
    ]


def test_llista_de_jugadors_sense_id_ni_data_de_naixement():
    antic = llegeix_jugadors("1 BLOMDAHL Torbjorn SE 1 402 Main Tournament Confirmed")
    assert (antic[0].nom, antic[0].nacionalitat, antic[0].umb_id) == (
        "BLOMDAHL Torbjorn",
        "SE",
        None,
    )
    # 2018: el país va escrit i hi ha la data de naixement, que no es desa.
    mitja = llegeix_jugadors("1 ANGUITA Carlos Spain 16/01/1997 1.029 Current World Champion")
    assert (mitja[0].nom, mitja[0].nacionalitat) == ("ANGUITA Carlos", "ES")
    assert "1997" not in repr(mitja)


def test_prova_2013_noms_amb_espais_i_decimals_amb_coma():
    ll = llegeix_prova(FIX / "50")
    assert ll.errors == []
    final = [p for p in ll.partides if p.fase.upper() == "FINAL"]
    assert len(final) == 1
    p = final[0]
    assert (p.a.jugador, p.a.caramboles, p.a.punts) == ("BLOMDAHL Torbjorn", 27, 0)
    assert (p.b.jugador, p.b.caramboles, p.b.punts) == ("CAUDRON Frédéric", 40, 2)
    assert (p.a.entrades, p.b.entrades) == (26, 26)
    assert p.b.mitjana == 1.538
    assert ll.classificacio[0].jugador == "CAUDRON Frédéric"
    assert ll.classificacio[0].posicio == 1
    assert ll.classificacio[0].nacionalitat == "BE"
    # Empat al tercer lloc: les dues files hi són.
    assert [c.posicio for c in ll.classificacio[:5]] == [1, 2, 3, 3, 5]
    # Una partida de grup porta la lletra del grup, i els jugadors venen de la llista.
    g = next(p for p in ll.partides if p.grup == "A")
    assert {g.a.jugador, g.b.jugador} <= {j.nom for j in ll.jugadors}


def test_prova_2018_noms_enganxats_sense_llista():
    ll = llegeix_prova(FIX / "200")
    assert ll.errors == []
    assert ll.jugadors and all(j.umb_id is None for j in ll.jugadors)
    final = next(p for p in ll.partides if p.fase.endswith("Final") and "Semi" not in p.fase)
    assert (final.a.jugador, final.b.jugador) == ("CHO Myung Woo", "JANG Daehyeon")
    assert (final.a.caramboles, final.b.caramboles) == (35, 18)
    spanish = [j for j in ll.jugadors if j.nacionalitat == "ES"]
    assert {j.nom for j in spanish} == {"ANGUITA Carlos", "MERCADER Mario"}
    # Els grups de classificació.
    grup = [p for p in ll.partides if p.grup == "A"]
    assert len(grup) == 6
    assert len({p.ordre for p in ll.partides}) == len(ll.partides)


def test_prova_2025_qui_comenca_juga_una_entrada_mes():
    ll = llegeix_prova(FIX / "307")
    semi = ll.partides[0]
    assert (semi.a.jugador, semi.b.jugador) == ("SIDHOM Sameh", "CEULEMANS Peter")
    assert (semi.a.entrades, semi.b.entrades) == (23, 22)
    assert semi.a.mitjana == 2.173
    assert (semi.a.serie, semi.b.serie) == (7, 9)
    assert ll.partides[1].fase.endswith("Semi_Final")
    assert ll.partides[-1].fase.endswith("Final")


def test_un_pdf_malmes_no_tomba_la_prova(tmp_path):
    carpeta = tmp_path / "50"
    shutil.copytree(FIX / "50", carpeta)
    (carpeta / "Z. Truncat.pdf").write_bytes(b"%PDF-1.4 res")
    ll = llegeix_prova(carpeta)
    assert len(ll.errors) == 1 and "Z. Truncat.pdf" in ll.errors[0]
    assert ll.partides and ll.classificacio


def _cache(tmp_path: Path, ids: list[int]) -> Path:
    cache = tmp_path / "umb"
    evs = []
    for i in ids:
        shutil.copytree(FIX / str(i), cache / str(i))
        evs.append(
            {
                "id": i,
                "nom": {50: "World Cup 3-Cushion", 200: "World Championship 3-Cushion Juniors"}.get(
                    i, "World Cup 3-Cushion"
                ),
                "lloc": "X",
                "inici": f"20{i % 100:02d}-01-01",
                "fi": f"20{i % 100:02d}-01-05",
                "descripcio": "",
                "pdfs": sorted(p.name for p in (cache / str(i)).glob("*.pdf")),
            }
        )
    (cache / "esdeveniments.json").write_text(json.dumps(evs), encoding="utf-8")
    return cache


def test_carrega_es_idempotent(tmp_path):
    cache = _cache(tmp_path, [50, 200, 307])
    conn = ensure_schema(tmp_path / "t.db")
    res = carrega(conn, cache)
    assert [r.estat for r in res] == ["desat"] * 3
    primer = resum(conn)
    assert primer["esdeveniments"] == 3
    assert primer["partides"] > 50 and primer["classificacions"] > 20

    taules = ("umb_esdeveniments", "umb_jugadors", "umb_classificacions", "umb_partides")
    abans = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in taules}
    carrega(conn, cache)
    carrega(conn, cache)
    despres = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in taules}
    assert abans == despres
    assert conn.execute("SELECT disciplina FROM umb_esdeveniments WHERE id = 50").fetchone()[:] == (
        "3 bandes",
    )


def test_prova_sense_resultats_es_reporta_i_no_atura_res(tmp_path):
    cache = _cache(tmp_path, [50])
    (cache / "9").mkdir()
    (cache / "9" / "A. Players List.pdf").write_bytes(b"no es un pdf")
    evs = json.loads((cache / "esdeveniments.json").read_text(encoding="utf-8"))
    evs.append(
        {"id": 9, "nom": "X", "lloc": "", "inici": None, "fi": None, "descripcio": "",
         "pdfs": ["A. Players List.pdf"]}
    )  # fmt: skip
    (cache / "esdeveniments.json").write_text(json.dumps(evs), encoding="utf-8")
    conn = ensure_schema(tmp_path / "t.db")
    res = {r.esdeveniment: r for r in carrega(conn, cache)}
    assert res[50].estat == "desat"
    assert res[9].estat == "buit" and res[9].errors


def test_l_id_umb_es_hereta_d_una_altra_prova(tmp_path):
    cache = _cache(tmp_path, [200])
    conn = ensure_schema(tmp_path / "t.db")
    carrega(conn, cache)
    # Sense id enlloc: un de sintètic, que no es confon amb cap de la UMB.
    ids = [r[0] for r in conn.execute("SELECT umb_id FROM umb_jugadors")]
    assert ids and all(i.startswith("x:") for i in ids)
    assert "x:anguitacarlos:ES" in ids
    conn.execute("INSERT INTO umb_esdeveniments (id, nom, font) VALUES (999, 'Altra', 'x')")
    conn.execute("INSERT INTO umb_jugadors VALUES (999, 'ANGUITA Carlos', '0777', 'ES')")
    from fcbillar.umb_carrega import _hereta_ids

    assert _hereta_ids(conn) == 1
    assert conn.execute(
        "SELECT umb_id FROM umb_jugadors WHERE esdeveniment_id = 200 AND nom = 'ANGUITA Carlos'"
    ).fetchone()[:] == ("0777",)


def test_id_0000_no_es_cap_id(tmp_path):
    js = llegeix_jugadors(
        "Players List\n5 GARCIA Pedro ES 10 100 0000\n6 LOPEZ Juan ES 11 90 0000\n"
    )
    assert [j.umb_id for j in js] == [None, None]
    conn = ensure_schema(tmp_path / "t.db")
    conn.execute("INSERT INTO umb_esdeveniments (id, nom, font) VALUES (1, 'A', 'x')")
    conn.executemany(
        "INSERT INTO umb_jugadors VALUES (1, ?, '0000', 'ES')", [("GARCIA Pedro",), ("LOPEZ Juan",)]
    )
    from fcbillar.umb_carrega import _hereta_ids

    _hereta_ids(conn)
    ids = {r[0] for r in conn.execute("SELECT umb_id FROM umb_jugadors")}
    assert ids == {"x:garciapedro:ES", "x:lopezjuan:ES"}


def test_un_id_compartit_per_dues_persones_es_separa(tmp_path):
    from fcbillar.umb_carrega import _hereta_ids

    conn = ensure_schema(tmp_path / "t.db")
    for i in (1, 2, 3):
        conn.execute(f"INSERT INTO umb_esdeveniments (id, nom, font) VALUES ({i}, 'A', 'x')")
    conn.executemany(
        "INSERT INTO umb_jugadors VALUES (?, ?, '2166', 'TR')",
        [(1, "YAVUZ Tarik"), (2, "YAVUZ Tarik"), (3, "YILMAZ Savas")],
    )
    conn.executemany(
        "INSERT INTO umb_jugadors VALUES (?, ?, '0211', 'ES')",
        [(1, "MAS Jose-Maria"), (2, "MAS Jose Maria"), (3, "MAS José María")],
    )
    _hereta_ids(conn)
    ids = dict(conn.execute("SELECT nom, umb_id FROM umb_jugadors"))
    assert ids["YAVUZ Tarik"] == "2166"
    assert ids["YILMAZ Savas"] == "x:yilmazsavas:TR"
    assert {
        i for n, i in conn.execute("SELECT nom, umb_id FROM umb_jugadors") if n.startswith("MAS")
    } == {"0211"}


def test_mundial_per_equips_nacionals():
    text = (
        "37th World Championship Nat. Teams 3-Cushion\n"
        "QUARTER FINALS\n"
        "Game Nation Match / players T-car T-Inn Av MP HR\n"
        "THE NETHERLANDS JASPERS Dick 40 28 1.428 2 7\n"
        "53\n"
        "KOREA CHO Myung Woo 28 28 1.000 0 4\n"
        "THE NETHERLANDS DE BRUIJN Jean Pau 33 25 1.320 0 8\n"
        "54\n"
        "SPAIN LEGAZPI Ruben 40 25 1.600 2 9\n"
        "Match Nation MP CAR INN GAV HR DC_SET\n"
        "THE NETHERLANDS 2 73 53 1.377 8 15\n"
        "27\n"
        "SPAIN 2 68 53 1.283 9 11\n"
    )
    assert es_equips(text)
    ps, errs = llegeix_equips(text, ["THE NETHERLANDS", "KOREA", "SPAIN"], "x")
    assert errs == [] and len(ps) == 2
    assert (ps[0].a.jugador, ps[0].a.nacio, ps[0].b.nacio) == ("JASPERS Dick", "NL", "KR")
    assert (ps[1].b.jugador, ps[1].b.nacio, ps[1].b.caramboles) == ("LEGAZPI Ruben", "ES", 40)
    assert ps[1].fase == "QUARTER FINALS"
    llista = (
        "Teams\n"
        "TEAM PLAYERS RESERVE\n"
        "1 LEGAZPI Ruben ANGUITA Carlos\n"
        "4 SPAIN\n"
        "2 JIMENEZ Sergio CRESPO Carlos\n"
        "1 CEULEMANS Peter MERCKX Eddy\n"
        "9 BELGIUM 2 FORTHOMME Roland LONCELLE Johann\n"
    )
    assert noms_de_la_llista_d_equips(llista, ["BELGIUM", "SPAIN"]) == [
        "LEGAZPI Ruben",
        "ANGUITA Carlos",
        "JIMENEZ Sergio",
        "CRESPO Carlos",
        "CEULEMANS Peter",
        "MERCKX Eddy",
        "FORTHOMME Roland",
        "LONCELLE Johann",
    ]


def test_pagina_d_esdeveniment():
    html = (
        '<meta /><script type="application/ld&#x2B;json">{"@type": "SportsEvent", '
        '"name": "World Cup 3-Cushion", "startDate": "2013-11-04", "endDate": "2013-11-09", '
        '"location": {"name": "MEDELLIN"}}</script>'
        '<a href="https://files.umb-carom.org/Uploads/Results/50/A. Players List.pdf">x</a>'
        '<a href="http://files.umb-carom.org/Uploads/Results/50/B.%20Groups.pdf">x</a>'
        '<a href="https://files.umb-carom.org/Uploads/Results/51/Altre.pdf">x</a>'
        '<a href="https://files.umb-carom.org/Uploads/Hotel Forms.docx">x</a>'
    )
    ev = llegeix_esdeveniment(50, html)
    assert ev is not None
    assert (ev.nom, ev.lloc, ev.inici) == ("World Cup 3-Cushion", "MEDELLIN", "2013-11-04")
    assert ev.pdfs == ["A. Players List.pdf", "B. Groups.pdf"]
    assert llegeix_esdeveniment(1, "<html>res</html>") is None


def test_disciplines():
    assert disciplina_de("World Cup 3-Cushion") == "3 bandes"
    assert disciplina_de("World Championship Cadre 47/2") == "quadre"
    assert disciplina_de("World Championship 5 pins") == "5 quilles"
    assert disciplina_de("Verhoeven Open Tournament") is None


# ------------------------------------ candidats ------------------------------------

CENS = [
    JugadorCens("1", "LEGAZPI CAÑIZARES, RUBEN", "C.B. A"),
    JugadorCens("2", "JIMENEZ GARCIA, SERGIO", "C.B. B"),
    JugadorCens("3", "JIMENEZ LOPEZ, SERGIO", "C.B. C"),
    JugadorCens("4", "ORTIZ TORRENT, ANTONI", "C.B. D"),
    JugadorCens("5", "SANCHEZ PEREZ, DANIEL", "C.B. E"),
]


def test_nom_natural():
    assert nom_natural("LEGAZPI Ruben") == "Ruben LEGAZPI"
    assert nom_natural("DE LA TORRE Juan Carlos") == "Juan Carlos DE LA TORRE"
    assert nom_natural("KIM") == "KIM"


def test_candidats_amb_els_motius_de_la_nacional(tmp_path):
    trobats = proposa(
        [
            JugadorUmb("0132", "LEGAZPI Ruben", 5),
            JugadorUmb("0189", "JIMENEZ Sergio", 4),  # dos al cens: ambigu, cap candidat
            JugadorUmb("0300", "ORTIZ Toni", 2),  # Toni = Antoni
            JugadorUmb("0301", "SANCHEZ PEREZ Daniel", 1),
        ],
        CENS,
    )
    per_umb = {j.umb_id: (m, c.fcb_id) for j, m, c in trobats}
    assert per_umb["0132"] == ("un cognom", "1")
    assert per_umb["0300"] == ("un cognom", "4")
    assert per_umb["0301"] == ("exacte", "5")
    assert "0189" not in per_umb

    csv = tmp_path / "fitxes.csv"
    assert escriu_candidats(trobats, csv) == (0, 3)
    assert escriu_candidats(trobats, csv) == (3, 0)  # no duplica
    text = csv.read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("validat,umb_id,jugador_umb")
    # Mai res de validat: ho decideix una persona.
    assert lligams_validats(csv) == {}
    csv.write_text(text.replace("\n,0132,", "\nsi,0132,"), encoding="utf-8")
    assert lligams_validats(csv) == {"0132": "1"}


# -------------------------------------- CEB --------------------------------------

PAGINA_CEB = """
<div id="onglet_6" class="onglet_texte">
 <div class="box_ligne box_titres"><div>Position</div><div>Player</div></div>
 <div class="box_ligne"><div><em>1</em></div><div>SANCHEZ Daniel (ES)</div><div>Placed</div></div>
 <div class="box_ligne"><div><em>2</em></div><div>JASPERS Dick (NL)</div><div>Placed</div></div>
</div>
<div id="onglet_8" class="onglet_texte">
 <div class="box_ligne box_titres"><div>Date</div></div>
 <div class="box_ligne"><div>14-06-2022 10:00</div><div>1</div><div>1</div><div>Final</div><div></div>
  <div><span class="bleu">SANCHEZ Daniel </span><br><span class="rouge">JASPERS Dick </span></div>
  <div><span class="bleu">2</span><br><span class="rouge">0</span></div>
  <div><span class="bleu">40</span><br><span class="rouge">31</span></div>
  <div><span class="bleu">21</span><br><span class="rouge">20</span></div>
  <div><span class="bleu">1.904</span><br><span class="rouge">1.550</span></div>
  <div><span class="bleu">7</span><br><span class="rouge">5</span></div></div>
 <div class="box_ligne"><div>14-06-2022 12:00</div><div>2</div><div>2</div><div>Final</div><div></div>
  <div><span class="bleu">A </span><br><span class="rouge">B </span></div>
  <div><span class="bleu"></span><br><span class="rouge"></span></div></div>
</div>
<div id="onglet_9" class="onglet_texte">
 <div class="box_ligne box_titres"><div>Place</div></div>
 <div class="box_ligne"><div>1</div><div>SANCHEZ Daniel (ES)</div><div>10</div><div>250</div><div>114</div>
  <div>2.192</div><div>9</div><div>2.631</div></div>
 <div class="box_ligne"><div>2</div><div>JASPERS Dick (NL)</div><div>8</div><div>235</div><div>99</div>
  <div>2.373</div><div>12</div><div>3.333</div></div>
</div>
"""


def test_pagina_de_la_ceb():
    from fcbillar.ceb import llegeix_pagina

    ll = llegeix_pagina(PAGINA_CEB.encode("utf-8"))
    assert len(ll.partides) == 1  # la partida sense jugar no compta
    p = ll.partides[0]
    assert (p.fase, p.a.jugador, p.a.caramboles, p.a.entrades, p.b.serie) == (
        "Final",
        "SANCHEZ Daniel",
        40,
        21,
        5,
    )
    assert [(c.posicio, c.jugador, c.nacionalitat) for c in ll.classificacio] == [
        (1, "SANCHEZ Daniel", "ES"),
        (2, "JASPERS Dick", "NL"),
    ]
    assert ll.classificacio[0].mitjana_particular == 2.631
    assert {(j.nom, j.nacionalitat) for j in ll.jugadors} == {
        ("SANCHEZ Daniel", "ES"),
        ("JASPERS Dick", "NL"),
    }


def test_valors_amb_desempat_o_en_blanc_a_la_ceb():
    from fcbillar.ceb import _enter, _mitjana

    assert _enter("120 (3)") == 120
    assert _mitjana("", "250", "1") == 250.0
    assert _mitjana("7.05", "120 (3)", "17") == 7.05


def test_llista_d_esdeveniments_de_la_ceb():
    from fcbillar.ceb import DESPLACAMENT, es_individual, llegeix_llista

    html = (
        "<tr><td>15-09-2017<br>17-09-2017</td><td>x</td><td>"
        "<a href='/events/ec-3c-u21-375.html' >European Championship 3-Cushion U21</a><br>"
        "<td>3-Cushion</td><td></td><td>X</td><td>Ronchin (FRA)</td></tr>"
        "<tr><td>25-09-2017<br>01-10-2017</td><td>&nbsp;</td><td>"
        "<a href='http://www.umb-carom.org/' target=\"_blank\">World Cup</a>"
        "<td>3-Cushion</td><td>Ronchin (FRA)</td></tr>"
        "<tr><td>01-10-2017<br>02-10-2017</td><td>x</td><td>"
        "<a href='/events/cde-5p-clubs-372.html'>Coupe d'Europe 5-Pins Club Teams</a>"
        "<td>5 pins</td><td>Y (BEL)</td></tr>"
    )
    evs = llegeix_llista(html)
    assert [e.id for e in evs] == [DESPLACAMENT + 375, DESPLACAMENT + 372]
    assert evs[0].inici == "2017-09-15" and evs[0].lloc == "Ronchin (FRA)"
    assert [es_individual(e) for e in evs] == [True, False]


def test_modalitats_d_un_campionat_que_n_aplega_unes_quantes():
    from fcbillar.ceb import DESPLACAMENT, es_individual, modalitats
    from fcbillar.umb_descarrega import Esdeveniment

    html = """
    <a href="#" onClick="eventTab('455');return false;" title="European Championships Classics">
    <a href="#" onClick="eventTab('490');return false;" title="European Championship 1-Cushion">
    <a href="#" onClick="eventTab('492');return false;" title="European Championships  Balkline 71/2">
    <a href="#" onClick="eventTab('493');return false;" title="European Championship 3-Cushion Teams">
    """
    ev = Esdeveniment(
        id=DESPLACAMENT + 455, nom="European Championships Classics", lloc="Cervera (ESP)",
        inici="2025-05-27", fi="2025-06-01", descripcio="", pdfs=[],
        font="https://www.eurobillard.org/events/ec classics-455.html",
    )  # fmt: skip
    ms = modalitats(html, ev)
    assert [m.id - DESPLACAMENT for m in ms] == [490, 492, 493]
    assert ms[1].nom == "European Championships Balkline 71/2"
    assert (ms[0].lloc, ms[0].inici, ms[0].fi, ms[0].font) == (ev.lloc, ev.inici, ev.fi, ev.font)
    assert [es_individual(m) for m in ms] == [True, True, False]


# --- partides a sets de 15 (fins al 2011) -----------------------------------------

GRUPS_A_SETS = """SLUISKIL WORLD CUP / GRAND PRIX
21 till 27 January 2008 -- Sluiskil (NL)
Qual Groups ABC
Group Match players S1-Car S1-Inn S2-Car S2-Inn S3-Car S3-Inn T-car T-Inn Av MP Sets HR
A MANCINI Giorgio 15 14 15 7 30 21 1,428 2 2 6
BLAUWBLOMME Henk 8 13 10 7 18 20 0,900 0 -2 7
DEMMING Adrie 12 10 15 17 15 9 42 36 1,166 2 1 6
MANCINI Giorgio 15 11 13 16 8 9 36 36 1,000 0 -1 6
Players Nat T-Car T-Inn Gen-Av MP Ba-Sets HR Place
MANCINI Giorgio IT 66 57 1,157 2 1 6 1
"""

#: La capçalera de les eliminatòries surt en tres línies, i es juga a cinc sets.
ELIMINATORIA_A_SETS = """21 till 27 January 2008 -- Sluiskil (NL) 1/16 Matches
S1- S1- S2- S2- S3- S3- S4- S4- S5- S5-
Match players Nat T-car T-Inn Av MP Sets HR
Car Inn Car Inn Car Inn Car Inn Car Inn
BLOMDAHL Torbjorn SE 9 11 4 7 15 11 15 4 15 7 58 40 1,450 2 1 9
PALAZON Javier ES 15 11 15 8 10 10 9 4 10 6 59 39 1,512 0 -1 7
"""


def test_sets_el_total_es_el_de_davant_de_la_mitjana():
    ps, errs = llegeix_partides(GRUPS_A_SETS, set(), "Q")
    assert not errs
    a, b = ps[0].a, ps[0].b
    assert (a.jugador, a.caramboles, a.entrades, a.punts, a.serie) == (
        "MANCINI Giorgio",
        30,
        21,
        2,
        6,
    )
    assert a.sets == [(15, 14), (15, 7)]
    # La diferència de sets negativa («-2») no es pren per la sèrie.
    assert (b.caramboles, b.entrades, b.punts, b.serie, b.sets) == (
        18,
        20,
        0,
        7,
        [(8, 13), (10, 7)],
    )
    # Tres sets: el perdedor de la partida pot guanyar-ne un.
    assert ps[1].a.sets == [(12, 10), (15, 17), (15, 9)]
    assert text_sets(ps[1].b.sets) == "15/11,13/16,8/9"


def test_sets_guanya_qui_guanya_mes_sets_no_mes_caramboles():
    ps, _ = llegeix_partides(ELIMINATORIA_A_SETS, set(), "1/16")
    [p] = ps
    assert (p.a.jugador, p.a.caramboles, p.a.punts) == ("BLOMDAHL Torbjorn", 58, 2)
    assert (p.b.jugador, p.b.caramboles, p.b.punts) == ("PALAZON Javier", 59, 0)
    assert len(p.a.sets) == 5 and p.b.sets[0] == (15, 11)
    assert (p.a.serie, p.b.serie) == (9, 7)


def test_sense_sets_res_no_canvia():
    text = """Match players Nat T-Car T-Inn Penalty T-car T-Inn Av MP HR
ZANETTI Marco IT 40 31 40 31 1,290 2 6
GARZON Cesar CO 33 31 33 31 1,064 0 5
"""
    [p] = llegeix_partides(text, set(), "1/16")[0]
    assert (p.a.caramboles, p.a.entrades, p.a.sets, p.b.serie) == (40, 31, [], 5)
    assert text_sets(p.a.sets) is None


def test_classificacio_del_web_vell_amb_punts_de_partida_en_forma_de_marcador():
    """«12:2» són les partides guanyades i perdudes; el nom hi va com «Monique VAN EXTER»."""
    from fcbillar.umb import llegeix_classificacio

    text = (
        "European Championship Ladies Libre\n"
        "RANK Players NAT MP CAR INN AVERAGE HR\n"
        "1 Monique VAN EXTER NL 12:2 938 103 9,11 64\n"
        "3 Véronique ALES FR 4:8 377 108 3,49 27\n"
    )
    primera, tercera = llegeix_classificacio(text)
    assert (primera.jugador, primera.nacionalitat, primera.punts) == ("VAN EXTER Monique", "NL", 12)
    assert (primera.caramboles, primera.entrades, primera.mitjana, primera.serie1) == (
        938,
        103,
        9.11,
        64,
    )
    assert (tercera.posicio, tercera.jugador) == (3, "ALES Véronique")


def test_un_jugador_que_es_diu_frank_no_es_una_fase():
    # «Frank 3» contenia «rank 3» i la fila de Spruzina passava per títol de fase.
    from fcbillar.umb import _fase_de_linia

    assert _fase_de_linia("SPRUZINA Frank 3 13 4 16 7 29 0,241 0 -2 1") is None
    assert _fase_de_linia("Pre-Qual Groups DEF") == "Pre-Qual Groups DEF"


def test_disciplina_de_les_proves_de_tres_bandes_que_el_nom_no_diu():
    from fcbillar.umb_carrega import disciplina_de

    assert disciplina_de("The World Games 2017 (3C)") == "3 bandes"
    assert disciplina_de("UMB Lausanne Billard Masters U25") == "3 bandes"
    assert disciplina_de("International Invitation Tournament Crystal Kelly") == "3 bandes"
    assert disciplina_de("European Cup Final Club Team Carom Series") is None
