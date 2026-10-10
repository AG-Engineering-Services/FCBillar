"""Les correccions a mà: s'apliquen només mentre la federació digui el que es va veure malament."""

from __future__ import annotations

import pytest

from fcbillar import correccions as C

CORRECCIO = C.Correccio(
    encontre_id=11885,
    jugador="Restrepo",
    camp="entrades",
    valor_federacio=9,
    valor_correcte=32,
    motiu="acta mal picada",
)


def _partides(entrades: int) -> list[dict]:
    return [
        {
            "encontre_id": 11885,
            "ordre": 1,
            "jugador_local": "RODRIGUEZ JIMÉNEZ, EDUARD",
            "jugador_visitant": "CARDET CALDERÓ, ISIDOR",
            "caramboles_local": 28,
            "caramboles_visitant": 22,
            "entrades": 50,
        },
        {
            "encontre_id": 11885,
            "ordre": 2,
            "jugador_local": "RESTREPO HERNÁNDEZ, CARLOS",
            "jugador_visitant": "DAVILA SILVA, HENRY",
            "caramboles_local": 30,
            "caramboles_visitant": 9,
            "entrades": entrades,
        },
        {
            "encontre_id": 11881,
            "ordre": 2,
            "jugador_local": "BRIZZI, LINO",
            "jugador_visitant": "RESTREPO HERNÁNDEZ, CARLOS",
            "caramboles_local": 26,
            "caramboles_visitant": 30,
            "entrades": 46,
        },
    ]


def test_corregeix_nomes_la_partida_i_el_camp_que_toca():
    files = _partides(9)
    assert C.aplica_a_partides(files, [CORRECCIO]) == 1
    assert [f["entrades"] for f in files] == [50, 32, 46]
    assert files[1]["caramboles_visitant"] == 9


def test_si_la_federacio_ja_ho_ha_arreglat_no_toca_res_i_avisa():
    files = _partides(32)
    avisos: list[tuple[str, str]] = []
    assert C.aplica_a_partides(files, [CORRECCIO], lambda n, m: avisos.append((n, m))) == 0
    assert files[1]["entrades"] == 32
    assert avisos and avisos[0][0] == "warn" and "ja no cal" in avisos[0][1]


def test_si_la_federacio_hi_posa_una_altra_cosa_mana_ella():
    files = _partides(31)
    avisos: list[tuple[str, str]] = []
    assert C.aplica_a_partides(files, [CORRECCIO], lambda n, m: avisos.append((n, m))) == 0
    assert files[1]["entrades"] == 31
    assert "Mana la federació" in avisos[0][1]


def test_si_la_partida_no_hi_es_avisa_i_no_toca_res():
    files = [f for f in _partides(9) if f["ordre"] != 2 or f["encontre_id"] != 11885]
    avisos: list[tuple[str, str]] = []
    assert C.aplica_a_partides(files, [CORRECCIO], lambda n, m: avisos.append((n, m))) == 0
    assert "no aplicada" in avisos[0][1]


def test_llegeix_el_fitxer_i_rebutja_un_camp_que_no_existeix(tmp_path):
    bo = tmp_path / "bo.csv"
    bo.write_text(
        "encontre_id,jugador,camp,valor_federacio,valor_correcte,motiu\n"
        "11885,Restrepo,entrades,9,32,acta mal picada\n",
        encoding="utf-8",
    )
    assert C.llegeix(bo) == [CORRECCIO]
    assert C.llegeix(tmp_path / "no-hi-es.csv") == []

    dolent = tmp_path / "dolent.csv"
    dolent.write_text(
        "encontre_id,jugador,camp,valor_federacio,valor_correcte,motiu\n"
        "11885,Restrepo,serie,9,32,x\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        C.llegeix(dolent)


def test_el_fitxer_del_repositori_es_llegeix():
    # Si algú hi afegeix una fila mal escrita, que peti aquí i no a la nit.
    C.llegeix()
