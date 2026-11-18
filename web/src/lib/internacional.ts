/** Una partida d'una prova UMB o CEB d'un jugador amb fitxa (vista umb_partides_fitxa). */
export interface UmbPartidaRow {
	fcb_id: string;
	esdeveniment_id: number;
	esdeveniment: string;
	disciplina: string | null;
	lloc: string | null;
	data_inici: string | null;
	fase: string;
	grup: string;
	ordre: number;
	caramboles: number | null;
	entrades: number | null;
	punts: number | null;
	serie: number | null;
	rival: string;
	rival_caramboles: number | null;
	rival_punts: number | null;
	rival_fcb_id: string | null;
	/** Fins al 2011 la UMB jugava a sets de 15: caramboles/entrades de cada set, «9/11,4/7». Null si no és a sets. */
	sets?: string | null;
	rival_sets?: string | null;
}

/** La posició final en una prova (vista umb_classificacions_fitxa). */
export interface UmbClassificacioRow {
	fcb_id: string;
	esdeveniment_id: number;
	esdeveniment: string;
	lloc: string | null;
	data_inici: string | null;
	posicio: number;
	ronda: string | null;
	mitjana: number | null;
	participants: number;
}

export interface UmbProva {
	id: number;
	nom: string;
	/** Modalitat de la prova (3 bandes, quadre…), si es coneix. */
	disciplina: string | null;
	lloc: string | null;
	data: string | null;
	any: string | null;
	classificacio: UmbClassificacioRow | null;
	partides: UmbPartidaRow[];
	pj: number;
	g: number;
	e: number;
	p: number;
	mitjana: number | null;
}

export interface ResultatSets {
	/** Sets guanyats pel jugador i pel rival. */
	jo: number;
	rival: number;
	/** Caramboles de cada set, «9-15». */
	detall: string[];
}

function caramblesPerSet(s: string | null | undefined): number[] | null {
	if (!s) return null;
	const car = s.split(',').map((x) => Number(x.split('/')[0]));
	return car.length && car.every((n) => Number.isFinite(n)) ? car : null;
}

/** Resultat d'una partida a sets: guanya el set qui fa més caramboles. Null si la partida no és a sets. */
export function resultatSets(r: Pick<UmbPartidaRow, 'sets' | 'rival_sets'>): ResultatSets | null {
	const a = caramblesPerSet(r.sets);
	const b = caramblesPerSet(r.rival_sets);
	if (!a || !b || a.length !== b.length) return null;
	return {
		jo: a.filter((x, i) => x > b[i]).length,
		rival: a.filter((x, i) => x < b[i]).length,
		detall: a.map((x, i) => `${x}-${b[i]}`)
	};
}

/** «Sets 3-2 · 9-15, 4-15, 15-10, 15-9, 15-10», o buit si no és a sets. */
export function textSets(r: Pick<UmbPartidaRow, 'sets' | 'rival_sets'>): string {
	const s = resultatSets(r);
	return s ? `Sets ${s.jo}-${s.rival} · ${s.detall.join(', ')}` : '';
}

/** Guanya qui té més punts de partida; si la font no en dona, qui guanya més sets
 *  (a sets el perdedor pot fer més caramboles) i, si no n'hi ha, qui fa més caramboles. */
export function resultatUmb(
	r: Pick<UmbPartidaRow, 'punts' | 'rival_punts' | 'caramboles' | 'rival_caramboles'> & Partial<Pick<UmbPartidaRow, 'sets' | 'rival_sets'>>
): 'G' | 'E' | 'P' {
	const sets = resultatSets(r);
	const [a, b] =
		r.punts != null && r.rival_punts != null
			? [r.punts, r.rival_punts]
			: sets
				? [sets.jo, sets.rival]
				: [r.caramboles ?? 0, r.rival_caramboles ?? 0];
	return a > b ? 'G' : a < b ? 'P' : 'E';
}

const DISCIPLINES: [RegExp, string][] = [
	[/3[- ]?cushion|three[- ]?cushion|3[- ]?bandes/i, '3 bandes'],
	[/1[- ]?cushion|one[- ]?cushion/i, '1 banda'],
	[/5[- ]?pins?|five[- ]?pins?/i, '5 quilles'],
	[/47[/-]?2|47\/1|71\/2|cadre|balkline/i, 'quadre'],
	[/artistic/i, 'artistic'],
	[/free|libre|straight/i, 'lliure'],
	[/pentathlon|biathlon|triathlon/i, 'combinada']
];

/** Mirall de `disciplina_de` del Python: per a les proves sense partides, que no en porten. */
export function disciplinaDeNom(nom: string): string | null {
	return DISCIPLINES.find(([re]) => re.test(nom))?.[1] ?? null;
}

/** Una entrada per prova, de la més nova a la més antiga, amb les partides en l'ordre del PDF. */
export function agrupaUmb(partides: UmbPartidaRow[], classificacions: UmbClassificacioRow[]): UmbProva[] {
	const proves = new Map<number, UmbProva>();
	const nova = (id: number, nom: string, lloc: string | null, data: string | null): UmbProva => ({
		id, nom, disciplina: disciplinaDeNom(nom), lloc, data, any: data ? data.slice(0, 4) : null, classificacio: null, partides: [], pj: 0, g: 0, e: 0, p: 0, mitjana: null
	});
	for (const r of partides) {
		if (!proves.has(r.esdeveniment_id)) proves.set(r.esdeveniment_id, nova(r.esdeveniment_id, r.esdeveniment, r.lloc, r.data_inici));
		proves.get(r.esdeveniment_id)!.partides.push(r);
	}
	for (const c of classificacions) {
		if (!proves.has(c.esdeveniment_id)) proves.set(c.esdeveniment_id, nova(c.esdeveniment_id, c.esdeveniment, c.lloc, c.data_inici));
		proves.get(c.esdeveniment_id)!.classificacio = c;
	}
	for (const pr of proves.values()) {
		pr.disciplina = pr.partides.find((r) => r.disciplina)?.disciplina ?? pr.disciplina;
		pr.partides.sort((a, b) => a.ordre - b.ordre);
		let car = 0, ent = 0;
		for (const r of pr.partides) {
			pr.pj++;
			pr[{ G: 'g', E: 'e', P: 'p' }[resultatUmb(r)] as 'g' | 'e' | 'p']++;
			if (r.caramboles != null && r.entrades) { car += r.caramboles; ent += r.entrades; }
		}
		pr.mitjana = ent ? car / ent : null;
	}
	return [...proves.values()].sort((a, b) => (b.data ?? '').localeCompare(a.data ?? '') || b.id - a.id);
}
