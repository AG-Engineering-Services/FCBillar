"""Model: accés a la BD SQLite sense dependències de Qt.

Tot el SQL viu aquí; els controllers el cridaran i emetran signals
amb els DataFrames resultants.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "fcbillar.db"


@dataclass
class Counts:
    clubs: int = 0
    players: int = 0
    rankings: int = 0
    games: int = 0
    encontres_lliga: int = 0
    temporades: int = 0


@dataclass
class ClubKpi:
    fcb_id: str
    nom: str
    num_jugadors: int
    num_equips: int
    num_partides: int


@dataclass
class PlayerKpi:
    fcb_id: str
    nom: str
    club: str | None
    num_partides: int
    seguiment: bool


@dataclass
class RankingEntry:
    modalitat: str
    posicio: int | None
    nom: str
    fcb_id: str
    mitjana: float | None
    mitjana_contraris: float | None
    caramboles: int | None
    entrades: int | None
    punts: int | None
    punts_totals: int | None
    definitiva: bool


@dataclass
class GameRow:
    data: str
    modalitat: str
    competicio: str | None
    local: str
    cara1: int | None
    visitant: str
    cara2: int | None
    entrades: int | None
    arbitre: str | None
    club_local: str | None = None
    club_visitant: str | None = None


class DataSource:
    """Façana de queries SQL. Reutilitzable des de controllers o tests."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._db_path = db_path

    # ------------- helpers -------------

    def _conn(self) -> sqlite3.Connection:
        if not self._db_path.exists():
            raise FileNotFoundError(
                f"BD no trobada a {self._db_path}. "
                f"Executa primer `uv run fcbillar import-temporada --historical`."
            )
        c = sqlite3.connect(str(self._db_path), check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    # ------------- counts -------------

    def counts(self) -> Counts:
        with self._conn() as c:
            def n(table: str) -> int:
                return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            return Counts(
                clubs=n("clubs"),
                players=n("players"),
                rankings=n("rankings"),
                games=n("games"),
                encontres_lliga=n("encontres_lliga"),
                temporades=n("temporades"),
            )

    # ------------- modalitats / rànquings -------------

    def modalitats(self) -> list[tuple[int, str]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT codi_fcb, nom FROM modalitats ORDER BY codi_fcb"
            ).fetchall()
            return [(r["codi_fcb"], r["nom"]) for r in rows]

    def top_ranking_per_modalitat(self, top_n: int = 10) -> list[RankingEntry]:
        """Top N del rànquing més recent per cada modalitat."""
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT m.nom AS modalitat, e.posicio, p.nom, p.fcb_id,
                       e.mitjana_general,
                       json_extract(e.extras_json, '$.mitjana_contraris') AS mitjana_contraris,
                       json_extract(e.extras_json, '$.caramboles')        AS caramboles,
                       json_extract(e.extras_json, '$.entrades')          AS entrades,
                       json_extract(e.extras_json, '$.punts')             AS punts,
                       json_extract(e.extras_json, '$.punts_totals')      AS punts_totals,
                       COALESCE(json_extract(e.extras_json, '$.definitiva'), 0) AS def
                FROM ranking_entries e
                JOIN rankings r   ON r.id = e.ranking_id
                JOIN modalitats m ON m.id = r.modalitat_id
                JOIN players p    ON p.id = e.player_id
                WHERE r.num_seq = (
                    SELECT MAX(r2.num_seq) FROM rankings r2 WHERE r2.modalitat_id = r.modalitat_id
                )
                  AND e.posicio <= ?
                ORDER BY m.codi_fcb, e.posicio
                """,
                (top_n,),
            ).fetchall()
            return [
                RankingEntry(
                    modalitat=r["modalitat"],
                    posicio=r["posicio"],
                    nom=r["nom"],
                    fcb_id=r["fcb_id"],
                    mitjana=r["mitjana_general"],
                    mitjana_contraris=r["mitjana_contraris"],
                    caramboles=r["caramboles"],
                    entrades=r["entrades"],
                    punts=r["punts"],
                    punts_totals=r["punts_totals"],
                    definitiva=bool(r["def"]),
                )
                for r in rows
            ]

    # ------------- clubs -------------

    def clubs_with_kpis(self) -> list[ClubKpi]:
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT c.fcb_id, c.nom,
                       COUNT(DISTINCT p.id) AS num_jugadors,
                       (SELECT COUNT(*) FROM equips e WHERE e.club_id = c.id) AS num_equips,
                       (
                         SELECT COUNT(DISTINCT g.id) FROM games g
                         WHERE g.equip1_id IN (SELECT id FROM equips WHERE club_id = c.id)
                            OR g.equip2_id IN (SELECT id FROM equips WHERE club_id = c.id)
                       ) AS num_partides
                FROM clubs c
                LEFT JOIN players p ON p.club_id = c.id
                GROUP BY c.id, c.fcb_id, c.nom
                ORDER BY num_partides DESC, c.nom
                """
            ).fetchall()
            return [
                ClubKpi(
                    fcb_id=r["fcb_id"],
                    nom=r["nom"],
                    num_jugadors=r["num_jugadors"],
                    num_equips=r["num_equips"],
                    num_partides=r["num_partides"],
                )
                for r in rows
            ]

    def club_players(self, club_fcb_id: str) -> list[PlayerKpi]:
        """Jugadors que han jugat amb equip d'aquest club (derivat de games)."""
        with self._conn() as c:
            cid_row = c.execute("SELECT id FROM clubs WHERE fcb_id = ?", (club_fcb_id,)).fetchone()
            if cid_row is None:
                return []
            cid = cid_row[0]
            rows = c.execute(
                """
                SELECT DISTINCT p.fcb_id, p.nom, p.seguiment,
                       (SELECT COUNT(*) FROM games g
                        WHERE g.player1_id = p.id OR g.player2_id = p.id) AS num_partides
                FROM games g
                JOIN equips e ON e.id IN (g.equip1_id, g.equip2_id)
                JOIN players p ON p.id IN (g.player1_id, g.player2_id)
                WHERE e.club_id = ?
                  AND (
                    (e.id = g.equip1_id AND p.id = g.player1_id)
                    OR (e.id = g.equip2_id AND p.id = g.player2_id)
                  )
                ORDER BY num_partides DESC, p.nom
                """,
                (cid,),
            ).fetchall()
            return [
                PlayerKpi(
                    fcb_id=r["fcb_id"],
                    nom=r["nom"],
                    club=club_fcb_id,
                    num_partides=r["num_partides"],
                    seguiment=bool(r["seguiment"]),
                )
                for r in rows
            ]

    # ------------- players -------------

    def search_players(self, query: str = "", limit: int = 200) -> list[PlayerKpi]:
        with self._conn() as c:
            sql = """
                SELECT p.fcb_id, p.nom, c.fcb_id AS club, p.seguiment,
                       (SELECT COUNT(*) FROM games g
                        WHERE g.player1_id = p.id OR g.player2_id = p.id) AS num_partides
                FROM players p
                LEFT JOIN clubs c ON c.id = p.club_id
            """
            params: list[Any] = []
            if query.strip():
                sql += " WHERE p.nom LIKE ? OR p.fcb_id = ? "
                params = [f"%{query}%", query.strip()]
            sql += " ORDER BY num_partides DESC, p.nom LIMIT ?"
            params.append(limit)
            rows = c.execute(sql, params).fetchall()
            return [
                PlayerKpi(
                    fcb_id=r["fcb_id"],
                    nom=r["nom"],
                    club=r["club"],
                    num_partides=r["num_partides"],
                    seguiment=bool(r["seguiment"]),
                )
                for r in rows
            ]

    def player_games(self, fcb_id: str, limit: int = 50) -> list[GameRow]:
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT g.data_partida AS data, m.nom AS modalitat,
                       c.nom AS competicio,
                       p1.nom AS local, g.caramboles1 AS cara1,
                       p2.nom AS visitant, g.caramboles2 AS cara2,
                       g.entrades, g.arbitre,
                       cl1.nom AS club_local, cl2.nom AS club_visitant
                FROM games g
                JOIN modalitats m ON m.id = g.modalitat_id
                LEFT JOIN competicions c ON c.id = g.competicio_id
                JOIN players p1 ON p1.id = g.player1_id
                JOIN players p2 ON p2.id = g.player2_id
                LEFT JOIN equips e1 ON e1.id = g.equip1_id LEFT JOIN clubs cl1 ON cl1.id = e1.club_id
                LEFT JOIN equips e2 ON e2.id = g.equip2_id LEFT JOIN clubs cl2 ON cl2.id = e2.club_id
                JOIN players pme ON pme.fcb_id = ?
                WHERE g.player1_id = pme.id OR g.player2_id = pme.id
                ORDER BY g.data_partida DESC
                LIMIT ?
                """,
                (fcb_id, limit),
            ).fetchall()
            return [
                GameRow(
                    data=r["data"], modalitat=r["modalitat"], competicio=r["competicio"],
                    local=r["local"], cara1=r["cara1"],
                    visitant=r["visitant"], cara2=r["cara2"],
                    entrades=r["entrades"], arbitre=r["arbitre"],
                    club_local=r["club_local"], club_visitant=r["club_visitant"],
                )
                for r in rows
            ]
