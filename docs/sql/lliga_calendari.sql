-- El calendari sencer de cada grup de lliga, per a la base del núvol (Neon).
--
-- Per què fa falta: la federació no publica els encontres al seu web fins que es
-- juguen —un partit no disputat no porta ni enllaç ni identificador—, o sigui
-- que del setembre fins a la primera jornada no hi ha competició a ensenyar. El
-- PDF del calendari, en canvi, ja diu qui hi ha a cada grup, contra qui es juga
-- i quin dia. Això permet ensenyar la temporada que comença amb la mateixa
-- forma que una de jugada, en comptes d'una pàgina buida.
--
-- No substitueix `lliga_encontres`: allò porta els identificadors de la
-- federació i els resultats. Quan la competició es publiqui, mana la competició.
--
-- Segueix el patró de `calendari_events`, que és la seva germana: esquema
-- `fcbillar`, RLS amb lectura pública i escriptura només per al rol de servei.
-- És calendari federatiu, no dada de soci.

CREATE TABLE IF NOT EXISTS fcbillar.lliga_calendari (
  temporada TEXT    NOT NULL,   -- '2026/2027'
  divisio   TEXT    NOT NULL,   -- '1a', '2a', '4a'
  grup      TEXT    NOT NULL,   -- 'A', 'B', 'D'
  jornada   INTEGER NOT NULL,
  data      DATE    NOT NULL,
  local     TEXT    NOT NULL,
  visitant  TEXT    NOT NULL,
  -- Els dos equips van a la clau perquè una jornada té diversos encontres.
  PRIMARY KEY (temporada, divisio, grup, jornada, local, visitant)
);

CREATE INDEX IF NOT EXISTS ix_lliga_calendari_grup
  ON fcbillar.lliga_calendari (temporada, divisio, grup, jornada);

ALTER TABLE fcbillar.lliga_calendari ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "read lliga_calendari" ON fcbillar.lliga_calendari;
CREATE POLICY "read lliga_calendari" ON fcbillar.lliga_calendari
  FOR SELECT TO anon, authenticated USING (true);

GRANT SELECT ON fcbillar.lliga_calendari TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON fcbillar.lliga_calendari TO service_role;

-- La Data API es guarda l'esquema en memòria: sense això seguiria dient que la
-- taula no existeix.
NOTIFY pgrst, 'reload schema';
