"""Operacions de persistència — inserts/upserts idempotents."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable

from fcbillar.models import (
    Club,
    Competicio,
    EncontreLliga,
    Equip,
    Game,
    Modalitat,
    Player,
    Ranking,
    RankingEntry,
    RankingGameLink,
    Temporada,
)


class Repository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ---------------------- clubs ----------------------

    def upsert_club(self, club: Club) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO clubs (fcb_id, nom) VALUES (?, ?)
            ON CONFLICT(fcb_id) DO UPDATE SET nom = excluded.nom
            RETURNING id
            """,
            (club.fcb_id, club.nom),
        )
        return cur.fetchone()[0]

    def get_club_id_by_fcb_id(self, fcb_id: str) -> int | None:
        row = self.conn.execute(
            "SELECT id FROM clubs WHERE fcb_id = ?", (fcb_id,)
        ).fetchone()
        return row[0] if row else None

    # ---------------------- players ----------------------

    def upsert_player(self, player: Player) -> int:
        club_id: int | None = None
        if player.club_fcb_id:
            club_id = self.get_club_id_by_fcb_id(player.club_fcb_id)
        cur = self.conn.execute(
            """
            INSERT INTO players (fcb_id, nom, club_id, seguiment)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(fcb_id) DO UPDATE SET
                nom = excluded.nom,
                club_id = COALESCE(excluded.club_id, players.club_id),
                updated_at = datetime('now')
            RETURNING id
            """,
            (player.fcb_id, player.nom, club_id, int(player.seguiment)),
        )
        return cur.fetchone()[0]

    def get_player_id_by_fcb_id(self, fcb_id: str) -> int | None:
        row = self.conn.execute(
            "SELECT id FROM players WHERE fcb_id = ?", (fcb_id,)
        ).fetchone()
        return row[0] if row else None

    def get_player_fcb_id_by_nom(self, nom: str) -> str | None:
        """Resol nom → fcb_id (cas-sensible, com el portal escriu els noms).

        Si hi ha homònims, retornem None per evitar associar partides incorrectes
        (cas a investigar amb dades reals).
        """
        rows = self.conn.execute(
            "SELECT fcb_id FROM players WHERE nom = ?", (nom,)
        ).fetchall()
        if len(rows) == 1:
            return rows[0][0]
        return None

    def get_player_nom_by_fcb_id(self, fcb_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT nom FROM players WHERE fcb_id = ?", (fcb_id,)
        ).fetchone()
        return row[0] if row else None

    def set_seguiment(self, fcb_id: str, seguiment: bool) -> bool:
        cur = self.conn.execute(
            "UPDATE players SET seguiment = ? WHERE fcb_id = ?",
            (int(seguiment), fcb_id),
        )
        return cur.rowcount > 0

    # ---------------------- modalitats ----------------------

    def upsert_modalitat(self, modalitat: Modalitat) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO modalitats (codi_fcb, nom) VALUES (?, ?)
            ON CONFLICT(codi_fcb) DO UPDATE SET nom = excluded.nom
            RETURNING id
            """,
            (modalitat.codi_fcb, modalitat.nom),
        )
        return cur.fetchone()[0]

    def get_modalitat_id_by_codi_fcb(self, codi_fcb: int) -> int | None:
        row = self.conn.execute(
            "SELECT id FROM modalitats WHERE codi_fcb = ?", (codi_fcb,)
        ).fetchone()
        return row[0] if row else None

    # ---------------------- competicions ----------------------

    def upsert_competicio(self, comp: Competicio) -> int:
        modalitat_id: int | None = None
        if comp.modalitat_codi_fcb is not None:
            modalitat_id = self.get_modalitat_id_by_codi_fcb(comp.modalitat_codi_fcb)
        row = self.conn.execute(
            """
            SELECT id FROM competicions
            WHERE nom = ? AND COALESCE(temporada, '') = COALESCE(?, '')
              AND COALESCE(modalitat_id, -1) = COALESCE(?, -1)
            """,
            (comp.nom, comp.temporada, modalitat_id),
        ).fetchone()
        if row:
            return row[0]
        cur = self.conn.execute(
            "INSERT INTO competicions (nom, temporada, modalitat_id) VALUES (?, ?, ?) RETURNING id",
            (comp.nom, comp.temporada, modalitat_id),
        )
        return cur.fetchone()[0]

    # ---------------------- rankings ----------------------

    def upsert_ranking(self, ranking: Ranking) -> int:
        modalitat_id = self.get_modalitat_id_by_codi_fcb(ranking.modalitat_codi_fcb)
        if modalitat_id is None:
            raise ValueError(
                f"Modalitat {ranking.modalitat_codi_fcb} no registrada; crea-la abans del rànquing"
            )
        cur = self.conn.execute(
            """
            INSERT INTO rankings (num_seq, modalitat_id, url, format_url, any_pub, mes_pub)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(num_seq, modalitat_id) DO UPDATE SET
                url = excluded.url,
                format_url = excluded.format_url,
                any_pub = COALESCE(excluded.any_pub, rankings.any_pub),
                mes_pub = COALESCE(excluded.mes_pub, rankings.mes_pub),
                scraped_at = datetime('now')
            RETURNING id
            """,
            (
                ranking.num_seq,
                modalitat_id,
                ranking.url,
                ranking.format_url,
                ranking.any_pub,
                ranking.mes_pub,
            ),
        )
        return cur.fetchone()[0]

    def get_ranking_id(self, num_seq: int, modalitat_codi_fcb: int) -> int | None:
        row = self.conn.execute(
            """
            SELECT r.id FROM rankings r
            JOIN modalitats m ON m.id = r.modalitat_id
            WHERE r.num_seq = ? AND m.codi_fcb = ?
            """,
            (num_seq, modalitat_codi_fcb),
        ).fetchone()
        return row[0] if row else None

    def get_ranking_format_url(self, num_seq: int, modalitat_codi_fcb: int) -> str | None:
        row = self.conn.execute(
            """
            SELECT r.format_url FROM rankings r
            JOIN modalitats m ON m.id = r.modalitat_id
            WHERE r.num_seq = ? AND m.codi_fcb = ?
            """,
            (num_seq, modalitat_codi_fcb),
        ).fetchone()
        return row[0] if row else None

    def latest_ranking_num_seq(self, modalitat_codi_fcb: int) -> int | None:
        row = self.conn.execute(
            """
            SELECT MAX(r.num_seq) FROM rankings r
            JOIN modalitats m ON m.id = r.modalitat_id
            WHERE m.codi_fcb = ?
            """,
            (modalitat_codi_fcb,),
        ).fetchone()
        return row[0]

    # ---------------------- ranking entries ----------------------

    def upsert_ranking_entry(self, ranking_id: int, entry: RankingEntry) -> None:
        player_id = self.get_player_id_by_fcb_id(entry.player_fcb_id)
        if player_id is None:
            raise ValueError(f"Player {entry.player_fcb_id} no registrat")
        extras = json.dumps(entry.extras, ensure_ascii=False) if entry.extras else None
        self.conn.execute(
            """
            INSERT INTO ranking_entries
                (ranking_id, player_id, posicio, mitjana_general, mitjana_particular, partides, extras_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ranking_id, player_id) DO UPDATE SET
                posicio = excluded.posicio,
                mitjana_general = excluded.mitjana_general,
                mitjana_particular = excluded.mitjana_particular,
                partides = excluded.partides,
                extras_json = excluded.extras_json
            """,
            (
                ranking_id,
                player_id,
                entry.posicio,
                entry.mitjana_general,
                entry.mitjana_particular,
                entry.partides,
                extras,
            ),
        )

    # ---------------------- games ----------------------

    def upsert_game(self, game: Game) -> str:
        p1 = self.get_player_id_by_fcb_id(game.player1_fcb_id)
        p2 = self.get_player_id_by_fcb_id(game.player2_fcb_id)
        if p1 is None or p2 is None:
            raise ValueError(
                f"Jugadors no registrats: {game.player1_fcb_id} o {game.player2_fcb_id}"
            )
        modalitat_id = self.get_modalitat_id_by_codi_fcb(game.modalitat_codi_fcb)
        competicio_id = self.upsert_competicio(
            Competicio(nom=game.competicio_nom, modalitat_codi_fcb=game.modalitat_codi_fcb)
        )
        guanyador_id = self.get_player_id_by_fcb_id(game.guanyador_fcb_id) if game.guanyador_fcb_id else None
        extras = json.dumps(game.extras, ensure_ascii=False) if game.extras else None
        self.conn.execute(
            """
            INSERT INTO games (id, data_partida, competicio_id, modalitat_id,
                               player1_id, player2_id,
                               caramboles1, caramboles2, entrades,
                               mitjana1, mitjana2, serie_max1, serie_max2,
                               guanyador_id, extras_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                caramboles1 = COALESCE(excluded.caramboles1, games.caramboles1),
                caramboles2 = COALESCE(excluded.caramboles2, games.caramboles2),
                entrades = COALESCE(excluded.entrades, games.entrades),
                mitjana1 = COALESCE(excluded.mitjana1, games.mitjana1),
                mitjana2 = COALESCE(excluded.mitjana2, games.mitjana2),
                serie_max1 = COALESCE(excluded.serie_max1, games.serie_max1),
                serie_max2 = COALESCE(excluded.serie_max2, games.serie_max2),
                guanyador_id = COALESCE(excluded.guanyador_id, games.guanyador_id),
                extras_json = COALESCE(excluded.extras_json, games.extras_json)
            """,
            (
                game.id_natural,
                game.data_partida.isoformat(),
                competicio_id,
                modalitat_id,
                p1,
                p2,
                game.caramboles1,
                game.caramboles2,
                game.entrades,
                game.mitjana1,
                game.mitjana2,
                game.serie_max1,
                game.serie_max2,
                guanyador_id,
                extras,
            ),
        )
        return game.id_natural

    def link_game_to_ranking(self, link: RankingGameLink) -> None:
        ranking_id = self.get_ranking_id(link.ranking_num_seq, link.ranking_modalitat)
        player_id = self.get_player_id_by_fcb_id(link.player_fcb_id_origen)
        if ranking_id is None or player_id is None:
            raise ValueError("ranking o player no registrats")
        self.conn.execute(
            """
            INSERT OR IGNORE INTO ranking_game_links (ranking_id, game_id, player_id_origen)
            VALUES (?, ?, ?)
            """,
            (ranking_id, link.game_id, player_id),
        )

    # ---------------------- bulk helpers ----------------------

    def bulk_upsert_players(self, players: Iterable[Player]) -> None:
        for p in players:
            self.upsert_player(p)

    # ---------------------- temporades ----------------------

    def upsert_temporada(self, temporada: Temporada) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO temporades (nom) VALUES (?)
            ON CONFLICT(nom) DO UPDATE SET nom = excluded.nom
            RETURNING id
            """,
            (temporada.nom,),
        )
        return cur.fetchone()[0]

    def get_temporada_id_by_nom(self, nom: str) -> int | None:
        row = self.conn.execute(
            "SELECT id FROM temporades WHERE nom = ?", (nom,)
        ).fetchone()
        return row[0] if row else None

    # ---------------------- equips ----------------------

    def upsert_equip(self, equip: Equip) -> int:
        club_id = self.get_club_id_by_fcb_id(equip.club_fcb_id)
        if club_id is None:
            raise ValueError(f"Club {equip.club_fcb_id} no registrat")
        cur = self.conn.execute(
            """
            INSERT INTO equips (club_id, lletra) VALUES (?, ?)
            ON CONFLICT(club_id, lletra) DO UPDATE SET lletra = excluded.lletra
            RETURNING id
            """,
            (club_id, equip.lletra),
        )
        return cur.fetchone()[0]

    def get_equip_id(self, club_fcb_id: str, lletra: str) -> int | None:
        row = self.conn.execute(
            """
            SELECT e.id FROM equips e
            JOIN clubs c ON c.id = e.club_id
            WHERE c.fcb_id = ? AND e.lletra = ?
            """,
            (club_fcb_id, lletra),
        ).fetchone()
        return row[0] if row else None

    # ---------------------- encontres_lliga ----------------------

    def upsert_encontre_lliga(self, encontre: EncontreLliga) -> int:
        local_id = self.upsert_equip(encontre.equip_local)
        visitant_id = self.upsert_equip(encontre.equip_visitant)
        temporada_id: int | None = None
        if encontre.temporada_nom:
            temporada_id = self.upsert_temporada(Temporada(nom=encontre.temporada_nom))
        cur = self.conn.execute(
            """
            INSERT INTO encontres_lliga (
                lliga_id, divisio_id, grup_id, jornada_id, encontre_id_extern,
                data, temporada_id,
                equip_local_id, equip_visitant_id,
                p_parcials_local, p_match_local,
                p_parcials_visitant, p_match_visitant
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(lliga_id, divisio_id, grup_id, jornada_id, encontre_id_extern)
            DO UPDATE SET
                data = COALESCE(excluded.data, encontres_lliga.data),
                temporada_id = COALESCE(excluded.temporada_id, encontres_lliga.temporada_id),
                equip_local_id = excluded.equip_local_id,
                equip_visitant_id = excluded.equip_visitant_id,
                p_parcials_local = COALESCE(excluded.p_parcials_local, encontres_lliga.p_parcials_local),
                p_match_local = COALESCE(excluded.p_match_local, encontres_lliga.p_match_local),
                p_parcials_visitant = COALESCE(excluded.p_parcials_visitant, encontres_lliga.p_parcials_visitant),
                p_match_visitant = COALESCE(excluded.p_match_visitant, encontres_lliga.p_match_visitant)
            RETURNING id
            """,
            (
                encontre.lliga_id,
                encontre.divisio_id,
                encontre.grup_id,
                encontre.jornada_id,
                encontre.encontre_id_extern,
                encontre.data.isoformat() if encontre.data else None,
                temporada_id,
                local_id,
                visitant_id,
                encontre.p_parcials_local,
                encontre.p_match_local,
                encontre.p_parcials_visitant,
                encontre.p_match_visitant,
            ),
        )
        return cur.fetchone()[0]

    # ---------------------- status ----------------------

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for table in [
            "clubs",
            "players",
            "modalitats",
            "competicions",
            "rankings",
            "ranking_entries",
            "games",
            "ranking_game_links",
            "temporades",
            "equips",
            "encontres_lliga",
        ]:
            out[table] = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return out
