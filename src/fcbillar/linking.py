"""Vincula partides individuals del rànquing (`games`) amb el campionat concret.

El portal etiqueta les partides baixades del rànquing només amb la categoria
genèrica `INDIVIDUAL`. Per saber de QUIN campionat és cada partida creuem la taula
`games` amb `torneig_partides` (els resultats reals scrapejats de cada campionat,
vegeu scripts/ingest_open_games.py):

    una partida de campionat (parella de jugadors + caramboles + entrades, dins
    d'una modalitat) identifica de manera (gairebé) única una partida del rànquing.

Quan hi ha coincidència exacta omplim `games.torneig_id` / `games.torneig_fase_id`
/ `games.torneig_link_method = 'exacte'`.

El mòdul separa la lògica pura de matching (`match_partida_to_games`, fàcil de
provar) del runner que toca la BD (`link_individual_games`).
"""

from __future__ import annotations

import logging
import sqlite3
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


def normalize_name(nom: str | None) -> str:
    """Normalitza un nom per a comparació robusta (sense accents, minúscules)."""
    s = "".join(
        c for c in unicodedata.normalize("NFD", nom or "") if unicodedata.category(c) != "Mn"
    )
    return " ".join(s.strip().lower().split())


@dataclass(frozen=True)
class GameRow:
    """Una partida individual del rànquing, candidata a ser vinculada."""

    id: str
    modalitat_id: int
    player1_id: int
    player2_id: int
    caramboles1: int | None
    caramboles2: int | None
    serie_max1: int | None
    serie_max2: int | None
    entrades: int | None
    data_partida: str | None = None


def season_of(data_partida: str | None) -> str | None:
    """Temporada (ex. '2023-2024') a partir de la data, amb tall a l'agost."""
    if not data_partida or len(data_partida) < 7:
        return None
    y, mo = int(data_partida[:4]), int(data_partida[5:7])
    return f"{y}-{y + 1}" if mo >= 8 else f"{y - 1}-{y}"


def _multiset(a, b) -> tuple | None:
    """Parella ordenada (multiset) si tots dos valors hi són; si no, None."""
    if a is None or b is None:
        return None
    return tuple(sorted((a, b)))


def match_partida_to_games(
    *,
    modalitat_id: int | None,
    caramboles: tuple[int, int],
    entrades: int | None,
    serie: tuple[int | None, int | None],
    candidates: list[GameRow],
) -> list[GameRow]:
    """Retorna els `games` que casen exactament amb una partida de campionat.

    Criteris (tots, dins de la mateixa parella de jugadors que ja filtra el caller):
      - modalitat: igual a la del torneig (si la coneixem; si és None, no filtra).
      - caramboles: multiset {c1, c2} idèntic.
      - entrades: iguals quan totes dues fonts el tenen.
    Si en queda més d'un, s'usa la sèrie major com a desempat.
    """
    target_car = tuple(sorted(caramboles))
    hits: list[GameRow] = []
    for g in candidates:
        if modalitat_id is not None and g.modalitat_id != modalitat_id:
            continue
        g_car = _multiset(g.caramboles1, g.caramboles2)
        if g_car is None or g_car != target_car:
            continue
        if entrades is not None and g.entrades is not None and g.entrades != entrades:
            continue
        hits.append(g)

    if len(hits) <= 1:
        return hits

    # Desempat per sèrie major (quan la tenim a totes dues bandes).
    target_serie = _multiset(serie[0], serie[1])
    if target_serie is not None:
        refined = [g for g in hits if _multiset(g.serie_max1, g.serie_max2) == target_serie]
        if refined:
            return refined
    return hits


@dataclass
class LinkResult:
    torneig_partides: int = 0  # files de torneig_partides processades
    linked_games: int = 0  # partides del rànquing vinculades
    matched_partides: int = 0  # partides de campionat amb ≥1 game
    ambiguous: int = 0  # >1 game i la sèrie no desempata
    unresolved_players: int = 0  # noms no resolts (byes "Descansa", etc.)
    unknown_torneig: int = 0  # (torneig,divisió) sense fila a torneigs_individuals
    no_game: int = 0  # cap game casa (forat del rànquing)
    conflicts: int = 0  # un game que casaria amb torneigs diferents
    conflict_samples: list = field(default_factory=list)


def _build_name_index(conn: sqlite3.Connection) -> dict[str, int]:
    """norm(nom) → player_id, només per a noms NO ambigus (un sol jugador)."""
    by_norm: dict[str, set[int]] = defaultdict(set)
    for pid, nom in conn.execute("SELECT id, nom FROM players"):
        by_norm[normalize_name(nom)].add(pid)
    return {n: next(iter(ids)) for n, ids in by_norm.items() if len(ids) == 1}


def _build_torneig_index(
    conn: sqlite3.Connection,
) -> dict[tuple[int, int], tuple[int, int | None, str | None]]:
    """(torneig_id_extern, divisio_id_extern) → (id, modalitat_id, temporada)."""
    out: dict[tuple[int, int], tuple[int, int | None, str | None]] = {}
    for r in conn.execute(
        "SELECT ti.id, ti.torneig_id_extern, ti.divisio_id_extern, ti.modalitat_id, te.nom AS temp "
        "FROM torneigs_individuals ti LEFT JOIN temporades te ON te.id = ti.temporada_id"
    ):
        out[(r["torneig_id_extern"], r["divisio_id_extern"])] = (
            r["id"],
            r["modalitat_id"],
            r["temp"],
        )
    return out


def _index_individual_games(
    conn: sqlite3.Connection,
) -> dict[frozenset[int], list[GameRow]]:
    """Indexa les partides INDIVIDUAL per parella de jugadors (frozenset d'ids)."""
    by_pair: dict[frozenset[int], list[GameRow]] = defaultdict(list)
    for r in conn.execute(
        """
        SELECT g.id, g.modalitat_id, g.player1_id, g.player2_id,
               g.caramboles1, g.caramboles2, g.serie_max1, g.serie_max2,
               g.entrades, g.data_partida
        FROM games g
        JOIN competicions co ON co.id = g.competicio_id
        WHERE UPPER(co.nom) = 'INDIVIDUAL'
        """
    ):
        g = GameRow(
            id=r["id"],
            modalitat_id=r["modalitat_id"],
            player1_id=r["player1_id"],
            player2_id=r["player2_id"],
            caramboles1=r["caramboles1"],
            caramboles2=r["caramboles2"],
            serie_max1=r["serie_max1"],
            serie_max2=r["serie_max2"],
            entrades=r["entrades"],
            data_partida=r["data_partida"],
        )
        by_pair[frozenset((g.player1_id, g.player2_id))].append(g)
    return by_pair


def link_individual_games(conn: sqlite3.Connection) -> LinkResult:
    """Recalcula (idempotent) l'atribució exacta de campionat a `games`.

    Neteja els vincles 'exacte' previs i els torna a calcular des de zero.
    """
    res = LinkResult()
    name_idx = _build_name_index(conn)
    torneig_idx = _build_torneig_index(conn)
    games_by_pair = _index_individual_games(conn)

    # Reset idempotent dels vincles que gestiona aquest mètode.
    conn.execute(
        "UPDATE games SET torneig_id = NULL, torneig_fase_id = NULL, "
        "torneig_link_method = NULL WHERE torneig_link_method = 'exacte'"
    )

    # game_id → (torneig_id, season_match, update_index). Permet resoldre conflictes:
    # si un game encaixa amb dos torneigs (mateixa parella+resultat en temporades
    # diferents), guanya el torneig la temporada del qual coincideix amb la data
    # del game. La data NO es fa servir com a filtre dur (perdria ~90 partides que
    # cauen al voltant del tall d'agost), només com a desempat de conflictes.
    assigned: dict[str, tuple[int, bool, int]] = {}
    updates: list[list] = []  # [torneig_id, fase_id, game_id]

    for tp in conn.execute("SELECT * FROM torneig_partides"):
        res.torneig_partides += 1
        p1 = name_idx.get(normalize_name(tp["player1_nom"]))
        p2 = name_idx.get(normalize_name(tp["player2_nom"]))
        if p1 is None or p2 is None or p1 == p2:
            res.unresolved_players += 1
            continue
        torneig = torneig_idx.get((tp["torneig_id_extern"], tp["divisio_id_extern"]))
        if torneig is None:
            res.unknown_torneig += 1
            continue
        torneig_id, modalitat_id, temporada = torneig

        candidates = games_by_pair.get(frozenset((p1, p2)), [])
        hits = match_partida_to_games(
            modalitat_id=modalitat_id,
            caramboles=(tp["caramboles1"], tp["caramboles2"]),
            entrades=tp["entrades"],
            serie=(tp["serie1"], tp["serie2"]),
            candidates=candidates,
        )
        if not hits:
            res.no_game += 1
            continue
        if len(hits) > 1:
            res.ambiguous += 1
        res.matched_partides += 1

        for g in hits:
            season_match = temporada is not None and season_of(g.data_partida) == temporada
            prev = assigned.get(g.id)
            if prev is None:
                assigned[g.id] = (torneig_id, season_match, len(updates))
                updates.append([torneig_id, tp["fase_id"], g.id])
            elif prev[0] != torneig_id:
                res.conflicts += 1
                if len(res.conflict_samples) < 20:
                    res.conflict_samples.append((g.id, prev[0], torneig_id))
                # Desempat: si el nou torneig casa la temporada i l'anterior no, el reemplacem.
                if season_match and not prev[1]:
                    updates[prev[2]][0] = torneig_id
                    updates[prev[2]][1] = tp["fase_id"]
                    assigned[g.id] = (torneig_id, season_match, prev[2])

    conn.executemany(
        "UPDATE games SET torneig_id = ?, torneig_fase_id = ?, "
        "torneig_link_method = 'exacte' WHERE id = ?",
        [tuple(u) for u in updates],
    )
    res.linked_games = len(updates)
    return res


@dataclass
class CoverageRow:
    season: str | None
    total: int
    linked: int

    @property
    def pct(self) -> int:
        return round(100 * self.linked / self.total) if self.total else 0


def coverage_by_season(conn: sqlite3.Connection) -> list[CoverageRow]:
    """Cobertura de l'atribució: partides INDIVIDUAL vinculades vs totals, per temporada.

    La temporada es deriva de la data de la partida (tall a l'agost, com a la lliga)
    perquè una partida no vinculada no té torneig del qual treure-la.
    """
    rows = conn.execute(
        """
        SELECT
            CASE WHEN CAST(substr(g.data_partida, 6, 2) AS INTEGER) >= 8
                 THEN substr(g.data_partida, 1, 4) || '-' ||
                      (CAST(substr(g.data_partida, 1, 4) AS INTEGER) + 1)
                 ELSE (CAST(substr(g.data_partida, 1, 4) AS INTEGER) - 1) || '-' ||
                      substr(g.data_partida, 1, 4)
            END AS season,
            COUNT(*) AS total,
            SUM(CASE WHEN g.torneig_id IS NOT NULL THEN 1 ELSE 0 END) AS linked
        FROM games g
        JOIN competicions co ON co.id = g.competicio_id
        WHERE UPPER(co.nom) = 'INDIVIDUAL'
        GROUP BY season
        ORDER BY season
        """
    ).fetchall()
    return [CoverageRow(season=r["season"], total=r["total"], linked=r["linked"]) for r in rows]
