"""Repàs PARAL·LEL de les partides d'un rànquing: N peticions concurrents.

Fins a l'agost de 2026 això eren N pestanyes de Chromium compartint una sessió,
perquè les partides exigien login i la federació tolerava les pestanyes però no
els navegadors separats. Amb el web nou són peticions HTTP normals: més ràpid,
sense navegador i sense sessió que es pugui morir a mitges.

Fetch en paral·lel (el coll d'ampolla és la xarxa); ingest a la BD inline amb
una sola connexió — l'event loop és d'un sol fil, o sigui que les escriptures
queden serialitzades i no calen locks.

Resumible (done-set + empty-skip), verbós i amb el mateix log estable.

És l'eina per posar-se al dia quan la federació toca un rànquing ja publicat,
cosa que fa sovint: durant l'agost de 2026 va afegir 104 jugadors al 124.
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys

import httpx

from fcbillar.config import get_settings
from fcbillar.db.migrations import ensure_schema
from fcbillar.db.repository import Repository
from fcbillar.pipeline import RankingGameLink, _build_game_from_raw_row, _partides_url
from fcbillar.scraper.parsers import parse_partides_jugador

N_CONCURRENTS = 3
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def load_pending(s):
    conn = sqlite3.connect(str(s.db_path))
    conn.row_factory = sqlite3.Row
    done = {
        (r["ranking_id"], r["player_id_origen"])
        for r in conn.execute("SELECT DISTINCT ranking_id, player_id_origen FROM ranking_game_links")
    }
    empty = set()
    ep = s.db_path.parent / "repas_empty.txt"
    if ep.exists():
        for line in ep.read_text(encoding="utf-8").splitlines():
            if "," in line:
                a, b = line.split(",", 1)
                empty.add((int(a), int(b)))
    rows = conn.execute(
        """SELECT rk.num_seq num, m.codi_fcb mod, p.fcb_id fcb, p.nom nom, m.nom modnom,
                  rk.format_url fmt, re.ranking_id rid, re.player_id pid
           FROM ranking_entries re JOIN rankings rk ON rk.id=re.ranking_id
           JOIN modalitats m ON m.id=rk.modalitat_id JOIN players p ON p.id=re.player_id
           WHERE p.fcb_id NOT LIKE 'name:%'
           ORDER BY rk.num_seq DESC, m.codi_fcb, p.fcb_id"""
    ).fetchall()
    conn.close()
    return [
        (r["num"], r["mod"], r["fcb"], r["nom"], r["modnom"], r["fmt"], r["rid"], r["pid"])
        for r in rows
        if (r["rid"], r["pid"]) not in done and (r["rid"], r["pid"]) not in empty
    ]


async def worker(tab, client, queue, repo, base, state, emit, emptyf):
    while not state["dead"]:
        try:
            num, mod, fcb, nom, modnom, fmt, rid, pid = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        state["i"] += 1
        et = f"[{state['i']}/{state['total']}] T{tab} {modnom:<11} R{num:<3} {nom[:24]:<24}"
        url = _partides_url(base, num, mod, fcb, fmt)
        try:
            resposta = await client.get(url)
            resposta.raise_for_status()
            parsed = parse_partides_jugador(resposta.text)
            owner = repo.get_player_nom_by_fcb_id(fcb)
            tot = new = 0
            for row in parsed.rows:
                game = _build_game_from_raw_row(row, mod, owner, repo, create_missing_players=True)
                if game is None:
                    continue
                if not repo.game_exists(game.id_natural):
                    new += 1
                repo.upsert_game(game)
                repo.link_game_to_ranking(RankingGameLink(num, mod, game.id_natural, fcb))
                tot += 1
            repo.conn.commit()
            state["ok"] += 1
            state["consec"] = 0
            if tot == 0:
                emptyf.write(f"{rid},{pid}\n")
                emptyf.flush()
                emit(f"{et} → sense partides")
            elif new == 0:
                emit(f"{et} → {tot} ja descarregades")
            elif new == tot:
                emit(f"{et} → {new} partides noves")
            else:
                emit(f"{et} → {new} noves (+{tot - new} ja hi eren)")
        except Exception:  # noqa: BLE001
            state["err"] += 1
            state["consec"] += 1
            emit(f"{et} → (buit)")
            if state["consec"] >= 25:
                state["dead"] = True
                emit("⚠️  Massa errors seguits — el portal no respon; atura i torna-hi.")


async def main():
    s = get_settings()
    pending = load_pending(s)
    total = len(pending)
    logf = open(s.db_path.parent / "repas_progress.log", "a", encoding="utf-8")
    emptyf = open(s.db_path.parent / "repas_empty.txt", "a", encoding="utf-8")

    def emit(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    emit(f"=== PARAL·LEL ({N_CONCURRENTS} peticions concurrents) · combos pendents: {total} ===")
    queue: asyncio.Queue = asyncio.Queue()
    for c in pending:
        queue.put_nowait(c)

    conn = ensure_schema(s.db_path)
    repo = Repository(conn)
    state = {"i": 0, "ok": 0, "err": 0, "consec": 0, "total": total, "dead": False}

    async with httpx.AsyncClient(
        headers={"User-Agent": UA, "Accept-Language": "ca-ES,ca;q=0.9"},
        follow_redirects=True,
        timeout=30.0,
    ) as client:
        await asyncio.gather(
            *[
                worker(t + 1, client, queue, repo, s.base_url, state, emit, emptyf)
                for t in range(N_CONCURRENTS)
            ]
        )

    emit(f"=== FET ({state['ok']} ok / {state['err']} err de {total}) ===")
    logf.close()
    emptyf.close()
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        N_CONCURRENTS = int(sys.argv[1])
    asyncio.run(main())
