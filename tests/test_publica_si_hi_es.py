"""Una taula acabada de crear no ha d'aturar la publicació nocturna.

El Data API de Neon reparteix les peticions entre diverses instàncies i cadascuna
porta el seu cache d'esquemes. Just després d'un `CREATE TABLE` les respostes
alternen —unes instàncies ja el veuen i les altres no— i la convergència triga de
l'ordre de mitja hora. `NOTIFY pgrst, 'reload schema'` no hi arriba: només es pot
esperar.

Durant aquella mitja hora la publicació no s'ha d'aturar sencera per una cosa que
es cura sola. Però tampoc no ha de passar per bona: el compte queda a -1 i surt un
avís que diu què cal fer.

El que NO s'empassa és res més. Una publicació que falla en silenci és pitjor que
una que peta, i és així com es van amagar els errors que aquesta tanda ha hagut
d'anar a buscar.
"""

from __future__ import annotations

import pytest

from fcbillar.cloud_sync import esquema_encara_no_hi_es, publica_si_hi_es


class APIErrorFals(Exception):
    """Com el que puja `supabase-py`: el codi va dins del text del missatge."""


def test_reconeix_la_taula_que_encara_no_hi_es() -> None:
    exc = APIErrorFals(
        "{'message': \"Could not find the table 'fcbillar.afiliacions' in the "
        "schema cache\", 'code': 'PGRST205'}"
    )
    assert esquema_encara_no_hi_es(exc)


def test_reconeix_la_columna_que_encara_no_hi_es() -> None:
    """PGRST204. Passa amb un `ALTER TABLE ... ADD COLUMN`, i pel camí d'ESCRIPTURA.

    Sondejar la lectura no serveix: un `select` de la columna nova pot tornar 200
    als catorze segons i la publicació petar igualment, perquè PostgREST valida
    les columnes del cos a l'escriptura i els dos camins no es refresquen alhora.
    """
    exc = APIErrorFals("{'code': 'PGRST204', 'message': \"Could not find the 'mitjana' column\"}")
    assert esquema_encara_no_hi_es(exc)


def test_no_confon_cap_altre_error() -> None:
    for text in (
        "connexio refusada",
        "{'code': 'PGRST301', 'message': 'JWT expired'}",
        "UNIQUE constraint failed",
        "",
    ):
        assert not esquema_encara_no_hi_es(APIErrorFals(text))


def test_la_publicacio_segueix_i_avisa() -> None:
    avisos: list[tuple[str, str]] = []

    def esclata():
        raise APIErrorFals("{'code': 'PGRST205'}")

    counts = publica_si_hi_es("afiliacions", esclata, lambda n, m: avisos.append((n, m)))

    # -1 i no 0: zero voldria dir «publicat, i no hi havia res», que és mentida.
    assert counts == {"afiliacions": -1}
    assert len(avisos) == 1
    nivell, missatge = avisos[0]
    assert nivell == "warn"
    assert "afiliacions" in missatge and "30 min" in missatge


def test_qualsevol_altre_error_puja() -> None:
    """Empassar-se'l faria que una publicació trencada semblés bona."""

    def esclata():
        raise APIErrorFals("{'code': 'PGRST301', 'message': 'JWT expired'}")

    with pytest.raises(APIErrorFals):
        publica_si_hi_es("afiliacions", esclata, lambda n, m: None)


def test_quan_va_be_no_toca_res() -> None:
    assert publica_si_hi_es("x", lambda: {"x": 42}, lambda n, m: None) == {"x": 42}
