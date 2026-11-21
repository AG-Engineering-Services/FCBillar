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


def test_una_prova_nova_es_desa_amb_l_id_desplacat(tmp_path):
    from fcbillar.db.migrations import ensure_schema
    from fcbillar.kozoom_carrega import carrega, seleccio

    _cache(tmp_path, "712", "classificacio_ec_712_2023.html", TITOL_EC)
    assert seleccio(tmp_path) == ["712"]
    conn = ensure_schema(tmp_path / "t.db")
    (r,) = carrega(conn, tmp_path, ["712"])
    assert (r.esdeveniment, r.estat) == (300712, "desat")
    fila = conn.execute(
        "SELECT posicio, caramboles FROM umb_classificacions WHERE esdeveniment_id = 300712 AND jugador = 'MATA Esteve'"
    ).fetchone()
    assert tuple(fila) == (8, 317)


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
