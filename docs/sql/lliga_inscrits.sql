-- De qui està fet cada club a la lliga, per a la base del núvol (Neon).
--
-- Des del setembre de 2026 la federació publica els jugadors que cada club
-- inscriu a cada lliga, amb la mitjana de cadascun i una etiqueta per als
-- fitxatges (`lligues/participants/{lliga}/{club}`). És la font OFICIAL del que
-- la seva germana `club_plantilles` només estima a partir de qui ha jugat.
--
-- Per què la vol el web: la mitjana d'aquesta pàgina és la que la federació fa
-- servir per ordenar els jugadors d'un club a la lliga, i hi és per a gent que
-- no surt al rànquing general —qui s'acaba de federar, o qui la federació encara
-- no hi ha tornat a entrar. Sense això, aquells socis surten amb 0,000 i van
-- tots al final de la graella de participació, barrejats amb els qui de debò no
-- tenen mitjana.
--
-- Un fitxatge hi surt DUES vegades: al seu club sense marca i al club que se
-- l'endú amb `fitxatge = true`. No és cap error de la font —comprovat contra el
-- llistat de divisions de l'individual 26/27, 349 coincidències de 349— i per
-- això el club va a la clau: la mateixa persona hi és dos cops i les dues files
-- volen dir coses diferents.
--
-- Mateix patró que les taules germanes: esquema `fcbillar`, RLS amb lectura
-- pública i escriptura només per al rol de servei. És dada federativa publicada,
-- no dada de soci.

CREATE TABLE IF NOT EXISTS fcbillar.lliga_inscrits (
  temporada      TEXT    NOT NULL,          -- '2026/2027'
  lliga_id       INTEGER NOT NULL,          -- id de la federació (38 = 3B 26-27)
  lliga          TEXT    NOT NULL,          -- 'Lliga Catalana Tres Bandes'
  -- 'Tres bandes', '4 Modalitats'. Hi és perquè les mitjanes de dues lligues NO
  -- es poden comparar: cadascuna és de la seva modalitat. Qui llegeixi aquesta
  -- taula per ordenar jugadors ha de filtrar per temporada I modalitat.
  modalitat      TEXT    NOT NULL DEFAULT '',
  club           TEXT    NOT NULL,          -- nom del cens, ja canonicalitzat
  -- El mateix identificador que porta la classificació, que és el que hi lliga.
  -- El NOM no serveix per creuar-les: ja va fallar al rànquing de jugadors.
  club_fcb_id   TEXT,
  club_id_extern INTEGER NOT NULL,
  jugador        TEXT    NOT NULL,          -- 'COGNOMS, NOM', com l'escriu la federació
  -- La del rànquing vigent de la modalitat. 0 per a qui no hi surt: la federació
  -- hi posa un zero, no un buit, i el zero l'envia a l'últim lloc del seu club.
  mitjana        DOUBLE PRECISION,
  fitxatge       BOOLEAN NOT NULL DEFAULT FALSE,
  posicio        INTEGER NOT NULL,          -- ordre a la llista del club
  PRIMARY KEY (lliga_id, club, jugador)
);

-- Per si la taula ja s'havia creat sense la columna.
ALTER TABLE fcbillar.lliga_inscrits
  ADD COLUMN IF NOT EXISTS modalitat TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS ix_lliga_inscrits_club
  ON fcbillar.lliga_inscrits (temporada, club);
CREATE INDEX IF NOT EXISTS ix_lliga_inscrits_jugador
  ON fcbillar.lliga_inscrits (temporada, jugador);
-- La lectura que fa el web: les mitjanes d'una temporada i una modalitat.
CREATE INDEX IF NOT EXISTS ix_lliga_inscrits_temporada_modalitat
  ON fcbillar.lliga_inscrits (temporada, modalitat);

ALTER TABLE fcbillar.lliga_inscrits ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "read lliga_inscrits" ON fcbillar.lliga_inscrits;
CREATE POLICY "read lliga_inscrits" ON fcbillar.lliga_inscrits
  FOR SELECT TO anon, authenticated USING (true);

GRANT SELECT ON fcbillar.lliga_inscrits TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON fcbillar.lliga_inscrits TO service_role;

NOTIFY pgrst, 'reload schema';

ALTER TABLE fcbillar.lliga_inscrits ADD COLUMN IF NOT EXISTS club_fcb_id TEXT;
