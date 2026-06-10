"""Repàs complet de partides: rànquing a rànquing, jugador a jugador.

El portal només exposa la finestra de partides d'un jugador EN un rànquing
concret, així que per recuperar tot l'historial cal cridar partideshome per
cada (rànquing, jugador). Idempotent (dedup per id_natural) i resumible
(saltem els (rànquing, jugador) que ja tenen partides enllaçades).

Resilient a la sessió: keep-alive periòdic per evitar morts per inactivitat,
i si la sessió cau (ratxa d'errors) s'atura a ESPERAR i sondeja cada 30s,
reprenent sol quan la sessió torna (p.ex. després d'un re-login manual) —
sense necessitat de reiniciar l'script.
"""

from __future__ import annotations

import sqlite3
import time

from fcbillar.config import get_settings
from fcbillar.pipeline import _partides_url, ingest_partides
from fcbillar.scraper.client import ScraperClient
from fcbillar.scraper.parsers import parse_partides_jugador

# Combo conegut que SEMPRE té partides: serveix de sonda de sessió i keep-alive.
PROBE_NUM, PROBE_MOD = 122, 1


def main() -> None:
    s = get_settings()
    conn = sqlite3.connect(str(s.db_path))
    conn.row_factory = sqlite3.Row

    probe_fcb = conn.execute(
        "SELECT fcb_id FROM players WHERE nom LIKE 'MAS CANADELL, JOSEP%' LIMIT 1"
    ).fetchone()
    probe_fcb = probe_fcb["fcb_id"] if probe_fcb else None

    done = {
        (r["ranking_id"], r["player_id_origen"])
        for r in conn.execute("SELECT DISTINCT ranking_id, player_id_origen FROM ranking_game_links")
    }
    # Combos ja comprovats SENSE partides (jugador inactiu en aquell rànquing):
    # els marquem perquè NO es tornin a mirar a cada reinici.
    empty_path = s.db_path.parent / "repas_empty.txt"
    empty_done: set[tuple[int, int]] = set()
    if empty_path.exists():
        for line in empty_path.read_text(encoding="utf-8").splitlines():
            if "," in line:
                a, b = line.split(",", 1)
                empty_done.add((int(a), int(b)))

    combos = [
        (r["num"], r["mod"], r["fcb"], r["nom"], r["modnom"], r["rid"], r["pid"])
        for r in conn.execute(
            """
            SELECT rk.num_seq AS num, m.codi_fcb AS mod, p.fcb_id AS fcb,
                   p.nom AS nom, m.nom AS modnom,
                   re.ranking_id AS rid, re.player_id AS pid
            FROM ranking_entries re
            JOIN rankings rk ON rk.id = re.ranking_id
            JOIN modalitats m ON m.id = rk.modalitat_id
            JOIN players p ON p.id = re.player_id
            WHERE p.fcb_id NOT LIKE 'name:%'
            ORDER BY rk.num_seq DESC, m.codi_fcb, p.fcb_id
            """
        )
        if (r["rid"], r["pid"]) not in done and (r["rid"], r["pid"]) not in empty_done
    ]
    conn.close()
    emptyf = open(empty_path, "a", encoding="utf-8")

    total = len(combos)
    logf = open(s.db_path.parent / "repas_progress.log", "a", encoding="utf-8")

    def emit(msg: str) -> None:
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    emit(f"=== combos pendents: {total} ===")
    ok = err = consec = 0

    def _new_client():
        cl = ScraperClient(s)
        cl.__enter__()
        return cl

    def _session_alive(cl) -> bool:
        """Sondeja un combo conegut amb partides. True si la sessió respon bé."""
        if not probe_fcb:
            return True
        try:
            url = _partides_url(s.base_url, PROBE_NUM, PROBE_MOD, probe_fcb, "datahome")
            html = cl.fetch_html(url, use_cache=False)
            return len(parse_partides_jugador(html).rows) > 0
        except Exception:  # noqa: BLE001
            return False

    def _wait_for_session(cl):
        """Atura i espera fins que la sessió torni (re-login manual o xarxa)."""
        emit("⚠️  SESSIÓ CAIGUDA — pausant. Si cal, re-logina:  uv run fcbillar login")
        waited = 0
        while True:
            time.sleep(30)
            waited += 30
            try:
                cl.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            cl = _new_client()
            if _session_alive(cl):
                emit(f"✅ Sessió recuperada després de {waited}s — reprenent")
                return cl
            if waited % 150 == 0:
                emit(f"   ...sessió encara caiguda ({waited}s). Re-logina si no ho has fet.")

    cl = _new_client()
    try:
        for i, (num, mod, fcb, nom, modnom, rid, pid) in enumerate(combos, 1):
            etiqueta = f"[{i}/{total}] {modnom:<12} R{num:<3} {nom[:26]:<26}"
            try:
                res = ingest_partides(
                    cl, num, mod, fcb, settings=s, create_missing_players=True, use_cache=False
                )
                ok += 1
                consec = 0
                tot, nou = res.games_upserted, res.games_new
                if tot == 0:
                    msg = "sense partides"
                    # marca aquest combo com a buit-comprovat (no es repetirà)
                    emptyf.write(f"{rid},{pid}\n")
                    emptyf.flush()
                elif nou == 0:
                    msg = f"{tot} ja descarregades"
                elif nou == tot:
                    msg = f"{nou} partides noves"
                else:
                    msg = f"{nou} noves (+{tot - nou} ja hi eren)"
                emit(f"{etiqueta} → {msg}")
            except Exception:  # noqa: BLE001
                err += 1
                consec += 1
                emit(f"{etiqueta} → (buit)")

            # Ratxa d'errors: pot ser un cluster de buits genuïns O la sessió morta.
            # Sondegem; si la sessió respon, era buit genuí (seguim). Si no, esperem.
            if consec >= 20:
                if _session_alive(cl):
                    consec = 0
                else:
                    cl = _wait_for_session(cl)
                    consec = 0

            # Keep-alive SENSE tancar el navegador (clau perquè la sessió duri:
            # el primer repàs va aguantar 57.000 amb un sol navegador obert).
            # Una sonda periòdica refresca el temporitzador i detecta caigudes;
            # el navegador NO es recrea (només dins _wait_for_session, si cau).
            if i % 100 == 0:
                if not _session_alive(cl):
                    cl = _wait_for_session(cl)
                else:
                    emit(f"  ── viu (ok={ok} err={err}) ──")
    finally:
        cl.__exit__(None, None, None)
    emit(f"=== FET ({ok}/{total}, err={err}) ===")
    logf.close()
    emptyf.close()


if __name__ == "__main__":
    main()
