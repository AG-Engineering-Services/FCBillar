-- Fix: les taules de lliga del schema `fcb_opens` (league_divisions, league_groups,
-- league_encontres) es van crear SENSE els GRANTs que tenen la resta de taules del
-- schema. Per això `fcb_opens supabase-sync` (que escriu amb la service_role) petava
-- amb "permission denied for table league_divisions" (SQLSTATE 42501), fallant el
-- pas 7 de la reingesta setmanal.
--
-- La RLS ja era correcta (cada taula té la policy "Public read" SELECT per a
-- anon/authenticated, qual=true) — l'únic que faltava eren els privilegis de taula.
-- Aquesta migració els iguala a la resta de taules de lliga (league_jornades,
-- league_partides, leagues, ...).

grant select
    on fcb_opens.league_divisions, fcb_opens.league_groups, fcb_opens.league_encontres
    to anon, authenticated;

grant all privileges
    on fcb_opens.league_divisions, fcb_opens.league_groups, fcb_opens.league_encontres
    to service_role;
