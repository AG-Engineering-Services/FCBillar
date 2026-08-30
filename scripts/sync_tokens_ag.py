"""Porta els tokens visuals d'AGenginyeria a dins d'aquest repositori.

Els tokens viuen a `ag-standards/skills/ag-disseny/` i són la font de veritat.
Aquí n'hi ha d'haver una còpia perquè les dues aplicacions han de funcionar amb
aquest repositori sol: Vercel només veu això quan desplega el web, i qualsevol
que es cloni el projecte ha de poder obrir l'escriptori sense tenir els
estàndards al costat. Això no és excusa per copiar-ne els valors a mà, que és
el que la norma prohibeix; els copia aquest script.

    uv run python scripts/sync_tokens_ag.py            # comprova que no han derivat
    uv run python scripts/sync_tokens_ag.py --escriu   # els torna a copiar

Surt amb codi 1 si alguna còpia no coincideix amb l'original, perquè un canvi
als estàndards no es quedi sense arribar aquí.
"""

from __future__ import annotations

import argparse
import io
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

ARREL = Path(__file__).resolve().parents[1]
ESTANDARDS = ARREL.parent / "ag-standards" / "skills" / "ag-disseny"

_AVIS = """GENERAT — no editis aquest fitxer.

Còpia de ag-standards/skills/ag-disseny/{nom}, que és la font de veritat.
Es refresca amb:

    uv run python scripts/sync_tokens_ag.py --escriu

{tancament}"""

#: El text generat va a fitxers que es commiten: que no hi surtin línies
#: llarguíssimes segons què digui el motiu de cada còpia.
_AMPLADA = 78


@dataclass(frozen=True)
class Copia:
    nom: str
    desti: Path
    motiu: str
    #: Com es marca l'avís al fitxer de destí. En un fitxer Python ha de ser un
    #: COMENTARI: una docstring al davant deixaria el `from __future__` de
    #: l'original fora del principi del fitxer i no compilaria.
    comentari: str = ""
    obre: str = ""
    tanca: str = ""

    @property
    def origen(self) -> Path:
        return ESTANDARDS / self.nom

    def contingut(self) -> str:
        tancament = textwrap.fill(
            f"Hi és perquè {self.motiu}. Si vols canviar un color, canvia'l als "
            f"estàndards, passa-hi l'auditoria de contrast i torna a sincronitzar.",
            width=_AMPLADA,
        )
        avis = _AVIS.format(nom=self.nom, tancament=tancament)
        if self.comentari:
            linies = [f"{self.comentari} {ln}".rstrip() for ln in avis.splitlines()]
            capcalera = "\n".join(linies) + "\n\n"
        else:
            capcalera = f"{self.obre}\n{avis}\n{self.tanca}\n\n"
        return capcalera + self.origen.read_text(encoding="utf-8")


COPIES = (
    Copia(
        nom="tokens.css",
        desti=ARREL / "web" / "src" / "lib" / "styles" / "ag-tokens.css",
        motiu="Vercel només veu aquest repositori quan desplega el web",
        obre="/*",
        tanca="*/",
    ),
    Copia(
        nom="tokens.py",
        desti=ARREL / "desktop" / "styles" / "ag_tokens.py",
        motiu="l'escriptori ha d'arrencar amb aquest repositori sol, sense tenir "
        "els estàndards al costat",
        comentari="#",
    ),
)


def main() -> int:
    # La consola de Windows no escriu accents sense això. Va aquí i no a dalt de
    # tot perquè importar aquest fitxer —ho fa `tests/test_tokens_sync.py`— no ha
    # de tocar el stdout de ningú.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--escriu", action="store_true", help="Actualitza les còpies")
    args = ap.parse_args()

    if not ESTANDARDS.is_dir():
        print(f"No hi ha els estàndards a {ESTANDARDS}.")
        print("Sense ells no es poden refrescar les còpies, però les que hi ha")
        print("al repositori segueixen servint: les aplicacions no en depenen.")
        return 1

    problemes = 0
    for c in COPIES:
        volgut = c.contingut()
        actual = c.desti.read_text(encoding="utf-8") if c.desti.exists() else None
        relatiu = c.desti.relative_to(ARREL)

        if actual == volgut:
            print(f"  al dia   {relatiu}")
            continue

        if not args.escriu:
            estat = "no hi és" if actual is None else "ha derivat"
            print(f"  {estat:8s} {relatiu}")
            problemes += 1
            continue

        c.desti.parent.mkdir(parents=True, exist_ok=True)
        c.desti.write_text(volgut, encoding="utf-8")
        print(f"  copiat   {c.nom} → {relatiu}")

    if problemes:
        print("\nPassa-hi --escriu per posar-les al dia.")
    return 1 if problemes else 0


if __name__ == "__main__":
    sys.exit(main())
