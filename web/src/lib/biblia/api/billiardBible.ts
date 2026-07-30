/**
 * Client de només lectura de l'API pública de billiard-bible.com.
 * Embolcalla les crides REST i RPC de Supabase que fa servir la seva web.
 */

import { BB_URL, BB_ANON_KEY, BB_MAX_ID } from './config';
import { bbADiamant, parseTraca, type Fotograma } from '$lib/biblia/billar/mapatge';
import type { Boles } from '$lib/biblia/billar/tipus';

type Fetch = typeof fetch;

function capsaleres(): Record<string, string> {
	return {
		apikey: BB_ANON_KEY,
		Authorization: `Bearer ${BB_ANON_KEY}`,
		'Content-Type': 'application/json'
	};
}

// ---------------------------------------------------------------------------
// Jugadors
// ---------------------------------------------------------------------------

export interface Jugador {
	id: number;
	nom: string;
	nomKo: string;
	nacionalitat: string;
	retratUrl: string;
	banderaUrl: string;
}

export async function fetchJugadors(fetch: Fetch): Promise<Jugador[]> {
	const url =
		`${BB_URL}/rest/v1/players` +
		`?select=id,name_en,name_kr,nationality,portrait_image_url,flag_image_url,order,has_shot_data` +
		`&has_shot_data=eq.1&order=name_en.asc`;
	const r = await fetch(url, { headers: capsaleres() });
	if (!r.ok) throw new Error(`players ${r.status}`);
	const files = (await r.json()) as Array<Record<string, unknown>>;
	return files.map((p) => ({
		id: p.id as number,
		nom: (p.name_en as string) ?? '',
		nomKo: (p.name_kr as string) ?? '',
		nacionalitat: (p.nationality as string) ?? '',
		retratUrl: (p.portrait_image_url as string) ?? '',
		banderaUrl: (p.flag_image_url as string) ?? ''
	}));
}

// ---------------------------------------------------------------------------
// Llista de tirades
// ---------------------------------------------------------------------------

export interface FiltresLlista {
	esAnalisi: boolean;
	/** id del jugador; -1 = tots. */
	jugador: number;
	/** índex de família (ball_choice); 0 = totes. */
	familia: number;
	posicio: boolean;
	defensa: boolean;
	evitarKiss: boolean;
	inici: number;
	mida: number;
}

export interface TiradaResum {
	id: number;
	jugadorId: number;
	familia: number;
	teAnalisi: boolean;
	teVideo: boolean;
	esPosicio: boolean;
	esDefensa: boolean;
	esEvitarKiss: boolean;
	esDificil: boolean;
	boles: Boles;
}

function bolesDesDeFila(f: Record<string, number>): Boles {
	return {
		b1: bbADiamant(f.white_ball_x, f.white_ball_y),
		b2: bbADiamant(f.yellow_ball_x, f.yellow_ball_y),
		b3: bbADiamant(f.red_ball_x, f.red_ball_y)
	};
}

function mapResum(f: Record<string, number>): TiradaResum {
	return {
		id: f.id,
		jugadorId: f.player,
		familia: f.ball_choice,
		teAnalisi: !!f.has_analysis_shot,
		teVideo: !!f.has_app_movie,
		esPosicio: !!f.is_position,
		esDefensa: !!f.is_defense,
		esEvitarKiss: !!f.is_avoid_kiss,
		esDificil: !!f.is_difficult,
		boles: bolesDesDeFila(f)
	};
}

export async function fetchLlistaTirades(
	fetch: Fetch,
	f: FiltresLlista
): Promise<{ total: number; tirades: TiradaResum[] }> {
	const cos = {
		p_user_id: null,
		p_has_analysis_shot: f.esAnalisi ? 1 : 0,
		p_player_id: f.jugador,
		p_ball_choice: f.familia,
		p_is_position: f.posicio ? 1 : 0,
		p_is_defense: f.defensa ? 1 : 0,
		p_is_avoid_kiss: f.evitarKiss ? 1 : 0,
		p_is_bookmark: 0,
		p_range_size: f.mida,
		p_range_start_index: f.inici,
		p_search_max_id: BB_MAX_ID,
		p_is_asc_order: 0
	};
	const r = await fetch(`${BB_URL}/rest/v1/rpc/fetch_shot_list_new`, {
		method: 'POST',
		headers: capsaleres(),
		body: JSON.stringify(cos)
	});
	if (!r.ok) throw new Error(`shot_list ${r.status}`);
	const d = (await r.json()) as { total_length: number; shot_list_rows: Record<string, number>[] | null };
	return {
		total: d.total_length ?? 0,
		tirades: (d.shot_list_rows ?? []).map(mapResum)
	};
}

/** Compta quantes tirades hi ha amb uns filtres, sense baixar-ne les files. */
export async function fetchComptador(fetch: Fetch, f: FiltresLlista): Promise<number> {
	const { total } = await fetchLlistaTirades(fetch, { ...f, inici: 0, mida: 1 });
	return total;
}

// ---------------------------------------------------------------------------
// Detall d'una tirada
// ---------------------------------------------------------------------------

export interface Video {
	id: string;
	inici: number | null;
	fi: number | null;
}

export interface DetallTirada {
	id: number;
	jugadorId: number;
	familia: number;
	teAnalisi: boolean;
	esPosicio: boolean;
	esDefensa: boolean;
	esEvitarKiss: boolean;
	esDificil: boolean;
	boles: Boles;
	/** Pistes d'animació (buides per als tirs pro). */
	tracaBlanca: Fotograma[];
	tracaGroga: Fotograma[];
	tracaVermella: Fotograma[];
	video: Video | null;
	puntContacte: string;
	gruix: number;
	velocitat: number;
	descripcio: string;
	consell: string;
	prevId: number | null;
	nextId: number | null;
}

/** Parseja "youtube_id" tipus "EH7pB0y18Wk?t=539&559" en id + inici/fi. */
function parseVideo(raw: string | null | undefined): Video | null {
	if (!raw) return null;
	const [id, query] = raw.split('?');
	if (!id) return null;
	let inici: number | null = null;
	let fi: number | null = null;
	if (query) {
		const m = query.match(/t=(\d+)(?:&(\d+))?/);
		if (m) {
			inici = Number(m[1]);
			fi = m[2] ? Number(m[2]) : null;
		}
	}
	return { id, inici, fi };
}

/** Primer punt (posició inicial) d'una pista, com a bola. */
function inicial(traca: Fotograma[], fallback: [number, number]): [number, number] {
	return traca.length ? [traca[0].x, traca[0].y] : fallback;
}

/** Converteix els "\n" literals del text original en salts de línia reals. */
function netejaText(s: string | null | undefined): string {
	return (s ?? '').replace(/\\n/g, '\n').trim();
}

export async function fetchDetall(
	fetch: Fetch,
	id: number,
	esAnalisi: boolean
): Promise<DetallTirada> {
	const r = await fetch(`${BB_URL}/rest/v1/rpc/fetch_shot_detail`, {
		method: 'POST',
		headers: capsaleres(),
		body: JSON.stringify({ p_shot_id: id, p_user_id: null, p_is_analysis_shot: esAnalisi })
	});
	if (!r.ok) throw new Error(`shot_detail ${r.status}`);
	const d = (await r.json()) as Record<string, unknown>;

	const tb = parseTraca(d.white_ball_positions as string);
	const tg = parseTraca(d.yellow_ball_positions as string);
	const tv = parseTraca(d.red_ball_positions as string);

	// Posició inicial: primer fotograma de la pista, o el camp *_positions "rot|x|y".
	const iniPunt = (s: string | undefined, fb: [number, number]): [number, number] => {
		if (!s) return fb;
		const p = s.split('|').map(Number);
		if (p.length >= 3) return bbADiamant(p[1], p[2]);
		return fb;
	};

	const boles: Boles = {
		b1: inicial(tb, iniPunt(d.white_ball_positions as string, [1, 1])),
		b2: inicial(tg, iniPunt(d.yellow_ball_positions as string, [4, 1])),
		b3: inicial(tv, iniPunt(d.red_ball_positions as string, [7, 3]))
	};

	return {
		id: d.shot_id as number,
		jugadorId: d.player as number,
		familia: (d.ball_choice as number) ?? 0,
		teAnalisi: !!(d.has_analysis_shot as number),
		esPosicio: !!(d.is_position as number),
		esDefensa: !!(d.is_defense as number),
		esEvitarKiss: !!(d.is_avoid_kiss as number),
		esDificil: !!(d.is_difficult as number),
		boles,
		tracaBlanca: tb,
		tracaGroga: tg,
		tracaVermella: tv,
		video: parseVideo(d.youtube_id as string),
		puntContacte: (d.ball_contract_point as string) ?? '',
		gruix: (d.ball_thickness as number) ?? 0,
		velocitat: (d.rail_speed as number) ?? 0,
		descripcio: netejaText(d.description_arrangement as string),
		consell: netejaText(d.description_tip as string),
		prevId: (d.prev_shot_id as number) ?? null,
		nextId: (d.next_shot_id as number) ?? null
	};
}
