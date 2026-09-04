-- De qui està fet cada club, estimat, per a la base del núvol (Neon).
--
-- La federació no publica plantilles: publica llicències, i aquella llista
-- inclou gent que fa anys que no juga. Aquí hi entra qui ha jugat la lliga
-- aquesta temporada o l'anterior, o qui consta al llistat de divisions del
-- campionat individual d'aquesta. És una ESTIMACIÓ i a la interfície va marcada
-- com a tal: ningú no ha de creure's que és una alineació oficial.
--
-- Mateix patró que les taules germanes: esquema `fcbillar`, RLS amb lectura
-- pública i escriptura només per al rol de servei.

CREATE TABLE IF NOT EXISTS fcbillar.club_plantilles (
  temporada     TEXT NOT NULL,
  club          TEXT NOT NULL,
  -- Buit per a qui s'acaba de federar: surt al llistat de divisions i encara no
  -- ha jugat res, o sigui que no té fitxa nostra. La clau és el nom.
  player_fcb_id TEXT,
  jugador       TEXT NOT NULL,
  mitjana       DOUBLE PRECISION,
  motiu         TEXT NOT NULL,
  PRIMARY KEY (temporada, club, jugador)
);

-- Per a la taula que ja existia amb `player_fcb_id` obligatori i a la clau.
-- Es fa en dos passos i no amb un DROP: la taula ja té dades publicades i
-- buidar-la deixaria les plantilles fora de línia fins a la propera publicació.
-- La clau primera primer: mentre la columna hi sigui, Postgres no la deixa
-- ser nul·la ("column is in a primary key").
ALTER TABLE fcbillar.club_plantilles DROP CONSTRAINT IF EXISTS club_plantilles_pkey;
ALTER TABLE fcbillar.club_plantilles ALTER COLUMN player_fcb_id DROP NOT NULL;
ALTER TABLE fcbillar.club_plantilles
  ADD CONSTRAINT club_plantilles_pkey PRIMARY KEY (temporada, club, jugador);

CREATE INDEX IF NOT EXISTS ix_club_plantilles_club
  ON fcbillar.club_plantilles (temporada, club);

ALTER TABLE fcbillar.club_plantilles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "read club_plantilles" ON fcbillar.club_plantilles;
CREATE POLICY "read club_plantilles" ON fcbillar.club_plantilles
  FOR SELECT TO anon, authenticated USING (true);

GRANT SELECT ON fcbillar.club_plantilles TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON fcbillar.club_plantilles TO service_role;

NOTIFY pgrst, 'reload schema';
