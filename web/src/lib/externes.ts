// Indicadors de la fitxa per àmbit: Catalunya, Espanya i Internacional.
//
// Catalunya són les partides de la FCB, que la fitxa ja calcula. Aquí hi ha les
// altres dues:
// - Espanya: la Lliga Nacional (partida a partida) i els Campionats d'Espanya i
//   Grans Premis de la RFEB, dels quals només hi ha els totals de cada jugador.
// - Internacional: Europeus (CEB), Mundials i Copes del Món (UMB), partida a
//   partida.
// Res d'aquí es barreja amb les mitjanes ni els rànquings catalans.

import { resultatPartida, type NacionalPartidaRow } from './nacional';

export type Ambit = 'catalunya' | 'espanya' | 'internacional';

/** Una fila de la vista `ext_partides_fitxa`: la partida vista des del jugador. */
export interface ExtPartidaRow {
	fcb_id: string;
	font: string;
	esdeveniment: string;
	competicio: string;
	modalitat: string;
	ambit: 'espanya' | 'internacional';
	tipus: string;
	temporada: string;
	data: string | null;
	fase: string;
	grup: string;
	ordre: number;
	jugador: string;
	caramboles: number | null;
	entrades: number | null;
	serie: number | null;
	punts: number | null;
	rival: string;
	nacio_rival: string;
	rival_fcb_id: string | null;
	caramboles_rival: number | null;
	entrades_rival: number | null;
	serie_rival: number | null;
	punts_rival: number | null;
}

/** Una fila de `ext_totals_fitxa`: els totals d'un jugador en un campionat sense partides. */
export interface ExtTotalRow {
	fcb_id: string;
	font: string;
	esdeveniment: string;
	competicio: string;
	modalitat: string;
	ambit: 'espanya' | 'internacional';
	tipus: string;
	temporada: string;
	data: string | null;
	jugador: string;
	federacio: string;
	posicio: number | null;
	jugades: number | null;
	guanyades: number | null;
	empatades: number | null;
	perdudes: number | null;
	caramboles: number | null;
	entrades: number | null;
	serie: number | null;
}

/** Modalitat de les fonts de fora → codi de modalitat de la FCB. El 47/1 no es juga aquí. */
export const CODI_MODALITAT: Record<string, number | null> = {
	'3B': 1,
	LLIURE: 2,
	'47/2': 3,
	BANDA: 4,
	'71/2': 6,
	'47/1': null
};

/** La Lliga Nacional és de tres bandes. */
const CODI_NACIONAL = 1;

const NOM_TIPUS: Record<string, string> = {
	campionat_espanya: "Campionat d'Espanya",
	gp_espanya: "Gran Premi d'Espanya",
	europeu: 'Europeu',
	mundial: 'Mundial',
	copa_mon: 'Copa del Món'
};

export function nomTipus(tipus: string): string {
	return NOM_TIPUS[tipus] ?? tipus;
}

/** Una partida qualsevol, d'on sigui, amb només el que fa falta per als indicadors. */
interface Partida {
	resultat: 'G' | 'E' | 'P';
	car: number;
	ent: number | null;
	serie: number | null;
	temporada: string;
}

export interface Indicadors {
	/** Partides jugades, incloses les dels campionats que només donen totals. */
	n: number;
	w: number;
	e: number;
	l: number;
	/** Mitjana general: caramboles / entrades de tot el que en porta. */
	mitjana: number;
	/** Sèrie major, si alguna font la dona. */
	sm: number | null;
	pct: number;
	/** Millor mitjana en una partida: només on hi ha partides. */
	best: number | null;
	bestN: number;
	/** Campionats que no diuen quantes partides es van jugar (quadre, banda, lliure). */
	senseDetall: number;
}

function resultatExtern(r: ExtPartidaRow): 'G' | 'E' | 'P' {
	// Els punts de match decideixen: en una eliminatòria empatada a caramboles hi
	// ha penals, i guanya qui els punts diuen.
	if (r.punts != null && r.punts_rival != null && r.punts !== r.punts_rival)
		return r.punts > r.punts_rival ? 'G' : 'P';
	return resultatPartida(r.caramboles ?? 0, r.caramboles_rival ?? 0);
}

function deNacional(r: NacionalPartidaRow): Partida {
	return {
		resultat: resultatPartida(r.caramboles, r.caramboles_rival),
		car: r.caramboles,
		ent: r.entrades,
		serie: null,
		temporada: r.temporada
	};
}

function deExterna(r: ExtPartidaRow): Partida {
	return {
		resultat: resultatExtern(r),
		car: r.caramboles ?? 0,
		ent: r.entrades,
		serie: r.serie,
		temporada: r.temporada
	};
}

/** Les dades d'un jugador de fora de Catalunya, ja filtrades per modalitat. */
export interface DadesExternes {
	nacional: NacionalPartidaRow[];
	partides: ExtPartidaRow[];
	totals: ExtTotalRow[];
}

export function filtraModalitat(d: DadesExternes, codi: number | null): DadesExternes {
	if (codi == null) return d;
	const val = (m: string) => CODI_MODALITAT[m] === codi;
	return {
		nacional: codi === CODI_NACIONAL ? d.nacional : [],
		partides: d.partides.filter((r) => val(r.modalitat)),
		totals: d.totals.filter((r) => val(r.modalitat))
	};
}

/** Quins àmbits tenen alguna dada, a part de Catalunya. */
export function ambitsAmbDades(d: DadesExternes): Ambit[] {
	const out: Ambit[] = [];
	if (
		d.nacional.length ||
		d.partides.some((r) => r.ambit === 'espanya') ||
		d.totals.some((r) => r.ambit === 'espanya')
	)
		out.push('espanya');
	if (d.partides.some((r) => r.ambit === 'internacional') || d.totals.some((r) => r.ambit === 'internacional'))
		out.push('internacional');
	return out;
}

/**
 * Indicadors d'un àmbit. Amb `temporada`, només els d'aquella temporada
 * ('2026-2027').
 */
export function indicadors(d: DadesExternes, ambit: 'espanya' | 'internacional', temporada?: string): Indicadors {
	const dins = (t: string) => temporada == null || t === temporada;
	const partides: Partida[] = [
		...(ambit === 'espanya' ? d.nacional.map(deNacional) : []),
		...d.partides.filter((r) => r.ambit === ambit).map(deExterna)
	].filter((p) => dins(p.temporada));
	const totals = d.totals.filter((r) => r.ambit === ambit && dins(r.temporada));

	let n = 0, w = 0, e = 0, l = 0, car = 0, ent = 0;
	let sm: number | null = null;
	let best: number | null = null, bestN = 0;
	let senseDetall = 0;
	for (const p of partides) {
		n++;
		if (p.resultat === 'G') w++;
		else if (p.resultat === 'E') e++;
		else l++;
		if (p.ent) {
			car += p.car;
			ent += p.ent;
			const a = p.car / p.ent;
			if (best == null || a > best + 1e-9) {
				best = a;
				bestN = 1;
			} else if (Math.abs(a - best) < 1e-9) bestN++;
		}
		if (p.serie != null) sm = Math.max(sm ?? 0, p.serie);
	}
	for (const t of totals) {
		if (t.jugades != null) {
			n += t.jugades;
			w += t.guanyades ?? 0;
			e += t.empatades ?? 0;
			l += t.perdudes ?? 0;
		} else senseDetall++;
		if (t.caramboles != null && t.entrades) {
			car += t.caramboles;
			ent += t.entrades;
		}
		if (t.serie != null) sm = Math.max(sm ?? 0, t.serie);
	}
	const decidides = w + e + l;
	return {
		n,
		w,
		e,
		l,
		mitjana: ent ? car / ent : 0,
		sm,
		pct: decidides ? Math.round((100 * w) / decidides) : 0,
		best,
		bestN,
		senseDetall
	};
}

export interface Competicio {
	clau: string;
	nom: string;
	tipus: string;
	modalitat: string;
	temporada: string;
	data: string | null;
	/** Posició final, quan la font la dona (RFEB). */
	posicio: number | null;
	partides: ExtPartidaRow[];
	total: ExtTotalRow | null;
	resum: { n: number | null; w: number; e: number; l: number; mitjana: number | null };
}

/** Les competicions d'un àmbit, de la més nova a la més antiga, amb les partides en ordre de joc. */
export function competicions(d: DadesExternes, ambit: 'espanya' | 'internacional'): Competicio[] {
	const map = new Map<string, Competicio>();
	const obte = (r: ExtPartidaRow | ExtTotalRow): Competicio => {
		const clau = `${r.font}:${r.esdeveniment}`;
		let c = map.get(clau);
		if (!c) {
			c = {
				clau,
				nom: r.competicio,
				tipus: r.tipus,
				modalitat: r.modalitat,
				temporada: r.temporada,
				data: r.data,
				posicio: null,
				partides: [],
				total: null,
				resum: { n: 0, w: 0, e: 0, l: 0, mitjana: null }
			};
			map.set(clau, c);
		}
		if (r.data && (!c.data || r.data < c.data)) c.data = r.data;
		return c;
	};
	for (const r of d.partides) if (r.ambit === ambit) obte(r).partides.push(r);
	for (const t of d.totals)
		if (t.ambit === ambit) {
			const c = obte(t);
			c.total = t;
			c.posicio = t.posicio;
		}
	for (const c of map.values()) {
		c.partides.sort((a, b) => a.ordre - b.ordre);
		if (c.total) {
			const t = c.total;
			c.resum = {
				n: t.jugades,
				w: t.guanyades ?? 0,
				e: t.empatades ?? 0,
				l: t.perdudes ?? 0,
				mitjana: t.caramboles != null && t.entrades ? t.caramboles / t.entrades : null
			};
		} else {
			let car = 0, ent = 0;
			const r = { n: c.partides.length, w: 0, e: 0, l: 0, mitjana: null as number | null };
			for (const p of c.partides) {
				const res = resultatExtern(p);
				if (res === 'G') r.w++;
				else if (res === 'E') r.e++;
				else r.l++;
				if (p.entrades) {
					car += p.caramboles ?? 0;
					ent += p.entrades;
				}
			}
			r.mitjana = ent ? car / ent : null;
			c.resum = r;
		}
	}
	return [...map.values()].sort(
		(a, b) => (b.data ?? b.temporada).localeCompare(a.data ?? a.temporada) || a.nom.localeCompare(b.nom)
	);
}

export function resultatDe(r: ExtPartidaRow): 'G' | 'E' | 'P' {
	return resultatExtern(r);
}

/** '2026-2027' per a la temporada en curs (canvia l'1 d'agost). */
export function temporadaActual(avui = new Date()): string {
	const y = avui.getMonth() + 1 >= 8 ? avui.getFullYear() : avui.getFullYear() - 1;
	return `${y}-${y + 1}`;
}
