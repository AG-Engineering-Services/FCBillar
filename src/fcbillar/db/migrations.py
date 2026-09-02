"""Gestió simple d'esquema via PRAGMA user_version.

Versions:
- 1: schema inicial (clubs, players, modalitats, competicions, rankings,
     ranking_entries, games, ranking_game_links).
- 2: club per-partida — afegides taules temporades, equips, encontres_lliga;
     i columnes a games (equip1_id, equip2_id, encontre_lliga_id, temporada_id,
     arbitre, assistencia).
- 3: unificació de noms de clubs — taula club_aliases per mapejar noms
     alternatius a un mateix club canònic.
- 4: torneigs individuals (opens, catalans, etc.) — taules torneigs_individuals
     i torneig_participants per saber quin jugador va participar a quin torneig
     per temporada.
- 5: clubs virtuals (virtual_clubs, virtual_club_members).
- 6: lliga_noms — noms llegibles de divisions/grups de lliga.
- 7: estructura de la COPA (copa_jornades, copa_encontres, copa_classificacio,
     copa_partides) i fases dels individuals (torneig_fases). Taules noves.
- 8: composició de grups de les fases d'individuals (torneig_fase_grups). El
     portal no publica classificacions amb punts per fase, només l'assignació
     jugador→grup. S'elimina la taula buida torneig_fase_classif del v7.
- 9: atribució de partides individuals al campionat concret — columnes
     games.torneig_id / torneig_fase_id / torneig_link_method, i formalització
     de la taula torneig_partides (resultats reals dels campionats). El vincle
     es calcula a linking.py creuant torneig_partides amb games.
- 10: rankings.data_pub — data ISO exacta de publicació (de l'historial), font
     autoritativa per a any_pub/mes_pub (substitueix la heurística monòtona).
- 11: lliga_pending_partides — partides de lliga jugades encara no al rànquing
     oficial; font de pendents per a la fitxa (la crea l'executescript).
- 12: calendari esportiu federatiu (calendari_events, calendari_versions,
     calendari_canvis) — el PDF de la RFEB parsejat, amb historial de revisions.
     Taules noves: les crea l'executescript.
- 13: el CHECK de rankings.format_url admet 'historial'/'llistat', que és per
     on entren els rànquings des del web d'agost de 2026.
- 14: inscrits_individual — a quina divisió i amb quin club juga cadascú el
     campionat individual, del PDF de divisions de la federació. Taula nova:
     la crea l'executescript.
- 15: encontres_lliga.equip_local_id / equip_visitant_id admeten NULL, i els
     2.035 que valien 0 hi passen. El 0 no era cap equip: era un «no ho sé»
     escrit com si fos un id.
- 16: repara les claus foranes que apuntaven a taules esborrades. Refer una
     taula reanomenant-la primer fa que SQLite reescrigui cap al nom temporal
     les claus foranes que hi apunten des d'altres taules; en esborrar-lo,
     aquelles taules queden apuntant al no-res i no s'hi pot inserir.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from importlib.resources import files
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA_VERSION = 16


def _read_schema_sql() -> str:
    return (files("fcbillar.db") / "schema.sql").read_text(encoding="utf-8")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def current_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


_V2_NEW_COLUMNS_GAMES = [
    ("equip1_id", "INTEGER REFERENCES equips(id)"),
    ("equip2_id", "INTEGER REFERENCES equips(id)"),
    ("encontre_lliga_id", "INTEGER REFERENCES encontres_lliga(id)"),
    ("temporada_id", "INTEGER REFERENCES temporades(id)"),
    ("arbitre", "TEXT"),
    ("assistencia", "TEXT"),
]


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Afegeix les columnes noves a `games`. Les taules noves (CREATE TABLE
    IF NOT EXISTS) ja les crearà el `executescript(schema.sql)` posterior."""
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(games)").fetchall()}
    for col_name, col_def in _V2_NEW_COLUMNS_GAMES:
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE games ADD COLUMN {col_name} {col_def}")
            log.info("v1→v2: afegida columna games.%s", col_name)


_V9_NEW_COLUMNS_GAMES = [
    ("torneig_id", "INTEGER REFERENCES torneigs_individuals(id) ON DELETE SET NULL"),
    ("torneig_fase_id", "INTEGER"),
    ("torneig_link_method", "TEXT"),
]


def _migrate_to_v9(conn: sqlite3.Connection) -> None:
    """Afegeix les columnes d'atribució de campionat a `games`. La taula
    torneig_partides (CREATE TABLE IF NOT EXISTS) la crea l'executescript."""
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(games)").fetchall()}
    for col_name, col_def in _V9_NEW_COLUMNS_GAMES:
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE games ADD COLUMN {col_name} {col_def}")
            log.info("→v9: afegida columna games.%s", col_name)


def _migrate_to_v10(conn: sqlite3.Connection) -> None:
    """Afegeix rankings.data_pub (data ISO de publicació, de l'historial)."""
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(rankings)").fetchall()}
    if "data_pub" not in existing_cols:
        conn.execute("ALTER TABLE rankings ADD COLUMN data_pub TEXT")
        log.info("→v10: afegida columna rankings.data_pub")



def _migrate_to_v13(conn: sqlite3.Connection) -> None:
    """El CHECK de `rankings.format_url` ha d'admetre les vigències noves.

    Amb el web d'agost de 2026 els rànquings ja no venen de `data`/`datahome`
    sinó de `historial`/`llistat`. Els valors antics es conserven: diuen per on
    va entrar cada fila que ja tenim, i esborrar-los seria perdre informació.

    SQLite no sap alterar un CHECK, així que cal refer la taula. Es fa amb el
    nom de columnes explícit per no dependre de l'ordre.

    L'ordre importa i abans era el contrari: es reanomenava l'original i després
    se'n creava una de nova amb el nom bo. Reanomenar una taula fa que SQLite
    reescrigui les claus foranes que hi apunten des d'ALTRES taules, o sigui que
    `ranking_entries` i `ranking_game_links` van passar a apuntar a
    `rankings_v12`, que tot seguit s'esborrava. Amb foreign_keys=ON, inserir-hi
    peta amb «no such table». Creant primer la nova amb un nom temporal i
    reanomenant-la al final, les referències a `rankings` no es toquen mai.
    """
    cols = [row[1] for row in conn.execute("PRAGMA table_info(rankings)").fetchall()]
    if not cols:
        return  # BD nova: la crearà schema.sql amb el CHECK ja bo
    llista = ", ".join(cols)
    conn.executescript(
        f"""
        PRAGMA foreign_keys = OFF;
        CREATE TABLE rankings_nou (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            num_seq         INTEGER NOT NULL,
            modalitat_id    INTEGER NOT NULL REFERENCES modalitats(id),
            url             TEXT NOT NULL,
            format_url      TEXT NOT NULL
                CHECK (format_url IN ('data', 'datahome', 'historial', 'llistat')),
            any_pub         INTEGER,
            mes_pub         INTEGER,
            scraped_at      TEXT NOT NULL DEFAULT (datetime('now')),
            data_pub        TEXT,
            UNIQUE (num_seq, modalitat_id)
        );
        INSERT INTO rankings_nou ({llista}) SELECT {llista} FROM rankings;
        DROP TABLE rankings;
        ALTER TABLE rankings_nou RENAME TO rankings;
        PRAGMA foreign_keys = ON;
        """
    )
    log.info("→v13: rankings.format_url admet 'historial' i 'llistat'")


def _migrate_to_v15(conn: sqlite3.Connection) -> None:
    """Un encontre pot no saber quins equips el jugaven, i ho ha de poder dir.

    Els dos camps eren NOT NULL, o sigui que una ingesta que no resolia l'equip
    hi posava un 0. I 0 no és cap equip: no existeix a `equips`, trenca la clau
    forana i, pitjor, fa que 2.035 encontres semblin partits d'un equip contra
    ell mateix quan es compara local amb visitant. És prou convincent per
    enganyar a qui ho miri —m'ha enganyat a mi.

    Són encontres del backfill històric de 2015-2019: sense data, sense equips i
    sense resultat, però amb 5.631 partides penjades. No es poden esborrar
    perquè s'endurien les partides, que sí que tenen dades. El que es pot fer és
    que el camp digui la veritat: NULL vol dir que no ho sabem.

    Cap ingesta d'ara no pot tornar a escriure un 0: `upsert_equip` es planta si
    el club no existeix.

    Es crea la taula nova amb un nom temporal i es reanomena al final, i no al
    revés: reanomenar l'original faria que SQLite reescrigués les claus foranes
    de `games` i `lliga_pending_partides` cap al nom temporal, que tot seguit
    s'esborra. Vegeu `_migrate_to_v13`, que ho feia així i ho va trencar.
    """
    cols = [row[1] for row in conn.execute("PRAGMA table_info(encontres_lliga)").fetchall()]
    if not cols:
        return  # BD nova: la crearà schema.sql amb els camps ja opcionals
    llista = ", ".join(cols)
    conn.executescript(
        f"""
        PRAGMA foreign_keys = OFF;
        CREATE TABLE encontres_lliga_nou (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            lliga_id                INTEGER NOT NULL,
            divisio_id              INTEGER NOT NULL,
            grup_id                 INTEGER NOT NULL,
            jornada_id              INTEGER NOT NULL,
            encontre_id_extern      INTEGER NOT NULL,
            data                    TEXT,
            temporada_id            INTEGER REFERENCES temporades(id),
            equip_local_id          INTEGER REFERENCES equips(id),
            equip_visitant_id       INTEGER REFERENCES equips(id),
            p_parcials_local        INTEGER,
            p_match_local           INTEGER,
            p_parcials_visitant     INTEGER,
            p_match_visitant        INTEGER,
            UNIQUE(lliga_id, divisio_id, grup_id, jornada_id, encontre_id_extern)
        );
        INSERT INTO encontres_lliga_nou ({llista})
            SELECT {llista} FROM encontres_lliga;
        DROP TABLE encontres_lliga;
        ALTER TABLE encontres_lliga_nou RENAME TO encontres_lliga;
        UPDATE encontres_lliga SET equip_local_id = NULL WHERE equip_local_id = 0;
        UPDATE encontres_lliga SET equip_visitant_id = NULL WHERE equip_visitant_id = 0;
        PRAGMA foreign_keys = ON;
        """
    )
    n = conn.execute(
        "SELECT COUNT(*) FROM encontres_lliga "
        "WHERE equip_local_id IS NULL OR equip_visitant_id IS NULL"
    ).fetchone()[0]
    log.info("→v15: encontres_lliga admet equips desconeguts; %d en tenien un 0", n)


def _taules_referenciades(sql: str) -> set[str]:
    """Els noms de taula que apareixen a les REFERENCES d'un CREATE TABLE."""
    return {
        (m.group(1) or m.group(2) or "")
        for m in re.finditer(r'REFERENCES\s+(?:"([^"]+)"|([A-Za-z_][A-Za-z0-9_]*))', sql)
    }


def claus_penjades(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """{taula: {destins que no existeixen}}. Buit vol dir que tot lliga.

    Amb foreign_keys=ON, una clau forana cap a una taula que no existeix no és
    un detall cosmètic: qualsevol INSERT a la taula que la porta peta amb «no
    such table». I no es veu fins que algú hi escriu.
    """
    existents = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    penjades: dict[str, set[str]] = {}
    for nom, sql in conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'table' AND sql IS NOT NULL"
    ):
        fora = {t for t in _taules_referenciades(sql) if t and t not in existents}
        if fora:
            penjades[nom] = fora
    return penjades


def _migrate_to_v16(conn: sqlite3.Connection) -> None:
    """Torna a lligar les claus foranes que van quedar apuntant al no-res.

    Les migracions v13 i v15 refeien una taula reanomenant primer l'original.
    SQLite, en reanomenar, reescriu les claus foranes que hi apunten des
    d'ALTRES taules perquè segueixin el nom nou —i tot seguit aquell nom
    s'esborrava. Van quedar així `ranking_entries` i `ranking_game_links`
    (cap a `rankings_v12`) i `games` i `lliga_pending_partides` (cap a
    `encontres_lliga_v14`), i inserir-hi petava.

    Aquí es refà cada taula tocada amb la referència corregida, ara sí creant la
    nova amb un nom temporal i reanomenant-la al final. Els índexs se'n van amb
    la taula i els torna a crear `schema.sql`, que s'executa després.
    """
    penjades = claus_penjades(conn)
    if not penjades:
        return
    existents = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    for taula, tots in penjades.items():
        # Només les restes de refer una taula, que porten el sufix de la versió
        # («rankings_v12»). Aquí encara no s'ha executat `schema.sql`, o sigui
        # que hi ha taules que legítimament no existeixen: una base de la v1 té
        # `games` apuntant a `torneigs_individuals`, que es crea després. Qui
        # comprova que al final tot lliga és el guardià d'`ensure_schema`.
        destins = {d for d in tots if re.search(r"_v\d+$", d)}
        if not destins:
            continue
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (taula,)
        ).fetchone()[0]
        nou = sql
        for destí in destins:
            # «rankings_v12» → «rankings»: el nom bo és el de sempre, sense el
            # sufix que hi va posar la migració.
            base = re.sub(r"_v\d+$", "", destí)
            if base not in existents:
                raise RuntimeError(
                    f"{taula} apunta a «{destí}», que sembla una resta de refer "
                    f"«{base}», però «{base}» tampoc no existeix. Cal mirar-ho a mà."
                )
            nou = nou.replace(f'"{destí}"', f'"{base}"').replace(f" {destí}(", f" {base}(")
        cols = ", ".join(
            f'"{r[1]}"' for r in conn.execute(f"PRAGMA table_info({taula})")
        )
        conn.executescript(
            f"""
            PRAGMA foreign_keys = OFF;
            {nou.replace(taula, f"{taula}_nou", 1)};
            INSERT INTO {taula}_nou ({cols}) SELECT {cols} FROM {taula};
            DROP TABLE {taula};
            ALTER TABLE {taula}_nou RENAME TO {taula};
            PRAGMA foreign_keys = ON;
            """
        )
        log.info("→v16: %s tornava a apuntar a %s", taula, ", ".join(sorted(destins)))


def ensure_schema(db_path: Path) -> sqlite3.Connection:
    conn = connect(db_path)
    version = current_version(conn)
    if version >= SCHEMA_VERSION:
        return conn

    # BD existent: aplicar migracions incrementals abans del executescript.
    if 1 <= version < 2:
        _migrate_v1_to_v2(conn)
    # v7 → v8: la taula torneig_fase_classif (mai poblada) es substitueix per
    # torneig_fase_grups. La fem fora; executescript crearà la nova.
    if version == 7:
        conn.execute("DROP TABLE IF EXISTS torneig_fase_classif")
    # → v9: columnes d'atribució de campionat a games (només BDs ja existents;
    # per a BDs noves les crea directament el schema.sql via executescript).
    if 1 <= version < 9:
        _migrate_to_v9(conn)
    # → v10: rankings.data_pub (data exacta de publicació de l'historial).
    if 1 <= version < 10:
        _migrate_to_v10(conn)
    # → v13: el web nou serveix els rànquings per 'historial'/'llistat'.
    if 1 <= version < 13:
        _migrate_to_v13(conn)
    # → v15: un encontre pot no saber quins equips el van jugar.
    if 1 <= version < 15:
        _migrate_to_v15(conn)
    # → v16: repara les claus foranes que la v13 i la v15 van deixar penjades.
    if 1 <= version < 16:
        _migrate_to_v16(conn)
    # v2 → v3 no necessita ALTER (només afegeix taula nova que crearà
    # executescript via CREATE TABLE IF NOT EXISTS).
    # v3 → v4 tampoc (afegeix torneigs_individuals + torneig_participants).

    # executescript és idempotent (CREATE TABLE IF NOT EXISTS, INSERT OR IGNORE,
    # CREATE INDEX IF NOT EXISTS) — segur per a BDs noves i ja migrades.
    conn.executescript(_read_schema_sql())
    # El guardià: una clau forana cap a una taula que no existeix no es veu fins
    # que algú hi escriu, i llavors peta amb «no such table» lluny d'aquí. Dues
    # migracions ho van deixar anar sense que ningú se n'adonés durant mesos.
    penjades = claus_penjades(conn)
    if penjades:
        detall = "; ".join(f"{t} → {', '.join(sorted(d))}" for t, d in sorted(penjades.items()))
        raise RuntimeError(
            f"Hi ha claus foranes que apunten a taules que no existeixen: {detall}. "
            f"Amb foreign_keys=ON no s'hi podrà inserir. Refer una taula ha de crear "
            f"primer la nova amb un nom temporal i reanomenar-la al final, no al revés."
        )
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return conn
