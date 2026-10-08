"""Les comandes de la reingesta nocturna, sense cap valor escrit i fallant quan toca.

La nocturna les crida sense arguments. Fins a l'octubre de 2026 això volia dir
«amb els valors per defecte del codi»: `--temporada "2026/2027"` a sis comandes.
El setembre de 2027 haurien seguit etiquetant-ho tot com a 2026/2027 i haurien
sortit bé totes.

I `ingest-lliga`, que ja seguia el llistat de la federació, s'empassava els
grups que petaven: una línia groga enmig de dues mil i `exit=0`.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from fcbillar import cli, cloud_sync, en_curs
from fcbillar.config import Settings
from fcbillar.db.migrations import ensure_schema
from fcbillar.scraper.parsers import LligaOberta

FIXTURES = Path(__file__).parent / "fixtures" / "nou"
LLISTAT = (FIXTURES / "lligues_llistat.html").read_text(encoding="utf-8")


@pytest.fixture
def settings(tmp_path, monkeypatch) -> Settings:
    for variable in ("FCB_LLIGA_3B_ID", "FCB_LLIGA_4M_ID", "FCB_TEMPORADA"):
        monkeypatch.delenv(variable, raising=False)
    s = Settings(db_path=tmp_path / "t.db", cache_dir=tmp_path / "cache")
    ensure_schema(s.db_path).close()
    monkeypatch.setattr(cli, "get_settings", lambda: s)
    return s


def _sortida(res) -> str:
    return " ".join(res.output.split())


# --------------------------- la temporada ---------------------------


def _obre_la_temporada(settings: Settings, any_inici: int) -> None:
    """El llistat de lligues vist, i un encontre que diu quan comença la temporada."""
    conn = ensure_schema(settings.db_path)
    en_curs.desa_lligues_obertes(
        conn,
        [
            LligaOberta(
                40, "Lliga Catalana Tres Bandes", "Tres bandes", date(any_inici, 9, 1), "Activa"
            )
        ],
    )
    conn.execute(
        "INSERT INTO encontres_lliga (lliga_id, divisio_id, grup_id, jornada_id, data) "
        "VALUES (40, 1, 1, 1, ?)",
        (f"{any_inici}-09-25",),
    )
    conn.execute(
        "INSERT INTO lliga_inscrits (temporada, lliga_id, lliga, modalitat, club, "
        "club_id_extern, jugador, mitjana, fitxatge, posicio) "
        "VALUES (?, 40, 'Lliga Catalana Tres Bandes', 'Tres bandes', 'C.B.BANYOLES', 16, "
        "'MAS, JOSEP', 0.5, 0, 1)",
        (f"{any_inici}/{any_inici + 1}",),
    )
    conn.commit()
    conn.close()


def test_la_temporada_de_la_comanda_es_la_de_les_lligues_obertes(settings) -> None:
    """El 2027 la comanda treballa amb la 2027/2028 sense que ningú toqui res."""
    _obre_la_temporada(settings, 2027)

    res = CliRunner().invoke(cli.app, ["afiliacions", "--sense-xarxa"])

    assert res.exit_code == 0, res.output
    conn = ensure_schema(settings.db_path)
    temporades = [f[0] for f in conn.execute("SELECT DISTINCT temporada FROM afiliacions")]
    assert temporades == ["2027/2028"]


def test_es_pot_demanar_una_altra_temporada(settings) -> None:
    _obre_la_temporada(settings, 2027)

    res = CliRunner().invoke(cli.app, ["afiliacions", "--sense-xarxa", "--temporada", "2026/2027"])

    assert res.exit_code == 0, res.output
    conn = ensure_schema(settings.db_path)
    assert conn.execute("SELECT COUNT(*) FROM afiliacions").fetchone()[0] == 0


@pytest.mark.parametrize("comanda", [["afiliacions", "--sense-xarxa"], ["plantilles"]])
def test_sense_saber_la_temporada_la_comanda_s_atura(settings, comanda) -> None:
    """Abans hauria treballat amb «2026/2027» i hauria sortit bé."""
    res = CliRunner().invoke(cli.app, comanda)

    assert res.exit_code == 1
    assert "No sé quina temporada és" in _sortida(res)


def test_ja_no_queda_cap_temporada_escrita_a_les_opcions() -> None:
    """Cap comanda no té una temporada concreta per defecte."""
    import click
    from typer.main import get_command

    escrites = []
    for nom, comanda in get_command(cli.app).commands.items():
        for param in comanda.params:
            es_la_temporada = isinstance(param, click.Option) and "--temporada" in param.opts
            if es_la_temporada and isinstance(param.default, str) and param.default[:2] == "20":
                escrites.append((nom, param.default))

    assert escrites == []


# --------------------------- ingest-lliga ---------------------------


class _Client:
    def __init__(self, *_a, **_k) -> None:
        pass

    def __enter__(self) -> _Client:
        return self

    def __exit__(self, *_a) -> None:
        return None

    def fetch_html(self, url: str, **_k) -> str:
        assert url.endswith("lligues/llistat"), url
        return LLISTAT


def _arbre(_client, lliga_id: int, **_k):
    """Una lliga amb una divisió i dos grups."""
    return SimpleNamespace(
        divisions=[SimpleNamespace(divisio_id=1, nom="HONOR")],
        grups_by_div={
            1: [
                SimpleNamespace(grup_id=lliga_id * 10 + 1, nom="GRUP A"),
                SimpleNamespace(grup_id=lliga_id * 10 + 2, nom="GRUP B"),
            ]
        },
    )


def _grup_be(*_a, **_k):
    return SimpleNamespace(
        jornades_processed=14,
        jornades_failed=0,
        total_encontres=56,
        total_games_upserted=0,
        total_games_skipped=4,
    )


@pytest.fixture
def lliga(settings, monkeypatch) -> Settings:
    monkeypatch.setattr(cli, "ScraperClient", _Client)
    monkeypatch.setattr(cli, "discover_lliga", _arbre)
    monkeypatch.setattr(cli, "ingest_lliga_grup", _grup_be)
    return settings


def test_ingest_lliga_desa_el_llistat_per_a_la_publicacio(lliga) -> None:
    """És d'aquí que `publish-cloud` sap quina lliga és la d'enguany."""
    res = CliRunner().invoke(cli.app, ["ingest-lliga"])

    assert res.exit_code == 0, res.output
    assert cloud_sync.lliga_a_publicar("3B", None, lliga.db_path) == 38
    assert cloud_sync.lliga_a_publicar("4M", None, lliga.db_path) == 39


def test_un_grup_que_peta_fa_fallar_el_pas_i_la_resta_s_ingereix(lliga, monkeypatch) -> None:
    ingerits: list[tuple[int, int]] = []

    def _un_peta(_client, *, lliga_id, grup_id, **_k):
        if (lliga_id, grup_id) == (39, 391):
            raise RuntimeError("HTTP 500")
        ingerits.append((lliga_id, grup_id))
        return _grup_be()

    monkeypatch.setattr(cli, "ingest_lliga_grup", _un_peta)

    res = CliRunner().invoke(cli.app, ["ingest-lliga"])

    assert res.exit_code == 1
    assert ingerits == [(39, 392), (38, 381), (38, 382)], "una lliga que falla no atura l'altra"
    assert "1 de 2 grups" in _sortida(res)


def test_una_jornada_fallada_tambe_compta(lliga, monkeypatch) -> None:
    """`ingest_lliga_grup` s'empassa les jornades que peten i les torna comptades."""
    monkeypatch.setattr(
        cli,
        "ingest_lliga_grup",
        lambda *_a, **_k: SimpleNamespace(
            jornades_processed=13,
            jornades_failed=1,
            total_encontres=52,
            total_games_upserted=0,
            total_games_skipped=0,
        ),
    )

    res = CliRunner().invoke(cli.app, ["ingest-lliga"])

    assert res.exit_code == 1


def test_una_lliga_que_tenia_encontres_i_no_en_dona_cap_es_una_fallada(lliga, monkeypatch) -> None:
    """La font ha desaparegut: abans sortia «OK lliga 38: 0 encontres»."""
    conn = ensure_schema(lliga.db_path)
    conn.execute(
        "INSERT INTO encontres_lliga (lliga_id, divisio_id, grup_id, jornada_id, data) "
        "VALUES (38, 1, 381, 1, '2026-09-26')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(
        cli, "discover_lliga", lambda *_a, **_k: SimpleNamespace(divisions=[], grups_by_div={})
    )

    res = CliRunner().invoke(cli.app, ["ingest-lliga"])

    assert res.exit_code == 1
    assert "ha desaparegut" in _sortida(res)


def test_una_lliga_oberta_que_encara_no_te_grups_no_es_cap_error(lliga, monkeypatch) -> None:
    """La federació obre la lliga setmanes abans de publicar-ne els grups."""
    monkeypatch.setattr(
        cli, "discover_lliga", lambda *_a, **_k: SimpleNamespace(divisions=[], grups_by_div={})
    )

    res = CliRunner().invoke(cli.app, ["ingest-lliga"])

    assert res.exit_code == 0, res.output


def test_una_fila_del_llistat_sense_llegir_fa_fallar_el_pas(lliga, monkeypatch) -> None:
    """Pot ser la lliga de la temporada nova, que no s'estaria ingerint."""
    monkeypatch.setattr(
        "fcbillar.inscrits_lliga.llegeix_lligues",
        lambda _c: (
            [LligaOberta(38, "Lliga Catalana Tres Bandes", "Tres bandes", None, "Activa")],
            ["Lliga Catalana 4 Modalitats"],
        ),
    )

    res = CliRunner().invoke(cli.app, ["ingest-lliga"])

    assert res.exit_code == 1
    assert "sense interpretar" in _sortida(res)


# --------------------------- publish-cloud ---------------------------


@pytest.fixture
def publicadors(settings, monkeypatch) -> list[str]:
    """Tots els `publish_*` de `cloud_sync` canviats per un que només s'apunta."""
    cridats: list[str] = []

    def _fals(nom: str):
        def _publica(*_a, **_k) -> dict[str, int]:
            cridats.append(nom)
            return {nom: 1}

        return _publica

    for nom in dir(cloud_sync):
        if nom.startswith("publish_"):
            monkeypatch.setattr(cloud_sync, nom, _fals(nom))
    return cridats


def test_si_no_se_sap_quina_lliga_es_la_resta_es_publica_i_el_pas_falla(
    publicadors, monkeypatch
) -> None:
    """Val més no publicar la lliga que publicar la de l'any passat sense dir-ho."""

    def _no_se_sap(*_a, **_k):
        raise en_curs.NoDeterminat("No sé quina és la lliga de Tres Bandes en curs")

    for nom in ("publish_lliga", "publish_lliga_player_rankings", "publish_lliga_encontres"):
        monkeypatch.setattr(cloud_sync, nom, _no_se_sap)

    res = CliRunner().invoke(cli.app, ["publish-cloud"])

    assert res.exit_code == 1
    assert "Publicació incompleta" in _sortida(res)
    # El que no és de lliga s'ha publicat igualment.
    for nom in ("publish_rankings", "publish_opens", "publish_open_ranking", "publish_calendari"):
        assert nom in publicadors


def test_el_pdf_del_ranquing_d_opens_que_no_es_troba_fa_fallar_la_publicacio(
    publicadors, monkeypatch
) -> None:
    """«PDF no aplicat… ronda marcada provisional» era un avís en groc."""
    monkeypatch.setattr(
        cloud_sync,
        "publish_open_ranking",
        lambda **_k: {"open_ranking": 187, "open_ranking_pdf_oficial": -1},
    )

    res = CliRunner().invoke(cli.app, ["publish-cloud"])

    assert res.exit_code == 1
    assert "open_ranking_pdf_oficial" in _sortida(res)
    assert "publish_calendari" in publicadors, "s'ha publicat fins al final"


def test_una_ronda_provisional_perque_encara_no_toca_no_es_cap_fallada(
    publicadors, settings, monkeypatch
) -> None:
    """El PDF hi és i encara no porta l'últim open: és l'estat normal uns dies."""
    monkeypatch.setattr(
        cloud_sync,
        "publish_open_ranking",
        lambda **_k: {"open_ranking": 187, "open_ranking_pdf_oficial": 0},
    )

    res = CliRunner().invoke(cli.app, ["publish-cloud"])

    assert res.exit_code == 0, res.output
    # I queda escrit per a `comprova-frescor`.
    deixat = json.loads(
        settings.db_path.with_name("darrera_publicacio.json").read_text(encoding="utf-8")
    )
    assert deixat["counts"]["open_ranking_pdf_oficial"] == 0
    assert deixat["no_publicat"] == []
