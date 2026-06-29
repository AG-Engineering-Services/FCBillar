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

// Estat de l'última reingesta al núvol (taula fcbillar.cloud_status, una sola fila).
// L'escriu el workflow reingest.yml via `fcbillar state report`. El PWA la llegeix
// per avisar l'admin quan cal re-login al PC (session_ok=false).
export interface CloudStatus {
	session_ok: boolean;
	last_run: string | null;
	last_error: string | null;
	n_ok: number | null;
	n_fail: number | null;
	updated_at: string | null;
}

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

// Projecció del proper rànquing (taula fcbillar.ranking_provisional). Es publica
// quan hi ha partides de competicions en curs encara no al rànquing oficial.
export interface ProvisionalRow {
	player_fcb_id: string;
	posicio_oficial: number | null;
	mitjana_oficial: number | null;
	posicio_provisional: number | null;
	mitjana_provisional: number | null;
	partides_post: number;
	// Desglossament de la finestra projectada (només per als qui s'han mogut).
	proj_won?: number | null;
	proj_lost?: number | null;
	proj_tie?: number | null;
	window_game_ids?: string[] | null; // IDs de `games` de la finestra PROJECTADA
	current_game_ids?: string[] | null; // IDs de `games` del rànquing OFICIAL vigent
}

// Partides jugades en competicions en curs encara NO al rànquing oficial
// (taula fcbillar.pending_games). Una fila per jugador i partida.
export interface PendingGameRow {
	modalitat_codi: number;
	competicio: string | null;
	font: string;
	opponent_nom: string | null;
	caramboles: number | null;
	caramboles_opp: number | null;
	entrades: number | null;
	serie: number | null;
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
	/** Punts restats per sanció federativa (> 0). null = sense sanció. */
	penalitzacio?: number | null;
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

export interface PlayerRankRow {
	divisio_id?: number;
	jornada?: number;
	grup_id: number;
	posicio: number | null;
	player_fcb_id: string;
	jugador: string | null;
	club: string | null;
	partides: number | null;
	punts: number | null;
	mitjana: number | null;
}

export interface Open {
	open_id: number;
	nom: string;
	tipus: 'open' | 'campionat' | null;
	temporada_id: number | null;
	temporada?: string | null;
}

// Classificació de tipus de torneig coherent entre temporades (mirall de
// fcbillar.torneig_naming.torneig_tipus). Trofeu amb nom propi → 'open'; només
// modalitat+divisió o CAMPIONAT/CATALUNYA → 'campionat'. Independent de si el nom
// porta literalment 'OPEN' (arregla Memorial Jaume Arnau, etc.). S'usa com a
// fallback quan el camp `tipus` publicat encara és null.
const OPEN_MARKERS = ['OPEN', 'MEMORIAL', 'TROFEU', 'CIUTAT', 'GRAN PREMI', 'CRITERIUM'];
export function torneigTipus(nom: string): 'open' | 'campionat' {
	const u = nom.normalize('NFD').replace(/\p{Diacritic}/gu, '').toUpperCase();
	if (u.includes('CAMPIONAT') || u.includes('CATALUNYA')) return 'campionat';
	if (OPEN_MARKERS.some((m) => u.includes(m))) return 'open';
	return 'campionat';
}
export const tipusOf = (o: Open): 'open' | 'campionat' => o.tipus ?? torneigTipus(o.nom);
// ---------------------------------------------------------------------------
// Opens EN DIRECTE (taula fcbillar.open_live, una fila per Open en curs).
// `payload_json` és l'estat complet raspat de la federació (mateixa forma que
// LiveOpenResponse del backend). El publisher és `fcbillar publish-live-opens`.
// ---------------------------------------------------------------------------
export interface OpenLiveStanding {
	player_name: string;
	club: string;
	punts: number;
	mitjana: number;
	pj?: number;
	caramboles?: number;
	entrades?: number;
}
export interface OpenLiveMatch {
	player_a: string;
	player_b: string;
	punts_a: number;
	punts_b: number;
	caramboles_a: number;
	caramboles_b: number;
	serie_major_a: number;
	serie_major_b: number;
	entrades: number | null;
	arbitre: string | null;
	observations?: string | null;
	is_played: boolean;
}
export interface OpenLiveGroup {
	label: string;
	url: string;
	venue: string | null;
	standings: OpenLiveStanding[];
	matches: OpenLiveMatch[];
	n_matches_played: number;
	n_matches_total: number;
}
export interface OpenLiveProvQual {
	group_label: string;
	position_in_group: number;
	player_name: string;
	club: string;
	punts: number;
	mitjana: number;
	serie_major: number;
	pj?: number;
	caramboles?: number;
	entrades?: number;
}
export interface OpenLivePhase {
	label: string;
	kind: 'group' | 'ko';
	url: string;
	groups: OpenLiveGroup[];
	ko_matches: OpenLiveMatch[];
	is_active: boolean;
	provisional_qualifiers: OpenLiveProvQual[];
	provisional_matches: OpenLiveMatch[];
	provisional_players: { name: string; club: string; mitjana: number; serie_major: number; source: string }[];
}
export interface OpenLiveClassRow {
	position: number;
	player_name: string;
	club: string;
	round_label: string;
	mitjana: number;
	serie_major: number;
	open_points: number;
	is_provisional_position: boolean;
	rank3b?: number; // posició al rànquing de 3 bandes (per mostrar entre parèntesi)
	prize?: string; // premi especial per banda de rànquing ("Millor 61-180" / "Millor 181+")
}
export interface OpenLivePayload {
	division_id: number;
	name: string;
	phase_id: number | null;
	phases: OpenLivePhase[];
	classification: OpenLiveClassRow[];
	classification_is_provisional: boolean;
	fetched_at: string;
	player_ids?: Record<string, string>;
	// num_seq del rànquing 3B amb què s'han calculat rank3b/prize (el de la
	// convocatòria si està fixat; si no, el darrer). El selector hi ancora el valor per defecte.
	prize_num_seq?: number;
}
export interface OpenLiveRow {
	fcb_division_id: number;
	name: string;
	modality: string | null;
	payload_json: OpenLivePayload;
	captured_at: string;
	updated_at: string;
}

// Marcador EN VIU d'una partida (OCR de la retransmissió de YouTube).
// Taula fcbillar.open_live_scores; el publica el worker de Multiview.
export interface OpenLiveScore {
	video_id: string;
	fcb_division_id: number;
	club: string | null;
	title: string | null;
	phase: string | null;
	group_label: string | null;
	player_a: string | null;
	player_b: string | null;
	car_a: number | null;
	car_b: number | null;
	entrades: number | null;
	finished: boolean | null;
	captured_at: string;
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
