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
    # True si la partida computa al darrer rànquing del jugador consultat
    # (segons ranking_game_links del num_seq més recent de la seva modalitat).
    computa: bool = False
    # Sèrie màxima (millor tacada) de cada jugador en aquesta partida.
    serie1: int | None = None
    serie2: int | None = None


@dataclass
class VirtualClub:
    id: int
    nom: str
    descripcio: str | None
    num_membres: int = 0


@dataclass
class StandingRow:
    posicio: int
    equip: str           # "C.B.BANYOLES A"
    club_fcb_id: str
    pj: int              # partides (encontres) jugades
    g: int
    e: int
    p: int
    punts: int           # 3·G + 1·E
    parcials_favor: int
    parcials_contra: int


@dataclass
class TorneigRow:
    id: int
    nom: str
    temporada: str | None
    num_participants: int


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
        # Pre-agregem games i equips per club amb CTEs, evitant les subqueries
        # correlated que serien O(N²) amb 26K+ games. Un sol scan per agregat.
        with self._conn() as c:
            rows = c.execute(
                """
                WITH club_equips AS (
                    SELECT club_id, COUNT(*) AS n FROM equips GROUP BY club_id
                ),
                club_games AS (
                    SELECT e.club_id, COUNT(DISTINCT g.id) AS n
                    FROM games g
                    JOIN equips e ON e.id IN (g.equip1_id, g.equip2_id)
                    GROUP BY e.club_id
                ),
                club_players AS (
                    SELECT club_id, COUNT(*) AS n FROM players
                    WHERE club_id IS NOT NULL GROUP BY club_id
                )
                SELECT c.fcb_id, c.nom,
                       COALESCE(cp.n, 0) AS num_jugadors,
                       COALESCE(ce.n, 0) AS num_equips,
                       COALESCE(cg.n, 0) AS num_partides
                FROM clubs c
                LEFT JOIN club_equips  ce ON ce.club_id = c.id
                LEFT JOIN club_games   cg ON cg.club_id = c.id
                LEFT JOIN club_players cp ON cp.club_id = c.id
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

    def club_players(
        self, club_fcb_id: str, current_season_only: bool = False
    ) -> list[PlayerKpi]:
        """Jugadors que han jugat amb equip d'aquest club (derivat de games).

        Si `current_season_only=True`, només els que han jugat a la temporada
        més recent registrada a la BD (per nom, format YYYY-YYYY).
        """
        with self._conn() as c:
            cid_row = c.execute("SELECT id FROM clubs WHERE fcb_id = ?", (club_fcb_id,)).fetchone()
            if cid_row is None:
                return []
            cid = cid_row[0]

            season_filter = ""
            season_count_filter = ""
            params: list = [cid]
            if current_season_only:
                # Última temporada per nom (lexicogràfic = cronològic per format YYYY-YYYY).
                t_row = c.execute(
                    "SELECT id FROM temporades ORDER BY nom DESC LIMIT 1"
                ).fetchone()
                if t_row is None:
                    return []
                temporada_id = t_row[0]
                season_filter = " AND g.temporada_id = ? "
                season_count_filter = " AND g2.temporada_id = ? "
                # Ordre dels placeholders segons aparició al SQL:
                # 1) subquery COUNT: season_count_filter
                # 2) WHERE e.club_id = ?
                # 3) season_filter al WHERE principal
                params = [temporada_id, cid, temporada_id]

            if current_season_only:
                sql = f"""
                    SELECT DISTINCT p.fcb_id, p.nom, p.seguiment,
                           (SELECT COUNT(*) FROM games g2
                            WHERE (g2.player1_id = p.id OR g2.player2_id = p.id)
                                  {season_count_filter}) AS num_partides
                    FROM games g
                    JOIN equips e ON e.id IN (g.equip1_id, g.equip2_id)
                    JOIN players p ON p.id IN (g.player1_id, g.player2_id)
                    WHERE e.club_id = ?
                          {season_filter}
                          AND (
                            (e.id = g.equip1_id AND p.id = g.player1_id)
                            OR (e.id = g.equip2_id AND p.id = g.player2_id)
                          )
                    ORDER BY num_partides DESC, p.nom
                """
            else:
                sql = """
                    SELECT DISTINCT p.fcb_id, p.nom, p.seguiment,
                           (SELECT COUNT(*) FROM games g2
                            WHERE g2.player1_id = p.id OR g2.player2_id = p.id) AS num_partides
                    FROM games g
                    JOIN equips e ON e.id IN (g.equip1_id, g.equip2_id)
                    JOIN players p ON p.id IN (g.player1_id, g.player2_id)
                    WHERE e.club_id = ?
                      AND (
                        (e.id = g.equip1_id AND p.id = g.player1_id)
                        OR (e.id = g.equip2_id AND p.id = g.player2_id)
                      )
                    ORDER BY num_partides DESC, p.nom
                """
            rows = c.execute(sql, params).fetchall()
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

    # ------------- KPI agregats per jugador i per club -------------

    def player_summary(self, fcb_id: str, modalitat_codi_fcb: int | None = None) -> dict:
        """KPIs agregats d'un jugador. Si es passa modalitat, només d'aquella."""
        with self._conn() as c:
            pid_row = c.execute("SELECT id, nom FROM players WHERE fcb_id = ?", (fcb_id,)).fetchone()
            if pid_row is None:
                return {}
            pid, nom = pid_row["id"], pid_row["nom"]
            mod_filter, mod_param = "", []
            if modalitat_codi_fcb is not None:
                mod_filter = (
                    " AND g.modalitat_id = (SELECT id FROM modalitats WHERE codi_fcb = ?) "
                )
                mod_param = [modalitat_codi_fcb]
            row = c.execute(
                f"""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN g.guanyador_id = ? THEN 1 ELSE 0 END) AS guanyades,
                    SUM(CASE WHEN g.guanyador_id IS NOT NULL AND g.guanyador_id != ? THEN 1 ELSE 0 END) AS perdudes,
                    SUM(CASE WHEN g.guanyador_id IS NULL THEN 1 ELSE 0 END) AS empats,
                    SUM(CASE WHEN g.player1_id = ? THEN g.caramboles1 ELSE g.caramboles2 END) AS car_a_favor,
                    SUM(CASE WHEN g.player1_id = ? THEN g.caramboles2 ELSE g.caramboles1 END) AS car_en_contra,
                    SUM(g.entrades) AS entrades_total,
                    MAX(CASE WHEN g.player1_id = ? THEN g.serie_max1 ELSE g.serie_max2 END) AS serie_max
                FROM games g
                WHERE (g.player1_id = ? OR g.player2_id = ?) {mod_filter}
                """,
                [pid, pid, pid, pid, pid, pid, pid, *mod_param],
            ).fetchone()
            return {
                "fcb_id": fcb_id, "nom": nom,
                "total": row["total"] or 0,
                "guanyades": row["guanyades"] or 0,
                "perdudes": row["perdudes"] or 0,
                "empats": row["empats"] or 0,
                "car_a_favor": row["car_a_favor"] or 0,
                "car_en_contra": row["car_en_contra"] or 0,
                "entrades_total": row["entrades_total"] or 0,
                "serie_max": row["serie_max"],
            }

    def player_ranking_history(
        self, fcb_id: str, modalitat_codi_fcb: int | None = None
    ) -> list[dict]:
        """Evolució del jugador a tots els rànquings (data, posicio, mitjana)."""
        with self._conn() as c:
            params: list = [fcb_id]
            where_mod = ""
            if modalitat_codi_fcb is not None:
                where_mod = " AND m.codi_fcb = ? "
                params.append(modalitat_codi_fcb)
            rows = c.execute(
                f"""
                SELECT r.num_seq, m.nom AS modalitat, m.codi_fcb,
                       e.posicio, e.mitjana_general AS mitjana,
                       json_extract(e.extras_json, '$.caramboles') AS caramboles,
                       json_extract(e.extras_json, '$.entrades') AS entrades
                FROM ranking_entries e
                JOIN rankings r ON r.id = e.ranking_id
                JOIN modalitats m ON m.id = r.modalitat_id
                JOIN players p ON p.id = e.player_id
                WHERE p.fcb_id = ? {where_mod}
                ORDER BY m.codi_fcb, r.num_seq
                """,
                params,
            ).fetchall()
            return [dict(r) for r in rows]

    def player_best_worst_games(self, fcb_id: str, top: int = 5) -> dict[str, list[GameRow]]:
        """Millors i pitjors partides del jugador per mitjana de la partida (C/E)."""
        with self._conn() as c:
            base = """
                SELECT g.id, g.data_partida AS data, m.nom AS modalitat,
                       co.nom AS competicio,
                       p1.nom AS local, g.caramboles1 AS cara1,
                       p2.nom AS visitant, g.caramboles2 AS cara2,
                       g.entrades, g.arbitre,
                       cl1.nom AS club_local, cl2.nom AS club_visitant,
                       g.guanyador_id,
                       (CASE WHEN g.player1_id = pme.id THEN g.caramboles1 ELSE g.caramboles2 END) AS car_jug,
                       CAST((CASE WHEN g.player1_id = pme.id THEN g.caramboles1 ELSE g.caramboles2 END) AS REAL)
                           / NULLIF(g.entrades, 0) AS mitj_partida,
                       (g.guanyador_id = pme.id) AS guanyada
                FROM games g
                JOIN players pme ON pme.fcb_id = ?
                JOIN modalitats m ON m.id = g.modalitat_id
                LEFT JOIN competicions co ON co.id = g.competicio_id
                JOIN players p1 ON p1.id = g.player1_id
                JOIN players p2 ON p2.id = g.player2_id
                LEFT JOIN equips e1 ON e1.id = g.equip1_id LEFT JOIN clubs cl1 ON cl1.id = e1.club_id
                LEFT JOIN equips e2 ON e2.id = g.equip2_id LEFT JOIN clubs cl2 ON cl2.id = e2.club_id
                WHERE (g.player1_id = pme.id OR g.player2_id = pme.id)
                  AND g.entrades > 0
            """
            best = c.execute(
                f"{base} ORDER BY mitj_partida DESC, car_jug DESC LIMIT ?",
                (fcb_id, top),
            ).fetchall()
            worst = c.execute(
                f"{base} ORDER BY mitj_partida ASC, car_jug ASC LIMIT ?",
                (fcb_id, top),
            ).fetchall()
            best_won = c.execute(
                f"{base} AND g.guanyador_id = pme.id ORDER BY mitj_partida DESC LIMIT ?",
                (fcb_id, top),
            ).fetchall()
            worst_lost = c.execute(
                f"{base} AND g.guanyador_id IS NOT NULL AND g.guanyador_id != pme.id "
                f"ORDER BY mitj_partida ASC LIMIT ?",
                (fcb_id, top),
            ).fetchall()

            def to_game_row(r):
                return GameRow(
                    data=r["data"], modalitat=r["modalitat"], competicio=r["competicio"],
                    local=r["local"], cara1=r["cara1"],
                    visitant=r["visitant"], cara2=r["cara2"],
                    entrades=r["entrades"], arbitre=r["arbitre"],
                    club_local=r["club_local"], club_visitant=r["club_visitant"],
                )
            return {
                "best": [to_game_row(r) for r in best],
                "worst": [to_game_row(r) for r in worst],
                "best_won": [to_game_row(r) for r in best_won],
                "worst_lost": [to_game_row(r) for r in worst_lost],
            }

    def _temporada_actual_dates(self, c) -> tuple[str, str] | tuple[None, None]:
        """Retorna (data_inici, data_fi) de la temporada més recent (setembre→agost).

        Deriva del nom format 'YYYY-YYYY'. Si 2025-2026 → ('2025-09-01', '2026-08-31').
        """
        tr = c.execute("SELECT nom FROM temporades ORDER BY nom DESC LIMIT 1").fetchone()
        if tr is None:
            return (None, None)
        try:
            first = int(tr["nom"][:4])
        except (ValueError, TypeError):
            return (None, None)
        return (f"{first}-09-01", f"{first + 1}-08-31")

    def _club_player_ids_current_season(self, c, club_fcb_id: str) -> list[int]:
        """Player IDs detectats com a club X a la temporada més recent.

        Detecció: jugadors que han jugat alguna partida de lliga amb un equip
        del club a la temporada més recent registrada a la BD.
        """
        cid_row = c.execute("SELECT id FROM clubs WHERE fcb_id = ?", (club_fcb_id,)).fetchone()
        if cid_row is None:
            return []
        tr = c.execute("SELECT id FROM temporades ORDER BY nom DESC LIMIT 1").fetchone()
        if tr is None:
            return []
        rows = c.execute(
            """
            SELECT DISTINCT p.id FROM games g
            JOIN equips e ON e.id IN (g.equip1_id, g.equip2_id)
            JOIN players p ON p.id IN (g.player1_id, g.player2_id)
            WHERE e.club_id = ?
              AND g.temporada_id = ?
              AND (
                (e.id = g.equip1_id AND p.id = g.player1_id)
                OR (e.id = g.equip2_id AND p.id = g.player2_id)
              )
            """,
            (cid_row["id"], tr["id"]),
        ).fetchall()
        return [r[0] for r in rows]

    def club_summary(self, club_fcb_id: str, current_season_only: bool = True) -> dict:
        """KPIs agregats d'un club.

        Si `current_season_only=True`, agrega **totes les partides** (lliga,
        copa, individuals, opens via partideshome) dels jugadors actuals del
        club. Sinó, només les partides amb equip del club (de lliga).
        """
        with self._conn() as c:
            cid_row = c.execute(
                "SELECT id FROM clubs WHERE fcb_id = ?", (club_fcb_id,)
            ).fetchone()
            if cid_row is None:
                return {}

            if current_season_only:
                player_ids = self._club_player_ids_current_season(c, club_fcb_id)
                if not player_ids:
                    return {"total": 0, "guanyades": 0, "perdudes": 0}
                inici, fi = self._temporada_actual_dates(c)
                placeholders = ",".join("?" * len(player_ids))
                date_filter = ""
                date_params: list = []
                if inici and fi:
                    date_filter = " AND g.data_partida BETWEEN ? AND ? "
                    date_params = [inici, fi]
                row = c.execute(
                    f"""
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN g.guanyador_id IN ({placeholders}) THEN 1 ELSE 0 END) AS guanyades,
                        SUM(CASE WHEN g.guanyador_id IS NOT NULL
                                  AND g.guanyador_id NOT IN ({placeholders})
                                 THEN 1 ELSE 0 END) AS perdudes
                    FROM games g
                    WHERE (g.player1_id IN ({placeholders}) OR g.player2_id IN ({placeholders}))
                      {date_filter}
                    """,
                    player_ids * 4 + date_params,
                ).fetchone()
                return {
                    "total": row["total"] or 0,
                    "guanyades": row["guanyades"] or 0,
                    "perdudes": row["perdudes"] or 0,
                }
            # Mode antic: només partides amb equip del club (lliga)
            cid = cid_row["id"]
            row = c.execute(
                """
                WITH club_eq AS (SELECT id FROM equips WHERE club_id = ?)
                SELECT COUNT(*) AS total,
                       SUM(CASE
                           WHEN (g.equip1_id IN (SELECT id FROM club_eq) AND g.guanyador_id = g.player1_id)
                             OR (g.equip2_id IN (SELECT id FROM club_eq) AND g.guanyador_id = g.player2_id)
                           THEN 1 ELSE 0 END) AS guanyades,
                       SUM(CASE
                           WHEN g.guanyador_id IS NOT NULL
                            AND ((g.equip1_id IN (SELECT id FROM club_eq) AND g.guanyador_id != g.player1_id)
                              OR (g.equip2_id IN (SELECT id FROM club_eq) AND g.guanyador_id != g.player2_id))
                           THEN 1 ELSE 0 END) AS perdudes
                FROM games g
                WHERE g.equip1_id IN (SELECT id FROM club_eq)
                   OR g.equip2_id IN (SELECT id FROM club_eq)
                """,
                (cid,),
            ).fetchone()
            return {
                "total": row["total"] or 0,
                "guanyades": row["guanyades"] or 0,
                "perdudes": row["perdudes"] or 0,
            }

    def club_best_worst_games(
        self, club_fcb_id: str, current_season_only: bool = True, top: int = 5
    ) -> dict[str, list[dict]]:
        """Millors i pitjors partides dels jugadors d'un club.

        Si `current_season_only=True`, agrega **totes** les partides (lliga,
        copa, individuals, opens) dels jugadors detectats com a actius del
        club a la temporada actual.
        """
        with self._conn() as c:
            empty = {"best": [], "worst": [], "best_won": [], "worst_lost": []}
            cid_row = c.execute(
                "SELECT id FROM clubs WHERE fcb_id = ?", (club_fcb_id,)
            ).fetchone()
            if cid_row is None:
                return empty

            if not current_season_only:
                # Mantenim la versió antiga "només equips de lliga" per compatibilitat.
                cid = cid_row["id"]
                base = """
                    WITH club_eq AS (SELECT id FROM equips WHERE club_id = ?)
                    SELECT g.data_partida AS data, m.nom AS modalitat,
                           p1.nom AS local, g.caramboles1 AS cara1,
                           p2.nom AS visitant, g.caramboles2 AS cara2,
                           g.entrades, g.arbitre,
                           CASE WHEN g.equip1_id IN (SELECT id FROM club_eq)
                                THEN p1.nom ELSE p2.nom END AS jugador_club,
                           CASE WHEN g.equip1_id IN (SELECT id FROM club_eq)
                                THEN g.caramboles1 ELSE g.caramboles2 END AS car_club,
                           CAST(CASE WHEN g.equip1_id IN (SELECT id FROM club_eq)
                                THEN g.caramboles1 ELSE g.caramboles2 END AS REAL)
                               / NULLIF(g.entrades, 0) AS mitj,
                           CASE WHEN g.guanyador_id =
                                (CASE WHEN g.equip1_id IN (SELECT id FROM club_eq)
                                      THEN g.player1_id ELSE g.player2_id END)
                                THEN 1 ELSE 0 END AS guanyada
                    FROM games g
                    JOIN modalitats m ON m.id = g.modalitat_id
                    JOIN players p1 ON p1.id = g.player1_id
                    JOIN players p2 ON p2.id = g.player2_id
                    WHERE (g.equip1_id IN (SELECT id FROM club_eq)
                        OR g.equip2_id IN (SELECT id FROM club_eq))
                      AND g.entrades > 0
                """
                bp = [cid]
            else:
                player_ids = self._club_player_ids_current_season(c, club_fcb_id)
                if not player_ids:
                    return empty
                inici, fi = self._temporada_actual_dates(c)
                ph = ",".join("?" * len(player_ids))
                date_filter = ""
                date_params: list = []
                if inici and fi:
                    date_filter = " AND g.data_partida BETWEEN ? AND ? "
                    date_params = [inici, fi]
                base = f"""
                    SELECT g.data_partida AS data, m.nom AS modalitat,
                           co.nom AS competicio,
                           p1.nom AS local, g.caramboles1 AS cara1,
                           p2.nom AS visitant, g.caramboles2 AS cara2,
                           g.entrades, g.arbitre,
                           CASE WHEN g.player1_id IN ({ph})
                                THEN p1.nom ELSE p2.nom END AS jugador_club,
                           CASE WHEN g.player1_id IN ({ph})
                                THEN g.caramboles1 ELSE g.caramboles2 END AS car_club,
                           CAST(CASE WHEN g.player1_id IN ({ph})
                                THEN g.caramboles1 ELSE g.caramboles2 END AS REAL)
                               / NULLIF(g.entrades, 0) AS mitj,
                           CASE WHEN g.guanyador_id IN ({ph})
                                THEN 1 ELSE 0 END AS guanyada
                    FROM games g
                    JOIN modalitats m ON m.id = g.modalitat_id
                    LEFT JOIN competicions co ON co.id = g.competicio_id
                    JOIN players p1 ON p1.id = g.player1_id
                    JOIN players p2 ON p2.id = g.player2_id
                    WHERE (g.player1_id IN ({ph}) OR g.player2_id IN ({ph}))
                      AND g.entrades > 0
                      {date_filter}
                """
                # 6 ocurrències del bloc IN ({ph}) + opcional date_params
                bp = player_ids * 6 + date_params

            best = c.execute(
                f"{base} ORDER BY mitj DESC LIMIT ?", bp + [top]
            ).fetchall()
            worst = c.execute(
                f"{base} ORDER BY mitj ASC LIMIT ?", bp + [top]
            ).fetchall()
            best_won = c.execute(
                f"{base} AND guanyada = 1 ORDER BY mitj DESC LIMIT ?", bp + [top]
            ).fetchall()
            worst_lost = c.execute(
                f"{base} AND guanyada = 0 AND g.guanyador_id IS NOT NULL "
                f"ORDER BY mitj ASC LIMIT ?",
                bp + [top],
            ).fetchall()
            return {
                "best": [dict(r) for r in best],
                "worst": [dict(r) for r in worst],
                "best_won": [dict(r) for r in best_won],
                "worst_lost": [dict(r) for r in worst_lost],
            }

    def club_players_ranking_evolution(
        self, club_fcb_id: str, modalitat_codi_fcb: int
    ) -> dict:
        """Pivot table: files = jugadors actuals del club, columnes = num_seq de rànquing,
        cell = mitjana general d'aquell jugador en aquell rànquing.

        Retorna `{'num_seqs': [int], 'rows': [{'player': str, 'fcb_id': str,
                                                'mitjanes': [float|None]}]}`.
        """
        with self._conn() as c:
            player_ids = self._club_player_ids_current_season(c, club_fcb_id)
            if not player_ids:
                return {"num_seqs": [], "rows": []}
            ph_pids = ",".join("?" * len(player_ids))
            # Tots els num_seqs disponibles per a la modalitat, ordenats.
            seqs = [r[0] for r in c.execute(
                """
                SELECT r.num_seq FROM rankings r
                JOIN modalitats m ON m.id = r.modalitat_id
                WHERE m.codi_fcb = ?
                ORDER BY r.num_seq
                """,
                (modalitat_codi_fcb,),
            ).fetchall()]
            if not seqs:
                return {"num_seqs": [], "rows": []}
            # Entrades dels jugadors per a aquesta modalitat
            rows = c.execute(
                f"""
                SELECT p.id AS pid, p.fcb_id, p.nom, r.num_seq, e.mitjana_general
                FROM ranking_entries e
                JOIN players p ON p.id = e.player_id
                JOIN rankings r ON r.id = e.ranking_id
                JOIN modalitats m ON m.id = r.modalitat_id
                WHERE m.codi_fcb = ? AND p.id IN ({ph_pids})
                ORDER BY p.nom, r.num_seq
                """,
                [modalitat_codi_fcb, *player_ids],
            ).fetchall()
            # Pivotar
            by_player: dict[int, dict] = {}
            for r in rows:
                pd = by_player.setdefault(
                    r["pid"],
                    {"fcb_id": r["fcb_id"], "player": r["nom"], "by_seq": {}},
                )
                pd["by_seq"][r["num_seq"]] = r["mitjana_general"]
            # Format final amb llista alineada al num_seqs
            out_rows = []
            for pid, data in by_player.items():
                mitjanes = [data["by_seq"].get(s) for s in seqs]
                out_rows.append({
                    "player": data["player"],
                    "fcb_id": data["fcb_id"],
                    "mitjanes": mitjanes,
                })
            # Ordenar per última mitjana (la més recent) descendent
            out_rows.sort(
                key=lambda r: r["mitjanes"][-1] if r["mitjanes"][-1] is not None else -1,
                reverse=True,
            )
            return {"num_seqs": seqs, "rows": out_rows}

    def player_games(
        self, fcb_id: str, limit: int = 50, modalitat_codi_fcb: int | None = None
    ) -> list[GameRow]:
        with self._conn() as c:
            # Darrer num_seq per modalitat (per saber quin és el "darrer rànquing").
            # Una partida computa si està linkada (ranking_game_links) a aquest
            # jugador en aquest darrer rànquing de la seva modalitat. El portal
            # ja aplica la regla de desempat 15ena/16ena del mateix dia.
            rows = c.execute(
                """
                WITH last_rk AS (
                    SELECT modalitat_id, MAX(num_seq) AS mx
                    FROM rankings GROUP BY modalitat_id
                )
                SELECT g.data_partida AS data, m.nom AS modalitat,
                       c.nom AS competicio,
                       p1.nom AS local, g.caramboles1 AS cara1,
                       p2.nom AS visitant, g.caramboles2 AS cara2,
                       g.entrades, g.arbitre,
                       g.serie_max1 AS serie1, g.serie_max2 AS serie2,
                       cl1.nom AS club_local, cl2.nom AS club_visitant,
                       EXISTS (
                           SELECT 1 FROM ranking_game_links rgl
                           JOIN rankings r2 ON r2.id = rgl.ranking_id
                           JOIN last_rk lk ON lk.modalitat_id = r2.modalitat_id
                                          AND lk.mx = r2.num_seq
                           WHERE rgl.game_id = g.id
                             AND rgl.player_id_origen = pme.id
                             AND r2.modalitat_id = g.modalitat_id
                       ) AS computa
                FROM games g
                JOIN modalitats m ON m.id = g.modalitat_id
                LEFT JOIN competicions c ON c.id = g.competicio_id
                JOIN players p1 ON p1.id = g.player1_id
                JOIN players p2 ON p2.id = g.player2_id
                LEFT JOIN equips e1 ON e1.id = g.equip1_id LEFT JOIN clubs cl1 ON cl1.id = e1.club_id
                LEFT JOIN equips e2 ON e2.id = g.equip2_id LEFT JOIN clubs cl2 ON cl2.id = e2.club_id
                JOIN players pme ON pme.fcb_id = ?
                WHERE (g.player1_id = pme.id OR g.player2_id = pme.id)
                  {mod_filter}
                ORDER BY g.data_partida DESC
                LIMIT ?
                """.replace(
                    "{mod_filter}",
                    " AND g.modalitat_id = (SELECT id FROM modalitats WHERE codi_fcb = "
                    + str(int(modalitat_codi_fcb)) + ") "
                    if modalitat_codi_fcb is not None else "",
                ),
                (fcb_id, limit),
            ).fetchall()
            return [
                GameRow(
                    data=r["data"], modalitat=r["modalitat"], competicio=r["competicio"],
                    local=r["local"], cara1=r["cara1"],
                    visitant=r["visitant"], cara2=r["cara2"],
                    entrades=r["entrades"], arbitre=r["arbitre"],
                    club_local=r["club_local"], club_visitant=r["club_visitant"],
                    computa=bool(r["computa"]),
                    serie1=r["serie1"], serie2=r["serie2"],
                )
                for r in rows
            ]

    # ===================================================================
    # Rànquings complets
    # ===================================================================

    def ranking_snapshots(self, modalitat_codi_fcb: int) -> list[int]:
        """num_seq disponibles per a una modalitat, del més recent al més antic."""
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT r.num_seq FROM rankings r
                JOIN modalitats m ON m.id = r.modalitat_id
                WHERE m.codi_fcb = ?
                ORDER BY r.num_seq DESC
                """,
                (modalitat_codi_fcb,),
            ).fetchall()
            return [r[0] for r in rows]

    def ranking_full(
        self, modalitat_codi_fcb: int, num_seq: int | None = None
    ) -> list[RankingEntry]:
        """Rànquing complet d'una modalitat. Si num_seq és None, el més recent."""
        with self._conn() as c:
            if num_seq is None:
                row = c.execute(
                    """
                    SELECT MAX(r.num_seq) FROM rankings r
                    JOIN modalitats m ON m.id = r.modalitat_id
                    WHERE m.codi_fcb = ?
                    """,
                    (modalitat_codi_fcb,),
                ).fetchone()
                num_seq = row[0] if row else None
            if num_seq is None:
                return []
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
                WHERE m.codi_fcb = ? AND r.num_seq = ?
                ORDER BY e.posicio
                """,
                (modalitat_codi_fcb, num_seq),
            ).fetchall()
            return [
                RankingEntry(
                    modalitat=r["modalitat"], posicio=r["posicio"], nom=r["nom"],
                    fcb_id=r["fcb_id"], mitjana=r["mitjana_general"],
                    mitjana_contraris=r["mitjana_contraris"], caramboles=r["caramboles"],
                    entrades=r["entrades"], punts=r["punts"],
                    punts_totals=r["punts_totals"], definitiva=bool(r["def"]),
                )
                for r in rows
            ]

    # ===================================================================
    # Cerca de partides
    # ===================================================================

    def search_games(
        self,
        player: str = "",
        club: str = "",
        modalitat_codi_fcb: int | None = None,
        competicio: str = "",
        season_only: bool = False,
        limit: int = 300,
    ) -> list[GameRow]:
        """Cerca global de partides amb filtres opcionals."""
        with self._conn() as c:
            where: list[str] = ["1=1"]
            params: list[Any] = []
            if player.strip():
                where.append("(p1.nom LIKE ? OR p2.nom LIKE ?)")
                params += [f"%{player}%", f"%{player}%"]
            if club.strip():
                # Match contra el club per-partida (equip) o, si no n'hi ha
                # (p.ex. copa/individuals via partideshome), el club registrat
                # del jugador.
                where.append(
                    "(cl1.nom LIKE ? OR cl2.nom LIKE ? "
                    "OR pcl1.nom LIKE ? OR pcl2.nom LIKE ?)"
                )
                params += [f"%{club}%"] * 4
            if modalitat_codi_fcb is not None:
                where.append("m.codi_fcb = ?")
                params.append(modalitat_codi_fcb)
            if competicio.strip():
                where.append("co.nom LIKE ?")
                params.append(f"%{competicio}%")
            if season_only:
                inici, fi = self._temporada_actual_dates(c)
                if inici and fi:
                    where.append("g.data_partida BETWEEN ? AND ?")
                    params += [inici, fi]
            sql = f"""
                SELECT g.data_partida AS data, m.nom AS modalitat, co.nom AS competicio,
                       p1.nom AS local, g.caramboles1 AS cara1,
                       p2.nom AS visitant, g.caramboles2 AS cara2,
                       g.entrades, g.arbitre,
                       COALESCE(cl1.nom, pcl1.nom) AS club_local,
                       COALESCE(cl2.nom, pcl2.nom) AS club_visitant
                FROM games g
                JOIN modalitats m ON m.id = g.modalitat_id
                LEFT JOIN competicions co ON co.id = g.competicio_id
                JOIN players p1 ON p1.id = g.player1_id
                JOIN players p2 ON p2.id = g.player2_id
                LEFT JOIN equips e1 ON e1.id = g.equip1_id LEFT JOIN clubs cl1 ON cl1.id = e1.club_id
                LEFT JOIN equips e2 ON e2.id = g.equip2_id LEFT JOIN clubs cl2 ON cl2.id = e2.club_id
                LEFT JOIN clubs pcl1 ON pcl1.id = p1.club_id
                LEFT JOIN clubs pcl2 ON pcl2.id = p2.club_id
                WHERE {' AND '.join(where)}
                ORDER BY g.data_partida DESC
                LIMIT ?
            """
            params.append(limit)
            rows = c.execute(sql, params).fetchall()
            return [
                GameRow(
                    data=r["data"], modalitat=r["modalitat"], competicio=r["competicio"],
                    local=r["local"], cara1=r["cara1"], visitant=r["visitant"],
                    cara2=r["cara2"], entrades=r["entrades"], arbitre=r["arbitre"],
                    club_local=r["club_local"], club_visitant=r["club_visitant"],
                )
                for r in rows
            ]

    # ===================================================================
    # Clubs virtuals (CRUD)
    # ===================================================================

    def list_virtual_clubs(self) -> list[VirtualClub]:
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT v.id, v.nom, v.descripcio,
                       (SELECT COUNT(*) FROM virtual_club_members m
                        WHERE m.virtual_club_id = v.id) AS n
                FROM virtual_clubs v ORDER BY v.nom
                """
            ).fetchall()
            return [
                VirtualClub(id=r["id"], nom=r["nom"], descripcio=r["descripcio"],
                            num_membres=r["n"])
                for r in rows
            ]

    def create_virtual_club(self, nom: str, descripcio: str | None = None) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO virtual_clubs (nom, descripcio) VALUES (?, ?)",
                (nom.strip(), (descripcio or "").strip() or None),
            )
            c.commit()
            return cur.lastrowid

    def update_virtual_club(self, vc_id: int, nom: str, descripcio: str | None) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE virtual_clubs SET nom = ?, descripcio = ? WHERE id = ?",
                (nom.strip(), (descripcio or "").strip() or None, vc_id),
            )
            c.commit()

    def delete_virtual_club(self, vc_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM virtual_clubs WHERE id = ?", (vc_id,))
            c.commit()

    def virtual_club_members(self, vc_id: int) -> list[PlayerKpi]:
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT p.fcb_id, p.nom, cl.fcb_id AS club, p.seguiment,
                       (SELECT COUNT(*) FROM games g
                        WHERE g.player1_id = p.id OR g.player2_id = p.id) AS num_partides
                FROM virtual_club_members m
                JOIN players p ON p.id = m.player_id
                LEFT JOIN clubs cl ON cl.id = p.club_id
                WHERE m.virtual_club_id = ?
                ORDER BY num_partides DESC, p.nom
                """,
                (vc_id,),
            ).fetchall()
            return [
                PlayerKpi(fcb_id=r["fcb_id"], nom=r["nom"], club=r["club"],
                          num_partides=r["num_partides"], seguiment=bool(r["seguiment"]))
                for r in rows
            ]

    def add_virtual_club_member(self, vc_id: int, player_fcb_id: str) -> bool:
        with self._conn() as c:
            pid = c.execute("SELECT id FROM players WHERE fcb_id = ?", (player_fcb_id,)).fetchone()
            if pid is None:
                return False
            c.execute(
                "INSERT OR IGNORE INTO virtual_club_members (virtual_club_id, player_id) "
                "VALUES (?, ?)",
                (vc_id, pid[0]),
            )
            c.commit()
            return True

    def remove_virtual_club_member(self, vc_id: int, player_fcb_id: str) -> None:
        with self._conn() as c:
            c.execute(
                """
                DELETE FROM virtual_club_members
                WHERE virtual_club_id = ?
                  AND player_id = (SELECT id FROM players WHERE fcb_id = ?)
                """,
                (vc_id, player_fcb_id),
            )
            c.commit()

    # ===================================================================
    # Focus genèric (club real o club virtual) — sobre un conjunt de player_ids
    # ===================================================================

    def real_club_player_ids(self, club_fcb_id: str, season_only: bool = True) -> list[int]:
        """Player ids associats a un club real.

        - season_only=False: TOTS els jugadors que han jugat mai amb equip
          d'aquest club (qualsevol temporada).
        - season_only=True: els que han jugat amb el club a la temporada actual
          MÉS els que, encara que no hagin jugat aquesta temporada, la seva
          ÚLTIMA partida amb equip (de qualsevol club) va ser amb aquest club
          (= segueixen "essent" del club fins que no fitxin per un altre).
        """
        with self._conn() as c:
            cid = c.execute("SELECT id FROM clubs WHERE fcb_id = ?", (club_fcb_id,)).fetchone()
            if cid is None:
                return []
            club_id = cid[0]

            # Tots els que han jugat mai amb el club.
            ever = {
                r[0]
                for r in c.execute(
                    """
                    SELECT DISTINCT p.id FROM games g
                    JOIN equips e ON e.id IN (g.equip1_id, g.equip2_id)
                    JOIN players p ON p.id IN (g.player1_id, g.player2_id)
                    WHERE e.club_id = ?
                      AND ((e.id = g.equip1_id AND p.id = g.player1_id)
                        OR (e.id = g.equip2_id AND p.id = g.player2_id))
                    """,
                    (club_id,),
                ).fetchall()
            }
            if not season_only:
                return list(ever)

            # season_only: (jugat amb el club aquesta temporada) ∪
            #              (última partida amb equip = aquest club)
            inici, fi = self._temporada_actual_dates(c)
            this_season: set[int] = set()
            if inici and fi:
                this_season = {
                    r[0]
                    for r in c.execute(
                        """
                        SELECT DISTINCT p.id FROM games g
                        JOIN equips e ON e.id IN (g.equip1_id, g.equip2_id)
                        JOIN players p ON p.id IN (g.player1_id, g.player2_id)
                        WHERE e.club_id = ? AND g.data_partida BETWEEN ? AND ?
                          AND ((e.id = g.equip1_id AND p.id = g.player1_id)
                            OR (e.id = g.equip2_id AND p.id = g.player2_id))
                        """,
                        (club_id, inici, fi),
                    ).fetchall()
                }
            # Dels que han jugat mai amb el club, quins tenen la seva última
            # partida amb equip en aquest club.
            still: set[int] = set()
            for pid in ever:
                last = c.execute(
                    """
                    SELECT e.club_id FROM games g
                    JOIN equips e ON e.id IN (g.equip1_id, g.equip2_id)
                    WHERE ((e.id = g.equip1_id AND g.player1_id = ?)
                        OR (e.id = g.equip2_id AND g.player2_id = ?))
                    ORDER BY g.data_partida DESC LIMIT 1
                    """,
                    (pid, pid),
                ).fetchone()
                if last and last[0] == club_id:
                    still.add(pid)
            return list(this_season | still)

    def virtual_club_player_ids(self, vc_id: int) -> list[int]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT player_id FROM virtual_club_members WHERE virtual_club_id = ?",
                (vc_id,),
            ).fetchall()
            return [r[0] for r in rows]

    def focus_summary(self, player_ids: list[int], season_only: bool = True) -> dict:
        """KPIs agregats per a un conjunt de jugadors (totes les competicions)."""
        if not player_ids:
            return {"total": 0, "guanyades": 0, "perdudes": 0, "num_jugadors": 0}
        with self._conn() as c:
            ph = ",".join("?" * len(player_ids))
            date_filter, date_params = "", []
            if season_only:
                inici, fi = self._temporada_actual_dates(c)
                if inici and fi:
                    date_filter = " AND g.data_partida BETWEEN ? AND ? "
                    date_params = [inici, fi]
            row = c.execute(
                f"""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN g.guanyador_id IN ({ph}) THEN 1 ELSE 0 END) AS guanyades,
                       SUM(CASE WHEN g.guanyador_id IS NOT NULL
                                 AND g.guanyador_id NOT IN ({ph}) THEN 1 ELSE 0 END) AS perdudes
                FROM games g
                WHERE (g.player1_id IN ({ph}) OR g.player2_id IN ({ph})) {date_filter}
                """,
                player_ids * 4 + date_params,
            ).fetchone()
            return {
                "total": row["total"] or 0,
                "guanyades": row["guanyades"] or 0,
                "perdudes": row["perdudes"] or 0,
                "num_jugadors": len(player_ids),
            }

    def focus_players(self, player_ids: list[int]) -> list[PlayerKpi]:
        if not player_ids:
            return []
        with self._conn() as c:
            ph = ",".join("?" * len(player_ids))
            rows = c.execute(
                f"""
                SELECT p.fcb_id, p.nom, cl.fcb_id AS club, p.seguiment,
                       (SELECT COUNT(*) FROM games g
                        WHERE g.player1_id = p.id OR g.player2_id = p.id) AS num_partides
                FROM players p
                LEFT JOIN clubs cl ON cl.id = p.club_id
                WHERE p.id IN ({ph})
                ORDER BY num_partides DESC, p.nom
                """,
                player_ids,
            ).fetchall()
            return [
                PlayerKpi(fcb_id=r["fcb_id"], nom=r["nom"], club=r["club"],
                          num_partides=r["num_partides"], seguiment=bool(r["seguiment"]))
                for r in rows
            ]

    def focus_order_evolution(
        self, player_ids: list[int], modalitat_codi_fcb: int,
        club_fcb_id: str | None = None,
    ) -> dict:
        """Evolució de l'ordre dels jugadors al rànquing al llarg del temps.

        Retorna, per cada num_seq (eix temporal), la posició absoluta i l'ordre
        INTERN (1..k entre els jugadors del focus, ordenat per mitjana general
        descendent) de cada jugador.

        Si es passa `club_fcb_id`, per cada jugador es calcula l'últim num_seq
        en què encara tenia partides amb equip d'aquest club; les cel·les de
        rànquings POSTERIORS es marquen a `out_of_club` (el jugador ja havia
        marxat), perquè la UI les pugui atenuar. L'ordre intern d'un rànquing
        només té en compte els jugadors que ENCARA eren del club en aquell
        rànquing.

        `{'num_seqs': [int], 'rows': [{'player','fcb_id',
            'posicions':[int|None], 'ordre_intern':[int|None],
            'mitjanes':[float|None], 'out_of_club':[bool]}]}`
        """
        if not player_ids:
            return {"num_seqs": [], "rows": []}
        with self._conn() as c:
            ph = ",".join("?" * len(player_ids))
            seqs = [r[0] for r in c.execute(
                """
                SELECT r.num_seq FROM rankings r
                JOIN modalitats m ON m.id = r.modalitat_id
                WHERE m.codi_fcb = ? ORDER BY r.num_seq
                """,
                (modalitat_codi_fcb,),
            ).fetchall()]
            if not seqs:
                return {"num_seqs": [], "rows": []}

            # Per jugador, l'últim num_seq (d'aquesta modalitat) on tenia una
            # partida linkada amb equip del club. Cel·les amb num_seq > aquest
            # → out_of_club. Si el club no s'especifica, mai out_of_club.
            last_club_seq: dict[int, int] = {}
            if club_fcb_id is not None:
                cidrow = c.execute(
                    "SELECT id FROM clubs WHERE fcb_id = ?", (club_fcb_id,)
                ).fetchone()
                if cidrow is not None:
                    for r in c.execute(
                        f"""
                        SELECT rgl.player_id_origen pid, MAX(r.num_seq) mx
                        FROM ranking_game_links rgl
                        JOIN rankings r ON r.id = rgl.ranking_id
                        JOIN modalitats m ON m.id = r.modalitat_id
                        JOIN games g ON g.id = rgl.game_id
                        JOIN equips e ON e.id IN (g.equip1_id, g.equip2_id)
                        WHERE m.codi_fcb = ? AND e.club_id = ?
                          AND rgl.player_id_origen IN ({ph})
                          AND ((e.id = g.equip1_id AND g.player1_id = rgl.player_id_origen)
                            OR (e.id = g.equip2_id AND g.player2_id = rgl.player_id_origen))
                        GROUP BY rgl.player_id_origen
                        """,
                        [modalitat_codi_fcb, cidrow[0], *player_ids],
                    ).fetchall():
                        last_club_seq[r["pid"]] = r["mx"]

            rows = c.execute(
                f"""
                SELECT p.id AS pid, p.fcb_id, p.nom, r.num_seq,
                       e.posicio, e.mitjana_general
                FROM ranking_entries e
                JOIN players p ON p.id = e.player_id
                JOIN rankings r ON r.id = e.ranking_id
                JOIN modalitats m ON m.id = r.modalitat_id
                WHERE m.codi_fcb = ? AND p.id IN ({ph})
                """,
                [modalitat_codi_fcb, *player_ids],
            ).fetchall()
            by_player: dict[int, dict] = {}
            for r in rows:
                pd = by_player.setdefault(
                    r["pid"], {"fcb_id": r["fcb_id"], "player": r["nom"], "by_seq": {}}
                )
                pd["by_seq"][r["num_seq"]] = (r["posicio"], r["mitjana_general"])

            def is_out(pid: int, seq: int) -> bool:
                if club_fcb_id is None:
                    return False
                last = last_club_seq.get(pid)
                # Sense cap rànquing amb el club (p.ex. només partides no
                # linkades) → no marquem res; amb un últim conegut, posteriors out.
                return last is not None and seq > last

            # Ordre intern per num_seq: només jugadors encara del club.
            ordre_by_seq: dict[int, dict[int, int]] = {}
            for s in seqs:
                presents = [
                    (pid, pd["by_seq"][s][1])
                    for pid, pd in by_player.items()
                    if s in pd["by_seq"] and pd["by_seq"][s][1] is not None
                    and not is_out(pid, s)
                ]
                presents.sort(key=lambda x: x[1], reverse=True)
                ordre_by_seq[s] = {pid: i + 1 for i, (pid, _) in enumerate(presents)}
            out_rows = []
            for pid, pd in by_player.items():
                posicions, ordre_intern, mitjanes, ooc = [], [], [], []
                for s in seqs:
                    cell = pd["by_seq"].get(s)
                    posicions.append(cell[0] if cell else None)
                    mitjanes.append(cell[1] if cell else None)
                    ordre_intern.append(ordre_by_seq[s].get(pid))
                    ooc.append(is_out(pid, s))
                out_rows.append({
                    "player": pd["player"], "fcb_id": pd["fcb_id"],
                    "posicions": posicions, "ordre_intern": ordre_intern,
                    "mitjanes": mitjanes, "out_of_club": ooc,
                })
            def _last_order(r):
                for v in reversed(r["ordre_intern"]):
                    if v is not None:
                        return v
                return 9999
            out_rows.sort(key=_last_order)
            return {"num_seqs": seqs, "rows": out_rows}

    def focus_best_worst_games(
        self, player_ids: list[int], season_only: bool = True, top: int = 10
    ) -> dict[str, list[dict]]:
        """Millors/pitjors partides per a un conjunt de jugadors."""
        empty = {"best": [], "worst": [], "best_won": [], "worst_lost": []}
        if not player_ids:
            return empty
        with self._conn() as c:
            ph = ",".join("?" * len(player_ids))
            date_filter, date_params = "", []
            if season_only:
                inici, fi = self._temporada_actual_dates(c)
                if inici and fi:
                    date_filter = " AND g.data_partida BETWEEN ? AND ? "
                    date_params = [inici, fi]
            base = f"""
                SELECT g.data_partida AS data, m.nom AS modalitat, co.nom AS competicio,
                       p1.nom AS local, g.caramboles1 AS cara1,
                       p2.nom AS visitant, g.caramboles2 AS cara2,
                       g.entrades, g.arbitre,
                       CASE WHEN g.player1_id IN ({ph}) THEN p1.nom ELSE p2.nom END AS jugador_club,
                       CASE WHEN g.player1_id IN ({ph}) THEN g.caramboles1 ELSE g.caramboles2 END AS car_club,
                       CAST(CASE WHEN g.player1_id IN ({ph})
                            THEN g.caramboles1 ELSE g.caramboles2 END AS REAL)
                           / NULLIF(g.entrades, 0) AS mitj,
                       CASE WHEN g.guanyador_id IN ({ph}) THEN 1 ELSE 0 END AS guanyada
                FROM games g
                JOIN modalitats m ON m.id = g.modalitat_id
                LEFT JOIN competicions co ON co.id = g.competicio_id
                JOIN players p1 ON p1.id = g.player1_id
                JOIN players p2 ON p2.id = g.player2_id
                WHERE (g.player1_id IN ({ph}) OR g.player2_id IN ({ph}))
                  AND g.entrades > 0 {date_filter}
            """
            bp = player_ids * 6 + date_params
            best = c.execute(f"{base} ORDER BY mitj DESC LIMIT ?", bp + [top]).fetchall()
            worst = c.execute(f"{base} ORDER BY mitj ASC LIMIT ?", bp + [top]).fetchall()
            best_won = c.execute(
                f"{base} AND guanyada = 1 ORDER BY mitj DESC LIMIT ?", bp + [top]
            ).fetchall()
            worst_lost = c.execute(
                f"{base} AND guanyada = 0 AND g.guanyador_id IS NOT NULL "
                f"ORDER BY mitj ASC LIMIT ?", bp + [top]
            ).fetchall()
            return {
                "best": [dict(r) for r in best], "worst": [dict(r) for r in worst],
                "best_won": [dict(r) for r in best_won],
                "worst_lost": [dict(r) for r in worst_lost],
            }

    def focus_games(
        self, player_ids: list[int], season_only: bool = True,
        result: str = "all", limit: int = 500,
    ) -> list[GameRow]:
        """Partides del conjunt de jugadors del focus, filtrant per resultat.

        result: 'all' | 'won' (guanyades pel focus) | 'lost' (perdudes pel focus).
        El guanyador es considera des del punt de vista del conjunt: una partida
        és 'won' si el guanyador és un dels player_ids.
        """
        if not player_ids:
            return []
        with self._conn() as c:
            ph = ",".join("?" * len(player_ids))
            where = [f"(g.player1_id IN ({ph}) OR g.player2_id IN ({ph}))"]
            params: list[Any] = player_ids * 2
            if season_only:
                inici, fi = self._temporada_actual_dates(c)
                if inici and fi:
                    where.append("g.data_partida BETWEEN ? AND ?")
                    params += [inici, fi]
            if result == "won":
                where.append(f"g.guanyador_id IN ({ph})")
                params += player_ids
            elif result == "lost":
                where.append(
                    f"g.guanyador_id IS NOT NULL AND g.guanyador_id NOT IN ({ph})"
                )
                params += player_ids
            sql = f"""
                SELECT g.data_partida AS data, m.nom AS modalitat, co.nom AS competicio,
                       p1.nom AS local, g.caramboles1 AS cara1,
                       p2.nom AS visitant, g.caramboles2 AS cara2,
                       g.entrades, g.arbitre,
                       COALESCE(cl1.nom, pcl1.nom) AS club_local,
                       COALESCE(cl2.nom, pcl2.nom) AS club_visitant
                FROM games g
                JOIN modalitats m ON m.id = g.modalitat_id
                LEFT JOIN competicions co ON co.id = g.competicio_id
                JOIN players p1 ON p1.id = g.player1_id
                JOIN players p2 ON p2.id = g.player2_id
                LEFT JOIN equips e1 ON e1.id = g.equip1_id LEFT JOIN clubs cl1 ON cl1.id = e1.club_id
                LEFT JOIN equips e2 ON e2.id = g.equip2_id LEFT JOIN clubs cl2 ON cl2.id = e2.club_id
                LEFT JOIN clubs pcl1 ON pcl1.id = p1.club_id
                LEFT JOIN clubs pcl2 ON pcl2.id = p2.club_id
                WHERE {' AND '.join(where)}
                ORDER BY g.data_partida DESC
                LIMIT ?
            """
            params.append(limit)
            return [
                GameRow(
                    data=r["data"], modalitat=r["modalitat"], competicio=r["competicio"],
                    local=r["local"], cara1=r["cara1"], visitant=r["visitant"],
                    cara2=r["cara2"], entrades=r["entrades"], arbitre=r["arbitre"],
                    club_local=r["club_local"], club_visitant=r["club_visitant"],
                )
                for r in c.execute(sql, params).fetchall()
            ]

    # ===================================================================
    # Resultats: lliga (classificacions), copa, individuals
    # ===================================================================

    def lliga_groups(self, season_only: bool = True) -> list[dict]:
        """Grups de lliga presents (lliga_id, divisio_id, grup_id) + etiqueta.

        Els noms de divisió/grup no es desen a la BD; mostrem ids + nombre
        d'encontres. Si season_only, només la temporada més recent."""
        with self._conn() as c:
            where, params = "", []
            if season_only:
                tr = c.execute("SELECT id, nom FROM temporades ORDER BY nom DESC LIMIT 1").fetchone()
                if tr is not None:
                    where = "WHERE en.temporada_id = ?"
                    params = [tr["id"]]
            rows = c.execute(
                f"""
                SELECT en.lliga_id, en.divisio_id, en.grup_id,
                       COUNT(*) AS n_encontres,
                       MIN(en.data) AS data_min, MAX(en.data) AS data_max
                FROM encontres_lliga en
                {where}
                GROUP BY en.lliga_id, en.divisio_id, en.grup_id
                ORDER BY en.lliga_id, en.divisio_id, en.grup_id
                """,
                params,
            ).fetchall()
            return [dict(r) for r in rows]

    def lliga_standings(
        self, lliga_id: int, divisio_id: int, grup_id: int
    ) -> list[StandingRow]:
        """Classificació d'un grup calculada des dels encontres (3·G + 1·E)."""
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT en.equip_local_id AS loc, en.equip_visitant_id AS vis,
                       en.p_match_local AS pml, en.p_match_visitant AS pmv
                FROM encontres_lliga en
                WHERE en.lliga_id = ? AND en.divisio_id = ? AND en.grup_id = ?
                """,
                (lliga_id, divisio_id, grup_id),
            ).fetchall()
            stats: dict[int, dict] = {}

            def _s(eid):
                return stats.setdefault(eid, {"pj": 0, "g": 0, "e": 0, "p": 0,
                                              "pf": 0, "pc": 0})
            for r in rows:
                loc, vis, pml, pmv = r["loc"], r["vis"], r["pml"], r["pmv"]
                if pml is None or pmv is None:
                    continue
                sl, sv = _s(loc), _s(vis)
                sl["pj"] += 1; sv["pj"] += 1
                sl["pf"] += pml; sl["pc"] += pmv
                sv["pf"] += pmv; sv["pc"] += pml
                if pml > pmv:
                    sl["g"] += 1; sv["p"] += 1
                elif pml < pmv:
                    sv["g"] += 1; sl["p"] += 1
                else:
                    sl["e"] += 1; sv["e"] += 1
            if not stats:
                return []
            eq_ids = list(stats.keys())
            ph = ",".join("?" * len(eq_ids))
            names = {
                r["id"]: (r["nom"], r["fcb_id"], r["lletra"])
                for r in c.execute(
                    f"""
                    SELECT e.id, e.lletra, c.nom, c.fcb_id
                    FROM equips e JOIN clubs c ON c.id = e.club_id
                    WHERE e.id IN ({ph})
                    """,
                    eq_ids,
                ).fetchall()
            }
            result = []
            for eid, s in stats.items():
                nom, fcb_id, lletra = names.get(eid, ("?", "?", ""))
                punts = 3 * s["g"] + s["e"]
                result.append((punts, s, eid, nom, fcb_id, lletra))
            result.sort(key=lambda x: (x[0], x[1]["pf"] - x[1]["pc"]), reverse=True)
            out = []
            for pos, (punts, s, eid, nom, fcb_id, lletra) in enumerate(result, 1):
                out.append(StandingRow(
                    posicio=pos, equip=f"{nom} {lletra}".strip(), club_fcb_id=fcb_id,
                    pj=s["pj"], g=s["g"], e=s["e"], p=s["p"], punts=punts,
                    parcials_favor=s["pf"], parcials_contra=s["pc"],
                ))
            return out

    def lliga_jornades(
        self, lliga_id: int, divisio_id: int, grup_id: int
    ) -> list[dict]:
        """Jornades d'un grup amb els seus encontres (equips + resultat match).

        Retorna `[{jornada_id, data, encontres: [{encontre_id, data,
        equip_local, equip_visitant, club_local, club_visitant,
        p_match_local, p_match_visitant, p_parcials_local, p_parcials_visitant,
        n_partides}]}]`, ordenades per data.
        """
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT en.id, en.jornada_id, en.data,
                       en.equip_local_id, en.equip_visitant_id,
                       en.p_match_local, en.p_match_visitant,
                       en.p_parcials_local, en.p_parcials_visitant,
                       el.lletra AS lletra_local, cll.nom AS club_local,
                       ev.lletra AS lletra_visit, clv.nom AS club_visit,
                       (SELECT COUNT(*) FROM games g WHERE g.encontre_lliga_id = en.id) AS n_partides
                FROM encontres_lliga en
                JOIN equips el ON el.id = en.equip_local_id
                JOIN clubs cll ON cll.id = el.club_id
                JOIN equips ev ON ev.id = en.equip_visitant_id
                JOIN clubs clv ON clv.id = ev.club_id
                WHERE en.lliga_id = ? AND en.divisio_id = ? AND en.grup_id = ?
                ORDER BY en.data, en.jornada_id, en.id
                """,
                (lliga_id, divisio_id, grup_id),
            ).fetchall()
            jornades: dict[int, dict] = {}
            order: list[int] = []
            for r in rows:
                j = r["jornada_id"]
                if j not in jornades:
                    jornades[j] = {"jornada_id": j, "data": r["data"], "encontres": []}
                    order.append(j)
                jornades[j]["encontres"].append({
                    "encontre_id": r["id"],
                    "data": r["data"],
                    "equip_local": f"{r['club_local']} {r['lletra_local']}".strip(),
                    "equip_visitant": f"{r['club_visit']} {r['lletra_visit']}".strip(),
                    "p_match_local": r["p_match_local"],
                    "p_match_visitant": r["p_match_visitant"],
                    "p_parcials_local": r["p_parcials_local"],
                    "p_parcials_visitant": r["p_parcials_visitant"],
                    "n_partides": r["n_partides"],
                })
            return [jornades[j] for j in order]

    def encontre_detail(self, encontre_id: int) -> dict:
        """Detall d'un encontre: capçalera + partides individuals (games)."""
        with self._conn() as c:
            head = c.execute(
                """
                SELECT en.id, en.data,
                       en.lliga_id, en.divisio_id, en.grup_id,
                       el.lletra AS ll_local, cll.nom AS club_local,
                       ev.lletra AS ll_visit, clv.nom AS club_visit,
                       en.p_match_local, en.p_match_visitant
                FROM encontres_lliga en
                JOIN equips el ON el.id = en.equip_local_id
                JOIN clubs cll ON cll.id = el.club_id
                JOIN equips ev ON ev.id = en.equip_visitant_id
                JOIN clubs clv ON clv.id = ev.club_id
                WHERE en.id = ?
                """,
                (encontre_id,),
            ).fetchone()
            if head is None:
                return {}
            # Fase llegible: divisió + grup (p.ex. "4A DIVISIÓ · FINAL 4A DIVISIÓ").
            noms = self._lliga_noms_map(c)
            lid = head["lliga_id"]
            divisio_nom = noms.get((lid, head["divisio_id"], 0))
            grup_nom = noms.get((lid, head["divisio_id"], head["grup_id"]))
            fase = " · ".join([x for x in (divisio_nom, grup_nom) if x])
            games = c.execute(
                """
                SELECT g.data_partida AS data, m.nom AS modalitat,
                       p1.nom AS local, g.caramboles1 AS cara1,
                       p2.nom AS visitant, g.caramboles2 AS cara2,
                       g.entrades, g.serie_max1 AS serie1, g.serie_max2 AS serie2,
                       g.arbitre, cl1.nom AS club_local, cl2.nom AS club_visitant
                FROM games g
                JOIN modalitats m ON m.id = g.modalitat_id
                JOIN players p1 ON p1.id = g.player1_id
                JOIN players p2 ON p2.id = g.player2_id
                LEFT JOIN equips e1 ON e1.id = g.equip1_id LEFT JOIN clubs cl1 ON cl1.id = e1.club_id
                LEFT JOIN equips e2 ON e2.id = g.equip2_id LEFT JOIN clubs cl2 ON cl2.id = e2.club_id
                WHERE g.encontre_lliga_id = ?
                ORDER BY g.data_partida
                """,
                (encontre_id,),
            ).fetchall()
            return {
                "encontre_id": head["id"],
                "data": head["data"],
                "fase": fase,
                "equip_local": f"{head['club_local']} {head['ll_local']}".strip(),
                "equip_visitant": f"{head['club_visit']} {head['ll_visit']}".strip(),
                "p_match_local": head["p_match_local"],
                "p_match_visitant": head["p_match_visitant"],
                "games": [dict(g) for g in games],
            }

    # Noms llegibles de les competicions de lliga (lliga_id → nom). Els ids
    # de divisió/grup es resolen via la taula lliga_noms (poblada amb la
    # comanda `fcbillar discover-lliga-noms`).
    LLIGA_NOMS = {
        36: "Lliga Catalana · Tres Bandes",
        37: "Lliga Catalana · 4 Modalitats",
    }

    def _lliga_noms_map(self, c) -> dict[tuple[int, int, int], str]:
        try:
            rows = c.execute(
                "SELECT lliga_id, divisio_id, grup_id, nom FROM lliga_noms"
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
        return {(r["lliga_id"], r["divisio_id"], r["grup_id"]): r["nom"] for r in rows}

    def lliga_tree(self, season_only: bool = True) -> list[dict]:
        """Arbre complet de la lliga: competició → categoria (divisió) → grups,
        cada grup amb la seva classificació calculada.

        Retorna `[{lliga_id, nom, categories: [{divisio_id, nom,
        groups: [{grup_id, nom, standings: [StandingRow...]}]}]}]`.
        Si season_only, només la temporada més recent.
        """
        with self._conn() as c:
            where, params = "", []
            if season_only:
                tr = c.execute(
                    "SELECT id FROM temporades ORDER BY nom DESC LIMIT 1"
                ).fetchone()
                if tr is not None:
                    where = "WHERE en.temporada_id = ?"
                    params = [tr["id"]]
            rows = c.execute(
                f"""
                SELECT en.lliga_id, en.divisio_id, en.grup_id,
                       en.equip_local_id AS loc, en.equip_visitant_id AS vis,
                       en.p_match_local AS pml, en.p_match_visitant AS pmv
                FROM encontres_lliga en
                {where}
                """,
                params,
            ).fetchall()
            if not rows:
                return []

            # Acumula estadístiques per (lliga, divisio, grup) → equip → stats.
            # clau de grup → dict equip_id → stats
            groups: dict[tuple[int, int, int], dict[int, dict]] = {}
            eq_ids: set[int] = set()

            def _s(g, eid):
                return g.setdefault(
                    eid, {"pj": 0, "g": 0, "e": 0, "p": 0, "pf": 0, "pc": 0}
                )

            for r in rows:
                key = (r["lliga_id"], r["divisio_id"], r["grup_id"])
                g = groups.setdefault(key, {})
                pml, pmv = r["pml"], r["pmv"]
                if pml is None or pmv is None:
                    continue
                loc, vis = r["loc"], r["vis"]
                eq_ids.add(loc)
                eq_ids.add(vis)
                sl, sv = _s(g, loc), _s(g, vis)
                sl["pj"] += 1
                sv["pj"] += 1
                sl["pf"] += pml
                sl["pc"] += pmv
                sv["pf"] += pmv
                sv["pc"] += pml
                if pml > pmv:
                    sl["g"] += 1
                    sv["p"] += 1
                elif pml < pmv:
                    sv["g"] += 1
                    sl["p"] += 1
                else:
                    sl["e"] += 1
                    sv["e"] += 1

            # Resol noms d'equips en bloc.
            names: dict[int, tuple[str, str, str]] = {}
            if eq_ids:
                ph = ",".join("?" * len(eq_ids))
                for r in c.execute(
                    f"""
                    SELECT e.id, e.lletra, cl.nom, cl.fcb_id
                    FROM equips e JOIN clubs cl ON cl.id = e.club_id
                    WHERE e.id IN ({ph})
                    """,
                    list(eq_ids),
                ).fetchall():
                    names[r["id"]] = (r["nom"], r["fcb_id"], r["lletra"])

            noms = self._lliga_noms_map(c)

            # Construeix l'arbre: lliga → divisió → grups.
            comps: dict[int, dict] = {}
            for (lliga_id, divisio_id, grup_id), stats in groups.items():
                comp = comps.setdefault(
                    lliga_id,
                    {
                        "lliga_id": lliga_id,
                        "nom": self.LLIGA_NOMS.get(lliga_id, f"Lliga {lliga_id}"),
                        "_cats": {},
                    },
                )
                cat = comp["_cats"].setdefault(
                    divisio_id,
                    {
                        "divisio_id": divisio_id,
                        "nom": noms.get(
                            (lliga_id, divisio_id, 0), f"Divisió {divisio_id}"
                        ),
                        "groups": [],
                    },
                )
                # Ordena la classificació d'aquest grup.
                ranked = []
                for eid, s in stats.items():
                    punts = 3 * s["g"] + s["e"]
                    ranked.append((punts, s, eid))
                ranked.sort(key=lambda x: (x[0], x[1]["pf"] - x[1]["pc"]), reverse=True)
                standings = []
                for pos, (punts, s, eid) in enumerate(ranked, 1):
                    nom, fcb_id, lletra = names.get(eid, ("?", "?", ""))
                    standings.append(
                        {
                            "posicio": pos,
                            "equip": f"{nom} {lletra}".strip(),
                            "club_fcb_id": fcb_id,
                            "pj": s["pj"],
                            "g": s["g"],
                            "e": s["e"],
                            "p": s["p"],
                            "punts": punts,
                            "parcials_favor": s["pf"],
                            "parcials_contra": s["pc"],
                        }
                    )
                cat["groups"].append(
                    {
                        "grup_id": grup_id,
                        "nom": noms.get(
                            (lliga_id, divisio_id, grup_id), f"Grup {grup_id}"
                        ),
                        "standings": standings,
                    }
                )

            # Aplana a llistes ordenades.
            out = []
            for lliga_id in sorted(comps):
                comp = comps[lliga_id]
                cats = []
                for divisio_id in sorted(comp["_cats"]):
                    cat = comp["_cats"][divisio_id]
                    cat["groups"].sort(key=lambda gr: gr["grup_id"])
                    cats.append(cat)
                out.append(
                    {
                        "lliga_id": lliga_id,
                        "nom": comp["nom"],
                        "categories": cats,
                    }
                )
            return out

    def copa_games(self, season_only: bool = True, limit: int = 300) -> list[GameRow]:
        return self.search_games(
            competicio="COPA", season_only=season_only, limit=limit
        )

    def individuals_list(self, temporada: str | None = None) -> list[TorneigRow]:
        with self._conn() as c:
            where, params = "", []
            if temporada:
                where = "WHERE t.nom = ?"
                params = [temporada]
            rows = c.execute(
                f"""
                SELECT ti.id, ti.nom, t.nom AS temporada,
                       (SELECT COUNT(*) FROM torneig_participants tp
                        WHERE tp.torneig_id = ti.id) AS n
                FROM torneigs_individuals ti
                LEFT JOIN temporades t ON t.id = ti.temporada_id
                {where}
                ORDER BY t.nom DESC, ti.nom
                """,
                params,
            ).fetchall()
            return [
                TorneigRow(id=r["id"], nom=r["nom"], temporada=r["temporada"],
                           num_participants=r["n"])
                for r in rows
            ]

    def individuals_seasons(self) -> list[str]:
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT DISTINCT t.nom FROM torneigs_individuals ti
                JOIN temporades t ON t.id = ti.temporada_id
                ORDER BY t.nom DESC
                """
            ).fetchall()
            return [r[0] for r in rows]

    def individual_classification(self, torneig_id: int) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT tp.posicio, p.nom, p.fcb_id, tp.club_text,
                       tp.partides_jugades, tp.punts, tp.caramboles, tp.entrades,
                       tp.mitjana_general, tp.mitjana_particular, tp.serie_max
                FROM torneig_participants tp
                JOIN players p ON p.id = tp.player_id
                WHERE tp.torneig_id = ?
                ORDER BY tp.posicio
                """,
                (torneig_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def individual_phases(self, torneig_id: int) -> list[dict]:
        """Composició de grups per fase d'un torneig (PRÈVIA, QUALIFICACIÓ...).

        El portal no publica classificacions amb punts per fase, només
        l'assignació jugador→grup. Retorna `[{fase_id, nom, tipus, ordre,
        grups: [{grup_nom, jugadors: [str]}]}]`. Buit si no hi ha fases.
        """
        with self._conn() as c:
            try:
                fases = c.execute(
                    """SELECT id, fase_id_extern, nom, tipus, ordre
                       FROM torneig_fases WHERE torneig_id = ?
                       ORDER BY ordre, id""",
                    (torneig_id,),
                ).fetchall()
            except sqlite3.OperationalError:
                return []
            out: list[dict] = []
            for f in fases:
                membres = c.execute(
                    """SELECT grup_nom, jugador_nom FROM torneig_fase_grups
                       WHERE fase_id = ? ORDER BY grup_nom, ordre""",
                    (f["id"],),
                ).fetchall()
                grups: dict[str, dict] = {}
                order: list[str] = []
                for m in membres:
                    g = m["grup_nom"] or ""
                    if g not in grups:
                        grups[g] = {"grup_nom": g, "jugadors": []}
                        order.append(g)
                    grups[g]["jugadors"].append(m["jugador_nom"])
                out.append({
                    "fase_id": f["id"],
                    "nom": f["nom"],
                    "tipus": f["tipus"],
                    "ordre": f["ordre"],
                    "grups": [grups[g] for g in order],
                })
            return out

    # ==================================================================
    # COPA — estructura: edició → jornades → grups → encontres → partides
    # ==================================================================

    def copa_edicions(self) -> list[dict]:
        """Edicions de copa disponibles, més recents primer.

        `[{edicio_id, nom, n_jornades}]`.
        """
        with self._conn() as c:
            try:
                rows = c.execute(
                    """SELECT edicio_id, COUNT(*) AS n
                       FROM copa_jornades GROUP BY edicio_id
                       ORDER BY edicio_id DESC"""
                ).fetchall()
            except sqlite3.OperationalError:
                return []
            # Àncora: edició 7 = temporada 2025-2026 (cadència anual). L'any
            # d'inici d'una edició N és 2018 + N.
            def _temporada(ed: int) -> str:
                y = 2018 + ed
                return f"{y}-{y + 1}"

            return [
                {"edicio_id": r["edicio_id"],
                 "temporada": _temporada(r["edicio_id"]),
                 "nom": f"Copa {_temporada(r['edicio_id'])} · edició {r['edicio_id']}",
                 "n_jornades": r["n"]}
                for r in rows
            ]

    def copa_jornades(self, edicio_id: int) -> list[dict]:
        """Jornades d'una edició amb els seus grups.

        `[{jornada, ordre, nom, grups: [{grup_id, grup_nom}]}]`.
        """
        with self._conn() as c:
            try:
                jors = c.execute(
                    """SELECT jornada, ordre, nom FROM copa_jornades
                       WHERE edicio_id = ? ORDER BY ordre, jornada""",
                    (edicio_id,),
                ).fetchall()
            except sqlite3.OperationalError:
                return []
            out: list[dict] = []
            for j in jors:
                grups = c.execute(
                    """SELECT DISTINCT grup_id, grup_nom FROM copa_encontres
                       WHERE edicio_id = ? AND jornada = ?
                       ORDER BY grup_id""",
                    (edicio_id, j["jornada"]),
                ).fetchall()
                out.append({
                    "jornada": j["jornada"],
                    "ordre": j["ordre"],
                    "nom": j["nom"],
                    "grups": [
                        {"grup_id": g["grup_id"], "grup_nom": g["grup_nom"]}
                        for g in grups
                    ],
                })
            return out

    def copa_grup(self, edicio_id: int, jornada: int, grup_id: int) -> dict:
        """Classificació + encontres d'un grup d'una jornada de copa."""
        with self._conn() as c:
            try:
                classif = c.execute(
                    """SELECT posicio, equip, punts, parcials, mitjana, grup_nom
                       FROM copa_classificacio
                       WHERE edicio_id = ? AND jornada = ? AND grup_id = ?
                       ORDER BY posicio""",
                    (edicio_id, jornada, grup_id),
                ).fetchall()
                encs = c.execute(
                    """SELECT id, equip_local, equip_visitant, p_match_local,
                              p_match_visitant, grup_nom,
                              (SELECT COUNT(*) FROM copa_partides cp
                               WHERE cp.encontre_copa_id = ce.id) AS n_partides
                       FROM copa_encontres ce
                       WHERE edicio_id = ? AND jornada = ? AND grup_id = ?
                       ORDER BY id""",
                    (edicio_id, jornada, grup_id),
                ).fetchall()
            except sqlite3.OperationalError:
                return {"grup_nom": "", "classificacio": [], "encontres": []}
            grup_nom = ""
            if classif:
                grup_nom = classif[0]["grup_nom"] or ""
            elif encs:
                grup_nom = encs[0]["grup_nom"] or ""
            return {
                "grup_nom": grup_nom,
                "classificacio": [
                    {"posicio": r["posicio"], "equip": r["equip"],
                     "punts": r["punts"], "parcials": r["parcials"],
                     "mitjana": r["mitjana"]}
                    for r in classif
                ],
                "encontres": [
                    {"encontre_copa_id": r["id"],
                     "equip_local": r["equip_local"],
                     "equip_visitant": r["equip_visitant"],
                     "p_match_local": r["p_match_local"],
                     "p_match_visitant": r["p_match_visitant"],
                     "n_partides": r["n_partides"]}
                    for r in encs
                ],
            }

    def copa_encontre_detail(self, encontre_copa_id: int) -> dict:
        """Detall d'un encontre de copa: capçalera + partides individuals."""
        with self._conn() as c:
            try:
                head = c.execute(
                    """SELECT id, equip_local, equip_visitant, p_match_local,
                              p_match_visitant, grup_nom
                       FROM copa_encontres WHERE id = ?""",
                    (encontre_copa_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                return {}
            if head is None:
                return {}
            parts = c.execute(
                """SELECT ordre, local_nom, local_caramboles, local_serie,
                          visitant_nom, visitant_caramboles, visitant_serie,
                          entrades, punts_local, punts_visitant
                   FROM copa_partides WHERE encontre_copa_id = ?
                   ORDER BY ordre""",
                (encontre_copa_id,),
            ).fetchall()
            return {
                "encontre_copa_id": head["id"],
                "grup_nom": head["grup_nom"],
                "equip_local": head["equip_local"],
                "equip_visitant": head["equip_visitant"],
                "p_match_local": head["p_match_local"],
                "p_match_visitant": head["p_match_visitant"],
                "partides": [dict(r) for r in parts],
            }

    # ------------------------------------------------------------------
    # Rànquings de jugadors per competició (lliga / copa)
    # ------------------------------------------------------------------

    def lliga_player_ranking(
        self,
        modalitat_codi_fcb: int | None = None,
        temporada_id: int | None = None,
    ) -> list[dict]:
        """Rànquing de jugadors a partir de les partides de LLIGA.

        Agrega per jugador (fcb_id) sobre la taula `games`: partides jugades,
        guanyades, punts (de `extras_json.punts1/2`), caramboles i entrades.
        Ordenat per punts i després mitjana (desc). Filtres opcionals per
        modalitat (codi_fcb) i temporada.
        """
        where = ["c.nom = 'LLIGA'"]
        params: list = []
        if modalitat_codi_fcb is not None:
            where.append("pg.modalitat_id = (SELECT id FROM modalitats WHERE codi_fcb = ?)")
            params.append(modalitat_codi_fcb)
        if temporada_id is not None:
            where.append("pg.temporada_id = ?")
            params.append(temporada_id)
        sql = f"""
            WITH pg AS (
                SELECT player1_id AS pid, caramboles1 AS car, entrades AS ent,
                       CAST(json_extract(extras_json, '$.punts1') AS INTEGER) AS pts,
                       CASE WHEN guanyador_id = player1_id THEN 1 ELSE 0 END AS won,
                       modalitat_id, temporada_id, competicio_id
                FROM games
                UNION ALL
                SELECT player2_id, caramboles2, entrades,
                       CAST(json_extract(extras_json, '$.punts2') AS INTEGER),
                       CASE WHEN guanyador_id = player2_id THEN 1 ELSE 0 END,
                       modalitat_id, temporada_id, competicio_id
                FROM games
            )
            SELECT p.fcb_id AS fcb_id, p.nom AS nom,
                   COUNT(*) AS pj, SUM(pg.won) AS g,
                   COALESCE(SUM(pg.pts), 0) AS punts,
                   SUM(pg.car) AS caramboles, SUM(pg.ent) AS entrades
            FROM pg
            JOIN players p ON p.id = pg.pid
            JOIN competicions c ON c.id = pg.competicio_id
            WHERE {' AND '.join(where)}
            GROUP BY pg.pid
            HAVING pj > 0
        """
        with self._conn() as c:
            rows = c.execute(sql, params).fetchall()
        return self._rank_rows(rows)

    def copa_player_ranking(self, edicio_id: int | None = None) -> list[dict]:
        """Rànquing de jugadors de COPA a partir de `copa_partides`.

        Els jugadors de copa només es coneixen pel nom (no fcb_id). Agrega
        punts, caramboles i entrades; ordena per punts i mitjana (desc).
        Filtre opcional per edició.
        """
        where = []
        params: list = []
        if edicio_id is not None:
            where.append("edicio_id = ?")
            params.append(edicio_id)
        wsql = ("WHERE " + " AND ".join(where)) if where else ""
        sql = f"""
            WITH pg AS (
                SELECT ce.edicio_id, cp.local_nom AS nom,
                       cp.local_caramboles AS car, cp.entrades AS ent,
                       cp.punts_local AS pts,
                       CASE WHEN cp.punts_local > cp.punts_visitant THEN 1 ELSE 0 END AS won
                FROM copa_partides cp
                JOIN copa_encontres ce ON ce.id = cp.encontre_copa_id
                UNION ALL
                SELECT ce.edicio_id, cp.visitant_nom,
                       cp.visitant_caramboles, cp.entrades,
                       cp.punts_visitant,
                       CASE WHEN cp.punts_visitant > cp.punts_local THEN 1 ELSE 0 END
                FROM copa_partides cp
                JOIN copa_encontres ce ON ce.id = cp.encontre_copa_id
            )
            SELECT nom AS nom, NULL AS fcb_id,
                   COUNT(*) AS pj, SUM(won) AS g,
                   COALESCE(SUM(pts), 0) AS punts,
                   SUM(car) AS caramboles, SUM(ent) AS entrades
            FROM pg
            {wsql}
            GROUP BY nom
            HAVING pj > 0 AND nom IS NOT NULL AND nom != ''
        """
        with self._conn() as c:
            try:
                rows = c.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                return []
        return self._rank_rows(rows)

    @staticmethod
    def _rank_rows(rows) -> list[dict]:
        """Converteix files agregades en dicts amb mitjana, ordena per punts +
        mitjana (desc) i assigna la posició."""
        out = []
        for r in rows:
            ent = r["entrades"] or 0
            car = r["caramboles"] or 0
            mitjana = (car / ent) if ent else 0.0
            out.append({
                "fcb_id": r["fcb_id"] if "fcb_id" in r.keys() else None,
                "nom": r["nom"],
                "pj": r["pj"],
                "g": r["g"] or 0,
                "punts": r["punts"] or 0,
                "caramboles": car,
                "entrades": ent,
                "mitjana": round(mitjana, 4),
            })
        out.sort(key=lambda x: (x["punts"], x["mitjana"]), reverse=True)
        for i, row in enumerate(out, 1):
            row["posicio"] = i
        return out

    def lliga_temporades(self) -> list[dict]:
        """Temporades amb partides de lliga, més recents primer: [{id, nom}]."""
        with self._conn() as c:
            rows = c.execute(
                """SELECT DISTINCT t.id, t.nom
                   FROM games g
                   JOIN competicions c ON c.id = g.competicio_id
                   JOIN temporades t ON t.id = g.temporada_id
                   WHERE c.nom = 'LLIGA'
                   ORDER BY t.nom DESC"""
            ).fetchall()
        return [{"id": r["id"], "nom": r["nom"]} for r in rows]
