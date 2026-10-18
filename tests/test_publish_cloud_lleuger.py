"""`publish-cloud --lleuger` no torna a pujar les taules grosses.

Les passades horàries de cap de setmana el fan servir. L'octubre de 2026, amb
cada passada pujant-ho tot, es van esgotar els 5 GB de transferència de Neon.
"""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

import fcbillar.cloud_sync as cloud_sync
from fcbillar import cli

GROSSES = {
    "publish_rankings",
    "publish_games",
    "publish_open_ranking",
    "publish_open_ranking_femeni",
    "publish_player_clubs",
    "publish_afiliacions",
    "publish_rating_buckets",
    "publish_calendari",
    "publish_estadistiques_partides",
    "publish_estadistiques_computa",
    "publish_estadistiques_fitxa",
}


@pytest.fixture
def cridades(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> list[str]:
    fetes: list[str] = []
    for nom in dir(cloud_sync):
        if nom.startswith("publish_"):

            def fals(*_a: Any, _nom: str = nom, **_k: Any) -> dict[str, int]:
                fetes.append(_nom)
                return {}

            monkeypatch.setattr(cloud_sync, nom, fals)
    monkeypatch.setattr(cloud_sync, "publica_si_hi_es", lambda _n, fn, _p: fn())
    monkeypatch.setattr(cli, "_fitxer_de_publicacio", lambda: tmp_path / "publicacio.json")
    return fetes


def test_lleuger_salta_les_taules_grosses(cridades: list[str]) -> None:
    res = CliRunner().invoke(cli.app, ["publish-cloud", "--lleuger"])
    assert res.exit_code == 0, res.output
    assert not GROSSES & set(cridades)
    assert {"publish_pending_games", "publish_lliga_encontres", "publish_opens"} <= set(cridades)


def test_sense_lleuger_ho_publica_tot(cridades: list[str]) -> None:
    res = CliRunner().invoke(cli.app, ["publish-cloud"])
    assert res.exit_code == 0, res.output
    assert GROSSES <= set(cridades)
