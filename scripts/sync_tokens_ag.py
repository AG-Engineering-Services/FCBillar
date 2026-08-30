"""Porta els tokens visuals d'AGenginyeria al web.

Els tokens viuen a `ag-standards/skills/ag-disseny/tokens.css` i són la font de
veritat. El web es desplega a Vercel des d'aquest repositori i prou, o sigui que
el fitxer hi ha de ser físicament; això no és excusa per copiar-ne els valors a
mà, que és exactament el que la norma prohibeix.

    uv run python scripts/sync_tokens_ag.py            # comprova que no ha derivat
    uv run python scripts/sync_tokens_ag.py --escriu   # el torna a copiar

Surt amb codi 1 si la còpia del web no coincideix amb l'original, perquè un
canvi als estàndards no es quedi sense arribar aquí.
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ARREL = Path(__file__).resolve().parents[1]
ORIGEN = ARREL.parent / "ag-standards" / "skills" / "ag-disseny" / "tokens.css"
DESTI = ARREL / "web" / "src" / "lib" / "styles" / "ag-tokens.css"

CAPCALERA = """/* GENERAT — no editis aquest fitxer.

   Còpia de ag-standards/skills/ag-disseny/tokens.css, que és la font de
   veritat. Es refresca amb:

       uv run python scripts/sync_tokens_ag.py --escriu

   Hi és perquè Vercel només veu aquest repositori. Si vols canviar un color,
   canvia'l als estàndards, passa-hi l'auditoria de contrast i torna a
   sincronitzar. */

"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--escriu", action="store_true", help="Actualitza la còpia del web")
    args = ap.parse_args()

    if not ORIGEN.exists():
        print(f"No hi ha els estàndards a {ORIGEN}")
        return 1

    volgut = CAPCALERA + ORIGEN.read_text(encoding="utf-8")
    actual = DESTI.read_text(encoding="utf-8") if DESTI.exists() else None

    if actual == volgut:
        print(f"Al dia: {DESTI.relative_to(ARREL)}")
        return 0

    if not args.escriu:
        estat = "no hi és" if actual is None else "ha derivat de l'original"
        print(f"La còpia {estat}: {DESTI.relative_to(ARREL)}")
        print("Passa-hi --escriu per posar-la al dia.")
        return 1

    DESTI.parent.mkdir(parents=True, exist_ok=True)
    DESTI.write_text(volgut, encoding="utf-8")
    print(f"Copiat {ORIGEN.name} → {DESTI.relative_to(ARREL)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
