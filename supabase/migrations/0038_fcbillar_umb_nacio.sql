-- El país de cada costat d'una partida de la UMB. Als mundials per equips nacionals
-- la partida és d'un jugador dins d'un encontre entre seleccions.
alter table fcbillar.umb_partides add column if not exists nacio_a text;
alter table fcbillar.umb_partides add column if not exists nacio_b text;

notify pgrst, 'reload schema';
