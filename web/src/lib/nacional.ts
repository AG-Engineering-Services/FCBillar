export interface NacionalPartidaRow {
	fcb_id: string;
	temporada: string;
	divisio: string;
	grup: string;
	jornada: number;
	data: string | null;
	ordre_encontre: number;
	ordre: number;
	jugador: string;
	caramboles: number;
	rival: string;
	caramboles_rival: number;
	rival_fcb_id: string | null;
	/** El rival com l'escriu la federació catalana, si té fitxa al cens. */
	rival_nom_fcb: string | null;
	entrades: number | null;
	equip: string;
	equip_rival: string;
	punts_equip: number;
	punts_rival: number;
	a_casa: boolean;
}

export interface NacionalResum {
	pj: number;
	g: number;
	e: number;
	p: number;
	caramboles: number;
	entrades: number;
	mitjana: number | null;
}

export interface NacionalGrup {
	clau: string;
	temporada: string;
	divisio: string;
	grup: string;
	/** Equips amb què ha jugat, amb la grafia més freqüent de cadascun. */
	equips: string[];
	resum: NacionalResum;
	partides: NacionalPartidaRow[];
}

const DIVISIONS: Record<string, string> = {
	honor: "Divisió d'Honor",
	'1': 'Primera',
	'2': 'Segona'
};

export function divisioNacional(divisio: string): string {
	return DIVISIONS[divisio] ?? divisio;
}

/** '2025-2026' -> '2025/26' */
export function temporadaCurta(temporada: string): string {
	const m = /^(\d{4})-(\d{4})$/.exec(temporada);
	return m ? `${m[1]}/${m[2].slice(2)}` : temporada;
}

/** Tres decimals amb coma, com als PDF de la federació. */
export function mitjanaNacional(mitjana: number | null): string {
	return mitjana == null ? '—' : mitjana.toFixed(3).replace('.', ',');
}

export function resultatPartida(caramboles: number, rival: number): 'G' | 'E' | 'P' {
	return caramboles > rival ? 'G' : caramboles < rival ? 'P' : 'E';
}

/** La RFEB escriu el mateix equip amb accents, cometes i majúscules diferents. */
export function normalitzaEquip(nom: string): string {
	return nom
		.normalize('NFD')
		.replace(/[̀-ͯ]/g, '')
		.replace(/["'“”‘’`]/g, '')
		.replace(/\s+/g, ' ')
		.trim()
		.toUpperCase();
}

/** Data descendent (les sense data, al final), després jornada descendent i ordre de l'encontre. */
function comparaPartides(a: NacionalPartidaRow, b: NacionalPartidaRow): number {
	if (a.data !== b.data) {
		if (!a.data) return 1;
		if (!b.data) return -1;
		return b.data.localeCompare(a.data);
	}
	return b.jornada - a.jornada || a.ordre_encontre - b.ordre_encontre || a.ordre - b.ordre;
}

const ordreDivisio = (d: string) => {
	const i = ['honor', '1', '2'].indexOf(d);
	return i < 0 ? 9 : i;
};

/** Temporada més recent primer; dins la temporada, Honor abans que Primera i Segona. */
export function ordenaNacional(rows: NacionalPartidaRow[]): NacionalPartidaRow[] {
	return [...rows].sort(
		(a, b) =>
			b.temporada.localeCompare(a.temporada) ||
			ordreDivisio(a.divisio) - ordreDivisio(b.divisio) ||
			a.grup.localeCompare(b.grup) ||
			comparaPartides(a, b)
	);
}

export function resumNacional(
	rows: Pick<NacionalPartidaRow, 'caramboles' | 'caramboles_rival' | 'entrades'>[]
): NacionalResum {
	const r: NacionalResum = { pj: rows.length, g: 0, e: 0, p: 0, caramboles: 0, entrades: 0, mitjana: null };
	for (const x of rows) {
		const res = resultatPartida(x.caramboles, x.caramboles_rival);
		if (res === 'G') r.g++;
		else if (res === 'P') r.p++;
		else r.e++;
		r.caramboles += x.caramboles;
		r.entrades += x.entrades ?? 0;
	}
	r.mitjana = r.entrades > 0 ? r.caramboles / r.entrades : null;
	return r;
}

/** Equips diferents (per nom normalitzat), cadascun amb la grafia més freqüent; ordre d'aparició. */
export function equipsDistints(noms: string[]): string[] {
	const grafies = new Map<string, Map<string, number>>();
	for (const n of noms) {
		const k = normalitzaEquip(n);
		const m = grafies.get(k) ?? new Map<string, number>();
		m.set(n, (m.get(n) ?? 0) + 1);
		grafies.set(k, m);
	}
	return [...grafies.values()].map((m) => [...m.entries()].sort((a, b) => b[1] - a[1])[0][0]);
}

/** Grafia més freqüent de cada equip, indexada pel nom normalitzat. */
export function grafiaPerEquip(noms: string[]): Map<string, string> {
	const res = new Map<string, string>();
	for (const g of equipsDistints(noms)) res.set(normalitzaEquip(g), g);
	return res;
}

/** Agrupa per temporada, divisió i grup; l'ordre de les files és el que arriba. */
export function agrupaNacional(rows: NacionalPartidaRow[]): NacionalGrup[] {
	const mapa = new Map<string, NacionalPartidaRow[]>();
	for (const r of rows) {
		const clau = `${r.temporada}|${r.divisio}|${r.grup}`;
		const l = mapa.get(clau);
		if (l) l.push(r);
		else mapa.set(clau, [r]);
	}
	return [...mapa.entries()].map(([clau, partides]) => ({
		clau,
		temporada: partides[0].temporada,
		divisio: partides[0].divisio,
		grup: partides[0].grup,
		equips: equipsDistints(partides.map((p) => p.equip)),
		resum: resumNacional(partides),
		partides
	}));
}

/** Una classificació final d'un campionat individual de la RFEB (vista rfeb_individuals_fitxa). */
export interface RfebIndividualRow {
	fcb_id: string;
	prova_id: string;
	posicio: number;
	/** La posició compartida quan la RFEB en dona una d'empatada. */
	posicio_empat: number | null;
	ronda: string | null;
	jugades: number | null;
	guanyades: number | null;
	empatades: number | null;
	perdudes: number | null;
	caramboles: number | null;
	entrades: number | null;
	mitjana: number | null;
	serie_major: number | null;
	temporada: string;
	modalitat: string;
	categoria: string;
	tipus: string;
	titol: string;
	lloc: string | null;
	data_inici: string | null;
	participants: number;
}

const TIPUS: Record<string, string> = {
	ce: "Campionat d'Espanya",
	gpe: "Gran Premi d'Espanya",
	playoff: 'Play-off de la Lliga Nacional',
	seleccions: "Campionat d'Espanya de seleccions",
	equips: "Campionat d'Espanya per equips"
};
const MODALITATS: Record<string, string> = {
	'3b': 'Tres bandes',
	banda: 'Banda',
	lliure: 'Lliure',
	'47_2': 'Quadre 47/2',
	'71_2': 'Quadre 71/2',
	artistic: 'Artístic',
	'5q': 'Cinc quilles',
	serie: 'Jocs de sèrie'
};
const CATEGORIES: Record<string, string> = {
	absolut: '',
	femeni: 'femení',
	sub15: 'sub-15',
	sub17: 'sub-17',
	sub21: 'sub-21',
	sub25: 'sub-25',
	senior: 'sènior',
	infantil: 'infantil',
	junior: 'júnior'
};

/** «Campionat d'Espanya · Tres bandes sub-21»; les proves sense tipus conegut fan servir el títol. */
export function nomProva(r: Pick<RfebIndividualRow, 'tipus' | 'modalitat' | 'categoria' | 'titol'>): string {
	const tipus = TIPUS[r.tipus];
	if (!tipus) return r.titol;
	const cat = CATEGORIES[r.categoria] ?? r.categoria;
	return `${tipus} · ${MODALITATS[r.modalitat] ?? r.modalitat}${cat ? ` ${cat}` : ''}`;
}

/** «3r de 14», o «4t (=3r) de 14» si la RFEB la dona empatada. */
export function posicioProva(r: Pick<RfebIndividualRow, 'posicio' | 'posicio_empat' | 'participants'>): string {
	const ord = (n: number) => `${n}${n === 1 ? 'r' : n === 2 ? 'n' : n === 3 ? 'r' : n === 4 ? 't' : 'è'}`;
	const empat = r.posicio_empat != null && r.posicio_empat !== r.posicio ? ` (=${ord(r.posicio_empat)})` : '';
	return `${ord(r.posicio)}${empat} de ${r.participants}`;
}

export function ordenaIndividuals(rows: RfebIndividualRow[]): RfebIndividualRow[] {
	return [...rows].sort(
		(a, b) =>
			b.temporada.localeCompare(a.temporada) ||
			(b.data_inici ?? '').localeCompare(a.data_inici ?? '') ||
			a.tipus.localeCompare(b.tipus) ||
			a.titol.localeCompare(b.titol)
	);
}

/** Una partida d'una prova de la RFEB vista des del jugador (vista rfeb_partides_fitxa). */
export interface RfebPartidaRow {
	fcb_id: string;
	prova_id: string;
	fase: string;
	grup: string;
	ordre: number;
	data: string | null;
	jugador: string;
	equip: string | null;
	caramboles: number;
	serie: number | null;
	punts: number | null;
	rival: string;
	equip_rival: string | null;
	rival_caramboles: number;
	rival_serie: number | null;
	rival_punts: number | null;
	entrades: number;
	/** La de la partida, o la de la prova si no en barreja. */
	modalitat: string;
	temporada: string;
	categoria: string;
	tipus: string;
	titol: string;
	lloc: string | null;
	data_inici: string | null;
	rival_fcb_id: string | null;
}

/** G, E o P: els punts quan el full els dona (hi ha eliminatòries que es decideixen als penals). */
export function resultatRfeb(r: Pick<RfebPartidaRow, 'caramboles' | 'rival_caramboles' | 'punts' | 'rival_punts'>): 'G' | 'E' | 'P' {
	if (r.punts != null && r.rival_punts != null && r.punts !== r.rival_punts) return r.punts > r.rival_punts ? 'G' : 'P';
	return resultatPartida(r.caramboles, r.rival_caramboles);
}

export interface RfebProvaPartides {
	prova_id: string;
	nom: string;
	titol: string;
	temporada: string;
	data: string | null;
	partides: RfebPartidaRow[];
	resum: NacionalResum;
}

/** Les partides agrupades per prova, la més recent primer, i dins de cada prova en l'ordre del full. */
export function agrupaRfebPartides(rows: RfebPartidaRow[]): RfebProvaPartides[] {
	const map = new Map<string, RfebPartidaRow[]>();
	for (const r of rows) map.set(r.prova_id, [...(map.get(r.prova_id) ?? []), r]);
	return [...map.values()]
		.map((ps) => {
			const r = ps[0]!;
			let g = 0, e = 0, p = 0, car = 0, ent = 0;
			for (const x of ps) {
				const res = resultatRfeb(x);
				if (res === 'G') g++;
				else if (res === 'E') e++;
				else p++;
				car += x.caramboles;
				ent += x.entrades;
			}
			return {
				prova_id: r.prova_id,
				nom: nomProva({ ...r, modalitat: ps.every((x) => x.modalitat === r.modalitat) ? r.modalitat : 'serie' }),
				titol: r.titol,
				temporada: r.temporada,
				data: r.data_inici,
				partides: ps,
				resum: { pj: ps.length, g, e, p, caramboles: car, entrades: ent, mitjana: ent ? car / ent : null }
			};
		})
		.sort((a, b) => b.temporada.localeCompare(a.temporada) || (b.data ?? '').localeCompare(a.data ?? ''));
}
