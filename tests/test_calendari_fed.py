"""Tests dels parsers del calendari esportiu federatiu (PDF de la RFEB i de la FCB).

Els fixtures són els PDF reals de la temporada 2026/2027 (RFEB V.1 del 28/07/2026;
FCB V-1 del 07/08/2026). Els casos comproven les coses que poden trencar-se en
silenci quan una federació torna a publicar el fitxer: la graella de columnes, la
derivació de dates (cap dels dos PDF no escriu l'any) i, a la RFEB, la distinció
entre nom de competició i seu.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from fcbillar.calendari_fed import (
    CARRILS_FCB,
    COLUMNES,
    Esdeveniment,
    _es_seu,
    descobreix_fcb,
    diff,
    ingest_calendari,
    parse_calendari,
    parse_calendari_fcb,
    rfeb_url,
    temporada_actual,
)

FIXTURE = Path(__file__).parent / "fixtures" / "cal_rfeb_2627.pdf"
FIXTURE_FCB = Path(__file__).parent / "fixtures" / "cal_fcb_2627_v1.pdf"


@pytest.fixture(scope="module")
def cal():
    return parse_calendari(FIXTURE.read_bytes())


@pytest.fixture(scope="module")
def cal_fcb():
    return parse_calendari_fcb(FIXTURE_FCB.read_bytes(), versio="V-1")


def test_capcalera(cal):
    assert cal.temporada == "2026/2027"
    assert cal.versio == "V.1"
    assert cal.data_versio == dt.date(2026, 7, 28)
    assert len(cal.sha256) == 64


def test_setmanes_i_dates(cal):
    """53 setmanes de dilluns, de finals d'agost a finals d'agost."""
    setmanes = sorted({e.setmana for e in cal.esdeveniments})
    assert all(s.weekday() == 0 for s in setmanes)
    assert min(setmanes) >= dt.date(2026, 8, 24)
    assert max(setmanes) <= dt.date(2027, 8, 23)
    # Les dates de cada esdeveniment cauen dins la seva setmana.
    for e in cal.esdeveniments:
        assert e.setmana <= e.data_inici <= e.data_fi <= e.setmana + dt.timedelta(days=6)


def test_columnes_totes_representades(cal):
    """Cada columna de la graella ha de produir esdeveniments: si una queda buida,
    és que el mapatge de COLUMNES ha quedat desplaçat."""
    vistes = {(e.disciplina, e.ambit, e.tipus) for e in cal.esdeveniments}
    for c in COLUMNES:
        assert (c.disciplina, c.ambit, c.tipus or "") in {(d, a, t or "") for d, a, t in vistes}, (
            f"cap esdeveniment a la columna {c}"
        )


def test_lliga_nacional_reparteix_per_dies(cal):
    """La LIGA NACIONAL no té seu i diu què es juga cada dia: Honor el dissabte i
    1ª-2ª divisió el diumenge."""
    e = next(
        x
        for x in cal.esdeveniments
        if x.setmana == dt.date(2026, 9, 7) and x.tipus == "equips" and x.ambit == "nacional"
    )
    assert e.titol == "LIGA NACIONAL 3 BANDAS"
    assert e.dissabte == "HONOR J1"
    assert e.diumenge == "1ª-2ª DIV. J1"
    assert e.seu is None


def test_setmana_amb_un_sol_dia(cal):
    """Hi ha setmanes on la Liga Nacional només juga el diumenge (sense Honor):
    el repartiment ha de mirar la data real de cada línia, no l'ordre."""
    e = next(
        x
        for x in cal.esdeveniments
        if x.setmana == dt.date(2026, 9, 21) and x.tipus == "equips" and x.ambit == "nacional"
    )
    assert e.dissabte is None
    assert e.diumenge == "1ª-2ª DIV. J2"


def test_campionat_amb_seu(cal):
    e = next(
        x
        for x in cal.esdeveniments
        if x.setmana == dt.date(2026, 10, 12) and x.ambit == "nacional" and x.tipus == "individual"
    )
    assert e.titol == "CTO. DE ESPAÑA · CUADRO 47/2"
    assert e.seu == "Cervera (LÉRIDA)"
    assert e.dissabte is None and e.diumenge is None


def test_cella_fusionada(cal):
    """Nadal i Setmana Santa són cel·les que travessen columnes: han de sortir una
    sola vegada, sense tipus ni àmbit, i marcades amb col_span > 1."""
    fusionats = [e for e in cal.esdeveniments if e.col_span > 1]
    titols = {e.titol for e in fusionats}
    assert titols == {"NAVIDAD - AÑO NUEVO", "SEMANA SANTA"}
    for e in fusionats:
        assert e.ambit == "tot"
        assert e.tipus is None


@pytest.mark.parametrize(
    "text, esperat",
    [
        ("Cervera (LÉRIDA)", True),
        ("(KOREA)", True),
        ("Sede R.F.E.B", True),
        ("?", True),
        ("ZARAGOZA", True),
        ("VALLADOLID", True),
        ("Móstoles (MADRID)", True),
        ("TRES BANDAS", False),  # modalitat, no localitat
        ("HONOR J1", False),
        ("1ª-2ª DIV. J1", False),
        ("LIGA NACIONAL 3 BANDAS", False),
        ("5 QUILLAS", False),
        ("PRIMERA", False),
    ],
)
def test_es_seu(text, esperat):
    assert _es_seu(text) is esperat


def test_diff_detecta_alta_baixa_i_canvi():
    def ev(setmana: str, titol: str, seu: str | None = None) -> Esdeveniment:
        d = dt.date.fromisoformat(setmana)
        return Esdeveniment(
            font="RFEB",
            temporada="2026/2027",
            setmana=d,
            data_inici=d,
            data_fi=d,
            disciplina="carambola",
            ambit="nacional",
            grup="Tres bandes",
            tipus="equips",
            titol=titol,
            seu=seu,
            dissabte=None,
            diumenge=None,
            col_span=1,
            raw="",
        )

    abans = [ev("2026-09-07", "A"), ev("2026-09-14", "B")]
    despres = [ev("2026-09-07", "A", seu="Vic"), ev("2026-09-21", "C")]
    canvis = {c.tipus_canvi: c for c in diff(abans, despres)}
    assert set(canvis) == {"modificacio", "baixa", "alta"}
    assert canvis["modificacio"].abans == "A"
    assert canvis["modificacio"].despres == "A · @ Vic"
    assert canvis["baixa"].setmana == dt.date(2026, 9, 14)
    assert canvis["alta"].setmana == dt.date(2026, 9, 21)


def test_ingest_idempotent(tmp_path):
    """Reingestar el mateix PDF no ha de tornar a escriure ni inventar canvis."""
    db = tmp_path / "test.db"
    r1 = ingest_calendari(db, pdf_bytes=FIXTURE.read_bytes())
    assert r1["estat"] == "actualitzat"
    assert r1["n_events"] == r1["n_canvis"] > 0  # primera vegada: tot són altes

    r2 = ingest_calendari(db, pdf_bytes=FIXTURE.read_bytes())
    assert r2["estat"] == "sense-canvis"

    import sqlite3

    conn = sqlite3.connect(str(db))
    (n,) = conn.execute("SELECT count(*) FROM calendari_events").fetchone()
    assert n == r1["n_events"]
    (nv,) = conn.execute("SELECT count(*) FROM calendari_versions").fetchone()
    assert nv == 1


def test_ingest_reemplaça_les_baixes(tmp_path):
    """Una revisió nova ha de fer desaparèixer el que la federació ha tret."""
    db = tmp_path / "test.db"
    ingest_calendari(db, pdf_bytes=FIXTURE.read_bytes())
    import sqlite3

    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO calendari_events (font, temporada, setmana, disciplina, ambit, grup, "
        "tipus, data_inici, data_fi, titol, raw) VALUES "
        "('RFEB','2026/2027','2027-08-23','carambola','nacional','Tres bandes','equips',"
        " '2027-08-28','2027-08-29','INVENTAT','')"
    )
    conn.commit()
    conn.close()

    r = ingest_calendari(db, pdf_bytes=FIXTURE.read_bytes(), force=True)
    assert any(c.tipus_canvi == "baixa" and c.abans == "INVENTAT" for c in r["canvis"])
    conn = sqlite3.connect(str(db))
    (n,) = conn.execute("SELECT count(*) FROM calendari_events WHERE titol = 'INVENTAT'").fetchone()
    assert n == 0


@pytest.mark.parametrize(
    "any_inici, url",
    [
        (2026, "https://rfeb.org/cal_rfeb_2627.pdf"),
        (2027, "https://rfeb.org/cal_rfeb_2728.pdf"),
        (2029, "https://rfeb.org/cal_rfeb_2930.pdf"),
        (2099, "https://rfeb.org/cal_rfeb_9900.pdf"),
    ],
)
def test_rfeb_url(any_inici, url):
    assert rfeb_url(any_inici) == url


@pytest.mark.parametrize(
    "avui, esperat",
    [
        (dt.date(2026, 7, 30), 2025),  # encara som a la 25/26
        (dt.date(2026, 8, 1), 2026),  # l'1 d'agost ja compta com a temporada nova
        (dt.date(2026, 12, 31), 2026),
        (dt.date(2027, 1, 1), 2026),
    ],
)
def test_temporada_actual(avui, esperat):
    assert temporada_actual(avui) == esperat


# --- Calendari de la FCB ----------------------------------------------------


def test_fcb_capcalera(cal_fcb):
    """La temporada s'escriu «2026/27» i s'ha de normalitzar a la mateixa forma
    que la RFEB, o la web no ajuntaria les dues fonts en una sola temporada."""
    assert cal_fcb.font == "FCB"
    assert cal_fcb.temporada == "2026/2027"
    assert cal_fcb.versio == "V-1"
    # El PDF no diu la revisió enlloc: la data surt de quan es va generar.
    assert cal_fcb.data_versio == dt.date(2026, 8, 7)


def test_fcb_nomes_la_meitat_catalana(cal_fcb):
    """De la meitat estatal del PDF no se n'ingesta res: ja entra per la RFEB."""
    carrils = {c.grup for c in CARRILS_FCB}
    for e in cal_fcb.esdeveniments:
        assert e.disciplina == "carambola"
        if e.ambit == "tot":  # Nadal, Setmana Santa
            continue
        assert e.ambit == "catala"
        assert e.grup in carrils


def test_fcb_tots_els_carrils_representats(cal_fcb):
    vistos = {e.grup for e in cal_fcb.esdeveniments}
    for c in CARRILS_FCB:
        assert c.grup in vistos, f"cap esdeveniment al carril {c.grup}"


def test_fcb_dates_dins_la_setmana(cal_fcb):
    """Cada acte cau dins la seva setmana. Els festius no: cobreixen justament les
    setmanes que la graella se salta, i per això en poden ocupar més d'una."""
    for e in cal_fcb.esdeveniments:
        assert e.setmana.weekday() == 0
        assert e.setmana <= e.data_inici <= e.data_fi
        if e.ambit != "tot":
            assert e.data_fi <= e.setmana + dt.timedelta(days=6)


def test_fcb_clau_unica(cal_fcb):
    """La clau natural és la clau primària de `calendari_events`: si dos carrils
    xoquessin, la ingesta en perdria un sense dir res."""
    claus = [e.clau() for e in cal_fcb.esdeveniments]
    assert len(claus) == len(set(claus))


def test_fcb_lliga_completa(cal_fcb):
    """Les 14 jornades de la Lliga 3 Bandes i les 14 de la de 4 Modalitats hi han
    de ser totes: si el parser perdés una fila, es notaria aquí i enlloc més."""
    text = " ".join(
        " ".join(p for p in (e.titol, e.dissabte, e.diumenge) if p)
        for e in cal_fcb.esdeveniments
        if e.tipus == "equips"
    )
    for n in range(1, 15):
        assert f"{n}ª jornada LL3B" in text, f"falta la jornada {n} de la LL3B"
    assert "FINALS LLIGA 3 BANDES" in text
    assert "FINAL COPA" in text


def test_fcb_cella_que_continua_al_diumenge(cal_fcb):
    """«Final Quadre 47/2» (ds) + «3ª Div.» (dg) és un sol acte partit en dues
    ratlles, no dues coses diferents."""
    e = next(
        x
        for x in cal_fcb.esdeveniments
        if x.setmana == dt.date(2026, 11, 30) and x.grup == "Campionats de Catalunya"
    )
    assert e.titol == "Final Quadre 47/2 3ª Div."
    assert e.dissabte is None and e.diumenge is None


def test_fcb_setmana_repartida_per_dies(cal_fcb):
    """Quan cada dia es juga una cosa, el títol passa a ser el del carril i el
    detall va al dia que toca."""
    e = next(
        x
        for x in cal_fcb.esdeveniments
        if x.setmana == dt.date(2026, 10, 5) and x.tipus == "equips"
    )
    assert e.titol == "Lligues catalanes"
    assert e.dissabte == "2ª jornada LL3B"
    assert e.diumenge == "1a jornada 4M"


def test_fcb_columnes_del_mateix_carril_es_juxtaposen(cal_fcb):
    """Les prèvies simultànies ocupen columnes diferents del mateix carril i han
    de sortir totes en un sol esdeveniment de la setmana."""
    e = next(
        x
        for x in cal_fcb.esdeveniments
        if x.setmana == dt.date(2026, 9, 14) and x.grup == "Campionats de Catalunya"
    )
    assert e.titol == (
        "Pre-Prèvia 3 Bandes 1ª Divisió · Prèvia 3 Bandes Div. Honor "
        "· Pre-Prèvia 3 Bandes 2ª Divisió"
    )
    assert e.col_span == 3


def test_fcb_festius(cal_fcb):
    """Nadal no cau en cap fila de dia —la graella se salta aquelles setmanes— i
    igualment ha de quedar registrat, amb `ambit = 'tot'` perquè la web no el
    llisti com si fos una competició."""
    festius = [e for e in cal_fcb.esdeveniments if e.ambit == "tot"]
    assert {e.titol for e in festius} == {"NADAL 2026", "SETMANA SANTA"}
    nadal = next(e for e in festius if e.titol == "NADAL 2026")
    assert nadal.data_inici == dt.date(2026, 12, 21)
    assert nadal.data_fi == dt.date(2027, 1, 1)
    assert all(e.tipus is None for e in festius)


def test_fcb_ingest_idempotent(tmp_path):
    db = tmp_path / "test.db"
    r1 = ingest_calendari(db, pdf_bytes=FIXTURE_FCB.read_bytes(), font="FCB", versio="V-1")
    assert r1["estat"] == "actualitzat"
    assert r1["n_events"] > 50
    assert ingest_calendari(db, pdf_bytes=FIXTURE_FCB.read_bytes(), font="FCB")["estat"] == (
        "sense-canvis"
    )


def test_fcb_i_rfeb_conviuen(tmp_path):
    """Les dues fonts comparteixen taula i temporada: cap de les dues no ha de
    trepitjar l'altra ni sortir al diff de l'altra."""
    db = tmp_path / "test.db"
    ingest_calendari(db, pdf_bytes=FIXTURE.read_bytes())
    r = ingest_calendari(db, pdf_bytes=FIXTURE_FCB.read_bytes(), font="FCB", versio="V-1")
    assert all(c.tipus_canvi == "alta" for c in r["canvis"])

    import sqlite3

    conn = sqlite3.connect(str(db))
    per_font = dict(
        conn.execute("SELECT font, count(*) FROM calendari_events GROUP BY font").fetchall()
    )
    assert per_font["FCB"] == r["n_events"]
    assert per_font["RFEB"] > 0


def test_descobreix_fcb_de_la_pagina_del_document():
    """Amb el web nou, el PDF s'enllaça des de la pàgina del document.

    La temporada i la versió surten del nom del fitxer, que és l'únic lloc on
    la federació les escriu: la ruta només porta identificadors.
    """
    html = """
    <a href="https://fcbillar.cat/download/36/calendari/232324/calendari-fcb-2026-27-v-2.pdf">baixa</a>
    <a href="https://fcbillar.cat/download/36/calendari/230001/calendari-fcb-2025-26-v-9.pdf">l'antic</a>
    <a href="https://fcbillar.cat/download/6/ranquings/230343/ranquing-opens-3-bandes-25-26.pdf">no és calendari</a>
    """
    trobats = descobreix_fcb(html)
    assert [(c.temporada, c.versio) for c in trobats] == [
        ("2026/2027", "V-2"),
        ("2025/2026", "V-9"),
    ]
    assert trobats[0].nom_fitxer == "calendari-fcb-2026-27-v-2.pdf"
    assert trobats[0].url.endswith("/calendari-fcb-2026-27-v-2.pdf")


def test_descobreix_fcb_ignora_el_que_no_sap_col_locar():
    """Sense temporada al nom no el sabem posar a cap lloc: val més deixar-lo."""
    html = '<a href="https://fcbillar.cat/download/36/calendari/1/calendari-fcb.pdf">x</a>'
    assert descobreix_fcb(html) == []


def test_la_versio_de_la_rfeb_tambe_va_en_minuscula():
    """La V.1 del juliol de 2026 anava amb majúscula i la v.1.2 de l'agost no.

    Sense això la revisió entrava sense versió ni data, i la capçalera del web
    seguia atribuint les dades a la revisió anterior.
    """
    from fcbillar.calendari_fed import _RE_VERSIO

    for text, versio in [
        ("CALENDARIO V.1 actualizado a 28/07/2026", "V.1"),
        ("CALENDARIO v.1.2 actualizado a 28/08/2026", "v.1.2"),
    ]:
        m = _RE_VERSIO.search(text)
        assert m is not None, text
        assert m.group(1) == versio
