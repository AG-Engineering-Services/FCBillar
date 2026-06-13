"""Anàlisi derivada: rendiment d'un jugador per nivell de l'oponent.

Per a la fitxa de jugador volem un gràfic "aranya" amb victòries i derrotes
contra oponents agrupats pel **nivell de rànquing en el moment de disputar la
partida**. Les branques **s'adapten al perfil del jugador**: un nombre fix de
branques (N_BRANCHES) d'igual amplada que reparteixen el rang real de rivals que
ha trobat (del més fluix al més fort). Així un jugador d'1,0+ veu la resolució a
dalt (1,1/1,2/1,3) i un de 0,5 veu fines les seves franges, en lloc d'una graella
fixa que els amaga.

Definició de la "mitjana de rànquing de l'oponent en aquell moment" (per cada
partida + oponent O):

1. **Primari** — la `mitjana_general` d'O al snapshot on la partida entra a la
   finestra de rànquing: la fila de `ranking_game_links` d'O per aquesta partida
   amb el `num_seq` mínim. És la mateixa relació que fa servir `player_games`.
2. **Fallback** — si O no té cap link per aquesta partida, la mitjana de la
   pròpia partida (`caramboles_oponent / entrades`).
3. Si no hi ha cap de les dues, la partida no es classifica.

A més es calculen dos indicadors (només partides decisives):
  - `weighted_index`: % de victòries ponderat pel nivell del rival (guanyar forts
    compta més). 100 · Σ_victòries r / Σ_decisives r.
  - `crossover`: nivell de rival on la taxa de victòries creua el 50% ("ets
    competitiu fins a ~X"), interpolat sobre les branques.

De moment només Tres bandes (codi_fcb = 1).
"""

from __future__ import annotations

import sqlite3
from itertools import pairwise

QUANTILE_N = 8  # nombre d'eixos; cada franja conté ~ el mateix nombre de partides


def _fmt(v: float) -> str:
    """Format d'una mitjana per a etiqueta (coma decimal, 2 decimals)."""
    return f"{v:.2f}".replace(".", ",")


def _quantile_buckets(games: list[tuple[int, float]], n: int = QUANTILE_N) -> list[dict]:
    """Franges per quantils: cada una conté ~el mateix nombre de partides, de
    manera que els rangs s'estrenyen on el jugador té més rivals. `games` =
    (res, rating) amb res ∈ {1 victòria, -1 derrota, 0 empat}.

    Es talla l'ordre de rivals en `n` trams d'igual mida **sense partir rivals amb
    la mateixa mitjana** (mateix valor → mateixa franja), així que pot retornar
    menys de `n` franges si hi ha molts empats de mitjana o poques partides."""
    if not games:
        return []
    gs = sorted(games, key=lambda g: g[1])
    ratings = [r for _res, r in gs]
    total = len(gs)

    # Índexs de tall: ~total/n per franja, empenyent el tall fins al final d'un
    # grup de mitjanes iguals per no partir-lo.
    edges = [0]
    for k in range(1, n):
        t = round(k * total / n)
        while 0 < t < total and ratings[t] == ratings[t - 1]:
            t += 1
        if edges[-1] < t < total:
            edges.append(t)
    edges.append(total)

    buckets = []
    for j, (lo_i, hi_i) in enumerate(pairwise(edges)):
        chunk = gs[lo_i:hi_i]
        lo_r, hi_r = ratings[lo_i], ratings[hi_i - 1]
        buckets.append({
            "order": j,
            "label": _fmt(lo_r) if lo_r == hi_r else f"{_fmt(lo_r)}-{_fmt(hi_r)}",
            "rating_min": round(lo_r, 4),
            "rating_max": round(hi_r, 4),
            "wins": sum(1 for res, _r in chunk if res == 1),
            "losses": sum(1 for res, _r in chunk if res == -1),
            "draws": sum(1 for res, _r in chunk if res == 0),
        })
    return buckets


def _weighted_index(games: list[tuple[int, float]]) -> float | None:
    """% de victòries ponderat pel nivell del rival (només decisives)."""
    num = den = 0.0
    for res, r in games:
        if res == 0:
            continue
        den += r
        if res == 1:
            num += r
    return round(100 * num / den, 1) if den > 0 else None


def _crossover(buckets: list[dict]) -> float | None:
    """Nivell de rival on la taxa de victòries creua el 50%, interpolat sobre els
    punts mitjos de les branques amb partides decisives."""
    pts = []
    for b in buckets:
        dec = b["wins"] + b["losses"]
        if dec:
            lo, hi = b["rating_min"], b["rating_max"]
            rep = hi if lo is None else lo if hi is None else (lo + hi) / 2
            pts.append((rep, b["wins"] / dec))
    if not pts:
        return None
    if all(wr >= 0.5 for _m, wr in pts):
        return round(pts[-1][0], 3)  # competitiu fins al rival més fort
    if all(wr < 0.5 for _m, wr in pts):
        return round(pts[0][0], 3)  # per sota de tot el rang
    for (m0, w0), (m1, w1) in pairwise(pts):
        if w0 >= 0.5 > w1:
            if w1 == w0:
                return round(m1, 3)
            return round(m0 + (0.5 - w0) * (m1 - m0) / (w1 - w0), 3)
    return round(pts[-1][0], 3)


def _opp_rating_rows(
    conn: sqlite3.Connection, modalitat_codi: int, player_ids: list[int] | None
) -> list[tuple[int, int, float]]:
    """(player_id, res, opp_rating) per cada partida-subjecte de la modalitat.

    `res` ∈ {1, 0, -1}. `opp_rating` = mitjana de rànquing del rival al moment de
    la partida (link de num_seq mínim) amb fallback a la mitjana de la partida.
    Les partides sense cap mitjana de rival queden excloses."""
    filt, params = "", []
    if player_ids is not None:
        ph = ",".join("?" * len(player_ids))
        filt = f"WHERE me IN ({ph})"
        params = list(player_ids)

    sql = f"""
        WITH tb AS (SELECT id AS mid FROM modalitats WHERE codi_fcb = {int(modalitat_codi)}),
        subj AS (
            SELECT g.id AS game_id, g.player1_id AS me, g.player2_id AS opp,
                   CASE WHEN g.guanyador_id = g.player1_id THEN 1
                        WHEN g.guanyador_id IS NULL THEN 0 ELSE -1 END AS res,
                   g.caramboles2 AS opp_car, g.entrades AS ent
            FROM games g WHERE g.modalitat_id = (SELECT mid FROM tb)
            UNION ALL
            SELECT g.id, g.player2_id, g.player1_id,
                   CASE WHEN g.guanyador_id = g.player2_id THEN 1
                        WHEN g.guanyador_id IS NULL THEN 0 ELSE -1 END,
                   g.caramboles1, g.entrades
            FROM games g WHERE g.modalitat_id = (SELECT mid FROM tb)
        ),
        rated AS (
            SELECT s.me, s.res,
                COALESCE(
                    (SELECT e.mitjana_general
                     FROM ranking_game_links l
                     JOIN rankings r ON r.id = l.ranking_id
                                    AND r.modalitat_id = (SELECT mid FROM tb)
                     JOIN ranking_entries e ON e.ranking_id = r.id
                                           AND e.player_id = l.player_id_origen
                     WHERE l.game_id = s.game_id AND l.player_id_origen = s.opp
                     ORDER BY r.num_seq ASC LIMIT 1),
                    (CAST(s.opp_car AS REAL) / NULLIF(s.ent, 0))
                ) AS opp_rating
            FROM subj s
        )
        SELECT me, res, opp_rating FROM rated {filt}
    """
    out = []
    for me, res, opp_rating in conn.execute(sql, params):
        if opp_rating is not None:
            out.append((me, res, float(opp_rating)))
    return out


def rating_breakdown(
    conn: sqlite3.Connection,
    modalitat_codi: int = 1,
    player_ids: list[int] | None = None,
) -> dict[int, dict]:
    """Perfil de rendiment per nivell de rival, per jugador.

    Retorna `{player_id: {"buckets": [...], "weighted_index": float|None,
    "crossover": float|None, "total": int}}`. Les franges es reparteixen per
    quantils (cada eix ~ el mateix nombre de partides), de manera que el repartiment
    s'adapta sol a l'escala de cada modalitat (Tres bandes ~0,2-1,8; Lliure ~5-40…)."""
    if player_ids is not None and not player_ids:
        return {}

    by_player: dict[int, list[tuple[int, float]]] = {}
    for me, res, rating in _opp_rating_rows(conn, modalitat_codi, player_ids):
        by_player.setdefault(me, []).append((res, rating))

    out: dict[int, dict] = {}
    for pid, games in by_player.items():
        buckets = _quantile_buckets(games)
        out[pid] = {
            "buckets": buckets,
            "weighted_index": _weighted_index(games),
            "crossover": _crossover(buckets),
            "total": len(games),
        }
    return out
