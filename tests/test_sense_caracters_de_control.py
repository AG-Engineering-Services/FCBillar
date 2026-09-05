"""Cap fitxer que escrivim nosaltres no porta caràcters de control.

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

Es mira **tot el que hi ha al repositori** i s'exclou el que no és nostre. Al
revés —una llista del que sí que es mira— el guardià es buida sol i en silenci:
n'hi ha prou que algú mogui una carpeta o esborri una línia de la llista. Ja
m'hi vaig equivocar dues vegades seguides muntant-lo així. Amb les exclusions,
oblidar-se'n una fa que es miri un fitxer de més, que es veu de seguida;
oblidar una inclusió fa que no es miri, i això no ho veu ningú.
"""

from __future__ import annotations

import subprocess
import unicodedata
from pathlib import Path

import pytest

ARREL = Path(__file__).resolve().parent.parent

#: Els únics de control que hi poden ser: fi de línia i tabulador.
PERMESOS = "\n\r\t"

#: El que NO es mira, i per què.
#:
#: Les fixtures són pàgines capturades del web de la federació, i els PDF i les
#: captures són seus o del navegador: el que hi hagi a dins no l'hem escrit
#: nosaltres i no ens diu res. La resta són binaris que no es poden llegir com a
#: text.
EXCLOSOS_PER_CAMI = (
    "tests/fixtures/",
    "scripts/opens_ui_shots/",
    "docs/ajuts-desplacaments/",
    # Còpies binàries de la base de dades que es van committejar sense voler:
    # 92 MB que el .gitignore no atrapa perquè cobreix data/*.db i aquestes
    # porten un sufix al darrere. Aquesta prova és qui les ha trobades.
    "data/fcbillar.db.bak-",
)
EXCLOSES_PER_EXTENSIO = (".pdf", ".png", ".db", ".csv", ".ico", ".woff", ".woff2", ".zip")


def _seguits() -> list[str]:
    fet = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ARREL,
        capture_output=True,
        check=True,
        text=True,
    )
    return [x for x in fet.stdout.split("\0") if x]


def _exclos(cami: str) -> bool:
    return cami.startswith(EXCLOSOS_PER_CAMI) or cami.endswith(EXCLOSES_PER_EXTENSIO)


def camins() -> list[str]:
    """Els camins que es miren, tal com els escriu el git.

    Es compara la cadena del git amb ella mateixa i no amb la que en tornaria un
    `Path`: els accents es poden escriure de dues maneres que valen igual —la ç
    de «test_publica_reemplaçant» n'és una— i el git i el sistema de fitxers no
    sempre trien la mateixa. Comparant-les tal qual, un fitxer que sí que es
    mira sembla que no.
    """
    return sorted(c for c in _seguits() if not _exclos(c))


def _ruta(cami: str) -> Path | None:
    """El fitxer d'aquest camí, provant les dues formes d'escriure els accents."""
    for forma in (cami, unicodedata.normalize("NFC", cami), unicodedata.normalize("NFD", cami)):
        f = ARREL / forma
        if f.is_file():
            return f
    return None


def fitxers() -> list[Path]:
    """Tot el que el repositori segueix, menys el que no hem escrit nosaltres."""
    return [f for c in camins() for f in [_ruta(c)] if f is not None]


def test_es_mira_tot_el_que_hi_ha() -> None:
    """La cobertura surt del repositori i no d'una llista que es pugui quedar curta.

    És la prova que fa que el guardià no es pugui buidar sense que es vegi: qui
    vulgui deixar de mirar alguna cosa ha d'afegir-la a les exclusions, i això
    surt al diff amb el motiu al costat.
    """
    mirats = set(camins())
    sense_motiu = [c for c in _seguits() if c not in mirats and not _exclos(c)]
    assert not sense_motiu, f"queden fora sense cap motiu declarat: {sorted(sense_motiu)[:10]}"

    # I que tots existeixin de debò: un camí que no arriba a fitxer no es mira,
    # i sense això la prova de sobre el donaria per cobert.
    fantasmes = [c for c in camins() if _ruta(c) is None]
    assert not fantasmes, f"aquests camins no arriben a cap fitxer: {fantasmes[:10]}"

    # I que de debò s'hi miri codi de cada mena, no només Python.
    extensions = {Path(c).suffix for c in camins()}
    assert {".py", ".ts", ".js", ".svelte", ".sql", ".yml", ".ps1"} <= extensions, extensions


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
