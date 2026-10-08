"""La Copa que s'ingereix és la del llistat de la federació, no una d'escrita.

La reingesta nocturna duia `COPA_EDICIO=7`: tornava a baixar cada nit l'edició
de la 2025-26, ja acabada —vuitanta peticions—, i el dia que la federació
n'obrís una de nova no l'hauria demanat ningú. La pàgina `copa/llistat` hi era
i no la mirava res.

Del llistat amb copes no en tenim cap captura: des del canvi de web sempre s'ha
vist buit. La forma de les files és la de tots els altres llistats del portal, i
és el que es prova aquí amb una fila feta a mà.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest
from typer.testing import CliRunner

from fcbillar import cli
from fcbillar.config import Settings
from fcbillar.db.migrations import ensure_schema
from fcbillar.scraper.parsers import parse_copa_llistat

FIXTURES = Path(__file__).parent / "fixtures" / "nou"
BUIT = (FIXTURES / "copa_llistat.html").read_text(encoding="utf-8")


def _llistat(*files: str) -> str:
    return (
        '<div class="card"><div class="card-header">COPES</div><div class="card-body">'
        "<table><thead><tr><th>Copa</th><th>Estat</th><th>Data límit inscripció</th><th></th>"
        f"</tr></thead><tbody>{''.join(files)}</tbody></table></div></div>"
    )


AMB_LA_8 = _llistat(
    "<tr><td>Copa Catalana 2026-27</td><td>Activa</td><td>2027-04-30</td>"
    '<td><a href="/frontend/copa/fase-grups/8">Veure</a></td></tr>'
)
SENSE_ENLLAC = _llistat(
    "<tr><td>Copa Catalana 2026-27</td><td>Inscripció</td><td></td><td></td></tr>"
)


# --------------------------- el llistat ---------------------------


def test_el_llistat_buit_de_debo_vol_dir_cap_copa() -> None:
    """La captura real: la taula hi és i no té files. No és un error."""
    assert parse_copa_llistat(BUIT) == ([], [])


def test_una_pagina_sense_la_taula_no_es_un_llistat_buit() -> None:
    """Si el portal canvia de forma no s'ha de confondre amb «no n'hi ha cap»."""
    assert parse_copa_llistat("<html><body><h1>Manteniment</h1></body></html>") is None


def test_l_edicio_surt_de_l_enllac_de_la_fila() -> None:
    obertes, descartades = parse_copa_llistat(AMB_LA_8)

    assert descartades == []
    assert [(c.edicio_id, c.nom, c.estat) for c in obertes] == [
        (8, "Copa Catalana 2026-27", "Activa")
    ]


def test_una_copa_sense_enllac_no_se_salta() -> None:
    """Es torna a part, perquè qui crida falli en comptes de donar-la per inexistent."""
    obertes, descartades = parse_copa_llistat(SENSE_ENLLAC)

    assert obertes == []
    assert descartades == ["Copa Catalana 2026-27"]


# --------------------------- la comanda ---------------------------


class _Client:
    """Un `ScraperClient` que serveix una sola pàgina i apunta què se li demana."""

    pagina: ClassVar[str] = BUIT
    demanades: ClassVar[list[str]] = []

    def __init__(self, *_a, **_k) -> None:
        pass

    def __enter__(self) -> _Client:
        return self

    def __exit__(self, *_a) -> None:
        return None

    def fetch_html(self, url: str, **_k) -> str:
        type(self).demanades.append(url)
        return type(self).pagina


@pytest.fixture
def entorn(tmp_path, monkeypatch):
    settings = Settings(db_path=tmp_path / "t.db", cache_dir=tmp_path / "cache")
    conn = ensure_schema(settings.db_path)
    conn.execute(
        "INSERT INTO copa_jornades (edicio_id, jornada, ordre, nom) VALUES (7, 26, 1, '1a')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "ScraperClient", _Client)
    _Client.demanades = []
    ingerides: list[int] = []

    def _ingereix(_client, edicio, **_k):
        ingerides.append(edicio)
        return type("R", (), {"jornades": 4, "grups": 20, "encontres": 55, "partides": 159})()

    monkeypatch.setattr(cli, "ingest_copa_edicio", _ingereix)
    return ingerides


def test_sense_cap_copa_oberta_no_es_baixa_res_i_surt_be(entorn) -> None:
    """El cas de cada nit fins al maig: una petició, i no les vuitanta de l'edició vella."""
    _Client.pagina = BUIT

    res = CliRunner().invoke(cli.app, ["ingest-copa"])

    assert res.exit_code == 0, res.output
    assert entorn == []
    assert len(_Client.demanades) == 1 and _Client.demanades[0].endswith("copa/llistat")
    assert "Cap copa oberta" in res.output


def test_s_ingereix_l_edicio_que_la_federacio_obre(entorn) -> None:
    _Client.pagina = AMB_LA_8

    res = CliRunner().invoke(cli.app, ["ingest-copa"])

    assert res.exit_code == 0, res.output
    assert entorn == [8]


def test_una_copa_que_no_se_sap_llegir_fa_fallar_el_pas(entorn) -> None:
    _Client.pagina = SENSE_ENLLAC

    res = CliRunner().invoke(cli.app, ["ingest-copa"])

    assert res.exit_code == 1
    assert entorn == []
    assert "ingest-copa <id>" in " ".join(res.output.split())


def test_si_la_pagina_canvia_de_forma_el_pas_falla(entorn) -> None:
    _Client.pagina = "<html><body>Error 500</body></html>"

    res = CliRunner().invoke(cli.app, ["ingest-copa"])

    assert res.exit_code == 1
    assert entorn == []


def test_amb_l_id_es_fa_com_sempre(entorn) -> None:
    """L'argument es queda, per tornar a baixar una edició concreta a mà."""
    res = CliRunner().invoke(cli.app, ["ingest-copa", "7"])

    assert res.exit_code == 0, res.output
    assert entorn == [7]
    assert _Client.demanades == [], "amb l'id no cal mirar el llistat"


def test_una_edicio_que_ja_teniem_i_no_dona_res_es_una_fallada(entorn, monkeypatch) -> None:
    """De la 7 en tenim jornades. Si ara no en surt cap, la font ha canviat."""
    monkeypatch.setattr(
        cli,
        "ingest_copa_edicio",
        lambda *_a, **_k: type(
            "R", (), {"jornades": 0, "grups": 0, "encontres": 0, "partides": 0}
        )(),
    )

    res = CliRunner().invoke(cli.app, ["ingest-copa", "7"])

    assert res.exit_code == 1
    assert "ha desaparegut" in " ".join(res.output.split())
