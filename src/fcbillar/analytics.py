"""Anàlisi derivada: rendiment d'un jugador per nivell de l'oponent.

Per a la fitxa de jugador volem un gràfic "aranya" amb victòries i derrotes
contra oponents agrupats pel **nivell de rànquing en el moment de disputar la
partida**. Les branques **s'adapten al perfil del jugador**: N_BRANCHES branques,
les del mig d'igual amplada (un pas rodó, p. ex. 0,15) sobre el rang on hi ha el
gruix dels seus rivals (percentils 10-90), i la primera («< X») i l'última
(«≥ Y») obertes per als rivals que en queden fora. Així un jugador d'1,0+ veu la
resolució a dalt i un de 0,5 veu fines les seves franges, i dues branques veïnes
sempre estan separades pel mateix salt de nivell.

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

import math
import sqlite3
from bisect import bisect_right
from itertools import pairwise

N_BRANCHES = 8  # eixos de l'aranya: 6 d'igual amplada + els dos extrems oberts


def _fmt(v: float) -> str:
    """Format d'una mitjana per a etiqueta (coma decimal, 2 decimals)."""
    return f"{v:.2f}".replace(".", ",")


def _pas_rodo(cru: float) -> tuple[float, float]:
    """(pas, quàntum): el pas és el primer múltiple del quàntum que no és més
    petit que `cru`. El quàntum és mitja potència de 10 (0,05 per a Tres bandes,
    0,5 per a Lliure), mai per sota de 0,01, perquè les etiquetes van amb dos
    decimals."""
    q = max(10 ** math.floor(math.log10(cru)) / 2, 0.01)
    return math.ceil(cru / q - 1e-9) * q, q


def _even_buckets(games: list[tuple[int, float]], n: int = N_BRANCHES) -> list[dict]:
    """Franges d'igual amplada amb els extrems oberts. `games` = (res, rating) amb
    res ∈ {1 victòria, -1 derrota, 0 empat}.

    Les `n - 2` del mig cobreixen dels percentils 10 al 90 de les mitjanes dels
    rivals amb un pas rodó; la primera agafa el que queda per sota («< X») i
    l'última el que queda per sobre («≥ Y»). Cada franja és [mínim, màxim): la
    mateixa regla que aplica la web per saber de quina franja és una partida.
    Si tots els rivals tenen la mateixa mitjana, una sola franja."""
    if not games:
        return []
    rs = sorted(round(r, 4) for _res, r in games)
    total = len(rs)
    lo, hi = rs[int(0.10 * (total - 1))], rs[math.ceil(0.90 * (total - 1))]
    if hi <= lo:
        lo, hi = rs[0], rs[-1]

    def franja(order: int, label: str, mn: float | None, mx: float | None, ress) -> dict:
        ress = list(ress)
        return {
            "order": order,
            "label": label,
            "rating_min": mn,
            "rating_max": mx,
            "wins": ress.count(1),
            "losses": ress.count(-1),
            "draws": ress.count(0),
        }

    if hi <= lo:
        return [franja(0, _fmt(lo), None, None, (res for res, _r in games))]

    m = n - 2
    pas, q = _pas_rodo((hi - lo) / m)
    inici = math.floor(lo / q + 1e-9) * q
    # Alinear l'inici al quàntum el pot haver baixat: si el tram del mig ja no
    # arriba al percentil 90, s'eixampla el pas un quàntum més.
    while inici + m * pas < hi - 1e-9:
        pas += q
    edges = [round(inici + k * pas, 4) for k in range(m + 1)]

    per_franja: list[list[int]] = [[] for _ in range(m + 2)]
    for res, r in games:
        per_franja[bisect_right(edges, round(r, 4))].append(res)

    buckets = [franja(0, f"< {_fmt(edges[0])}", None, edges[0], per_franja[0])]
    for k in range(1, m + 1):
        a, b = edges[k - 1], edges[k]
        buckets.append(franja(k, f"{_fmt(a)}-{_fmt(b)}", a, b, per_franja[k]))
    buckets.append(franja(m + 1, f"≥ {_fmt(edges[-1])}", edges[-1], None, per_franja[m + 1]))
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
            if lo is None and hi is None:
                continue  # una sola franja sense límits: no hi ha nivell on situar-la
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


def _sql_opp_rating(modalitat_codi: int, n_players: int = 0) -> str:
    """Una fila per partida-subjecte de la modalitat: (game_id, me, opp, res,
    rank_rating, game_rating). `rank_rating` és la mitjana de rànquing del rival
    al snapshot on la partida entra a la finestra (link de num_seq mínim);
    `game_rating`, la mitjana del rival en aquella partida.

    Amb `n_players` > 0 filtra per jugador dins de cada branca de la unió (els
    paràmetres van dues vegades): si el filtre va fora, SQLite calcula la
    subconsulta per a totes les partides de la modalitat."""
    f1 = f2 = ""
    if n_players:
        ph = ",".join("?" * n_players)
        f1, f2 = f" AND g.player1_id IN ({ph})", f" AND g.player2_id IN ({ph})"
    return f"""
        WITH tb AS (SELECT id AS mid FROM modalitats WHERE codi_fcb = {int(modalitat_codi)}),
        subj AS (
            SELECT g.id AS game_id, g.player1_id AS me, g.player2_id AS opp,
                   CASE WHEN g.guanyador_id = g.player1_id THEN 1
                        WHEN g.guanyador_id IS NULL THEN 0 ELSE -1 END AS res,
                   g.caramboles2 AS opp_car, g.entrades AS ent
            FROM games g WHERE g.modalitat_id = (SELECT mid FROM tb){f1}
            UNION ALL
            SELECT g.id, g.player2_id, g.player1_id,
                   CASE WHEN g.guanyador_id = g.player2_id THEN 1
                        WHEN g.guanyador_id IS NULL THEN 0 ELSE -1 END,
                   g.caramboles1, g.entrades
            FROM games g WHERE g.modalitat_id = (SELECT mid FROM tb){f2}
        )
        SELECT s.game_id, s.me, s.opp, s.res,
            (SELECT e.mitjana_general
             FROM ranking_game_links l
             JOIN rankings r ON r.id = l.ranking_id
                            AND r.modalitat_id = (SELECT mid FROM tb)
             JOIN ranking_entries e ON e.ranking_id = r.id
                                   AND e.player_id = l.player_id_origen
             WHERE l.game_id = s.game_id AND l.player_id_origen = s.opp
             ORDER BY r.num_seq ASC LIMIT 1) AS rank_rating,
            (CAST(s.opp_car AS REAL) / NULLIF(s.ent, 0)) AS game_rating
        FROM subj s
    """


def _opp_rating_rows(
    conn: sqlite3.Connection, modalitat_codi: int, player_ids: list[int] | None
) -> list[tuple[int, int, float]]:
    """(player_id, res, opp_rating) per cada partida-subjecte de la modalitat.

    `res` ∈ {1, 0, -1}. `opp_rating` = mitjana de rànquing del rival al moment de
    la partida amb fallback a la mitjana de la partida. Les partides sense cap
    mitjana de rival queden excloses."""
    ids = list(player_ids) if player_ids is not None else []
    out = []
    for _gid, me, _opp, res, rank_r, game_r in conn.execute(
        _sql_opp_rating(modalitat_codi, len(ids)), ids + ids
    ):
        r = rank_r if rank_r is not None else game_r
        if r is not None:
            out.append((me, res, float(r)))
    return out


def rank_ratings_by_game(conn: sqlite3.Connection, modalitat_codi: int) -> dict[tuple, float]:
    """{(game_id, player_id): mitjana de rànquing del jugador quan es va jugar la
    partida}, només quan la té (sense el fallback de la mitjana de la partida).

    La web la llegeix per ensenyar, a cada branca de l'aranya, quin nivell tenia
    el rival; si falta, hi posa la mitjana de la partida, igual que el càlcul de
    les franges."""
    out: dict[tuple, float] = {}
    for gid, _me, opp, _res, rank_r, _game_r in conn.execute(_sql_opp_rating(modalitat_codi)):
        if rank_r is not None:
            out[(gid, opp)] = round(float(rank_r), 4)
    return out


def rating_breakdown(
    conn: sqlite3.Connection,
    modalitat_codi: int = 1,
    player_ids: list[int] | None = None,
) -> dict[int, dict]:
    """Perfil de rendiment per nivell de rival, per jugador.

    Retorna `{player_id: {"buckets": [...], "weighted_index": float|None,
    "crossover": float|None, "total": int}}`. Les franges són d'igual amplada
    sobre el gruix dels rivals de cada jugador (vegeu `_even_buckets`), de manera
    que s'adapten soles a l'escala de cada modalitat (Tres bandes ~0,2-1,8;
    Lliure ~5-40…)."""
    if player_ids is not None and not player_ids:
        return {}

    by_player: dict[int, list[tuple[int, float]]] = {}
    for me, res, rating in _opp_rating_rows(conn, modalitat_codi, player_ids):
        by_player.setdefault(me, []).append((res, rating))

    out: dict[int, dict] = {}
    for pid, games in by_player.items():
        buckets = _even_buckets(games)
        out[pid] = {
            "buckets": buckets,
            "weighted_index": _weighted_index(games),
            "crossover": _crossover(buckets),
            "total": len(games),
        }
    return out
