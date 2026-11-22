/**
 * El palmarès individual de Catalunya en una sola llista: el Quadre d'Honor de la FCB
 * (1961-2025, només campió i subcampió) i els podis de la web de la federació (des del
 * 2014, amb els tercers llocs, els opens i els tornejos). Un títol que surt a totes dues
 * fonts compta un cop.
 */

export type MenaDePalmares = 'campionat' | 'open' | 'torneig';

/** Un podi de la web de la federació, tal com el llegeix la fitxa. */
export interface PodiWeb {
	openId: number;
	nom: string;
	categoria: string | null;
	modalitat: number | null;
	tipus: MenaDePalmares;
	/** «2018-2019» */
	temporada: string;
	posicio: number;
	club: string | null;
}

/** Una medalla del Quadre d'Honor. */
export interface MedallaQH {
	competicio: string;
	categoria: string;
	/** «2018-19» */
	edicio: string;
	posicio: 1 | 2 | 3;
	lloc: string | null;
}

export interface EntradaPalmares {
	tipus: MenaDePalmares;
	/** Modalitat del campionat, o nom de l'open o el torneig. */
	nom: string;
	/** Buida quan és l'absoluta o no se sap. */
	categoria: string;
	posicio: number;
	club: string | null;
	/** Només els podis de la web porten enllaç a la prova. */
	openId: number | null;
}

export const NOM_MODALITAT: Record<number, string> = {
	1: 'Tres bandes',
	2: 'Lliure',
	3: 'Quadre 47/2',
	4: 'Banda',
	6: 'Quadre 71/2'
};

/** «2018-2019» → «2018-19»; la resta, tal com ve. */
export const temporadaCurta = (t: string) => t.replace(/^(\d{4})-\d{2}(\d{2})$/, '$1-$2');

const pla = (s: string) =>
	s
		.normalize('NFD')
		.replace(/\p{M}/gu, '')
		.toLowerCase()
		.trim();

/** Les categories que no distingeixen res: absoluta, única o no publicada. */
const GENERICA = new Set(['', 'absolut', 'absoluta', 'unica', 'categoria no publicada']);
const categoriaPlana = (c: string | null) => {
	const p = pla(c ?? '');
	return GENERICA.has(p) ? '' : p;
};

/** La web escriu «HONOR» i el Quadre d'Honor «honor»: es mostren igual. */
const minuscules = (c: string) => (c === c.toUpperCase() ? c.toLowerCase() : c);

const clau = (temporada: string, modalitat: string, posicio: number) =>
	`${temporada}|${pla(modalitat)}|${posicio}`;

/**
 * Per temporada, de la més recent a la més antiga. Dins de cada temporada, primer els
 * campionats i després per lloc.
 */
export function palmaresCatalunya(
	web: PodiWeb[],
	qh: MedallaQH[]
): { temporada: string; entries: EntradaPalmares[] }[] {
	const perTemporada = new Map<string, EntradaPalmares[]>();
	const posa = (t: string, e: EntradaPalmares) => perTemporada.set(t, [...(perTemporada.get(t) ?? []), e]);
	// Campionats de la web per temporada, modalitat i lloc, amb la categoria, per no repetir-los.
	const webCampionats = new Map<string, Set<string>>();
	for (const p of web) {
		const t = temporadaCurta(p.temporada) || 'Temporada desconeguda';
		const campionat = p.tipus === 'campionat' && p.modalitat != null;
		const nom = campionat ? NOM_MODALITAT[p.modalitat!] ?? p.nom : p.nom;
		if (campionat) {
			const k = clau(t, nom, p.posicio);
			webCampionats.set(k, (webCampionats.get(k) ?? new Set()).add(categoriaPlana(p.categoria)));
		}
		posa(t, {
			tipus: p.tipus,
			nom,
			categoria: categoriaPlana(p.categoria) ? minuscules(p.categoria!) : '',
			posicio: p.posicio,
			club: p.club,
			openId: p.openId
		});
	}
	for (const m of qh) {
		const cats = webCampionats.get(clau(m.edicio, m.competicio, m.posicio));
		const cat = categoriaPlana(m.categoria);
		// Ja hi és si la web té el mateix títol amb la mateixa categoria, o sense poder-les distingir.
		if (cats && (cats.has(cat) || cats.has('') || cat === '')) continue;
		posa(m.edicio, {
			tipus: 'campionat',
			nom: m.competicio,
			categoria: cat ? m.categoria : '',
			posicio: m.posicio,
			club: m.lloc,
			openId: null
		});
	}
	const ordre: Record<MenaDePalmares, number> = { campionat: 0, open: 1, torneig: 2 };
	return [...perTemporada]
		.sort(([a], [b]) => b.localeCompare(a))
		.map(([temporada, entries]) => ({
			temporada,
			entries: entries.sort(
				(a, b) => ordre[a.tipus] - ordre[b.tipus] || a.posicio - b.posicio || a.nom.localeCompare(b.nom, 'ca')
			)
		}));
}

export interface RecompteMena {
	tipus: MenaDePalmares;
	primers: number;
	segons: number;
	tercers: number;
}

/** 1rs, 2ns i 3rs per mena (campionats, opens, tornejos), només les menes que en tenen. */
export function recomptePerMena(grups: { entries: EntradaPalmares[] }[]): RecompteMena[] {
	const r = (['campionat', 'open', 'torneig'] as const).map((tipus) => ({ tipus, primers: 0, segons: 0, tercers: 0 }));
	for (const g of grups)
		for (const e of g.entries) {
			const f = r.find((x) => x.tipus === e.tipus)!;
			if (e.posicio === 1) f.primers++;
			else if (e.posicio === 2) f.segons++;
			else if (e.posicio === 3) f.tercers++;
		}
	return r.filter((f) => f.primers + f.segons + f.tercers > 0);
}
