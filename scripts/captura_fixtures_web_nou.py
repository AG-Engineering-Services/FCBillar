"""Captura fixtures HTML del web nou de la FCB (agost 2026).

El web de la federació es va partir en tres l'agost de 2026 (vegeu
`docs/canvi-web-fcb-2026.md`). Aquest script baixa una pàgina de cada mena a
`tests/fixtures/nou/` perquè els parsers es puguin escriure i provar sense
tocar la xarxa.

    uv run python scripts/captura_fixtures_web_nou.py [--force]

Només cal tornar-lo a executar quan la federació canviï el marcatge o quan
vulguem cobrir una pàgina que ara no tenim (p.ex. el detall d'encontre de
lliga, que avui retorna HTTP 500).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

INTRANET = "https://intranet.fcbillar.cat"
WEB = "https://fcbillar.cat"
DEST = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "nou"

# Pàgines de referència. La tria busca cobertura de FORMES, no de dades: una
# pàgina per cada plantilla que hem de saber llegir.
#
# Els ids són els de la temporada 2025-26, que continua accessible pel seu id
# encara que no surti als llistats: lliga 36, open de Mataró 211, copa edició 7.
PAGINES: list[tuple[str, str]] = [
    # --- rànquings ---
    ("rankings_llistat", f"{INTRANET}/frontend/rankings/llistat"),
    ("rankings_dades_vigent_124_1", f"{INTRANET}/frontend/rankings/llistat-dades?idranking=124&idmodalitat=1"),
    ("rankings_dades_historic_123_6", f"{INTRANET}/frontend/rankings/historial-dades?idranking=123&idmodalitat=6"),
    ("rankings_partides_vigent_124_1_843", f"{INTRANET}/frontend/rankings/llistat-partides?idranking=124&idmodalitat=1&idjugador=843"),
    ("rankings_partides_historic_123_1_843", f"{INTRANET}/frontend/rankings/historial-partides?idranking=123&idmodalitat=1&idjugador=843"),
    # --- lliga ---
    ("lligues_llistat", f"{INTRANET}/frontend/lligues/llistat"),
    ("lligues_divisions_36", f"{INTRANET}/frontend/lligues/divisions/36"),
    ("lligues_grups_36_148", f"{INTRANET}/frontend/lligues/grups/36/148"),
    ("lligues_jornades_36_148_316", f"{INTRANET}/frontend/lligues/jornades/36/148/316"),
    ("lligues_encontres_36_148_316_2593", f"{INTRANET}/frontend/lligues/encontres/36/148/316/2593"),
    ("lligues_classificacio_36_148_316", f"{INTRANET}/frontend/lligues/classificacio/36/148/316"),
    ("lligues_inscripcions_39", f"{INTRANET}/frontend/lligues/inscripcions/39"),
    # HTTP 500 des del canvi de web; el desem igualment per veure quan es cura.
    ("lligues_partides_36_148_316_2593_10939", f"{INTRANET}/frontend/lligues/partides/36/148/316/2593/10939"),
    # --- individuals ---
    ("individuals_llistat", f"{INTRANET}/frontend/individuals/llistat"),
    ("individuals_divisions_211", f"{INTRANET}/frontend/individuals/divisions/211"),
    ("individuals_fases_211_447", f"{INTRANET}/frontend/individuals/fases/211/447"),
    ("individuals_grups_211_447_799", f"{INTRANET}/frontend/individuals/grups/211/447/799"),
    ("individuals_partides_grup_211_447_799_5100", f"{INTRANET}/frontend/individuals/partides-grup/211/447/799/5100"),
    ("individuals_partides_eliminatories_211_447_1185", f"{INTRANET}/frontend/individuals/partides-eliminatories/211/447/1185"),
    # --- copa ---
    ("copa_llistat", f"{INTRANET}/frontend/copa/llistat"),
    ("copa_fase_grups_7", f"{INTRANET}/frontend/copa/fase-grups/7"),
    ("copa_grups_7_26", f"{INTRANET}/frontend/copa/grups/7/26"),
    ("copa_encontres_grup_7_26_150", f"{INTRANET}/frontend/copa/encontres-grup/7/26/150"),
    ("copa_partides_grup_7_26_150_472_245_238", f"{INTRANET}/frontend/copa/partides-grup/7/26/150/472/245/238"),
    # --- WordPress ---
    ("wp_clubs", f"{WEB}/federacio/llistat-de-clubs-federacio-catalana-de-billar/"),
    ("wp_sitemap_documents", f"{WEB}/wpfd_file-sitemap.xml"),
    ("wp_document_calendari", f"{WEB}/wpfd_file/ranquing-opens-3-bandes-25-26/"),
]

UA = "FCBillar/1.0 (seguiment de jugadors del C.B. Banyoles)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="Rebaixa les que ja hi ha")
    args = ap.parse_args()

    DEST.mkdir(parents=True, exist_ok=True)
    errors = 0
    with httpx.Client(
        headers={"User-Agent": UA}, follow_redirects=True, timeout=60.0
    ) as client:
        for nom, url in PAGINES:
            ext = ".xml" if url.endswith(".xml") else ".html"
            desti = DEST / f"{nom}{ext}"
            if desti.exists() and not args.force:
                print(f"  = {desti.name} (ja hi és)")
                continue
            try:
                r = client.get(url)
            except httpx.HTTPError as e:
                print(f"  ! {nom}: {e}")
                errors += 1
                continue
            marca = "OK " if r.status_code == 200 else f"{r.status_code}"
            desti.write_text(r.text, encoding="utf-8")
            print(f"  {marca} {desti.name}  ({len(r.text):,} car.)")
            if r.status_code != 200:
                errors += 1
            time.sleep(0.4)  # el portal és petit; no l'atabalem

    print(f"\n{len(PAGINES)} pàgines, {errors} amb problema → {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
