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
from fcbillar.umb import clau, llegeix_jugadors, llegeix_prova, separa_nom
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
