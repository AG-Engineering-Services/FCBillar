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
