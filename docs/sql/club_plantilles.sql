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
  player_fcb_id TEXT NOT NULL,
  jugador       TEXT NOT NULL,
  mitjana       DOUBLE PRECISION,
  motiu         TEXT NOT NULL,
  PRIMARY KEY (temporada, club, player_fcb_id)
);

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
