"""Els PDF de la Lliga Nacional que esperen al magatzem de pas.

El fa servir `.github/workflows/nacional-puja.yml`, en dos temps:

    python scripts/nacional_pujades.py reconeix   # abans d'ingerir
    python scripts/nacional_pujades.py tanca      # després de publicar

PER QUÈ TOTS ELS PENDENTS I NO NOMÉS EL QUE HA ENGEGAT EL PROCÉS: GitHub només
guarda un procés en cua per torn. Si algú puja dos documents seguits mentre corre
la càrrega de cada nit, el segon fa fora el primer de la cua i aquell document es
quedaria «processant» per sempre. Aquí cada passada s'endú tot el que hi ha
pendent, de manera que un procés cancel·lat no perd res: el següent ho recull.

Un document és pendent quan té el PDF al magatzem i encara no té fitxer d'estat.

L'ORIGINAL NO ES QUEDA ENLLOC: es baixa a una carpeta temporal, se'n treu el que
es pot guardar (`fcbillar nacional-puja`) i s'esborra, del disc i del magatzem.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PREFIX = "nacional-pujades/"
#: `nacional-pujades/<club>/<id>.pdf`: lletres, xifres i guions. Res més s'accepta.
CLAU_VALIDA = re.compile(r"^nacional-pujades/[a-z0-9-]+/[a-z0-9-]+\.pdf$")
DIVISIONS = ("honor", "1", "2")

BUCKET = os.environ.get("R2_BUCKET", "")
ENDPOINT = os.environ.get("R2_ENDPOINT", "")
TEMP = Path(os.environ.get("RUNNER_TEMP", "."))
ESTATS = TEMP / "estats"


def _aws(*args: str, captura: bool = False) -> str:
    r = subprocess.run(
        ["aws", "s3", *args, "--endpoint-url", ENDPOINT],
        check=True,
        text=True,
        capture_output=captura,
    )
    return r.stdout if captura else ""


def _claus() -> list[str]:
    """Totes les claus de sota el prefix de pas."""
    sortida = _aws("ls", f"s3://{BUCKET}/{PREFIX}", "--recursive", captura=True)
    return [linia.split(None, 3)[3].strip() for linia in sortida.splitlines() if linia.strip()]


def pendents(claus: list[str]) -> list[str]:
    """Els PDF que encara no tenen fitxer d'estat, pel nom."""
    amb_estat = {c[: -len(".estat.json")] for c in claus if c.endswith(".estat.json")}
    return sorted(c for c in claus if CLAU_VALIDA.match(c) and c[: -len(".pdf")] not in amb_estat)


def _divisio_de(clau: str) -> str:
    """La divisió que va dir qui el va pujar: és al fitxer de metadades."""
    desti = TEMP / "meta.json"
    try:
        _aws("cp", f"s3://{BUCKET}/{clau[:-4]}.meta.json", str(desti), "--only-show-errors")
        divisio = str(json.loads(desti.read_text(encoding="utf-8")).get("divisio", "1"))
    except Exception:
        divisio = "1"
    return divisio if divisio in DIVISIONS else "1"


def reconeix() -> int:
    """Baixa cada pendent, el reconeix i en deixa l'estat en un fitxer local."""
    ESTATS.mkdir(parents=True, exist_ok=True)
    pas = TEMP / "pas"
    pas.mkdir(parents=True, exist_ok=True)
    bons = 0
    for clau in pendents(_claus()):
        nom = clau[len(PREFIX) : -len(".pdf")].replace("/", "__")
        local = pas / "pujat.pdf"
        estat_local = ESTATS / f"{nom}.json"
        try:
            _aws("cp", f"s3://{BUCKET}/{clau}", str(local), "--only-show-errors")
            subprocess.run(
                [
                    "uv", "run", "--no-dev", "fcbillar", "nacional-puja", str(local),
                    "--divisio", _divisio_de(clau), "--sortida", str(estat_local),
                ],
                check=False,
            )  # fmt: skip
        finally:
            # L'original no ha de sobreviure a aquest pas, passi el que passi.
            local.unlink(missing_ok=True)
        try:
            estat = json.loads(estat_local.read_text(encoding="utf-8"))
        except Exception:
            estat = {"estat": "error", "error": "El procés no ha arribat a llegir el document."}
        estat["clau"] = clau
        estat_local.write_text(json.dumps(estat, ensure_ascii=False), encoding="utf-8")
        print(f"{clau}: {estat.get('resum') or estat.get('error')}")
        bons += estat.get("estat") == "reconegut"
    # Per al workflow: quants n'hi ha de bons, i una frase per al commit.
    sortida = os.environ.get("GITHUB_OUTPUT")
    if sortida:
        with open(sortida, "a", encoding="utf-8") as f:
            f.write(f"bons={bons}\n")
    return 0


def tanca() -> int:
    """Puja l'estat de cada document i esborra del magatzem els PDF ja tractats."""
    publicat = os.environ.get("RC_PUBLICA") == "0"
    ara = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
    for fitxer in sorted(ESTATS.glob("*.json")) if ESTATS.exists() else []:
        estat = json.loads(fitxer.read_text(encoding="utf-8"))
        clau = estat.pop("clau", "")
        if not CLAU_VALIDA.match(clau):
            continue
        if estat.get("estat") == "reconegut":
            if publicat:
                estat["estat"] = "publicat"
            else:
                estat["estat"] = "error"
                estat["error"] = (
                    "El document s'ha llegit i desat, però no s'ha pogut publicar. "
                    "Entrarà amb la càrrega d'aquesta nit."
                )
        estat["acabat"] = ara
        estat["run"] = os.environ.get("RUN_URL", "")
        fitxer.write_text(json.dumps(estat, ensure_ascii=False), encoding="utf-8")
        _aws(
            "cp", str(fitxer), f"s3://{BUCKET}/{clau[:-4]}.estat.json",
            "--content-type", "application/json", "--only-show-errors",
        )  # fmt: skip
    # Qualsevol PDF que ja té estat no hi ha de seguir: ni els d'ara ni els que
    # una passada anterior hagués deixat (un procés que va fallar a mig fer).
    claus = _claus()
    amb_estat = {c[: -len(".estat.json")] for c in claus if c.endswith(".estat.json")}
    for clau in claus:
        if CLAU_VALIDA.match(clau) and clau[: -len(".pdf")] in amb_estat:
            _aws("rm", f"s3://{BUCKET}/{clau}", "--only-show-errors")
    return 0


if __name__ == "__main__":
    ordre = sys.argv[1] if len(sys.argv) > 1 else ""
    if ordre not in ("reconeix", "tanca") or not BUCKET or not ENDPOINT:
        sys.exit("Ús: nacional_pujades.py reconeix|tanca  (amb R2_BUCKET i R2_ENDPOINT)")
    sys.exit(reconeix() if ordre == "reconeix" else tanca())
