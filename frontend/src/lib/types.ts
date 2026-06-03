// Mirall TypeScript dels dataclasses del backend (api/app.py + DataSource).

export interface Counts {
	clubs: number;
	players: number;
	rankings: number;
	games: number;
	encontres_lliga: number;
	temporades: number;
}

export interface Modalitat {
	codi_fcb: number;
	nom: string;
}

export interface RankingEntry {
	modalitat: string;
	posicio: number | null;
	nom: string;
	fcb_id: string;
	mitjana: number | null;
	mitjana_contraris: number | null;
	caramboles: number | null;
	entrades: number | null;
	punts: number | null;
	punts_totals: number | null;
	definitiva: boolean;
}

export interface PlayerKpi {
	fcb_id: string;
	nom: string;
	club: string | null;
	num_partides: number;
	seguiment: boolean;
}

export interface GameRow {
	data: string;
	modalitat: string;
	competicio: string | null;
	local: string;
	cara1: number | null;
	visitant: string;
	cara2: number | null;
	entrades: number | null;
	arbitre: string | null;
	club_local: string | null;
	club_visitant: string | null;
	computa?: boolean;
	serie1?: number | null;
	serie2?: number | null;
}

export interface ClubKpi {
	fcb_id: string;
	nom: string;
	num_jugadors: number;
	num_equips: number;
	num_partides: number;
}

export interface StandingRow {
	posicio: number;
	equip: string;
	club_fcb_id: string;
	pj: number;
	g: number;
	e: number;
	p: number;
	punts: number;
	parcials_favor: number;
	parcials_contra: number;
}

export interface TorneigRow {
	id: number;
	nom: string;
	temporada: string | null;
	num_participants: number;
}

export interface VirtualClub {
	id: number;
	nom: string;
	descripcio: string | null;
	num_membres: number;
}

export interface PlayerSummary {
	fcb_id: string;
	nom: string;
	total: number;
	guanyades: number;
	perdudes: number;
	empats: number;
	car_a_favor: number;
	car_en_contra: number;
	entrades_total: number;
	serie_max: number | null;
}

export interface OrderEvolutionRow {
	player: string;
	fcb_id: string;
	posicions: (number | null)[];
	ordre_intern: (number | null)[];
	mitjanes: (number | null)[];
	out_of_club?: boolean[];
}

export interface OrderEvolution {
	num_seqs: number[];
	rows: OrderEvolutionRow[];
}
