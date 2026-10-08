"""El pas nocturn dels rànquings de mitjana, contra les pàgines del 8/10/2026.

Aquell dia l'últim rànquing que teníem era el 124, del 27 de juliol, i la
federació ja havia publicat el 126 (2 d'octubre). No s'havia carregat per tres
motius, i cada test de sota n'aguanta un:

1. ningú no l'anava a buscar: els rànquings els ingeria la tasca del PC, que
   està aturada des de l'agost, i la reingesta del núvol només els republicava;
2. encara que hi hagués anat, no l'hauria sabut llegir: la federació havia tret
   les columnes `MR` i `Rang` del rànquing vigent, i la taula es buscava per
   «Rang»;
3. l'índex tenia DUES files de vigents (126 i 124) i totes dues es datarien
   amb la data de la primera.

Les captures són de `intranet.fcbillar.cat/frontend/rankings/…`, públiques:
l'índex, el 126 de Quadre 71/2 (30 jugadors) i les partides d'un d'ells.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from test_pipeline import FIXTURES, StubScraperClient, StubSettings

from fcbillar.db.migrations import ensure_schema
from fcbillar.db.repository import Repository
from fcbillar.models import Ranking
from fcbillar.pipeline import ingest_ranking, ingest_ranquings_vigents
from fcbillar.ranking_dates import month_for_publication_date
from fcbillar.scraper.parsers import (
    parse_home_current_rankings,
    parse_ranking,
    parse_rankings_index,
)

BASE = "https://intranet.fcbillar.cat"
INDEX = f"{BASE}/frontend/rankings/llistat"
DADES_126_6 = f"{BASE}/frontend/rankings/llistat-dades?idranking=126&idmodalitat=6"
PARTIDES_126_6_551 = (
    f"{BASE}/frontend/rankings/llistat-partides?idranking=126&idmodalitat=6&idjugador=551"
)

URLS = {
    INDEX: "nou/rankings_llistat_2026_10.html",
    DADES_126_6: "nou/rankings_dades_vigent_126_6.html",
    PARTIDES_126_6_551: "nou/rankings_partides_vigent_126_6_551.html",
}

MODALITATS = (1, 2, 3, 4, 6)


def _html(nom: str) -> str:
    return (FIXTURES / nom).read_text(encoding="utf-8")


@pytest.fixture
def settings(tmp_path: Path) -> StubSettings:
    return StubSettings(base_url=BASE, db_path=tmp_path / "test.db")


@pytest.fixture
def amb_el_124(settings: StubSettings) -> Repository:
    """La BD tal com era: el 124 de totes les modalitats, catalogat com a agost."""
    repo = Repository(ensure_schema(settings.db_path))
    for mod in MODALITATS:
        repo.upsert_ranking(
            Ranking(
                num_seq=124,
                modalitat_codi_fcb=mod,
                url="x",
                format_url="llistat",
                any_pub=2026,
                mes_pub=8,
                data_pub="2026-07-27",
            )
        )
    return repo


def _rankings(settings: StubSettings) -> list[tuple]:
    conn = ensure_schema(settings.db_path)
    return [
        tuple(r)
        for r in conn.execute(
            """SELECT m.codi_fcb, r.num_seq, r.any_pub, r.mes_pub, r.data_pub
               FROM rankings r JOIN modalitats m ON m.id = r.modalitat_id
               ORDER BY r.num_seq, m.codi_fcb"""
        )
    ]


# ---------------- el que es llegeix ----------------


def test_el_ranquing_vigent_es_llegeix_sense_mr_ni_rang() -> None:
    parsed = parse_ranking(_html(URLS[DADES_126_6]), 126, 6)

    assert len(parsed.entries) == 30
    primer = parsed.entries[0]
    assert parsed.players[0].nom == "TUSET MALLOL, CARLES"
    assert (primer.player_fcb_id, primer.posicio) == ("551", 1)
    assert primer.mitjana_general == pytest.approx(8.56204)
    assert primer.extras["caramboles"] == 1173
    assert primer.extras["entrades"] == 137
    assert (primer.extras["punts"], primer.extras["punts_totals"]) == (10, 20)
    assert primer.extras["definitiva"] is True
    # Les dues columnes que la federació ha tret: buides, no inventades.
    assert primer.extras["mitjana_contraris"] is None
    assert primer.extras["rang"] is None


def test_l_index_amb_dues_files_de_vigents_dona_el_mes_nou_de_cada_modalitat() -> None:
    html = _html(URLS[INDEX])

    # L'índex cru les porta totes dues, cadascuna amb la SEVA data…
    dates = {(r.num_seq, r.data) for r in parse_rankings_index(html).vigents}
    assert dates == {(126, date(2026, 10, 2)), (124, date(2026, 7, 27))}

    # …i «el vigent» n'és un per modalitat: el de número més alt.
    home = parse_home_current_rankings(html)
    assert home.data_ranking == date(2026, 10, 2)
    assert [(r.modalitat_codi_fcb, r.num_seq) for r in home.rankings] == [
        (m, 126) for m in MODALITATS
    ]
    assert {r.data for r in home.rankings} == {date(2026, 10, 2)}


def test_el_126_es_d_octubre_i_el_124_segueix_sent_d_agost() -> None:
    assert month_for_publication_date(date(2026, 10, 2), 126) == (2026, 10)
    assert month_for_publication_date(date(2026, 7, 27), 124) == (2026, 8)


# ---------------- el que es desa ----------------


def test_ingereix_el_ranquing_nou_amb_la_seva_data_i_no_toca_els_d_abans(
    settings: StubSettings, amb_el_124: Repository
) -> None:
    client = StubScraperClient(settings, URLS)
    res = ingest_ranquings_vigents(client, settings=settings)

    # El stub només serveix el de Quadre 71/2: la resta són publicats i no
    # desats, i s'han de dir, no passar per bons.
    assert res.nous == [(126, 6)]
    assert sorted(res.fallats) == [(126, m) for m in (1, 2, 3, 4)]
    assert res.refrescats == [] and res.endarrerits == []

    files = _rankings(settings)
    assert (6, 126, 2026, 10, "2026-10-02") in files
    # Cap 125 inventat per omplir el forat, i el 124 tal com estava.
    assert [f for f in files if f[1] == 124] == [
        (m, 124, 2026, 8, "2026-07-27") for m in MODALITATS
    ]
    assert len(files) == 6

    conn = ensure_schema(settings.db_path)
    assert conn.execute("SELECT COUNT(*) FROM ranking_entries").fetchone()[0] == 30
    assert amb_el_124.get_ranking_format_url(126, 6) == "llistat"


def test_baixa_les_partides_dels_jugadors_que_encara_no_en_tenen(
    settings: StubSettings, amb_el_124: Repository
) -> None:
    client = StubScraperClient(settings, URLS)
    res = ingest_ranquings_vigents(client, settings=settings)

    # Dels 30, el stub només té la pàgina del primer.
    assert res.jugadors_amb_partides == 1
    assert res.jugadors_fallats == 29
    assert res.jugadors_pendents == 0

    conn = ensure_schema(settings.db_path)
    links = conn.execute(
        """SELECT COUNT(*) FROM ranking_game_links l
           JOIN rankings r ON r.id = l.ranking_id
           JOIN players p ON p.id = l.player_id_origen
           WHERE r.num_seq = 126 AND p.fcb_id = '551'"""
    ).fetchone()[0]
    # Deu, no quinze: és la finestra de Quadre 71/2.
    assert links == 10
    assert res.partides_noves == 10


def test_repetir_la_passada_no_duplica_res_ni_torna_a_demanar_el_que_ja_te(
    settings: StubSettings, amb_el_124: Repository
) -> None:
    ingest_ranquings_vigents(StubScraperClient(settings, URLS), settings=settings)
    counts = Repository(ensure_schema(settings.db_path)).counts()
    files = _rankings(settings)

    client = StubScraperClient(settings, URLS)
    res = ingest_ranquings_vigents(client, settings=settings)

    # Ara el 126/6 ja és el nostre últim: es refresca, no es torna a crear.
    assert res.nous == []
    assert res.refrescats == [(126, 6)]
    assert res.partides_noves == 0
    assert Repository(ensure_schema(settings.db_path)).counts() == counts
    assert _rankings(settings) == files
    # I el jugador que ja té les partides lligades no es torna a baixar.
    assert PARTIDES_126_6_551 not in client.fetched_urls


def test_quan_s_acaba_el_temps_la_resta_queda_per_a_la_propera_passada(
    settings: StubSettings, amb_el_124: Repository
) -> None:
    client = StubScraperClient(settings, URLS)
    res = ingest_ranquings_vigents(client, settings=settings, pressupost_seg=0)

    # El rànquing es desa sempre; el que s'ajorna són les partides.
    assert res.nous == [(126, 6)]
    assert res.jugadors_amb_partides == 0
    assert res.jugadors_pendents == 30
    assert not any("llistat-partides" in u for u in client.fetched_urls)

    # La passada següent continua on s'havia quedat.
    res2 = ingest_ranquings_vigents(StubScraperClient(settings, URLS), settings=settings)
    assert res2.jugadors_amb_partides == 1


def test_els_jugadors_seguits_passen_davant_quan_el_temps_es_just(
    settings: StubSettings, amb_el_124: Repository
) -> None:
    ingest_ranquings_vigents(StubScraperClient(settings, URLS), settings=settings, partides=False)
    # El segon del rànquing (402) és seguit; el primer (551), no.
    amb_el_124.set_seguiment("402", True)

    # Un rellotge que deixa temps per a un sol jugador.
    temps = iter([0.0, 0.0, 100.0])
    client = StubScraperClient(settings, URLS)
    res = ingest_ranquings_vigents(
        client, settings=settings, pressupost_seg=50, rellotge=lambda: next(temps)
    )

    demanades = [u for u in client.fetched_urls if "llistat-partides" in u]
    assert len(demanades) == 1 and demanades[0].endswith("idjugador=402")
    assert res.jugadors_pendents == 29


def test_sense_partides_nomes_ingereix_els_ranquings(
    settings: StubSettings, amb_el_124: Repository
) -> None:
    client = StubScraperClient(settings, URLS)
    res = ingest_ranquings_vigents(client, settings=settings, partides=False)

    assert res.nous == [(126, 6)]
    assert not any("llistat-partides" in u for u in client.fetched_urls)


def test_si_ja_en_tenim_un_de_mes_nou_no_toca_res(settings: StubSettings) -> None:
    repo = Repository(ensure_schema(settings.db_path))
    for mod in MODALITATS:
        repo.upsert_ranking(
            Ranking(num_seq=127, modalitat_codi_fcb=mod, url="x", format_url="llistat")
        )
    client = StubScraperClient(settings, URLS)
    res = ingest_ranquings_vigents(client, settings=settings)

    assert res.nous == [] and res.refrescats == [] and res.fallats == []
    assert sorted(res.endarrerits) == [(126, m) for m in MODALITATS]
    assert client.fetched_urls == [INDEX]


def test_un_ranquing_sense_cap_fila_no_es_desa(settings: StubSettings, tmp_path: Path) -> None:
    """Una taula buida no ha de passar a ser «l'últim rànquing publicat»."""
    buida = tmp_path / "buida.html"
    buida.write_text(
        "<html><body><table><thead><tr><th>#</th><th>Jugador</th><th>MJ</th><th>C</th>"
        "<th>E</th><th>P / PT</th><th>Def</th><th></th></tr></thead><tbody></tbody></table>"
        + " " * 600
        + "</body></html>",
        encoding="utf-8",
    )
    # El stub llegeix `FIXTURES / nom`, i un camí absolut s'hi queda tal qual.
    client = StubScraperClient(settings, {DADES_126_6: str(buida)})

    assert ingest_ranking(client, 126, 6, settings=settings) is None
    assert _rankings(settings) == []
