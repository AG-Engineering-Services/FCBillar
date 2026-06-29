"""Operacions de persistència — inserts/upserts idempotents."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
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
    TorneigIndividualRecord,
    TorneigParticipantRecord,
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

    @staticmethod
    def normalize_club_name(nom: str) -> str:
        """Normalitza un nom de club per a comparació fuzzy.

        Estratègia: minúscules + sense espais + sense accents + sense punts.
        Permet matchejar 'C.B. SANTS' ↔ 'C.B.SANTS' ↔ 'c.b.sants'.
        NO matcheja 'SB FOMENT MOLINS' ↔ 'S.B.F.MOLINS' (abreviacions
        diferents); aquest cas requereix un alias manual.
        """
        # Treure accents
        nfkd = unicodedata.normalize("NFKD", nom)
        no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
        # Minúscules + treure espais, punts, cometes
        return re.sub(r"[\s.\"']+", "", no_accents.lower())

    def resolve_club_id_by_nom(self, nom: str) -> int | None:
        """Resol nom_brut → club.id, intentant 3 estratègies en ordre:

        1. Match exacte de fcb_id (nom tal com el va donar el portal).
        2. Match de nom normalitzat contra qualsevol nom de la taula clubs.
        3. Match exacte contra la taula club_aliases.
        Retorna None si cap funciona.
        """
        # 1. Exact
        row = self.conn.execute(
            "SELECT id FROM clubs WHERE fcb_id = ?", (nom,)
        ).fetchone()
        if row:
            return row[0]
        # 2. Normalitzat
        norm = self.normalize_club_name(nom)
        for cid, cnom in self.conn.execute("SELECT id, nom FROM clubs").fetchall():
            if self.normalize_club_name(cnom) == norm:
                return cid
        # 3. Alias
        row = self.conn.execute(
            "SELECT club_id FROM club_aliases WHERE alias_nom = ?", (nom,)
        ).fetchone()
        if row:
            return row[0]
        # 3b. Alias normalitzat
        for cid, alias in self.conn.execute(
            "SELECT club_id, alias_nom FROM club_aliases"
        ).fetchall():
            if self.normalize_club_name(alias) == norm:
                return cid
        return None

    def add_club_alias(self, alias_nom: str, club_fcb_id: str) -> int:
        """Registra un alias manualment. El club ha d'existir."""
        cid = self.get_club_id_by_fcb_id(club_fcb_id)
        if cid is None:
            raise ValueError(f"Club {club_fcb_id} no registrat")
        cur = self.conn.execute(
            """
            INSERT INTO club_aliases (alias_nom, club_id) VALUES (?, ?)
            ON CONFLICT(alias_nom) DO UPDATE SET club_id = excluded.club_id
            RETURNING id
            """,
            (alias_nom, cid),
        )
        return cur.fetchone()[0]

    def merge_clubs(self, source_fcb_id: str, target_fcb_id: str) -> dict[str, int]:
        """Fusiona el club `source` dins de `target`.

        - Reassigna `equips.club_id` i `players.club_id` de source → target.
        - Reassigna `club_aliases.club_id` de source → target.
        - Crea un alias amb el nom del source apuntant a target (per preservar
          la possibilitat de resolució futura).
        - Esborra el club source.

        Retorna comptadors de què s'ha mogut. Llença ValueError si source==target
        o si algun dels dos no existeix.
        """
        if source_fcb_id == target_fcb_id:
            raise ValueError("source i target no poden ser el mateix club")
        source_id = self.get_club_id_by_fcb_id(source_fcb_id)
        target_id = self.get_club_id_by_fcb_id(target_fcb_id)
        if source_id is None:
            raise ValueError(f"Club source {source_fcb_id} no registrat")
        if target_id is None:
            raise ValueError(f"Club target {target_fcb_id} no registrat")

        # Si ja hi ha equips iguals (mateixa lletra) a target, els del source
        # caldria reassignar-los; podríen colidir amb UNIQUE(club_id, lletra).
        # Solució: per cada (target_id, lletra) ja existent, els games i
        # encontres del source.equip cal redirigir a l'equip target.lletra
        # equivalent abans d'esborrar el source.equip.
        source_equips = self.conn.execute(
            "SELECT id, lletra FROM equips WHERE club_id = ?", (source_id,)
        ).fetchall()
        equips_moved = 0
        for src_eq_id, lletra in source_equips:
            existing_target_eq = self.conn.execute(
                "SELECT id FROM equips WHERE club_id = ? AND lletra = ?",
                (target_id, lletra),
            ).fetchone()
            if existing_target_eq is not None:
                # Reassignar games i encontres a l'equip target existent + esborrar el source.equip
                tgt_eq_id = existing_target_eq[0]
                self.conn.execute(
                    "UPDATE games SET equip1_id = ? WHERE equip1_id = ?",
                    (tgt_eq_id, src_eq_id),
                )
                self.conn.execute(
                    "UPDATE games SET equip2_id = ? WHERE equip2_id = ?",
                    (tgt_eq_id, src_eq_id),
                )
                self.conn.execute(
                    "UPDATE encontres_lliga SET equip_local_id = ? WHERE equip_local_id = ?",
                    (tgt_eq_id, src_eq_id),
                )
                self.conn.execute(
                    "UPDATE encontres_lliga SET equip_visitant_id = ? WHERE equip_visitant_id = ?",
                    (tgt_eq_id, src_eq_id),
                )
                self.conn.execute("DELETE FROM equips WHERE id = ?", (src_eq_id,))
            else:
                # Reassignar simple: el source.equip passa a pertànyer al target.club
                self.conn.execute(
                    "UPDATE equips SET club_id = ? WHERE id = ?",
                    (target_id, src_eq_id),
                )
            equips_moved += 1

        # Players: reassignar de source → target
        cur = self.conn.execute(
            "UPDATE players SET club_id = ? WHERE club_id = ?",
            (target_id, source_id),
        )
        players_moved = cur.rowcount

        # Aliases: reassignar de source → target
        cur = self.conn.execute(
            "UPDATE club_aliases SET club_id = ? WHERE club_id = ?",
            (target_id, source_id),
        )
        aliases_moved = cur.rowcount

        # Crear alias per preservar el nom del source.
        # INSERT OR IGNORE perquè potser ja existeix com a alias.
        self.conn.execute(
            "INSERT OR IGNORE INTO club_aliases (alias_nom, club_id) VALUES (?, ?)",
            (source_fcb_id, target_id),
        )

        # Esborrar el club source.
        self.conn.execute("DELETE FROM clubs WHERE id = ?", (source_id,))

        return {
            "equips_moved": equips_moved,
            "players_moved": players_moved,
            "aliases_moved": aliases_moved,
        }

    def list_clubs_with_aliases(self) -> list[tuple[str, list[str]]]:
        """Llista (club_fcb_id, [alias_nom, ...]) ordenat per nom de club."""
        rows = self.conn.execute(
            """
            SELECT c.fcb_id, a.alias_nom
            FROM clubs c
            LEFT JOIN club_aliases a ON a.club_id = c.id
            ORDER BY c.nom, a.alias_nom
            """
        ).fetchall()
        result: dict[str, list[str]] = {}
        for fcb_id, alias in rows:
            result.setdefault(fcb_id, [])
            if alias is not None:
                result[fcb_id].append(alias)
        return list(result.items())

    # ---------------------- players ----------------------

    # Prefix usat per als fcb_id de jugadors creats com a placeholder (només
    # coneixem el seu nom, no l'id intern del portal). Quan més tard arriba un
    # `upsert_player` amb fcb_id real i el mateix nom, fusionem automàticament.
    PLACEHOLDER_PREFIX = "name:"

    @classmethod
    def make_placeholder_fcb_id(cls, nom: str) -> str:
        return f"{cls.PLACEHOLDER_PREFIX}{nom}"

    def upsert_player(self, player: Player) -> int:
        club_id: int | None = None
        if player.club_fcb_id:
            club_id = self.get_club_id_by_fcb_id(player.club_fcb_id)

        # Fusió de placeholder: si arriba un fcb_id real i ja existeix un
        # placeholder amb el mateix nom (i no hi ha ja un player amb el nou
        # fcb_id), promocionem el placeholder reassignant-li el fcb_id real.
        # Així els games existents (player1_id, player2_id, ...) segueixen
        # apuntant al mateix id intern sense haver de moure files.
        if not player.fcb_id.startswith(self.PLACEHOLDER_PREFIX):
            existing_real = self.conn.execute(
                "SELECT id FROM players WHERE fcb_id = ?", (player.fcb_id,)
            ).fetchone()
            if existing_real is None:
                placeholder_row = self.conn.execute(
                    "SELECT id FROM players WHERE fcb_id LIKE ? AND nom = ?",
                    (f"{self.PLACEHOLDER_PREFIX}%", player.nom),
                ).fetchone()
                if placeholder_row is not None:
                    self.conn.execute(
                        """
                        UPDATE players
                        SET fcb_id = ?,
                            club_id = COALESCE(?, club_id),
                            updated_at = datetime('now')
                        WHERE id = ?
                        """,
                        (player.fcb_id, club_id, placeholder_row[0]),
                    )
                    return placeholder_row[0]

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

    def resolve_or_create_player_by_nom(self, nom: str) -> str:
        """Retorna l'fcb_id del jugador amb aquest nom; en crea un placeholder si no existeix.

        Si hi ha homònims, retorna l'fcb_id del primer trobat (per evitar
        rebentar). Documentat: en cas d'ambigüitat, no podem distingir,
        però almenys no perdem la partida.
        """
        existing = self.get_player_fcb_id_by_nom(nom)
        if existing is not None:
            return existing
        # Crear placeholder. No usem upsert_player perquè el placeholder
        # NO ha de disparar la lògica de fusió (no té sentit fusionar amb
        # ell mateix).
        placeholder = Player(fcb_id=self.make_placeholder_fcb_id(nom), nom=nom)
        cur = self.conn.execute(
            """
            INSERT INTO players (fcb_id, nom, seguiment) VALUES (?, ?, 0)
            ON CONFLICT(fcb_id) DO UPDATE SET nom = excluded.nom
            RETURNING fcb_id
            """,
            (placeholder.fcb_id, placeholder.nom),
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
            INSERT INTO rankings (num_seq, modalitat_id, url, format_url, any_pub, mes_pub, data_pub)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(num_seq, modalitat_id) DO UPDATE SET
                url = excluded.url,
                format_url = excluded.format_url,
                any_pub = COALESCE(excluded.any_pub, rankings.any_pub),
                mes_pub = COALESCE(excluded.mes_pub, rankings.mes_pub),
                data_pub = COALESCE(excluded.data_pub, rankings.data_pub),
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
                ranking.data_pub,
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
                mitjana_general = CASE
                    WHEN (
                        SELECT COUNT(*) FROM ranking_game_links rgl
                        WHERE rgl.ranking_id = excluded.ranking_id
                          AND rgl.player_id_origen = excluded.player_id
                    ) <> excluded.partides
                    THEN excluded.mitjana_general
                    ELSE mitjana_general
                END,
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

    def game_exists(self, game_id: str) -> bool:
        return (
            self.conn.execute("SELECT 1 FROM games WHERE id = ?", (game_id,)).fetchone()
            is not None
        )

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
                               guanyador_id,
                               equip1_id, equip2_id, encontre_lliga_id, temporada_id,
                               arbitre, assistencia,
                               extras_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                caramboles1 = COALESCE(excluded.caramboles1, games.caramboles1),
                caramboles2 = COALESCE(excluded.caramboles2, games.caramboles2),
                entrades = COALESCE(excluded.entrades, games.entrades),
                mitjana1 = COALESCE(excluded.mitjana1, games.mitjana1),
                mitjana2 = COALESCE(excluded.mitjana2, games.mitjana2),
                serie_max1 = COALESCE(excluded.serie_max1, games.serie_max1),
                serie_max2 = COALESCE(excluded.serie_max2, games.serie_max2),
                guanyador_id = COALESCE(excluded.guanyador_id, games.guanyador_id),
                equip1_id = COALESCE(excluded.equip1_id, games.equip1_id),
                equip2_id = COALESCE(excluded.equip2_id, games.equip2_id),
                encontre_lliga_id = COALESCE(excluded.encontre_lliga_id, games.encontre_lliga_id),
                temporada_id = COALESCE(excluded.temporada_id, games.temporada_id),
                arbitre = COALESCE(excluded.arbitre, games.arbitre),
                assistencia = COALESCE(excluded.assistencia, games.assistencia),
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
                game.equip1_id,
                game.equip2_id,
                game.encontre_lliga_id,
                game.temporada_id,
                game.arbitre,
                game.assistencia,
                extras,
            ),
        )
        return game.id_natural

    def enrich_game_by_signature(self, game: Game, season_range: tuple[str, str] | None = None) -> bool:
        """Enriqueix un game EXISTENT (de partideshome) amb context de competició.

        Cerca per signatura física (jugadors + caramboles + entrades),
        independentment de la modalitat — la modalitat l'estableix només
        partideshome i NO s'ha de tocar mai. Assigna encontre/equips/temporada/sèrie.
        No crea cap game: si no existeix, retorna False.

        Si el game porta data, casa per data exacta. Si no (pàgines històriques de
        lliga, que no en porten), casa dins del rang de dates de la temporada
        (season_range = (data_min, data_max)) per evitar col·lisions.
        """
        p1 = self.get_player_id_by_fcb_id(game.player1_fcb_id)
        p2 = self.get_player_id_by_fcb_id(game.player2_fcb_id)
        if p1 is None or p2 is None:
            return False
        players = (
            "((player1_id=? AND player2_id=? AND caramboles1 IS ? AND caramboles2 IS ?) "
            "OR (player1_id=? AND player2_id=? AND caramboles1 IS ? AND caramboles2 IS ?))"
        )
        pargs = (p1, p2, game.caramboles1, game.caramboles2, p2, p1, game.caramboles2, game.caramboles1)
        if game.data_partida is not None:
            row = self.conn.execute(
                f"SELECT id, player1_id FROM games WHERE data_partida=? AND entrades IS ? AND {players} LIMIT 1",
                (game.data_partida.isoformat(), game.entrades, *pargs),
            ).fetchone()
        elif season_range is not None:
            row = self.conn.execute(
                f"SELECT id, player1_id FROM games WHERE data_partida BETWEEN ? AND ? "
                f"AND entrades IS ? AND {players} LIMIT 1",
                (season_range[0], season_range[1], game.entrades, *pargs),
            ).fetchone()
        else:
            return False
        if row is None:
            return False
        swapped = row["player1_id"] == p2 and p1 != p2
        e1, e2 = (game.equip2_id, game.equip1_id) if swapped else (game.equip1_id, game.equip2_id)
        # La sèrie major SÍ ve a les partides de lliga; partideshome no la porta.
        # L'assignem (COALESCE: no sobreescriu si ja n'hi ha). Respecta l'ordre.
        s1, s2 = (game.serie_max2, game.serie_max1) if swapped else (game.serie_max1, game.serie_max2)
        self.conn.execute(
            """
            UPDATE games SET
                equip1_id = COALESCE(?, equip1_id),
                equip2_id = COALESCE(?, equip2_id),
                encontre_lliga_id = COALESCE(?, encontre_lliga_id),
                temporada_id = COALESCE(?, temporada_id),
                arbitre = COALESCE(?, arbitre),
                assistencia = COALESCE(?, assistencia),
                serie_max1 = COALESCE(serie_max1, ?),
                serie_max2 = COALESCE(serie_max2, ?)
            WHERE id = ?
            """,
            (e1, e2, game.encontre_lliga_id, game.temporada_id, game.arbitre,
             game.assistencia, s1, s2, row["id"]),
        )
        return True

    def infer_lliga_distance_limit(
        self,
        *,
        lliga_id: int,
        divisio_id: int,
        grup_id: int,
        modalitat_codi_fcb: int,
    ) -> tuple[int | None, int | None]:
        """Infereix (distància, límit d'entrades) d'un grup+modalitat a partir de
        les partides ja desades amb entrades>0.

        - distància = màx. caràmboles del guanyador: la partida s'atura just en
          assolir-la, així que cap guanyador la supera.
        - límit d'entrades = màx. entrades observades: les partides que no arriben
          a la distància van fins al límit d'entrades.

        Retorna (None, None) si encara no hi ha cap partida de referència.
        """
        row = self.conn.execute(
            """
            SELECT MAX(MAX(COALESCE(g.caramboles1, 0), COALESCE(g.caramboles2, 0))) AS dist,
                   MAX(g.entrades) AS lim
            FROM games g
            JOIN encontres_lliga en ON en.id = g.encontre_lliga_id
            JOIN modalitats m ON m.id = g.modalitat_id
            WHERE en.lliga_id = ? AND en.divisio_id = ? AND en.grup_id = ?
              AND m.codi_fcb = ? AND g.entrades > 0
            """,
            (lliga_id, divisio_id, grup_id, modalitat_codi_fcb),
        ).fetchone()
        if row is None:
            return None, None
        return row["dist"], row["lim"]

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

    # ---------------------- torneigs individuals (v4) ----------------------

    def upsert_torneig_individual(self, t: TorneigIndividualRecord) -> int:
        modalitat_id: int | None = None
        if t.modalitat_codi_fcb is not None:
            modalitat_id = self.get_modalitat_id_by_codi_fcb(t.modalitat_codi_fcb)
        temporada_id: int | None = None
        if t.temporada_nom:
            temporada_id = self.upsert_temporada(Temporada(nom=t.temporada_nom))
        cur = self.conn.execute(
            """
            INSERT INTO torneigs_individuals
                (torneig_id_extern, divisio_id_extern, nom, modalitat_id, temporada_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(torneig_id_extern, divisio_id_extern, temporada_id)
            DO UPDATE SET nom = excluded.nom,
                          modalitat_id = COALESCE(excluded.modalitat_id, torneigs_individuals.modalitat_id)
            RETURNING id
            """,
            (t.torneig_id_extern, t.divisio_id_extern, t.nom, modalitat_id, temporada_id),
        )
        return cur.fetchone()[0]

    def upsert_torneig_participant(self, p: TorneigParticipantRecord, temporada_nom: str | None = None) -> None:
        # Resoldre torneig_id intern via clau composta
        temporada_id: int | None = None
        if temporada_nom:
            temporada_id = self.upsert_temporada(Temporada(nom=temporada_nom))
        torneig_row = self.conn.execute(
            """
            SELECT id FROM torneigs_individuals
            WHERE torneig_id_extern = ? AND divisio_id_extern = ?
              AND COALESCE(temporada_id, -1) = COALESCE(?, -1)
            """,
            (p.torneig_id_extern, p.divisio_id_extern, temporada_id),
        ).fetchone()
        if torneig_row is None:
            raise ValueError(
                f"Torneig ({p.torneig_id_extern}, {p.divisio_id_extern}, {temporada_nom}) no registrat"
            )
        player_id = self.get_player_id_by_fcb_id(p.player_fcb_id)
        if player_id is None:
            raise ValueError(f"Player {p.player_fcb_id} no registrat")
        self.conn.execute(
            """
            INSERT INTO torneig_participants
                (torneig_id, player_id, posicio, partides_jugades, punts,
                 caramboles, entrades, mitjana_general, mitjana_particular,
                 serie_max, club_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(torneig_id, player_id) DO UPDATE SET
                posicio = COALESCE(excluded.posicio, torneig_participants.posicio),
                partides_jugades = COALESCE(excluded.partides_jugades, torneig_participants.partides_jugades),
                punts = COALESCE(excluded.punts, torneig_participants.punts),
                caramboles = COALESCE(excluded.caramboles, torneig_participants.caramboles),
                entrades = COALESCE(excluded.entrades, torneig_participants.entrades),
                mitjana_general = COALESCE(excluded.mitjana_general, torneig_participants.mitjana_general),
                mitjana_particular = COALESCE(excluded.mitjana_particular, torneig_participants.mitjana_particular),
                serie_max = COALESCE(excluded.serie_max, torneig_participants.serie_max),
                club_text = COALESCE(excluded.club_text, torneig_participants.club_text)
            """,
            (
                torneig_row[0], player_id, p.posicio, p.partides_jugades, p.punts,
                p.caramboles, p.entrades, p.mitjana_general, p.mitjana_particular,
                p.serie_max, p.club_text,
            ),
        )

    # ---------------------- copa ----------------------
    # La connexió és autocommit (isolation_level=None), així que cada execute
    # persisteix sol. Idempotent via ON CONFLICT; les partides es reescriuen.

    def upsert_copa_jornada(
        self, edicio_id: int, jornada: int, ordre: int | None, nom: str | None
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO copa_jornades (edicio_id, jornada, ordre, nom)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(edicio_id, jornada) DO UPDATE SET
                ordre = COALESCE(excluded.ordre, copa_jornades.ordre),
                nom = COALESCE(excluded.nom, copa_jornades.nom)
            """,
            (edicio_id, jornada, ordre, nom),
        )

    def upsert_copa_encontre(
        self,
        *,
        edicio_id: int,
        jornada: int,
        grup_id: int,
        grup_nom: str | None,
        enc_id_extern: int,
        team_a_extern: int,
        team_b_extern: int,
        equip_local: str | None,
        equip_visitant: str | None,
        p_match_local: int | None,
        p_match_visitant: int | None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO copa_encontres (
                edicio_id, jornada, grup_id, grup_nom, enc_id_extern,
                team_a_extern, team_b_extern, equip_local, equip_visitant,
                p_match_local, p_match_visitant
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(edicio_id, jornada, grup_id, enc_id_extern, team_a_extern, team_b_extern)
            DO UPDATE SET
                grup_nom = COALESCE(excluded.grup_nom, copa_encontres.grup_nom),
                equip_local = excluded.equip_local,
                equip_visitant = excluded.equip_visitant,
                p_match_local = excluded.p_match_local,
                p_match_visitant = excluded.p_match_visitant
            RETURNING id
            """,
            (
                edicio_id, jornada, grup_id, grup_nom, enc_id_extern,
                team_a_extern, team_b_extern, equip_local, equip_visitant,
                p_match_local, p_match_visitant,
            ),
        )
        return int(cur.fetchone()[0])

    def upsert_copa_classificacio(
        self,
        *,
        edicio_id: int,
        jornada: int,
        grup_id: int,
        grup_nom: str | None,
        posicio: int | None,
        equip: str,
        punts: int | None,
        parcials: int | None,
        mitjana: float | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO copa_classificacio (
                edicio_id, jornada, grup_id, grup_nom, posicio, equip,
                punts, parcials, mitjana
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(edicio_id, jornada, grup_id, equip) DO UPDATE SET
                grup_nom = COALESCE(excluded.grup_nom, copa_classificacio.grup_nom),
                posicio = excluded.posicio,
                punts = excluded.punts,
                parcials = excluded.parcials,
                mitjana = excluded.mitjana
            """,
            (edicio_id, jornada, grup_id, grup_nom, posicio, equip, punts, parcials, mitjana),
        )

    def replace_copa_partides(
        self, encontre_copa_id: int, rows: list[tuple]
    ) -> None:
        """Reescriu les partides d'un encontre (delete + insert) — idempotent.

        Cada tupla: (ordre, local_nom, local_caramboles, local_serie,
        visitant_nom, visitant_caramboles, visitant_serie, entrades,
        punts_local, punts_visitant).
        """
        self.conn.execute(
            "DELETE FROM copa_partides WHERE encontre_copa_id = ?", (encontre_copa_id,)
        )
        if rows:
            self.conn.executemany(
                """
                INSERT INTO copa_partides (
                    encontre_copa_id, ordre, local_nom, local_caramboles, local_serie,
                    visitant_nom, visitant_caramboles, visitant_serie, entrades,
                    punts_local, punts_visitant
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(encontre_copa_id, *r) for r in rows],
            )

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
            "club_aliases",
            "torneigs_individuals",
            "torneig_participants",
        ]:
            out[table] = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return out
