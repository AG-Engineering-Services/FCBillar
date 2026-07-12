// Índex de "qualitat" de club a partir del nivell dels jugadors que el conformen.
//
// NIVELL d'un jugador = percentil de la seva posició dins la SEVA modalitat
// (100 = primer del rànquing, 0 = últim). El percentil fa comparables jugadors
// de modalitats amb escales de mitjana molt diferents (3 bandes ~0,5 · lliure/
// quadre molt més alt) i, com que la posició ja ordena els definitius davant dels
// no-definitius, aquests últims queden amb nivell baix sense càlcul extra.
//
// A partir del nivell, cada club té DOS eixos independents (no un sol número):
//   • POTÈNCIA    — mitjana dels K millors nivells (força de l'equip que juga).
//   • PROFUNDITAT — "massa" de jugadors per damunt de la mediana del camp
//                   (quantitat de qualitat, no només l'elit).
// El CQI combinable (w·Potència + (1−w)·Profunditat) és secundari: el mapa 2D
// Profunditat×Potència és més honest perquè un club pot ser elit-però-prim o
// profund-però-sense-estrelles i es veu d'un cop d'ull.

export interface RankEntry {
	player_fcb_id: string;
	jugador: string;
	club: string | null; // nom canònic (clubs.nom) o null si el jugador no en té
	posicio: number;
	mitjana_general: number | null;
}

export interface PlayerNivell {
	fcb_id: string;
	nom: string;
	club: string;
	nivell: number; // 0..100
	posicio: number; // posició dins la modalitat de referència del nivell
	mitjana: number | null;
}

/** Percentil 0..100 d'una posició dins d'un camp de N jugadors (1r→100, últim→0). */
export function nivellFromPos(posicio: number, N: number): number {
	if (N <= 1) return 100;
	return Math.max(0, Math.min(100, 100 * (1 - (posicio - 1) / (N - 1))));
}

/** Entrades d'UNA modalitat → jugadors amb nivell. Els sense club s'ometen. */
export function playersWithNivell(entries: RankEntry[]): PlayerNivell[] {
	const N = entries.length;
	const out: PlayerNivell[] = [];
	for (const e of entries) {
		if (!e.club) continue;
		out.push({
			fcb_id: e.player_fcb_id,
			nom: e.jugador,
			club: e.club,
			nivell: nivellFromPos(e.posicio, N),
			posicio: e.posicio,
			mitjana: e.mitjana_general
		});
	}
	return out;
}

/** Combina modalitats: per cada jugador es queda el MILLOR nivell entre les
 *  modalitats on apareix (la seva disciplina més forta). */
export function bestNivellAcrossModalities(perMod: RankEntry[][]): PlayerNivell[] {
	const best = new Map<string, PlayerNivell>();
	for (const entries of perMod) {
		for (const p of playersWithNivell(entries)) {
			const prev = best.get(p.fcb_id);
			if (!prev || p.nivell > prev.nivell) best.set(p.fcb_id, p);
		}
	}
	return [...best.values()];
}

export interface ClubIndex {
	club: string;
	players: PlayerNivell[]; // ordenats per nivell desc
	n: number;
	potencia: number; // mitjana dels K millors nivells (0..100)
	depthMass: number; // Σ max(0, nivell−50)/50 ≈ jugadors efectius per damunt de la mediana
	depthCount: number; // jugadors amb nivell ≥ 50
	best: PlayerNivell;
	depthScore: number; // Profunditat escalada a 0..100 (relativa al conjunt) — l'omple rankClubs
	cqi: number; // w·Potència + (1−w)·Profunditat — l'omple rankClubs
}

/** Agrupa jugadors per club i calcula Potència (top-K) i Profunditat. */
export function buildClubIndexes(players: PlayerNivell[], K: number): ClubIndex[] {
	const byClub = new Map<string, PlayerNivell[]>();
	for (const p of players) {
		const arr = byClub.get(p.club);
		if (arr) arr.push(p);
		else byClub.set(p.club, [p]);
	}
	const res: ClubIndex[] = [];
	for (const [club, ps] of byClub) {
		ps.sort((a, b) => b.nivell - a.nivell);
		const topK = ps.slice(0, Math.max(1, K));
		const potencia = topK.reduce((s, p) => s + p.nivell, 0) / topK.length;
		const depthMass = ps.reduce((s, p) => s + Math.max(0, p.nivell - 50) / 50, 0);
		const depthCount = ps.filter((p) => p.nivell >= 50).length;
		res.push({
			club,
			players: ps,
			n: ps.length,
			potencia,
			depthMass,
			depthCount,
			best: ps[0],
			depthScore: 0,
			cqi: 0
		});
	}
	return res;
}

/** Escala Profunditat a 0..100 (relativa al club amb més massa del conjunt) i
 *  calcula el CQI = w·Potència + (1−w)·Profunditat. Retorna ordenat per CQI. */
export function rankClubs(idx: ClubIndex[], w: number): ClubIndex[] {
	const maxMass = Math.max(1e-9, ...idx.map((c) => c.depthMass));
	for (const c of idx) {
		c.depthScore = 100 * (c.depthMass / maxMass);
		c.cqi = w * c.potencia + (1 - w) * c.depthScore;
	}
	return [...idx].sort((a, b) => b.cqi - a.cqi || b.potencia - a.potencia);
}
