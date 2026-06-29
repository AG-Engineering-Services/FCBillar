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

-- v4: Torneigs individuals (opens, catalans, etc.).
-- El portal els organitza per `divisions/{torneig_id}` i cada torneig té diverses
-- divisions (HONOR, 1a, 2a...). Per cada divisió hi ha una classificació final
-- amb participants. Aquí desem els torneigs + participants per saber
-- "el jugador X va participar al torneig Y a la temporada Z".
CREATE TABLE IF NOT EXISTS torneigs_individuals (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    torneig_id_extern       INTEGER NOT NULL,  -- id del portal (192, 206...)
    divisio_id_extern       INTEGER NOT NULL,  -- id divisió interna (417, 418...)
    nom                     TEXT NOT NULL,     -- "TRES BANDES - 1A DIVISIÓ"
    modalitat_id            INTEGER REFERENCES modalitats(id),
    temporada_id            INTEGER REFERENCES temporades(id),
    UNIQUE(torneig_id_extern, divisio_id_extern, temporada_id)
);
CREATE INDEX IF NOT EXISTS ix_torneigs_ind_temp ON torneigs_individuals(temporada_id);

CREATE TABLE IF NOT EXISTS torneig_participants (
    torneig_id              INTEGER NOT NULL REFERENCES torneigs_individuals(id) ON DELETE CASCADE,
    player_id               INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    posicio                 INTEGER,
    partides_jugades        INTEGER,
    punts                   INTEGER,
    caramboles              INTEGER,
    entrades                INTEGER,
    mitjana_general         REAL,
    mitjana_particular      REAL,
    serie_max               INTEGER,
    club_text               TEXT,  -- nom del club tal com surt a la classificació
    PRIMARY KEY (torneig_id, player_id)
);
CREATE INDEX IF NOT EXISTS ix_torneig_part_player ON torneig_participants(player_id);

-- Alias per a noms alternatius de clubs (v3). El portal usa convencions
-- diferents segons la pàgina (p.ex. "C.B.SANTS" al listing oficial vs
-- "C.B. SANTS" a la lliga); aquesta taula permet mapejar-los al mateix
-- club canònic. La resolució (exact → normalitzat → alias) viu al repository.
CREATE TABLE IF NOT EXISTS club_aliases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    alias_nom   TEXT NOT NULL UNIQUE,
    club_id     INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_club_aliases_club ON club_aliases(club_id);

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
    data_pub        TEXT,  -- data ISO exacta de publicació (de l'historial); font de any_pub/mes_pub
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
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    -- v9: atribució d'una partida individual al campionat (torneig) concret.
    -- competicio_id només dona la categoria genèrica ('INDIVIDUAL'); aquí desem
    -- l'enllaç precís al torneig + fase, derivat de creuar `torneig_partides`
    -- (partides reals scrapejades dels campionats) amb aquesta partida del
    -- rànquing per (modalitat + parella + caramboles + entrades). Vegeu linking.py.
    torneig_id              INTEGER REFERENCES torneigs_individuals(id) ON DELETE SET NULL,
    torneig_fase_id         INTEGER,            -- fase_id extern (pàgina del portal)
    torneig_link_method     TEXT                -- 'exacte' | (futur: 'participacio')
);
CREATE INDEX IF NOT EXISTS ix_games_data ON games(data_partida);
CREATE INDEX IF NOT EXISTS ix_games_p1 ON games(player1_id);
CREATE INDEX IF NOT EXISTS ix_games_p2 ON games(player2_id);
CREATE INDEX IF NOT EXISTS ix_games_modalitat ON games(modalitat_id);
CREATE INDEX IF NOT EXISTS ix_games_competicio ON games(competicio_id);
CREATE INDEX IF NOT EXISTS ix_games_torneig ON games(torneig_id);

CREATE TABLE IF NOT EXISTS ranking_game_links (
    ranking_id              INTEGER NOT NULL REFERENCES rankings(id) ON DELETE CASCADE,
    game_id                 TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    player_id_origen        INTEGER NOT NULL REFERENCES players(id),
    PRIMARY KEY (ranking_id, game_id, player_id_origen)
);
CREATE INDEX IF NOT EXISTS ix_rgl_game ON ranking_game_links(game_id);

-- v5: Clubs virtuals. Una agrupació arbitrària de jugadors que NO depèn d'un
-- club real federat (p.ex. "Club Foment Martinenc": jugadors que juguen per
-- altres clubs però que es plantegen muntar un club federat). Permet aplicar
-- les mateixes vistes de "focus de club" (KPIs, evolució d'ordre al rànquing,
-- millors/pitjors partides) a una selecció manual de jugadors.
CREATE TABLE IF NOT EXISTS virtual_clubs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nom         TEXT NOT NULL UNIQUE,
    descripcio  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS virtual_club_members (
    virtual_club_id INTEGER NOT NULL REFERENCES virtual_clubs(id) ON DELETE CASCADE,
    player_id       INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    PRIMARY KEY (virtual_club_id, player_id)
);
CREATE INDEX IF NOT EXISTS ix_vcm_player ON virtual_club_members(player_id);

-- v6: Noms de divisions i grups de lliga. El portal no els desa als encontres
-- (només ids numèrics a la URL); aquesta taula mapeja (lliga, divisio, grup) →
-- nom llegible, descobert via `discover_lliga` (pàgines públiques). grup_id = 0
-- significa "nom de la divisió/categoria". Permet mostrar les classificacions
-- agrupades per categoria amb noms reals enlloc d'ids.
CREATE TABLE IF NOT EXISTS lliga_noms (
    lliga_id    INTEGER NOT NULL,
    divisio_id  INTEGER NOT NULL,
    grup_id     INTEGER NOT NULL DEFAULT 0,  -- 0 = nom de la divisió/categoria
    nom         TEXT NOT NULL,
    PRIMARY KEY (lliga_id, divisio_id, grup_id)
);

-- v7: Estructura de la COPA. El portal serveix la classificació de cada grup de
-- cada jornada (no es computa com a la lliga: els grups es refan cada jornada).
-- Pàgines públiques. ids "extern" = ids numèrics de les URLs del portal.
CREATE TABLE IF NOT EXISTS copa_jornades (
    edicio_id   INTEGER NOT NULL,
    jornada     INTEGER NOT NULL,        -- id extern de la jornada (URL)
    ordre       INTEGER,                 -- 1a, 2a, 3a... dins l'edició
    nom         TEXT,
    PRIMARY KEY (edicio_id, jornada)
);

CREATE TABLE IF NOT EXISTS copa_encontres (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    edicio_id       INTEGER NOT NULL,
    jornada         INTEGER NOT NULL,
    grup_id         INTEGER NOT NULL,
    grup_nom        TEXT,
    enc_id_extern   INTEGER NOT NULL,
    team_a_extern   INTEGER NOT NULL,
    team_b_extern   INTEGER NOT NULL,
    equip_local     TEXT,
    equip_visitant  TEXT,
    p_match_local   INTEGER,
    p_match_visitant INTEGER,
    UNIQUE (edicio_id, jornada, grup_id, enc_id_extern, team_a_extern, team_b_extern)
);
CREATE INDEX IF NOT EXISTS ix_copa_enc_grup ON copa_encontres(edicio_id, jornada, grup_id);

CREATE TABLE IF NOT EXISTS copa_classificacio (
    edicio_id   INTEGER NOT NULL,
    jornada     INTEGER NOT NULL,
    grup_id     INTEGER NOT NULL,
    grup_nom    TEXT,
    posicio     INTEGER,
    equip       TEXT NOT NULL,
    punts       INTEGER,
    parcials    INTEGER,
    mitjana     REAL,
    PRIMARY KEY (edicio_id, jornada, grup_id, equip)
);

CREATE TABLE IF NOT EXISTS copa_partides (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    encontre_copa_id  INTEGER NOT NULL REFERENCES copa_encontres(id) ON DELETE CASCADE,
    ordre             INTEGER,
    local_nom         TEXT,
    local_caramboles  INTEGER,
    local_serie       INTEGER,
    visitant_nom      TEXT,
    visitant_caramboles INTEGER,
    visitant_serie    INTEGER,
    entrades          INTEGER,
    punts_local       INTEGER,
    punts_visitant    INTEGER
);
CREATE INDEX IF NOT EXISTS ix_copa_part_enc ON copa_partides(encontre_copa_id);

-- v7/v8: Fases de grups dels torneigs individuals (PRÈVIA, QUALIFICACIÓ...).
-- El portal NO publica classificacions amb punts per a aquestes fases: només
-- l'assignació de cada jugador al seu grup. La classificació rica (PJ, punts,
-- mitjanes...) només existeix a la final → torneig_participants. Aquí desem la
-- composició de grups de cada fase.
CREATE TABLE IF NOT EXISTS torneig_fases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    torneig_id      INTEGER NOT NULL REFERENCES torneigs_individuals(id) ON DELETE CASCADE,
    fase_id_extern  INTEGER NOT NULL,
    nom             TEXT,
    tipus           TEXT,                -- 'grups' | 'ko'
    ordre           INTEGER,
    UNIQUE (torneig_id, fase_id_extern)
);

CREATE TABLE IF NOT EXISTS torneig_fase_grups (
    fase_id      INTEGER NOT NULL REFERENCES torneig_fases(id) ON DELETE CASCADE,
    grup_nom     TEXT,
    jugador_nom  TEXT,
    ordre        INTEGER
);
CREATE INDEX IF NOT EXISTS ix_tfg_fase ON torneig_fase_grups(fase_id);

-- v9: Partides reals (resultats) dels campionats individuals, scrapejades de les
-- pàgines `/individuals/partidesgrups/...` i `/individuals/partideseliminatoria/...`
-- (i les variants històriques). NO porten data: la data ve de creuar-les amb les
-- partides del rànquing (taula `games`). `fase_id` és l'id extern de la pàgina del
-- portal. Poblada per scripts/ingest_open_games.py; consumida pel linker (linking.py)
-- per omplir games.torneig_id. Identitat lògica: (torneig, divisió, fase, jugadors,
-- caramboles, entrades) — no s'hi posa PRIMARY KEY perquè el portal pot repetir el
-- mateix enfrontament en fases diferents.
CREATE TABLE IF NOT EXISTS torneig_partides (
    torneig_id_extern  INTEGER,
    divisio_id_extern  INTEGER,
    fase_id            INTEGER,
    player1_nom        TEXT,
    caramboles1        INTEGER,
    serie1             INTEGER,
    punts1             INTEGER,
    player2_nom        TEXT,
    caramboles2        INTEGER,
    serie2             INTEGER,
    punts2             INTEGER,
    entrades           INTEGER
);
CREATE INDEX IF NOT EXISTS ix_torneig_partides_div
    ON torneig_partides(torneig_id_extern, divisio_id_extern);

-- v11: Partides individuals de lliga JUGADES (entrades>0) que encara NO consten al
-- rànquing oficial (partideshome/`games`). La ingesta de lliga normalment les salta
-- (espera que arribin via partideshome); aquí les desem perquè surtin com a PENDENTS
-- a la fitxa fins que la ingesta oficial les incorpora a `games`. publish_pending_games
-- les dedup per signatura contra `games`. Poblada per ingest_lliga_encontre (DELETE +
-- INSERT per encontre). NO té PK: el mateix enfrontament pot repetir-se.
CREATE TABLE IF NOT EXISTS lliga_pending_partides (
    encontre_lliga_id INTEGER NOT NULL REFERENCES encontres_lliga(id) ON DELETE CASCADE,
    modalitat_codi    INTEGER,
    competicio        TEXT,
    data              TEXT,
    player1_nom       TEXT,
    caramboles1       INTEGER,
    serie1            INTEGER,
    player2_nom       TEXT,
    caramboles2       INTEGER,
    serie2            INTEGER,
    entrades          INTEGER
);
CREATE INDEX IF NOT EXISTS ix_lliga_pending_enc
    ON lliga_pending_partides(encontre_lliga_id);
