-- Els inscrits al campionat individual, per a la base del núvol (Neon).
--
-- Del PDF de divisions que publica la federació abans de començar la temporada.
-- És l'única font de mitjana per a qui encara no ha jugat mai: al rànquing
-- general no hi és -no s'hi entra fins que es juga- però aquí sí, amb la que la
-- federació li assigna per repartir-lo per divisions.
--
-- `definitiva` a false vol dir que la federació encara la pot moure, i amb ella
-- la divisió.

CREATE TABLE IF NOT EXISTS fcbillar.inscrits_individual (
  temporada  TEXT    NOT NULL,
  jugador    TEXT    NOT NULL,
  club       TEXT    NOT NULL,
  divisio    TEXT    NOT NULL,
  posicio    INTEGER NOT NULL,
  mitjana    DOUBLE PRECISION NOT NULL,
  definitiva BOOLEAN NOT NULL,
  PRIMARY KEY (temporada, jugador)
);

ALTER TABLE fcbillar.inscrits_individual ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "read inscrits_individual" ON fcbillar.inscrits_individual;
CREATE POLICY "read inscrits_individual" ON fcbillar.inscrits_individual
  FOR SELECT TO anon, authenticated USING (true);

GRANT SELECT ON fcbillar.inscrits_individual TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON fcbillar.inscrits_individual TO service_role;

NOTIFY pgrst, 'reload schema';
