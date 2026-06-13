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

WINDOW_T = 3  # mitja finestra en dècimes (±0,3 al voltant del nivell del jugador)
STEP_T = 1    # amplada de cada franja central en dècimes (0,1)


def _fmt(v: float) -> str:
    """Format d'una dècima per a etiqueta (coma decimal, 1 decimal). 0,2 / 1,0."""
    return f"{v:.1f}".replace(".", ",")


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _centered_buckets(games: list[tuple[int, float]], center: float) -> list[dict]:
    """Franges centrades en el nivell del jugador, amb límits a la dècima i les
    cues agrupades. `games` = (res, rating) amb res ∈ {1, -1, 0}. `center` = nivell
    del jugador (la seva mitjana de rànquing).

    Una finestra de ±0,3 al voltant del centre es talla en franges de 0,1; tot el
    que cau per sota de la finestra va a un paquet "< x" i tot el que cau per sobre
    a un paquet "> y". P.ex. centre 0,6 → < 0,3 · 0,3-0,4 · … · 0,8-0,9 · > 0,9."""
    c_t = round(center * 10)
    lo_t = c_t - WINDOW_T
    hi_t = c_t + WINDOW_T
    has_low = lo_t > 0  # cap rival per sota de 0,0: no cal cua inferior

    edges_t = list(range(max(lo_t, 0), hi_t + 1, STEP_T))  # límits interns (dècimes)
    buckets: list[dict] = []
    if has_low:
        buckets.append({
            "order": 0, "label": f"< {_fmt(lo_t / 10)}",
            "rating_min": None, "rating_max": lo_t / 10,
            "wins": 0, "losses": 0, "draws": 0,
        })
    for a, b in pairwise(edges_t):
        buckets.append({
            "order": len(buckets), "label": f"{_fmt(a / 10)}-{_fmt(b / 10)}",
            "rating_min": a / 10, "rating_max": b / 10,
            "wins": 0, "losses": 0, "draws": 0,
        })
    buckets.append({
        "order": len(buckets), "label": f"> {_fmt(hi_t / 10)}",
        "rating_min": hi_t / 10, "rating_max": None,
        "wins": 0, "losses": 0, "draws": 0,
    })

    first_inner = 1 if has_low else 0
    for res, r in games:
        rt = round(r * 10, 4)
        if has_low and rt < lo_t:
            idx = 0
        elif rt >= hi_t:
            idx = len(buckets) - 1
        else:
            idx = first_inner + int((rt - max(lo_t, 0)) / STEP_T + 1e-9)
            idx = min(idx, len(buckets) - 2)  # no envair la cua superior
        if res == 1:
            buckets[idx]["wins"] += 1
        elif res == -1:
            buckets[idx]["losses"] += 1
        else:
            buckets[idx]["draws"] += 1
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


def _player_centers(
    conn: sqlite3.Connection, player_ids: list[int] | None
) -> dict[int, float]:
    """Nivell de cada jugador = la seva mitjana de rànquing Tres bandes més recent."""
    filt, params = "", []
    if player_ids is not None:
        ph = ",".join("?" * len(player_ids))
        filt = f"AND p.id IN ({ph})"
        params = list(player_ids)
    centers: dict[int, float] = {}
    for pid, mg in conn.execute(
        f"""
        SELECT p.id, re.mitjana_general
        FROM ranking_entries re
        JOIN rankings rk ON rk.id = re.ranking_id
        JOIN modalitats m ON m.id = rk.modalitat_id
        JOIN players p ON p.id = re.player_id
        WHERE m.codi_fcb = 1 {filt}
        ORDER BY rk.num_seq DESC
        """,
        params,
    ):
        if pid not in centers and mg is not None:
            centers[pid] = float(mg)
    return centers


def rating_breakdown(
    conn: sqlite3.Connection,
    modalitat_codi: int = 1,
    player_ids: list[int] | None = None,
) -> dict[int, dict]:
    """Perfil de rendiment per nivell de rival, per jugador.

    Retorna `{player_id: {"buckets": [...], "center": float, "weighted_index":
    float|None, "crossover": float|None, "total": int}}`. Les franges es centren
    en el nivell del jugador (±0,3 en passos de 0,1, cues agrupades). De moment
    només Tres bandes; per a altres modalitats retorna {}."""
    if modalitat_codi != 1:
        return {}
    if player_ids is not None and not player_ids:
        return {}

    by_player: dict[int, list[tuple[int, float]]] = {}
    for me, res, rating in _opp_rating_rows(conn, modalitat_codi, player_ids):
        by_player.setdefault(me, []).append((res, rating))

    centers = _player_centers(conn, list(by_player.keys()) or None)
    out: dict[int, dict] = {}
    for pid, games in by_player.items():
        # Sense rànquing propi: aproximem el nivell amb la mediana dels rivals.
        center = centers.get(pid)
        if center is None:
            center = _median([r for _res, r in games])
        buckets = _centered_buckets(games, center)
        out[pid] = {
            "buckets": buckets,
            "center": round(center, 3),
            "weighted_index": _weighted_index(games),
            "crossover": _crossover(buckets),
            "total": len(games),
        }
    return out
