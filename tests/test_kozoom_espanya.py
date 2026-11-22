"""Les proves espanyoles de Kozoom van a les taules de la RFEB."""

from __future__ import annotations

import sqlite3
from datetime import date

from fcbillar.kozoom import Titol
from fcbillar.kozoom_espanya import (
    categoria,
    crea_taules,
    desa_nova,
    desa_partides,
    es_espanyola,
    ja_hi_es,
    temporada,
    tipus,
)
from fcbillar.umb import Classificat, Costat, Llegit, Partida


def _t(nom: str, lloc: str = "Madrid (ESP)", disc: str = "3-Cushion", d=date(2012, 6, 26)) -> Titol:
    return Titol(disciplina=disc, nom=nom, lloc=lloc, inici=d, fi=d)


def test_quines_son_espanyoles():
    assert es_espanyola(_t("Spanish National Championship"))
    assert es_espanyola(_t("Spain National Ladies Championship", lloc="(UNK)"))
    assert es_espanyola(_t("Grand Prix of Spain"))
    assert es_espanyola(_t("Juanjo Trilles Challenge", lloc="Marxuquera (ESP)"))
    # Un mundial o una copa del món jugats a Espanya són internacionals.
    assert not es_espanyola(_t("World Championship", lloc="Lugo (ESP)"))
    assert not es_espanyola(_t("World Cup", lloc="Alcalà (ESP)"))
    assert not es_espanyola(_t("European Championship", lloc="Cervera (ESP)", disc="1-Cushion"))
    # «Carom Series» no és cap modalitat.
    assert not es_espanyola(_t("National Tournament Round 1", lloc="(ESP)", disc="Carom Series"))
    assert not es_espanyola(_t("Invitational", lloc="Antwerp (BEL)"))


def test_categoria_tipus_i_temporada():
    assert categoria(_t("Spain National Junior Championship")) == "junior"
    assert categoria(_t("National Championship U21")) == "sub21"
    assert categoria(_t("Spain National Ladies Championship")) == "femeni"
    assert tipus(_t("Spanish League final round")) == "lliga"
    assert tipus(_t("Grand Prix of Spain")) == "gpe"
    assert temporada(date(2012, 6, 26)) == "2011-2012"
    assert temporada(date(2003, 10, 3)) == "2003-2004"


def _existent(**kw) -> dict:
    base = {"id": "x", "temporada": "2016-2017", "modalitat": "3b", "categoria": "absolut",
            "tipus": "ce", "titol": "", "lloc": None, "data_inici": None, "data_fi": None,
            "font": "f", "partides": 0}  # fmt: skip
    return base | kw


def test_casa_amb_la_prova_de_la_rfeb():
    t = _t("Spanish National Championship", d=date(2017, 6, 19))
    assert ja_hi_es(t, [_existent(id="ce")]).id == "ce"
    assert ja_hi_es(t, [_existent(categoria="sub21")]) is None
    # El «Junior» de Kozoom és el sub-17 de la RFEB.
    j = _t("Spain National Junior Championship", d=date(2010, 9, 25))
    assert ja_hi_es(j, [_existent(id="s17", temporada="2010-2011", categoria="sub17")]).id == "s17"
    # Un gran premi ha de començar la mateixa setmana.
    gp = _t("Grand Prix of Spain", d=date(2016, 7, 4))
    lluny = _existent(temporada="2015-2016", tipus="gpe", data_inici="2016-01-20")
    a_prop = _existent(id="mad", temporada="2015-2016", tipus="gpe", data_inici="2016-07-05")
    assert ja_hi_es(gp, [lluny]) is None
    assert ja_hi_es(gp, [lluny, a_prop]).id == "mad"


def _ll() -> Llegit:
    ll = Llegit()
    ll.classificacio = [Classificat(1, "MATA Esteve", "ES", None, 10, 1.2, None, 9, None, 120, 100)]
    a = Costat("MATA Esteve", 40, 1.0, 2, 9, None, entrades=40)
    b = Costat("SANCHEZ Daniel", 35, 0.875, 0, 7, None, entrades=40)
    ll.partides = [Partida("Final", "", 1, a, b)]
    return ll


def test_una_prova_nova_porta_classificacio_i_partides():
    conn = sqlite3.connect(":memory:")
    crea_taules(conn)
    prova_id, nc, np_ = desa_nova(conn, "8576", _t("Spanish National Championship"), _ll())
    assert (prova_id, nc, np_) == ("kozoom/8576", 1, 1)
    assert conn.execute("SELECT temporada, tipus, lloc FROM rfeb_proves").fetchone() == (
        "2011-2012",
        "ce",
        "Madrid",
    )
    assert conn.execute("SELECT entrades, serie_a FROM rfeb_partides").fetchone() == (40, 9)


def test_a_una_prova_de_la_rfeb_nomes_hi_van_les_partides():
    conn = sqlite3.connect(":memory:")
    crea_taules(conn)
    n = desa_partides(conn, _existent(id="noticias2016/res_ce_3b", titol="CE"), _ll())
    assert n == 1
    assert conn.execute("SELECT count(*) FROM rfeb_classificacions").fetchone()[0] == 0
    assert conn.execute("SELECT id, titol FROM rfeb_proves").fetchone() == (
        "noticias2016/res_ce_3b",
        "CE",
    )


def test_un_gran_premi_sense_data_es_casa_per_la_ciutat():
    gp = _t("Grand Prix of Spain", lloc="Madrid (ESP)", d=date(2016, 7, 4))
    llinars = _existent(id="noticias2015/res_gpe_3b_llinars", temporada="2015-2016", tipus="gpe")
    madrid = _existent(id="noticias2015/res_gpe_3b_madrid", temporada="2015-2016", tipus="gpe")
    assert ja_hi_es(gp, [llinars]) is None
    assert ja_hi_es(gp, [llinars, madrid]).id == "noticias2015/res_gpe_3b_madrid"


def test_la_lliga_no_porta_la_classificacio_d_equips():
    conn = sqlite3.connect(":memory:")
    crea_taules(conn)
    ll = _ll()
    ll.classificacio[0].jugador = "PAIPORTA"
    _id, nc, np_ = desa_nova(
        conn, "8350", _t("Spanish League final round", lloc="Gandia (ESP)"), ll
    )
    assert (nc, np_) == (0, 1)
    assert conn.execute("SELECT count(*) FROM rfeb_classificacions").fetchone()[0] == 0
