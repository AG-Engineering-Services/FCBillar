"""La publicació dels rànquings retira les files que la federació ha tret."""

from __future__ import annotations

from fcbillar import cloud_sync
from tests.test_publish_lliga_retirada import ClientFals


def _e(mod: int, num: int, fcb: str) -> dict:
    return {"modalitat_codi": mod, "num_seq": num, "player_fcb_id": fcb}


def test_una_fila_treta_d_un_ranquing_recent_marxa_del_nuvol() -> None:
    """El 126 deixava dos jugadors a la mateixa posició: una fila vella no es retirava."""
    locals_ = [_e(1, n, str(p)) for n in (124, 125, 126, 127) for p in range(1, 40)]
    nuvol = [dict(e) for e in locals_] + [_e(1, 126, "173"), _e(1, 124, "999")]
    magatzem = {"ranking_entries": nuvol}

    n = cloud_sync._retira_entrades_sobrants(ClientFals(magatzem), locals_, lambda *_: None)

    assert n == 1  # el 124 no és dels tres darrers: no es mira
    quedats = {(f["num_seq"], f["player_fcb_id"]) for f in magatzem["ranking_entries"]}
    assert (126, "173") not in quedats and (124, "999") in quedats


def test_un_ranquing_que_no_quadra_gens_no_es_toca() -> None:
    locals_ = [_e(1, 127, "1")]
    magatzem = {"ranking_entries": [_e(1, 127, str(p)) for p in range(100)]}
    avisos = []

    n = cloud_sync._retira_entrades_sobrants(
        ClientFals(magatzem), locals_, lambda nivell, msg: avisos.append(msg)
    )

    assert n == 0 and len(magatzem["ranking_entries"]) == 100
    assert "NO s'ha retirat res" in avisos[0]
