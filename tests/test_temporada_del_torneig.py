"""La temporada d'un torneig surt del torneig, no del dia que s'ingereix.

`ingest-individuals` etiquetava tot el llistat amb «la temporada d'avui», amb el
tall a l'agost. La temporada és part de la clau d'un torneig, o sigui que un de
la temporada vella que encara fos al llistat el dia 1 d'agost —l'Open de Mataró
es juga al juliol i la federació triga a treure'l— s'hauria desat un altre cop,
com a nou, a la temporada següent.

I el llistat que no es podia baixar tornava «0 torneigs, 0 partides» i la
comanda sortia bé: ara és un error.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fcbillar import cli, pipeline
from fcbillar.config import Settings
from fcbillar.db.migrations import ensure_schema
from fcbillar.individuals import Divisio, Grup, Partida

FIXTURES = Path(__file__).parent / "fixtures" / "nou"
LLISTAT = (FIXTURES / "individuals_llistat_2026_10.html").read_text(encoding="utf-8")


def _partida(data: date | None) -> Partida:
    return Partida(1, "Grup A", data, "A, A", 30, 5, "B, B", 20, 4, 40, None, None)


def _divisio(torneig: int, *dates: date | None, grups: tuple[date, ...] = ()) -> Divisio:
    return Divisio(
        torneig_id_extern=torneig,
        divisio_id_extern=torneig * 2,
        nom=f"TORNEIG {torneig}",
        partides=[_partida(d) for d in dates],
        grups=[Grup(1, "Grup A", data=d) for d in grups],
    )


@pytest.fixture
def conn(tmp_path):
    return ensure_schema(tmp_path / "t.db")


# --------------------------- d'on surt ---------------------------


def test_un_torneig_de_juliol_es_de_la_temporada_que_s_acaba(conn) -> None:
    """Mataró: es juga el 18 de juliol de 2026 i és de la 2025-2026, s'ingereixi quan s'ingereixi."""
    divisions = [_divisio(211, date(2026, 7, 18), date(2026, 7, 4))]

    assert pipeline.temporada_de_torneig(conn, 211, divisions) == "2025-2026"


def test_un_de_setembre_es_de_la_nova(conn) -> None:
    assert (
        pipeline.temporada_de_torneig(conn, 217, [_divisio(217, date(2026, 9, 4))]) == "2026-2027"
    )


def test_mana_el_primer_dia_que_s_hi_juga(conn) -> None:
    """Un campionat que comença al setembre i acaba al maig és d'una sola temporada."""
    divisions = [_divisio(216, date(2027, 5, 8), date(2026, 9, 19))]

    assert pipeline.temporada_de_torneig(conn, 216, divisions) == "2026-2027"


def test_la_data_del_grup_tambe_val(conn) -> None:
    """Les eliminatòries no porten data; el sorteig del grup sí."""
    divisions = [_divisio(219, None, grups=(date(2026, 9, 26),))]

    assert pipeline.temporada_de_torneig(conn, 219, divisions) == "2026-2027"


def test_la_que_ja_te_a_la_base_de_dades_no_es_toca(conn) -> None:
    """És part de la clau: amb una altra se'n crearia un de nou al costat."""
    conn.execute("INSERT INTO temporades (id, nom) VALUES (1, '2025-2026')")
    conn.execute(
        "INSERT INTO torneigs_individuals (torneig_id_extern, divisio_id_extern, nom, temporada_id) "
        "VALUES (211, 447, 'OPEN TRES BANDES MATARO', 1)"
    )

    assert pipeline.temporada_de_torneig(conn, 211, [_divisio(211, date(2026, 9, 1))]) == (
        "2025-2026"
    )


def test_sense_base_ni_dates_no_s_inventa_res(conn) -> None:
    assert pipeline.temporada_de_torneig(conn, 300, [_divisio(300, None, None)]) is None


# --------------------------- la ingesta del llistat ---------------------------


class _Client:
    def __init__(self, settings, llistat: str | None) -> None:
        self.settings, self._llistat = settings, llistat

    def fetch_html(self, url: str, **_k) -> str:
        if self._llistat is None:
            raise RuntimeError("HTTP 500")
        return self._llistat


@pytest.fixture
def entorn(tmp_path, monkeypatch):
    settings = Settings(db_path=tmp_path / "t.db", cache_dir=tmp_path / "cache")
    desats: list[tuple[str, str]] = []

    def _desa(_conn, div, temporada, **_k):
        desats.append((div.nom, temporada))
        return {"partides": len(div.partides), "participants": 2, "fases": 1, "grups": 1}

    monkeypatch.setattr(pipeline, "desa_torneig", _desa)
    # Les regles dels PDF de sorteig es baixen del web de la federació: aquí no.
    monkeypatch.setattr("fcbillar.sorteig_fase.desa_regles", lambda *_a, **_k: (0, []))
    monkeypatch.setattr(pipeline, "_ingereix_fora_del_llistat", lambda *_a, **_k: _RES_FORA)
    return settings, desats


_RES_FORA = {"torneigs": 0, "partides": 0, "participants": 0, "oficials": 0, "deduides": 0}


def test_cada_torneig_del_llistat_va_a_la_seva_temporada(entorn, monkeypatch) -> None:
    """Un de la temporada vella encara al llistat no s'endú l'etiqueta dels altres."""
    settings, desats = entorn
    dates = {
        216: date(2026, 9, 19),
        217: date(2026, 9, 4),
        218: date(2026, 10, 3),
        219: date(2026, 9, 26),
        220: date(2026, 7, 11),  # com si encara hi hagués un torneig de juliol
    }
    monkeypatch.setattr(
        pipeline, "llegeix_torneig", lambda _c, tid, _nom, **_k: [_divisio(tid, dates[tid])]
    )

    res = pipeline.ingest_individuals_temporada(_Client(settings, LLISTAT), settings=settings)

    assert res.torneigs_failed == 0
    assert dict(desats) == {
        "TORNEIG 216": "2026-2027",
        "TORNEIG 217": "2026-2027",
        "TORNEIG 218": "2026-2027",
        "TORNEIG 219": "2026-2027",
        "TORNEIG 220": "2025-2026",
    }


def test_un_torneig_sense_dates_agafa_la_dels_altres_del_llistat(entorn, monkeypatch) -> None:
    settings, desats = entorn
    monkeypatch.setattr(
        pipeline,
        "llegeix_torneig",
        lambda _c, tid, _nom, **_k: [_divisio(tid, None if tid == 220 else date(2026, 9, 19))],
    )

    res = pipeline.ingest_individuals_temporada(_Client(settings, LLISTAT), settings=settings)

    assert res.torneigs_failed == 0
    assert dict(desats)["TORNEIG 220"] == "2026-2027"


def test_si_cap_no_porta_dates_no_es_desa_i_compta_com_a_fallat(entorn, monkeypatch) -> None:
    """Val més no desar que desar amb la temporada que no és."""
    settings, desats = entorn
    monkeypatch.setattr(
        pipeline, "llegeix_torneig", lambda _c, tid, _nom, **_k: [_divisio(tid, None)]
    )

    res = pipeline.ingest_individuals_temporada(_Client(settings, LLISTAT), settings=settings)

    assert desats == []
    assert res.torneigs_failed == 5


def test_un_torneig_acabat_de_donar_d_alta_no_es_cap_fallada(entorn, monkeypatch) -> None:
    """Sense divisions i sense haver-lo vist mai: encara no hi ha res a llegir."""
    settings, _ = entorn
    monkeypatch.setattr(pipeline, "llegeix_torneig", lambda *_a, **_k: [])

    res = pipeline.ingest_individuals_temporada(_Client(settings, LLISTAT), settings=settings)

    assert (res.torneigs_processed, res.torneigs_failed) == (5, 0)


def test_un_torneig_que_ja_teniem_i_perd_les_divisions_si_que_ho_es(entorn, monkeypatch) -> None:
    settings, _ = entorn
    conn = ensure_schema(settings.db_path)
    conn.execute(
        "INSERT INTO torneigs_individuals (torneig_id_extern, divisio_id_extern, nom) "
        "VALUES (216, 454, 'TRES BANDES INDIVIDUAL - HONOR')"
    )
    conn.commit()
    monkeypatch.setattr(pipeline, "llegeix_torneig", lambda *_a, **_k: [])

    res = pipeline.ingest_individuals_temporada(_Client(settings, LLISTAT), settings=settings)

    assert res.torneigs_failed == 1


def test_un_llistat_que_no_es_pot_baixar_es_un_error(entorn) -> None:
    settings, _ = entorn

    with pytest.raises(pipeline.ErrorLlistat):
        pipeline.ingest_individuals_temporada(_Client(settings, None), settings=settings)


def test_una_pagina_sense_la_taula_de_torneigs_tambe(entorn) -> None:
    settings, _ = entorn

    with pytest.raises(pipeline.ErrorLlistat):
        pipeline.ingest_individuals_temporada(
            _Client(settings, "<html><body>Manteniment</body></html>"), settings=settings
        )


# --------------------------- la comanda ---------------------------


class _ClientDeComanda:
    def __init__(self, *_a, **_k) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_a) -> None:
        return None


def test_la_comanda_surt_amb_error_si_el_llistat_falla(tmp_path, monkeypatch) -> None:
    settings = Settings(db_path=tmp_path / "t.db", cache_dir=tmp_path / "cache")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "ScraperClient", _ClientDeComanda)

    def _peta(*_a, **_k):
        raise pipeline.ErrorLlistat("No he pogut baixar el llistat d'individuals")

    monkeypatch.setattr(cli, "ingest_individuals_temporada", _peta)

    res = CliRunner().invoke(cli.app, ["ingest-individuals"])

    assert res.exit_code == 1


def test_la_comanda_surt_amb_error_si_un_torneig_falla(tmp_path, monkeypatch) -> None:
    """Abans era una línia groga i «OK individuals: 5 torneigs (1 fallats)»."""
    settings = Settings(db_path=tmp_path / "t.db", cache_dir=tmp_path / "cache")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "ScraperClient", _ClientDeComanda)
    monkeypatch.setattr(
        cli,
        "ingest_individuals_temporada",
        lambda *_a, **_k: pipeline.IngestIndividualsResult(4, 1, 250, 370),
    )

    res = CliRunner().invoke(cli.app, ["ingest-individuals"])

    assert res.exit_code == 1
    assert "1 torneigs del llistat han fallat" in " ".join(res.output.split())
