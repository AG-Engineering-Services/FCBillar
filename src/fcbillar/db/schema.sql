-- Esquema SQLite de FCBillar
-- Versió de l'esquema gestionada amb PRAGMA user_version

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS clubs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fcb_id      TEXT NOT NULL UNIQUE,
    nom         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fcb_id          TEXT NOT NULL UNIQUE,
    nom             TEXT NOT NULL,
    club_id         INTEGER REFERENCES clubs(id) ON DELETE SET NULL,
    seguiment       INTEGER NOT NULL DEFAULT 0,  -- 0/1: jugador d'interès marcat per l'usuari
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_players_club ON players(club_id);
CREATE INDEX IF NOT EXISTS ix_players_seguiment ON players(seguiment) WHERE seguiment = 1;

CREATE TABLE IF NOT EXISTS modalitats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codi_fcb    INTEGER NOT NULL UNIQUE,  -- id que apareix a la URL
    nom         TEXT NOT NULL UNIQUE
);
INSERT OR IGNORE INTO modalitats (codi_fcb, nom) VALUES
    (1, 'Tres bandes'),
    (2, 'Lliure'),
    (3, 'Quadre 47/2'),
    (4, 'Banda'),
    (6, 'Quadre 71/2');

CREATE TABLE IF NOT EXISTS competicions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nom                 TEXT NOT NULL,
    temporada           TEXT,
    modalitat_id        INTEGER REFERENCES modalitats(id) ON DELETE SET NULL,
    UNIQUE(nom, temporada, modalitat_id)
);

CREATE TABLE IF NOT EXISTS rankings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    num_seq         INTEGER NOT NULL,
    modalitat_id    INTEGER NOT NULL REFERENCES modalitats(id),
    url             TEXT NOT NULL,
    format_url      TEXT NOT NULL CHECK (format_url IN ('data', 'datahome')),
    any_pub         INTEGER,
    mes_pub         INTEGER,
    scraped_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(num_seq, modalitat_id)
);
CREATE INDEX IF NOT EXISTS ix_rankings_modalitat ON rankings(modalitat_id);

CREATE TABLE IF NOT EXISTS ranking_entries (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    ranking_id              INTEGER NOT NULL REFERENCES rankings(id) ON DELETE CASCADE,
    player_id               INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    posicio                 INTEGER,
    mitjana_general         REAL,
    mitjana_particular      REAL,
    partides                INTEGER,
    extras_json             TEXT,
    UNIQUE(ranking_id, player_id)
);
CREATE INDEX IF NOT EXISTS ix_entries_player ON ranking_entries(player_id);

CREATE TABLE IF NOT EXISTS temporades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nom         TEXT NOT NULL UNIQUE  -- p.ex. "2025-2026"
);

CREATE TABLE IF NOT EXISTS equips (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    club_id     INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
    lletra      TEXT NOT NULL,  -- "A", "B", "C", o variant ("UNICO", etc.)
    UNIQUE(club_id, lletra)
);
CREATE INDEX IF NOT EXISTS ix_equips_club ON equips(club_id);

CREATE TABLE IF NOT EXISTS encontres_lliga (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Identificadors derivats de la URL del portal (composta única):
    lliga_id                INTEGER NOT NULL,
    divisio_id              INTEGER NOT NULL,
    grup_id                 INTEGER NOT NULL,
    jornada_id              INTEGER NOT NULL,
    encontre_id_extern      INTEGER NOT NULL,
    --
    data                    TEXT,
    temporada_id            INTEGER REFERENCES temporades(id),
    equip_local_id          INTEGER NOT NULL REFERENCES equips(id),
    equip_visitant_id       INTEGER NOT NULL REFERENCES equips(id),
    p_parcials_local        INTEGER,
    p_match_local           INTEGER,
    p_parcials_visitant     INTEGER,
    p_match_visitant        INTEGER,
    UNIQUE(lliga_id, divisio_id, grup_id, jornada_id, encontre_id_extern)
);
CREATE INDEX IF NOT EXISTS ix_encontres_data ON encontres_lliga(data);
CREATE INDEX IF NOT EXISTS ix_encontres_local ON encontres_lliga(equip_local_id);
CREATE INDEX IF NOT EXISTS ix_encontres_visitant ON encontres_lliga(equip_visitant_id);

CREATE TABLE IF NOT EXISTS games (
    id                      TEXT PRIMARY KEY,  -- id_natural (hash determinista)
    data_partida            TEXT NOT NULL,
    competicio_id           INTEGER REFERENCES competicions(id) ON DELETE SET NULL,
    modalitat_id            INTEGER NOT NULL REFERENCES modalitats(id),
    player1_id              INTEGER NOT NULL REFERENCES players(id),
    player2_id              INTEGER NOT NULL REFERENCES players(id),
    caramboles1             INTEGER,
    caramboles2             INTEGER,
    entrades                INTEGER,
    mitjana1                REAL,
    mitjana2                REAL,
    serie_max1              INTEGER,
    serie_max2              INTEGER,
    guanyador_id            INTEGER REFERENCES players(id),
    -- Camps afegits a v2: trasllat de "club per-partida".
    equip1_id               INTEGER REFERENCES equips(id),
    equip2_id               INTEGER REFERENCES equips(id),
    encontre_lliga_id       INTEGER REFERENCES encontres_lliga(id),
    temporada_id            INTEGER REFERENCES temporades(id),
    arbitre                 TEXT,
    assistencia             TEXT,
    extras_json             TEXT,
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_games_data ON games(data_partida);
CREATE INDEX IF NOT EXISTS ix_games_p1 ON games(player1_id);
CREATE INDEX IF NOT EXISTS ix_games_p2 ON games(player2_id);
CREATE INDEX IF NOT EXISTS ix_games_modalitat ON games(modalitat_id);
CREATE INDEX IF NOT EXISTS ix_games_competicio ON games(competicio_id);

CREATE TABLE IF NOT EXISTS ranking_game_links (
    ranking_id              INTEGER NOT NULL REFERENCES rankings(id) ON DELETE CASCADE,
    game_id                 TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    player_id_origen        INTEGER NOT NULL REFERENCES players(id),
    PRIMARY KEY (ranking_id, game_id, player_id_origen)
);
CREATE INDEX IF NOT EXISTS ix_rgl_game ON ranking_game_links(game_id);
