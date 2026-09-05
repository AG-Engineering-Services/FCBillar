"""Cap fitxer de codi no porta caràcters de control.

Sembla una comprovació absurda i no ho és. Escrivint codi amb expressions
regulars a través d'un heredoc, els escapaments es poden convertir en el
caràcter que representen: `\\b` en un retrocés de veritat (0x08) i `\\1` en un
0x01. Al fitxer es llegeixen com el que volies escriure —l'editor no els
dibuixa— i el programa fa una altra cosa.

Ha passat tres vegades el mateix dia:

- un guardià de sigles amb `\\b` que no coincidia mai amb res, o sigui que no
  hauria enxampat el cas per al qual estava escrit;
- i el reemplaçament d'una expressió regular amb `\\1`, que enviava les
  peticions a una URL sense esquema.

Les dues vegades el codi es llegia perfectament.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

ARREL = Path(__file__).resolve().parent.parent

#: Els únics de control que hi poden ser: fi de línia i tabulador.
PERMESOS = "\n\r\t"

#: Tot el que escrivim nosaltres. Els heredocs no distingeixen llenguatges: la
#: mateixa corrupció pot caure a un SQL, a un workflow o a un fitxer del web.
#:
#: Les fixtures no hi són a posta: són pàgines capturades del web de la
#: federació i el que hi hagi dins és seu, no nostre.
PATRONS = (
    "src/**/*.py",
    "tests/**/*.py",
    "scripts/**/*.py",
    "scripts/**/*.ps1",
    "src/**/*.sql",
    "docs/**/*.sql",
    "web/src/**/*.ts",
    "web/src/**/*.js",
    "web/src/**/*.svelte",
    ".github/workflows/*.yml",
)


def fitxers() -> list[Path]:
    return sorted(f for p in PATRONS for f in ARREL.glob(p) if "__pycache__" not in f.parts)


def test_cada_patro_troba_fitxers() -> None:
    """Un patró que ha deixat de trobar res buida el guardià sense dir-ho.

    Si es mou un directori o es reanomena una carpeta, el seu patró passa a no
    casar amb res i aquells fitxers deixen de mirar-se. La prova seguiria en
    verd, perquè els altres patrons encara en porten centenars.

    Es comprova patró a patró i no per un compte total ni per una llista
    d'extensions escrita a mà: la llista escrita a mà ja se'm va quedar curta
    -hi vaig posar sis de les set menes- i amb un compte total, treure el patró
    del web encara passaria pel volum dels de Python.
    """
    buits = [p for p in PATRONS if not list(ARREL.glob(p))]
    assert not buits, f"aquests patrons no troben cap fitxer: {buits}"


def test_n_hi_ha_per_mirar() -> None:
    """I que en conjunt siguin els que esperem, no quatre de despistats."""
    assert len(fitxers()) > 190


@pytest.mark.parametrize("fitxer", fitxers(), ids=lambda f: f.name)
def test_cap_caracter_de_control(fitxer: Path) -> None:
    text = fitxer.read_text(encoding="utf-8", errors="replace")
    dolents = [
        (i, hex(ord(c)))
        for i, c in enumerate(text)
        if unicodedata.category(c) == "Cc" and c not in PERMESOS
    ]
    if dolents:
        i, codi = dolents[0]
        volta = text[max(0, i - 40) : i + 20].replace("\n", " ")
        pytest.fail(
            f"{fitxer.relative_to(ARREL)} porta un caràcter de control {codi} "
            f"a la posició {i}: …{volta}… "
            f"(segurament un escapament que s'ha convertit en el seu caràcter)"
        )
