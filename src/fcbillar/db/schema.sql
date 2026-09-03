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
    -- Quin endpoint va servir el rànquing. 'data'/'datahome' són del web
    -- antic (fins a l'agost de 2026); 'historial'/'llistat' són del nou.
    -- Els vells es conserven: diuen d'on va sortir cada fila i encara hi són.
    format_url      TEXT NOT NULL
        CHECK (format_url IN ('data', 'datahome', 'historial', 'llistat')),
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
    -- Opcionals: hi ha encontres del backfill històric dels quals no sabem els
    -- equips. NULL ho diu; un 0, que és el que s'hi posava, no és cap equip i
    -- els feia semblar partits d'un equip contra ell mateix.
    equip_local_id          INTEGER REFERENCES equips(id),
    equip_visitant_id       INTEGER REFERENCES equips(id),
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

-- v12: Calendari esportiu federatiu (PDF de la RFEB; la FCB quan el publiqui).
-- Una fila per cel·la de la graella del PDF: setmana × columna. La clau natural
-- (font, temporada, setmana, disciplina, ambit, grup, tipus) permet reingestar
-- revisions amb UPSERT i comparar-les. Vegeu fcbillar/calendari_fed.py.
CREATE TABLE IF NOT EXISTS calendari_events (
    font        TEXT NOT NULL,              -- 'RFEB' | 'FCB'
    temporada   TEXT NOT NULL,              -- '2026/2027'
    setmana     TEXT NOT NULL,              -- ISO, dilluns de la setmana
    disciplina  TEXT NOT NULL,              -- carambola | pool | snooker
    ambit       TEXT NOT NULL,              -- nacional | internacional | mixt | tot
    grup        TEXT NOT NULL DEFAULT '',   -- subgrup de modalitats ('' = cap)
    tipus       TEXT NOT NULL DEFAULT '',   -- equips | individual | '' (no aplica)
    data_inici  TEXT NOT NULL,
    data_fi     TEXT NOT NULL,
    titol       TEXT NOT NULL,
    seu         TEXT,
    dissabte    TEXT,                       -- què es juga el ds (patró LIGA NACIONAL)
    diumenge    TEXT,
    col_span    INTEGER NOT NULL DEFAULT 1, -- >1 = cel·la fusionada (NADAL, S. SANTA)
    raw         TEXT NOT NULL,              -- línies crues del PDF, per auditar
    PRIMARY KEY (font, temporada, setmana, disciplina, ambit, grup, tipus)
);
CREATE INDEX IF NOT EXISTS ix_calendari_events_setmana
    ON calendari_events(setmana);

-- Revisions del PDF: la RFEB en va publicant de noves («V.1 actualizado a …»)
-- sobre la mateixa URL. Es desa una fila per descàrrega amb contingut NOU (sha256
-- diferent), amb l'ETag per poder fer peticions condicionals i estalviar feina.
CREATE TABLE IF NOT EXISTS calendari_versions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    font          TEXT NOT NULL,
    temporada     TEXT NOT NULL,
    versio        TEXT,                     -- 'V.1' tal com ho escriu el PDF
    data_versio   TEXT,                     -- data del "actualizado a dd/mm/aaaa"
    sha256        TEXT NOT NULL,
    etag          TEXT,
    last_modified TEXT,
    url           TEXT,
    n_events      INTEGER NOT NULL DEFAULT 0,
    n_canvis      INTEGER NOT NULL DEFAULT 0,
    ingested_at   TEXT NOT NULL DEFAULT (datetime('now')),
    -- Es refresca a CADA comprovació, tingui canvis o no: és el que permet
    -- veure a la web que la revisió periòdica del PDF segueix corrent.
    last_checked_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (font, temporada, sha256)
);

-- Diferències respecte de la revisió anterior. És el que fa útil revisar el PDF
-- periòdicament: no només tenir-lo al dia, sinó poder veure QUÈ han mogut.
CREATE TABLE IF NOT EXISTS calendari_canvis (
    versio_id   INTEGER NOT NULL REFERENCES calendari_versions(id) ON DELETE CASCADE,
    tipus_canvi TEXT NOT NULL,              -- alta | baixa | modificacio
    setmana     TEXT NOT NULL,
    disciplina  TEXT NOT NULL,
    ambit       TEXT NOT NULL,
    grup        TEXT,
    tipus       TEXT,
    abans       TEXT,
    despres     TEXT
);
CREATE INDEX IF NOT EXISTS ix_calendari_canvis_versio
    ON calendari_canvis(versio_id);

-- A quina divisió juga cadascú el campionat individual, i amb quin club. Surt
-- del PDF de divisions que publica la federació abans de començar la temporada.
--
-- És la font oficial de qui juga on: fins ara els traspassos s'anotaven a mà a
-- `scripts/projeccio_lliga_2627.py`, i d'aquesta llista en surten tots els que
-- afecten jugadors inscrits a l'individual. No tots: qui no s'hi inscriu no surt
-- al PDF, i aquell traspàs se segueix sabent per una altra banda.
--
-- La clau és (temporada, jugador) perquè el PDF dona una sola divisió per
-- jugador i temporada. El nom va tal com l'escriu la federació, «COGNOMS, NOM»,
-- que és la manera com es lliga amb `players.nom`.
CREATE TABLE IF NOT EXISTS inscrits_individual (
    temporada   TEXT NOT NULL,
    jugador     TEXT NOT NULL,
    club        TEXT NOT NULL,              -- nom del cens, ja canonicalitzat
    divisio     TEXT NOT NULL,              -- 'Honor', '1ª'… '6ª'
    posicio     INTEGER NOT NULL,           -- ordre al rànquing de sortida
    mitjana     REAL NOT NULL,
    -- 0 = mitjana provisional: la federació encara la pot moure, i amb ella la
    -- divisió. Val més saber-ho que ensenyar-ho tot com si fos definitiu.
    definitiva  INTEGER NOT NULL,
    PRIMARY KEY (temporada, jugador)
);

-- El calendari sencer d'un grup de lliga, tal com el publica la federació en PDF.
--
-- No és la competició: és el que se'n sap ABANS que la competició existeixi. La
-- federació no publica els encontres al seu web fins que es juguen —un partit no
-- disputat no porta ni enllaç ni identificador—, o sigui que del setembre fins a
-- la primera jornada no hi ha res a `encontres_lliga`. El PDF, en canvi, ja diu
-- qui juga contra qui i quin dia.
--
-- Per això va a part i no a `encontres_lliga`: allò porta identificadors de la
-- federació i resultats, i això són noms d'equip i dates que encara poden
-- canviar. Quan la competició es publiqui, mana la competició.
--
-- La clau inclou els dos equips perquè una jornada té diversos encontres.
CREATE TABLE IF NOT EXISTS lliga_calendari (
    temporada  TEXT NOT NULL,              -- '2026/2027'
    divisio    TEXT NOT NULL,              -- '1a', '2a', '4a'
    grup       TEXT NOT NULL,              -- 'A', 'B', 'D'
    jornada    INTEGER NOT NULL,
    data       TEXT NOT NULL,              -- ISO
    local      TEXT NOT NULL,
    visitant   TEXT NOT NULL,
    PRIMARY KEY (temporada, divisio, grup, jornada, local, visitant)
);
CREATE INDEX IF NOT EXISTS ix_lliga_calendari_grup
    ON lliga_calendari(temporada, divisio, grup, jornada);
