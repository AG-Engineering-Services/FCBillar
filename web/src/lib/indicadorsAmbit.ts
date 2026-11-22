// Indicadors de la fitxa (Històric, Temporada actual, Temporada anterior) per a
// Espanya i Internacional, amb les mateixes xifres que ensenya Catalunya però
// calculats només amb les dades de cada àmbit.

import type { GameRow } from './db';
import { disciplinaDePartida, resultatUmb, textSets, type UmbProva } from './internacional';
import {
	nomProva,
	resultatPartida,
	resultatRfeb,
	type NacionalPartidaRow,
	type RfebIndividualRow,
	type RfebPartidaRow
} from './nacional';

/** Una partida, o el total d'un campionat, amb el que aporta als indicadors. */
export interface Aportacio {
	/** Any en què comença la temporada (2025 per a 2025/26), o null si no se sap. */
	temporada: number | null;
	modalitat: string;
	/** Partides jugades: 1 per partida, `jugades` per a un campionat, 0 si només en sabem la mitjana. */
	n: number;
	g: number;
	e: number;
	p: number;
	car: number | null;
	ent: number | null;
	serie: number | null;
	/** Cert si és una partida concreta: només aquestes poden ser la millor mitjana. */
	partida: boolean;
}

export interface Indicadors {
	n: number;
	w: number;
	t: number;
	l: number;
	mitjana: number;
	sm: number | null;
	pct: number;
	best: number | null;
	bestN: number;
	/** Campionats sense partides publicades: només han comptat per a la mitjana. */
	nomesMitjana: number;
}

/** Any en què comença la temporada d'una data: l'1 d'agost canvia. */
export function temporadaDeData(data: string | null | undefined): number | null {
	const m = /^(\d{4})-(\d{2})/.exec(data ?? '');
	if (!m) return null;
	return Number(m[2]) >= 8 ? Number(m[1]) : Number(m[1]) - 1;
}

/** '2025-2026' o '2025/26' -> 2025. */
export function temporadaDeText(t: string | null | undefined): number | null {
	const m = /^(\d{4})\s*[-/]/.exec(t ?? '');
	return m ? Number(m[1]) : null;
}

export function temporadaActual(avui: Date = new Date()): number {
	return avui.getMonth() + 1 >= 8 ? avui.getFullYear() : avui.getFullYear() - 1;
}

export const MOD_TRES_BANDES = 'Tres bandes';
export const MOD_ALTRES = 'Altres';

const MOD_RFEB: Record<string, string> = {
	'3b': MOD_TRES_BANDES,
	banda: 'Banda',
	lliure: 'Lliure',
	'47_2': 'Quadre',
	'71_2': 'Quadre',
	artistic: 'Artístic',
	'5q': 'Cinc quilles'
};
const MOD_UMB: Record<string, string> = {
	'3 bandes': MOD_TRES_BANDES,
	'1 banda': 'Banda',
	'5 quilles': 'Cinc quilles',
	quadre: 'Quadre',
	artistic: 'Artístic',
	lliure: 'Lliure'
	// Les proves combinades (pentatló, triatló) sumen modalitats: van a «Altres».
};

export function modalitatRfeb(modalitat: string): string {
	return MOD_RFEB[modalitat] ?? MOD_ALTRES;
}
export function modalitatUmb(disciplina: string | null): string {
	return (disciplina && MOD_UMB[disciplina]) || MOD_ALTRES;
}

export function aportacionsNacional(rows: NacionalPartidaRow[]): Aportacio[] {
	return rows.map((r) => {
		const res = resultatPartida(r.caramboles, r.caramboles_rival);
		return {
			temporada: temporadaDeText(r.temporada) ?? temporadaDeData(r.data),
			modalitat: MOD_TRES_BANDES,
			n: 1,
			g: +(res === 'G'),
			e: +(res === 'E'),
			p: +(res === 'P'),
			car: r.caramboles,
			ent: r.entrades,
			serie: null,
			partida: true
		};
	});
}

/**
 * La RFEB només publica el total de cada campionat: sense `jugades` només en surt la mitjana.
 * Les proves de `ambPartides` es compten partida a partida (`aportacionsRfebPartides`) i aquí no.
 */
export function aportacionsRfeb(rows: RfebIndividualRow[], ambPartides: Set<string> = new Set()): Aportacio[] {
	const out: Aportacio[] = [];
	for (const r of rows) {
		if (ambPartides.has(r.prova_id)) continue;
		const jugades = r.jugades ?? 0;
		const teMitjana = r.caramboles != null && !!r.entrades;
		if (!jugades && !teMitjana && r.serie_major == null) continue;
		out.push({
			temporada: temporadaDeText(r.temporada) ?? temporadaDeData(r.data_inici),
			modalitat: modalitatRfeb(r.modalitat),
			n: jugades,
			g: jugades ? (r.guanyades ?? 0) : 0,
			e: jugades ? (r.empatades ?? 0) : 0,
			p: jugades ? (r.perdudes ?? 0) : 0,
			car: r.caramboles,
			ent: r.entrades,
			serie: r.serie_major,
			partida: false
		});
	}
	return out;
}

/**
 * Les proves on les partides del jugador poden substituir el total oficial.
 *
 * Moltes proves només en tenen una part (una fase que no s'ha pogut llegir).
 * Les partides compten als indicadors només si sumen exactament les caramboles,
 * les entrades i (si la RFEB les diu) les partides de la classificació del
 * jugador; si no, mana el total oficial. Una prova amb partides i sense
 * classificació hi és sempre: no hi ha cap total que les desmenteixi.
 */
export function provesAmbPartidesCompletes(rows: RfebPartidaRow[], individuals: RfebIndividualRow[]): Set<string> {
	const suma = new Map<string, { n: number; car: number; ent: number }>();
	for (const r of rows) {
		const t = suma.get(r.prova_id) ?? { n: 0, car: 0, ent: 0 };
		t.n++;
		t.car += r.caramboles;
		t.ent += r.entrades;
		suma.set(r.prova_id, t);
	}
	const oficials = new Map(individuals.map((r) => [r.prova_id, r]));
	const out = new Set<string>();
	for (const [prova, t] of suma) {
		const o = oficials.get(prova);
		if (!o || (o.caramboles === t.car && o.entrades === t.ent && (o.jugades == null || o.jugades === t.n)))
			out.add(prova);
	}
	return out;
}

export function aportacionsRfebPartides(rows: RfebPartidaRow[]): Aportacio[] {
	return rows.map((r) => {
		const res = resultatRfeb(r);
		return {
			temporada: temporadaDeText(r.temporada) ?? temporadaDeData(r.data ?? r.data_inici),
			modalitat: modalitatRfeb(r.modalitat),
			n: 1,
			g: +(res === 'G'),
			e: +(res === 'E'),
			p: +(res === 'P'),
			car: r.caramboles,
			ent: r.entrades,
			serie: r.serie,
			partida: true
		};
	});
}

export function aportacionsUmb(proves: UmbProva[]): Aportacio[] {
	const out: Aportacio[] = [];
	for (const pr of proves) {
		for (const r of pr.partides) {
			const res = resultatUmb(r);
			out.push({
				temporada: temporadaDeData(pr.data ?? r.data_inici),
				modalitat: modalitatUmb(disciplinaDePartida(pr.disciplina, r.fase)),
				n: 1,
				g: +(res === 'G'),
				e: +(res === 'E'),
				p: +(res === 'P'),
				car: r.caramboles,
				ent: r.entrades,
				serie: r.serie,
				partida: true
			});
		}
	}
	return out;
}

export function indicadors(aps: Aportacio[]): Indicadors {
	let n = 0, w = 0, t = 0, l = 0, car = 0, ent = 0, nomesMitjana = 0;
	let sm: number | null = null;
	let best: number | null = null;
	let bestN = 0;
	for (const a of aps) {
		n += a.n;
		w += a.g;
		t += a.e;
		l += a.p;
		if (!a.n && a.car != null && a.ent) nomesMitjana++;
		if (a.car != null && a.ent) {
			car += a.car;
			ent += a.ent;
		}
		if (a.serie != null) sm = Math.max(sm ?? 0, a.serie);
		if (a.partida && a.car != null && a.ent) {
			const m = a.car / a.ent;
			if (best == null || m > best + 1e-9) {
				best = m;
				bestN = 1;
			} else if (Math.abs(m - best) < 1e-9) bestN++;
		}
	}
	return { n, w, t, l, mitjana: ent ? car / ent : 0, sm, pct: n ? Math.round((100 * w) / n) : 0, best, bestN, nomesMitjana };
}

export interface FinestresIndicadors {
	historic: Indicadors;
	actual: Indicadors;
	anterior: Indicadors;
}

/** Les tres targetes. Sense temporada ni data, l'aportació només compta a l'Històric. */
export function finestres(aps: Aportacio[], avui: Date = new Date()): FinestresIndicadors {
	const t = temporadaActual(avui);
	return {
		historic: indicadors(aps),
		actual: indicadors(aps.filter((a) => a.temporada === t)),
		anterior: indicadors(aps.filter((a) => a.temporada === t - 1))
	};
}

export interface OpcioModalitat {
	clau: string;
	n: number;
}

/** Modalitats amb dades, la més jugada primer. */
export function modalitatsDe(claus: string[]): OpcioModalitat[] {
	const m = new Map<string, number>();
	for (const c of claus) m.set(c, (m.get(c) ?? 0) + 1);
	return [...m]
		.map(([clau, n]) => ({ clau, n }))
		.sort(
			(a, b) =>
				// «Altres» barreja modalitats: sempre l'última, i mai la triada per defecte.
				+(a.clau === MOD_ALTRES) - +(b.clau === MOD_ALTRES) || b.n - a.n || a.clau.localeCompare(b.clau)
		);
}

export function filtraModalitat(aps: Aportacio[], mod: string | null): Aportacio[] {
	return mod == null ? aps : aps.filter((a) => a.modalitat === mod);
}

// --- Partides d'Espanya i Internacional en la forma de les catalanes ----------
//
// Tots els apartats de la fitxa catalana (millor partida, rivals destacats,
// mitjana mòbil, distribució…) surten d'una llista de `GameRow` vista des del
// jugador. Escrivint les partides de la Lliga Nacional i de la UMB/CEB de la
// mateixa manera, els tres àmbits tenen els mateixos apartats calculats igual.

/** Una partida d'un altre àmbit, amb la modalitat amb què s'agrupa a l'àmbit. */
/**
 * Una partida d'un altre àmbit, amb la modalitat amb què s'agrupa i, si cal, un
 * detall que el llistat ensenya sota la competició (la jornada i l'encontre de
 * la Lliga Nacional, la fase d'un campionat, els sets d'una partida de la UMB).
 */
export type GameRowAmbit = GameRow & { modAmbit: string; detall?: string };

/** Guanyador: el jugador, el rival (`'rival'`) o ningú si és empat. */
function guanyador(fcbId: string, res: 'G' | 'E' | 'P'): string | null {
	return res === 'G' ? fcbId : res === 'P' ? 'rival' : null;
}

export function gamesDeNacional(fcbId: string, rows: NacionalPartidaRow[]): GameRowAmbit[] {
	return rows.map((r) => {
		const res = resultatPartida(r.caramboles, r.caramboles_rival);
		return {
			id: `nac:${r.temporada}:${r.divisio}:${r.grup}:${r.jornada}:${r.ordre_encontre}:${r.ordre}`,
			data_partida: r.data,
			modalitat_codi: null,
			competicio: 'Lliga Nacional',
			player1_fcb_id: fcbId,
			player1_nom: null,
			caramboles1: r.caramboles,
			serie_max1: null,
			player2_fcb_id: r.rival_fcb_id,
			player2_nom: r.rival_nom_fcb ?? r.rival,
			caramboles2: r.caramboles_rival,
			serie_max2: null,
			entrades: r.entrades,
			guanyador_fcb_id: guanyador(fcbId, res),
			modAmbit: MOD_TRES_BANDES,
			detall: `J${r.jornada}${r.grup ? ` ${r.grup}` : ''} · ${r.equip} ${r.punts_equip}–${r.punts_rival} ${r.equip_rival}`
		};
	});
}

export function gamesDeRfeb(fcbId: string, rows: RfebPartidaRow[]): GameRowAmbit[] {
	return rows.map((r) => ({
		id: `rfeb:${r.prova_id}:${r.fase}:${r.grup}:${r.ordre}`,
		data_partida: r.data ?? r.data_inici,
		modalitat_codi: null,
		competicio: nomProva(r),
		player1_fcb_id: fcbId,
		player1_nom: null,
		caramboles1: r.caramboles,
		serie_max1: r.serie,
		player2_fcb_id: r.rival_fcb_id,
		player2_nom: r.rival,
		caramboles2: r.rival_caramboles,
		serie_max2: r.rival_serie,
		entrades: r.entrades,
		guanyador_fcb_id: guanyador(fcbId, resultatRfeb(r)),
		modAmbit: modalitatRfeb(r.modalitat),
		detall: r.fase + (r.grup ? ` ${r.grup}` : '')
	}));
}

export function gamesDeUmb(fcbId: string, proves: UmbProva[]): GameRowAmbit[] {
	const out: GameRowAmbit[] = [];
	for (const pr of proves) {
		for (const r of pr.partides) {
			out.push({
				id: `umb:${r.esdeveniment_id}:${r.fase}:${r.grup}:${r.ordre}`,
				data_partida: pr.data ?? r.data_inici,
				modalitat_codi: null,
				competicio: pr.nom,
				player1_fcb_id: fcbId,
				player1_nom: null,
				caramboles1: r.caramboles,
				serie_max1: r.serie,
				player2_fcb_id: r.rival_fcb_id,
				player2_nom: r.rival,
				caramboles2: r.rival_caramboles,
				serie_max2: null,
				entrades: r.entrades,
				// A sets, i amb penals, guanya qui diuen els punts, no les caramboles.
				guanyador_fcb_id: guanyador(fcbId, resultatUmb(r)),
				modAmbit: modalitatUmb(disciplinaDePartida(pr.disciplina, r.fase)),
				detall: [r.fase, textSets(r)].filter(Boolean).join(' · ')
			});
		}
	}
	return out;
}

/** El grup d'«Efectivitat per competició» on va una competició de cada àmbit. */
export function tipusCompeticio(ambit: 'cat' | 'esp' | 'int', competicio: string | null): string | null {
	const s = (competicio ?? '').toLowerCase();
	if (ambit === 'int') {
		if (/world cup|coupe du monde|copa del m/.test(s)) return 'Copa del Món';
		if (/world championship|world games|mundial/.test(s)) return 'Mundial';
		if (/europ/.test(s)) return 'Europeu';
		return 'Altres';
	}
	if (ambit === 'esp') {
		if (s.includes('play-off')) return 'Play-off de la Lliga Nacional';
		if (s.includes('lliga')) return 'Lliga Nacional';
		if (s.includes('gran premi')) return "Gran Premi d'Espanya";
		if (s.includes('seleccions')) return 'Seleccions autonòmiques';
		if (s.includes('per equips')) return "Campionat d'Espanya per equips";
		if (s.includes("campionat d'espanya")) return "Campionat d'Espanya";
		return null;
	}
	if (s.includes('lliga') || s.includes('liga')) return 'Lliga';
	if (s.includes('open')) return 'Open';
	if (s.includes('individual') || s.includes('catalunya')) return 'Individual';
	if (s.includes('copa')) return 'Copa';
	return null;
}

/**
 * Els campionats de la RFEB a l'efectivitat: només els que diuen quantes partides es van jugar,
 * i no els de `ambPartides`, que ja hi són partida a partida.
 */
export function efectivitatRfeb(
	rows: RfebIndividualRow[],
	ambPartides: Set<string> = new Set()
): { tipus: string; w: number; e: number; l: number; n: number }[] {
	const map = new Map<string, { w: number; e: number; l: number; n: number }>();
	for (const r of rows) {
		if (!r.jugades || ambPartides.has(r.prova_id)) continue;
		const tipus = r.tipus === 'gpe' ? "Gran Premi d'Espanya" : r.tipus === 'ce' ? "Campionat d'Espanya" : 'Altres';
		const b = map.get(tipus) ?? { w: 0, e: 0, l: 0, n: 0 };
		b.w += r.guanyades ?? 0;
		b.e += r.empatades ?? 0;
		b.l += r.perdudes ?? 0;
		b.n += r.jugades;
		map.set(tipus, b);
	}
	return [...map].map(([tipus, b]) => ({ tipus, ...b }));
}
