"""Lector dels resultats de Kozoom (còpies del Wayback Machine)."""

from datetime import date
from pathlib import Path

from fcbillar.kozoom import (
    de_les_pagines_de_jugador,
    llegeix_classificacio,
    llegeix_partides,
    llegeix_titol,
    nom_umb,
    proves_del_jugador,
)

FIX = Path(__file__).parent / "fixtures" / "kozoom"


def _html(nom: str) -> str:
    return (FIX / nom).read_text(encoding="utf-8")


def test_noms_a_l_ordre_de_la_umb():
    assert nom_umb("Esteve MATA") == "MATA Esteve"
    assert nom_umb("Michel VAN SILFHOUT") == "VAN SILFHOUT Michel"
    assert nom_umb("Ricardo GARCIA ALARCON") == "GARCIA ALARCON Ricardo"


def test_titol():
    t = llegeix_titol("3-Cushion - World Cup - Hurghada (EGY) - 9/4/06 to 9/9/06")
    assert (t.disciplina, t.nom, t.inici, t.fi) == (
        "3-Cushion",
        "World Cup",
        date(2006, 9, 4),
        date(2006, 9, 9),
    )


def test_classificacio_del_quadre_71_2_de_l_europeu_2023():
    titol, files, _ = llegeix_classificacio(_html("classificacio_ec_712_2023.html"))
    assert (titol.disciplina, titol.nom) == ("Balk-Line 71/2", "European Championship")
    mata = next(f for f in files if f.jugador == "MATA Esteve")
    assert (mata.posicio, mata.caramboles, mata.entrades, mata.serie1, mata.nacionalitat) == (
        8,
        317,
        12,
        100,
        "ES",
    )


def test_partides_d_una_prova_amb_el_guanyador_marcat():
    titol, partides, jugadors = llegeix_partides(_html("partides_bundesliga.html"))
    assert titol.nom == "German 1st Bundesliga round 14"
    p = partides[0]
    assert (p.a.jugador, p.a.caramboles, p.a.entrades, p.a.serie, p.a.punts) == (
        "KERLS Uwe",
        40,
        55,
        6,
        2,
    )
    assert (p.b.jugador, p.b.caramboles, p.b.punts) == ("ZITLAU Jörg", 35, 0)
    assert "DE" in {j.nacionalitat for j in jugadors}


def test_partides_a_sets_des_de_la_pagina_d_un_jugador():
    html = _html("jugador_sets_hurghada_2006.html")
    _t, partides, _ = llegeix_partides(html)
    p = partides[0]
    assert p.a.sets == [(10, 13), (12, 14)] and p.b.sets == [(15, 13), (15, 15)]
    assert (p.a.punts, p.b.punts, p.a.caramboles, p.a.entrades) == (0, 2, 22, 27)
    assert proves_del_jugador(html)[0] == (
        550,
        "3-Cushion - World Cup - Séville (ESP) - 5/3/04 to 5/9/04",
    )


def test_una_partida_vista_des_dels_dos_jugadors_surt_un_cop():
    html = _html("jugador_sets_hurghada_2006.html")
    ll = de_les_pagines_de_jugador([html, html])
    assert len(ll.partides) == len(llegeix_partides(html)[1])


def _cache(tmp_path, pid: str, ranking: str, titol: str):
    import json
    import shutil

    shutil.copy(FIX / ranking, tmp_path / f"{pid}_rankings.html")
    (tmp_path / "proves.json").write_text(
        json.dumps({pid: {"id": pid, "titol": titol}}), encoding="utf-8"
    )


TITOL_EC = "Carom Billiard Ranking - Balk-Line 71/2 - European Championship - Antalya (TUR) - 4/12/23 to 4/13/23"


def test_una_prova_nova_es_desa_amb_l_id_desplacat(tmp_path, monkeypatch):
    from fcbillar import kozoom_carrega as kc
    from fcbillar.db.migrations import ensure_schema

    monkeypatch.setattr(kc, "ANY_MAX_NOVES", 2030)
    _cache(tmp_path, "712", "classificacio_ec_712_2023.html", TITOL_EC)
    assert kc.seleccio(tmp_path) == ["712"]
    conn = ensure_schema(tmp_path / "t.db")
    (r,) = kc.carrega(conn, tmp_path, ["712"])
    assert (r.esdeveniment, r.estat) == (300712, "desat")
    fila = conn.execute(
        "SELECT posicio, caramboles FROM umb_classificacions WHERE esdeveniment_id = 300712 AND jugador = 'MATA Esteve'"
    ).fetchone()
    assert tuple(fila) == (8, 317)


def test_del_2017_enca_kozoom_no_crea_cap_prova(tmp_path):
    from fcbillar.db.migrations import ensure_schema
    from fcbillar.kozoom_carrega import carrega

    _cache(tmp_path, "712", "classificacio_ec_712_2023.html", TITOL_EC)
    conn = ensure_schema(tmp_path / "t.db")
    (r,) = carrega(conn, tmp_path, ["712"])
    assert r.estat == "fora_d_abast"
    assert conn.execute("SELECT COUNT(*) FROM umb_esdeveniments").fetchone()[0] == 0


def test_una_prova_que_la_umb_ja_te_amb_partides_no_es_duplica(tmp_path):
    from fcbillar.db.migrations import ensure_schema
    from fcbillar.kozoom_carrega import carrega

    _cache(tmp_path, "712", "classificacio_ec_712_2023.html", TITOL_EC)
    conn = ensure_schema(tmp_path / "t.db")
    conn.execute(
        "INSERT INTO umb_esdeveniments (id, nom, disciplina, data_inici, font) "
        "VALUES (100050, 'European Championship Balkline 71/2', 'quadre', '2023-04-11', 'ceb')"
    )
    conn.execute(
        "INSERT INTO umb_partides (esdeveniment_id, fase, grup, ordre, jugador_a, jugador_b) "
        "VALUES (100050, 'G', 'A', 1, 'X', 'Y')"
    )
    (r,) = carrega(conn, tmp_path, ["712"])
    assert (r.esdeveniment, r.estat) == (100050, "ja_hi_es")
    assert (
        conn.execute("SELECT count(*) FROM umb_esdeveniments WHERE id = 300712").fetchone()[0] == 0
    )


def test_una_partida_llegida_a_dues_fonts_es_desa_un_sol_cop(tmp_path):
    from fcbillar.db.migrations import ensure_schema
    from fcbillar.kozoom_carrega import Firmes, treu_repetides
    from fcbillar.umb import Llegit

    titol, partides, _ = llegeix_partides(_html("partides_bundesliga.html"))
    conn = ensure_schema(tmp_path / "t.db")
    d = titol.inici.isoformat()
    conn.execute(
        "INSERT INTO umb_esdeveniments (id, nom, data_inici, data_fi, font) VALUES (7, 'x', ?, ?, 'umb')",
        (d, d),
    )
    # La mateixa partida que la primera de Kozoom, amb els noms escrits d'una altra manera
    # i els jugadors a l'inrevés.
    conn.execute(
        "INSERT INTO umb_partides (esdeveniment_id, fase, grup, ordre, jugador_a, caramboles_a, "
        "entrades_a, jugador_b, caramboles_b, entrades_b) "
        "VALUES (7, 'R', '', 1, 'Jorg Zitlau', 35, 55, 'Uwe Kerls', 40, 55)"
    )
    ll = Llegit(partides=list(partides))
    assert treu_repetides(Firmes(conn), ll, titol) == 1
    assert len(ll.partides) == len(partides) - 1
    assert ("KERLS Uwe", 40) not in {(p.a.jugador, p.a.caramboles) for p in ll.partides}


def test_la_pagina_mes_alta_de_partides():
    from fcbillar.kozoom_carrega import _ultima_pagina

    html = '<a href="/en/billiard-carom/results/9984/matches.html?page=2">2</a> <a href="?x"><a href="/en/billiard-carom/results/9984/matches.html?page=3">3</a>'
    assert _ultima_pagina(html) == 3
    assert _ultima_pagina("<p>sense paginació</p>") == 1


def test_els_anys_de_dos_xifres_inclouen_l_historic_dels_europeus():
    # Kozoom té també els europeus de 1947 o 1998: el «47» no és el 2047.
    t = llegeix_titol("Balk-Line 47/2 - European Championship - Brno (CZE) - 5/1/98 to 5/3/98")
    assert (t.inici, t.fi) == (date(1998, 5, 1), date(1998, 5, 3))
    t = llegeix_titol("3-Cushion - European Championship - Brussel (BEL) - 4/5/47 to 4/8/47")
    assert t.inici == date(1947, 4, 5)
    t = llegeix_titol("3-Cushion - World Cup - Porto (POR) - 6/26/23 to 7/2/23")
    assert t.inici == date(2023, 6, 26)


def test_la_seleccio_no_llegeix_la_classificacio_d_una_prova_internacional(tmp_path):
    import json

    from fcbillar.kozoom_carrega import seleccio

    proves = {
        "1": {
            "id": "1",
            "titol": "3-Cushion - European Championship - Brno (CZE) - 5/1/98 to 5/3/98",
        },
        "2": {
            "id": "2",
            "titol": "3-Cushion - Dutch National Championship - Wijchen (NED) - 1/1/05 to 1/2/05",
        },
        "3": {"id": "3", "titol": "text que no és un títol"},
    }
    (tmp_path / "proves.json").write_text(json.dumps(proves), encoding="utf-8")
    # Sense cap «rankings.html»: l'europeu entra pel títol, el nacional sense jugadors d'aquí no.
    assert seleccio(tmp_path) == ["1"]


def _umb_amb_partides(conn, classificacio: bool) -> None:
    conn.execute(
        "INSERT INTO umb_esdeveniments (id, nom, disciplina, data_inici, font) "
        "VALUES (200050, 'European Championship Cadre 71/2', 'quadre', '2023-04-11', 'ceb')"
    )
    conn.execute(
        "INSERT INTO umb_partides (esdeveniment_id, fase, grup, ordre, jugador_a, jugador_b) "
        "VALUES (200050, 'G', 'A', 1, 'X', 'Y')"
    )
    if classificacio:
        conn.execute(
            "INSERT INTO umb_classificacions (esdeveniment_id, posicio, jugador) "
            "VALUES (200050, 1, 'OFICIAL Un')"
        )


def test_si_la_prova_antiga_no_te_classificacio_s_hi_posa_la_de_kozoom(tmp_path):
    from fcbillar.db.migrations import ensure_schema
    from fcbillar.kozoom_carrega import carrega

    _cache(tmp_path, "712", "classificacio_ec_712_2023.html", TITOL_EC)
    conn = ensure_schema(tmp_path / "t.db")
    _umb_amb_partides(conn, classificacio=False)
    carrega(conn, tmp_path, ["712"])
    fila = conn.execute(
        "SELECT posicio, caramboles FROM umb_classificacions "
        "WHERE esdeveniment_id = 200050 AND jugador = 'MATA Esteve'"
    ).fetchone()
    assert tuple(fila) == (8, 317)


def test_la_classificacio_oficial_no_es_toca(tmp_path):
    from fcbillar.db.migrations import ensure_schema
    from fcbillar.kozoom_carrega import carrega

    _cache(tmp_path, "712", "classificacio_ec_712_2023.html", TITOL_EC)
    conn = ensure_schema(tmp_path / "t.db")
    _umb_amb_partides(conn, classificacio=True)
    carrega(conn, tmp_path, ["712"])
    noms = [
        f[0]
        for f in conn.execute(
            "SELECT jugador FROM umb_classificacions WHERE esdeveniment_id = 200050"
        )
    ]
    assert noms == ["OFICIAL Un"]


def test_la_classificacio_amb_la_bandera_en_una_cel_la_a_part():
    html = """<title>Carom Billiard Ranking - Artistic - World Championship - Schelle  (BEL) - 4/1/08 to 4/5/08 - Kozoom</title>
    <table class="listing"><thead><tr><th>Rank</th><th></th><th>Players</th></tr></thead><tbody>
    <tr><td>1</td><td><img src="/thumbnails/flag_16/images/fo/flags/be.png.png"></td>
    <td><a href="/en/billiard-carom/players/caudron-frederic/matches.html">Frédéric CAUDRON</a></td></tr>
    </tbody></table>"""
    _t, files, _j = llegeix_classificacio(html)
    assert [(f.posicio, f.jugador, f.nacionalitat) for f in files] == [
        (1, "CAUDRON Frédéric", "BE")
    ]


def test_dos_europeus_de_quadre_la_mateixa_setmana_no_es_confonen(tmp_path):
    from fcbillar.db.migrations import ensure_schema
    from fcbillar.kozoom import Titol
    from fcbillar.kozoom_carrega import _quadre, ja_hi_es

    assert (_quadre("European Championship Balkline 47/2"), _quadre("Balk-Line 71/2")) == (
        "47/2",
        "71/2",
    )
    conn = ensure_schema(tmp_path / "t.db")
    conn.execute(
        "INSERT INTO umb_esdeveniments (id, nom, disciplina, data_inici, font) "
        "VALUES (100411, 'European Championship Balkline 47/2', 'quadre', '2024-05-02', 'ceb')"
    )
    mateixa_setmana = date(2024, 5, 4)
    el_71 = Titol("Balk-Line 71/2", "European Championship", "Cervera (ESP)", mateixa_setmana, None)
    el_47 = Titol("Balk-Line 47/2", "European Championship", "Cervera (ESP)", mateixa_setmana, None)
    assert ja_hi_es(conn, el_71) is None
    assert ja_hi_es(conn, el_47).id == 100411


def test_una_prova_antiga_sense_disciplina_es_reconeix_pel_nom(tmp_path):
    from fcbillar.db.migrations import ensure_schema
    from fcbillar.kozoom import Titol
    from fcbillar.kozoom_carrega import ja_hi_es

    conn = ensure_schema(tmp_path / "t.db")
    conn.execute(
        "INSERT INTO umb_esdeveniments (id, nom, disciplina, data_inici, font) "
        "VALUES (200153, 'European Championship Ladies -3- Cushion', NULL, '2007-10-05', 'x')"
    )
    kozoom = Titol(
        "3-Cushion", "European Championship Ladies", "Roeser (LUX)", date(2007, 10, 5), None
    )
    assert ja_hi_es(conn, kozoom).id == 200153


def test_les_grafies_velles_de_la_disciplina():
    from fcbillar.umb_carrega import disciplina_de

    assert disciplina_de("European Championship Ladies -3- Cushion") == "3 bandes"
    assert disciplina_de("European Championship Artistique") == "artistic"
    assert disciplina_de("CMT-European Championship One Cushion") == "1 banda"


def test_l_inventari_s_atura_a_l_id_maxim(tmp_path, monkeypatch):
    import contextlib

    from fcbillar import kozoom_carrega as kc

    cdx = (
        "20200101000000 http://www.kozoom.com/en/billiard-carom/results/100/rankings.html\n"
        "20200101000000 http://www.kozoom.com/en/billiard-carom/results/30000/rankings.html\n"
    )
    demanades = []

    def _get(_c, url):
        demanades.append(url)
        return (
            cdx
            if "cdx" in url
            else "<title>3-Cushion - World Cup - X (ESP) - 1/1/10 - Kozoom</title>"
        )

    monkeypatch.setattr(kc, "_get", _get)
    monkeypatch.setattr(kc, "_client", lambda: contextlib.nullcontext())
    proves = kc.inventaria(tmp_path, espera=0, id_max=17500)
    assert list(proves) == ["100"]
    assert not any("/results/30000/" in u for u in demanades)


def test_fora_d_abast_el_billar_america_les_lligues_i_els_nacionals():
    from fcbillar.kozoom import Titol
    from fcbillar.kozoom_carrega import fora_d_abast

    def t(nom: str, disciplina: str = "3-Cushion") -> Titol:
        return Titol(disciplina=disciplina, nom=nom, lloc="", inici=None, fi=None)

    assert fora_d_abast(t("European Championship Women", "10-Ball"))
    assert fora_d_abast(t("European Championship Women", "Straight"))
    assert fora_d_abast(t("Buffalo League Round 12"))
    assert fora_d_abast(t("Belgian National Championship Round 4"))
    assert fora_d_abast(t("Spanish National Championship"))
    assert fora_d_abast(t("Grand Prix of Spain"))
    assert not fora_d_abast(t("World Cup"))
    assert not fora_d_abast(t("European Championship National Team"))
    assert not fora_d_abast(t("European Championship", "Balk-Line 71/2"))
    assert not fora_d_abast(t("European Cup Final Club Team", "Carom Series"))


def test_youth_i_juniors_women_i_ladies_son_el_mateix_tipus():
    from fcbillar.kozoom_carrega import _tipus

    assert _tipus("European Championship Youth 3-Cushion") == _tipus(
        "European Championship Juniors 3-Cushion"
    )
    assert _tipus("European Championship Women Free game") == _tipus(
        "European Championship Ladies Free game"
    )
    assert _tipus("European Championship Juniors 3-Cushion") != _tipus(
        "European Championship 3-Cushion"
    )


def test_el_ranquing_de_la_barra_no_es_una_classificacio():
    from fcbillar.kozoom_carrega import es_de_la_barra
    from fcbillar.umb import Classificat

    def fila(pos, nom, **kw):
        base = dict(nacionalitat="BE", ronda=None, punts=None, mitjana=None,
                    mitjana_particular=None, serie1=None, serie2=None, caramboles=None,
                    entrades=None)  # fmt: skip
        return Classificat(pos, nom, **(base | kw))

    barra = [fila(1, "JASPERS Dick"), fila(2, "CAUDRON Frédéric")]
    assert es_de_la_barra(barra)
    assert not es_de_la_barra([fila(1, "JASPERS Dick", mitjana=2.1), fila(2, "CAUDRON Frédéric")])
    assert not es_de_la_barra([])
