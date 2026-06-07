// Client Supabase fixat al schema `fcbillar` (només lectura via anon + RLS).
// Les variables s'inlinen en build (Vite) → al .env.local en dev i a les env
// vars de Vercel en producció.
import { createClient } from '@supabase/supabase-js';
import { PUBLIC_SUPABASE_ANON_KEY, PUBLIC_SUPABASE_URL } from '$env/static/public';

if (!PUBLIC_SUPABASE_URL) throw new Error('Falta PUBLIC_SUPABASE_URL');
if (!PUBLIC_SUPABASE_ANON_KEY) throw new Error('Falta PUBLIC_SUPABASE_ANON_KEY');

export const supabase = createClient(PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY, {
	db: { schema: 'fcbillar' },
	auth: { persistSession: false }
});

export interface Modalitat {
	codi_fcb: number;
	nom: string;
}
export interface Snapshot {
	num_seq: number;
	any_pub: number | null;
	mes_pub: number | null;
}
export interface RankingRow {
	posicio: number | null;
	player_fcb_id: string;
	jugador: string;
	club: string | null;
	mitjana_general: number | null;
	partides: number | null;
}

export interface GameRow {
	id: string;
	data_partida: string | null;
	modalitat_codi: number | null;
	competicio: string | null;
	player1_fcb_id: string | null;
	player1_nom: string | null;
	caramboles1: number | null;
	serie_max1: number | null;
	player2_fcb_id: string | null;
	player2_nom: string | null;
	caramboles2: number | null;
	serie_max2: number | null;
	entrades: number | null;
	guanyador_fcb_id: string | null;
}

export interface LligaGroup {
	lliga_id: number;
	divisio_id: number;
	grup_id: number;
	divisio_nom: string | null;
	grup_nom: string | null;
}
export interface StandingRow {
	divisio_id: number;
	grup_id: number;
	posicio: number | null;
	equip: string;
	club_fcb_id: string | null;
	pj: number | null;
	g: number | null;
	e: number | null;
	p: number | null;
	punts: number | null;
	pf: number | null;
	pc: number | null;
}

export interface CopaGroup {
	edicio_id: number;
	jornada: number;
	grup_id: number;
	grup_nom: string | null;
	jornada_nom: string | null;
	ordre: number | null;
}
export interface CopaStanding {
	edicio_id: number;
	jornada: number;
	grup_id: number;
	posicio: number | null;
	equip: string;
	punts: number | null;
	parcials: number | null;
	mitjana: number | null;
}

export interface Open {
	open_id: number;
	nom: string;
	temporada_id: number | null;
}
export interface OpenClassification {
	open_id: number;
	posicio: number | null;
	player_fcb_id: string | null;
	jugador: string | null;
	club: string | null;
	partides: number | null;
	punts: number | null;
	caramboles: number | null;
	entrades: number | null;
	mitjana_general: number | null;
	mitjana_particular: number | null;
	serie_max: number | null;
}
