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
    ("lligues_inscripcions_38", f"{INTRANET}/frontend/lligues/inscripcions/38"),
    # Els inscrits d'un club: el 16 és el C.B.BANYOLES (cap fitxatge) i el 22
    # el C.B.MONT-ROIG, que en porta dos. Calen totes dues formes de fila.
    ("lligues_participants_38_16", f"{INTRANET}/frontend/lligues/participants/38/16"),
    ("lligues_participants_38_22", f"{INTRANET}/frontend/lligues/participants/38/22"),
    # El detall d'encontre va tornar a funcionar el setembre de 2026, i per a
    # totes les temporades: el 500 era un error seu, no un tancament.
    ("lligues_partides_36_148_316_2593_10939", f"{INTRANET}/frontend/lligues/partides/36/148/316/2593/10939"),
    # --- lliga 38: Tres Bandes 2026-27, la temporada en joc ---
    # Honor Grup A, jornada 1: DOS encontres jugats i DOS oberts a la mateixa
    # pàgina. És la forma que importa: els oberts no porten enllaç ni id, i si
    # el parser els salta la jornada surt mig buida a la web.
    ("lligues_jornades_38_159_343", f"{INTRANET}/frontend/lligues/jornades/38/159/343"),
    ("lligues_encontres_38_159_343_2790", f"{INTRANET}/frontend/lligues/encontres/38/159/343/2790"),
    # La classificació porta els VUIT equips del grup des del primer dia, quatre
    # amb J=1 i quatre amb J=0. És l'únic cens dels equips d'un grup.
    ("lligues_classificacio_38_159_343", f"{INTRANET}/frontend/lligues/classificacio/38/159/343"),
    # El detall d'un encontre de debò de la temporada nova: les capçaleres són
    # els NOMS DELS EQUIPS i els resultats venen aparellats, "SM / Caramboles".
    ("lligues_partides_38_159_343_2790_11656", f"{INTRANET}/frontend/lligues/partides/38/159/343/2790/11656"),
    # Els inscrits d'un club a la lliga de 4 Modalitats: la federació els va
    # publicar el setembre de 2026 i, a diferència dels de tres bandes, van
    # SENSE mitjana. El mateix jugador pot sortir a clubs diferents a cada lliga.
    ("lligues_participants_39_13", f"{INTRANET}/frontend/lligues/participants/39/13"),
    # --- individuals ---
    ("individuals_llistat", f"{INTRANET}/frontend/individuals/llistat"),
    ("individuals_divisions_211", f"{INTRANET}/frontend/individuals/divisions/211"),
    ("individuals_fases_211_447", f"{INTRANET}/frontend/individuals/fases/211/447"),
    ("individuals_grups_211_447_799", f"{INTRANET}/frontend/individuals/grups/211/447/799"),
    ("individuals_partides_grup_211_447_799_5100", f"{INTRANET}/frontend/individuals/partides-grup/211/447/799/5100"),
    ("individuals_partides_eliminatories_211_447_1185", f"{INTRANET}/frontend/individuals/partides-eliminatories/211/447/1185"),
    # L'OPEN LLIURE PUNT D'ATAC 2026-27 (217), tancat el 2026-09-06: un open
    # sencer i petit -3 fases de grups i 3 eliminatories, 44 partides- que
    # serveix de prova de regressio de la ingesta d'opens del web nou.
    ("individuals_divisions_217", f"{INTRANET}/frontend/individuals/divisions/217"),
    ("individuals_fases_217_452", f"{INTRANET}/frontend/individuals/fases/217/452"),
    ("individuals_grups_217_452_807", f"{INTRANET}/frontend/individuals/grups/217/452/807"),
    ("individuals_partides_grup_217_452_807_5257", f"{INTRANET}/frontend/individuals/partides-grup/217/452/807/5257"),
    ("individuals_partides_eliminatories_217_452_1189", f"{INTRANET}/frontend/individuals/partides-eliminatories/217/452/1189"),
    # El CAMPIONAT DE CATALUNYA de tres bandes 2026-27 (216). No és un open: té
    # vuit divisions (Honor, 1a…6a, Única) i les fases es diuen PRÈVIA i
    # PRE-PRÈVIA. La pàgina de partides d'un grup porta, a més de les partides,
    # la CLASSIFICACIÓ del grup amb punts i mitjana —que és el que fa falta per
    # saber qui s'ha classificat, i que cap parser no llegia.
    ("individuals_divisions_216", f"{INTRANET}/frontend/individuals/divisions/216"),
    ("individuals_fases_216_454", f"{INTRANET}/frontend/individuals/fases/216/454"),
    ("individuals_grups_216_454_808", f"{INTRANET}/frontend/individuals/grups/216/454/808"),
    ("individuals_partides_grup_216_454_808_5263", f"{INTRANET}/frontend/individuals/partides-grup/216/454/808/5263"),
    # Un grup de la pre-prèvia de 1a: TRES jugadors, i un d'ells sense cap
    # partida jugada, que a la classificació surt amb la mitjana buida.
    ("individuals_partides_grup_216_455_809_5268", f"{INTRANET}/frontend/individuals/partides-grup/216/455/809/5268"),
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
    # El calendari d'un grup de lliga: la pàgina porta l'enllaç al seu PDF i
    # també el del calendari esportiu de la temporada, que no és el mateix.
    (
        "wp_document_calendari_grup",
        f"{WEB}/wpfd_file/calendari-lliga-tres-bandes-2026-27-honor-grup-a/",
    ),
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
