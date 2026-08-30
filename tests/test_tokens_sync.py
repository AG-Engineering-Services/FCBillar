"""Les còpies dels tokens visuals no poden derivar de l'original.

`scripts/sync_tokens_ag.py` porta els tokens d'AGenginyeria a dins d'aquest
repositori: `tokens.css` al web i `tokens.py` a l'escriptori. Les còpies hi són
perquè les dues aplicacions han de funcionar amb aquest repositori sol.

El problema d'un mecanisme així és que només salta si algú executa l'script, i
ja va passar una vegada: es va canviar el format de la capçalera, es van
regenerar les còpies i una es va quedar fora del commit. Amb això, la
comprovació va amb els tests.

Si no hi ha els estàndards al costat —cas de qualsevol que es cloni només aquest
repositori— el test se salta: llavors no es pot comparar amb res, i les còpies
que hi ha segueixen servint igual.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ARREL = Path(__file__).resolve().parents[1]


def _carrega_sincronitzador():
    spec = importlib.util.spec_from_file_location(
        "sync_tokens_ag", ARREL / "scripts" / "sync_tokens_ag.py"
    )
    assert spec is not None and spec.loader is not None
    modul = importlib.util.module_from_spec(spec)
    # El mòdul ha de ser a `sys.modules` abans d'executar-lo: els `@dataclass`
    # de dins hi busquen el mòdul per resoldre les anotacions de tipus.
    sys.modules[spec.name] = modul
    spec.loader.exec_module(modul)
    return modul


SYNC = _carrega_sincronitzador()

te_estandards = pytest.mark.skipif(
    not SYNC.ESTANDARDS.is_dir(),
    reason="no hi ha ag-standards al costat; no hi ha res amb què comparar",
)


@te_estandards
@pytest.mark.parametrize("copia", SYNC.COPIES, ids=lambda c: c.nom)
def test_la_copia_es_igual_que_l_original(copia) -> None:
    assert copia.desti.exists(), (
        f"falta {copia.desti.relative_to(ARREL)}; "
        f"executa `uv run python scripts/sync_tokens_ag.py --escriu`"
    )
    assert copia.desti.read_text(encoding="utf-8") == copia.contingut(), (
        f"{copia.desti.relative_to(ARREL)} no coincideix amb {copia.nom} dels "
        f"estàndards. Si el canvi és bo, executa "
        f"`uv run python scripts/sync_tokens_ag.py --escriu` i commita el resultat."
    )


def test_les_copies_hi_son_encara_que_no_hi_hagi_estandards() -> None:
    """Sense aquest fitxer, ni el web compila ni l'escriptori arrenca."""
    for copia in SYNC.COPIES:
        assert copia.desti.exists(), f"falta {copia.desti.relative_to(ARREL)}"
        assert copia.desti.stat().st_size > 1000
