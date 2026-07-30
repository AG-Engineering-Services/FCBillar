"""Tests del parser del calendari esportiu federatiu (PDF de la RFEB).

El fixture és el PDF real de la temporada 2026/2027 (V.1, 28/07/2026). Els casos
comproven les tres coses que poden trencar-se en silenci quan la federació torna a
publicar el fitxer: la graella de columnes, la derivació de dates (el PDF no
escriu l'any) i la distinció entre nom de competició i seu.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from fcbillar.calendari_fed import (
    COLUMNES,
    Esdeveniment,
    _es_seu,
    descobreix_fcb,
    diff,
    ingest_calendari,
    parse_calendari,
    rfeb_url,
    temporada_actual,
)

FIXTURE = Path(__file__).parent / "fixtures" / "cal_rfeb_2627.pdf"


@pytest.fixture(scope="module")
def cal():
    return parse_calendari(FIXTURE.read_bytes())


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
        assert (c.disciplina, c.ambit, c.tipus or "") in {
            (d, a, t or "") for d, a, t in vistes
        }, f"cap esdeveniment a la columna {c}"


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
    (n,) = conn.execute(
        "SELECT count(*) FROM calendari_events WHERE titol = 'INVENTAT'"
    ).fetchone()
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


def test_descobreix_fcb_del_layout():
    """L'enllaç al calendari de la FCB surt al layout de qualsevol pàgina del web,
    amb la versió dins el nom del fitxer."""
    html = """
    <a href="https://www.fcbillar.cat/media/2025-2026/CALENDARIS/CALENDARI%20FCB%202025-26%20V-9.pdf">cal</a>
    <a href="/media/2026-2027/CALENDARIS/CALENDARI FCB 2026-27 V-2.pdf">nou</a>
    <a href="/media/2025-2026/COMPETICIO/OPENS/altra-cosa.pdf">no és calendari</a>
    """
    trobats = descobreix_fcb(html)
    assert [(c.temporada, c.versio) for c in trobats] == [
        ("2026/2027", "V-2"),
        ("2025/2026", "V-9"),
    ]
    assert trobats[0].nom_fitxer == "CALENDARI FCB 2026-27 V-2.pdf"
    assert trobats[1].url.startswith("https://www.fcbillar.cat/media/2025-2026/CALENDARIS/")
