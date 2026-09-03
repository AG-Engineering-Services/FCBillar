-- El calendari sencer de cada grup de lliga, per a la base del núvol (Neon).
--
-- Amb PostgREST no es pot fer cap DDL, o sigui que aquesta taula l'ha de crear
-- l'administrador. Mentre no existeixi, `publish_calendari` avisa i segueix: la
-- resta del calendari es publica igual.
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

CREATE TABLE IF NOT EXISTS lliga_calendari (
  temporada TEXT    NOT NULL,   -- '2026/2027'
  divisio   TEXT    NOT NULL,   -- '1a', '2a', '4a'
  grup      TEXT    NOT NULL,   -- 'A', 'B', 'D'
  jornada   INTEGER NOT NULL,
  data      DATE    NOT NULL,
  local     TEXT    NOT NULL,
  visitant  TEXT    NOT NULL,
  PRIMARY KEY (temporada, divisio, grup, jornada, local, visitant)
);

CREATE INDEX IF NOT EXISTS ix_lliga_calendari_grup
  ON lliga_calendari (temporada, divisio, grup, jornada);

-- Lectura pública: és calendari federatiu, no dada de soci. Mateix criteri que
-- `calendari_events`.
ALTER TABLE lliga_calendari ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS lliga_calendari_public_read ON lliga_calendari;
CREATE POLICY lliga_calendari_public_read ON lliga_calendari FOR SELECT USING (true);
GRANT SELECT ON lliga_calendari TO anon, authenticated;

NOTIFY pgrst, 'reload schema';
