"""La publicació de `games` retira del núvol les partides que la base ja no té."""

from __future__ import annotations

from fcbillar import cloud_sync
from tests.test_publish_lliga_retirada import ClientFals, TaulaFalsa


def _client(monkeypatch, ids: list[str]) -> tuple[ClientFals, dict]:
    monkeypatch.setattr(TaulaFalsa, "order", lambda self, *_a, **_k: self, raising=False)
    magatzem = {"games": [{"id": i} for i in ids]}
    return ClientFals(magatzem), magatzem


def test_una_partida_fusionada_marxa_del_nuvol(monkeypatch) -> None:
    sb, magatzem = _client(monkeypatch, ["a", "b", "copia"])

    n = cloud_sync._retira_games_sobrants(sb, {"a", "b"}, lambda *_: None)

    assert n == 1
    assert [f["id"] for f in magatzem["games"]] == ["a", "b"]


def test_amb_una_base_a_mitges_no_es_retira_res(monkeypatch) -> None:
    """Des d'un PC amb la base incompleta, esborraria mig núvol."""
    ids = [f"g{i}" for i in range(1000)]
    sb, magatzem = _client(monkeypatch, ids)
    avisos = []

    n = cloud_sync._retira_games_sobrants(sb, {"g0"}, lambda nivell, msg: avisos.append(msg))

    assert n == 0
    assert len(magatzem["games"]) == 1000
    assert "NO s'ha retirat res" in avisos[0]
