/** Resum de medalles per a qui en té tantes que la llista sola no es llegeix d'un cop d'ull. */

/** A partir de quantes medalles d'un àmbit es mostra el resum, a més de la llista. */
export const LLINDAR_RESUM = 6;

export interface MedallaResumible {
	competicio: string;
	categoria: string;
	posicio: 1 | 2 | 3;
}

export interface Recompte {
	primers: number;
	segons: number;
	tercers: number;
	total: number;
}

export interface FilaResum extends Recompte {
	competicio: string;
}

export interface ResumMedalles extends Recompte {
	perCompeticio: FilaResum[];
}

const buit = (): Recompte => ({ primers: 0, segons: 0, tercers: 0, total: 0 });

function suma(r: Recompte, posicio: 1 | 2 | 3) {
	if (posicio === 1) r.primers++;
	else if (posicio === 2) r.segons++;
	else r.tercers++;
	r.total++;
}

/** Les medalles comptades per lloc, en total i per competició (la categoria no absoluta, al nom). */
export function resumMedalles(medalles: MedallaResumible[]): ResumMedalles {
	const total = buit();
	const per = new Map<string, FilaResum>();
	for (const m of medalles) {
		const nom = m.categoria && m.categoria !== 'absolut' ? `${m.competicio} · ${m.categoria}` : m.competicio;
		let fila = per.get(nom);
		if (!fila) per.set(nom, (fila = { competicio: nom, ...buit() }));
		suma(fila, m.posicio);
		suma(total, m.posicio);
	}
	const perCompeticio = [...per.values()].sort(
		(a, b) =>
			b.primers - a.primers ||
			b.segons - a.segons ||
			b.tercers - a.tercers ||
			a.competicio.localeCompare(b.competicio, 'ca')
	);
	return { ...total, perCompeticio };
}

/** La modalitat d'una competició, pel nom: «Campionat d'Europa tres bandes» -> «Tres Bandes». */
export function modalitatDe(competicio: string): string {
	const c = competicio.toLowerCase();
	if (/tres bandes|3 bandes/.test(c)) return 'Tres Bandes';
	if (/47\/1|45\/1/.test(c)) return 'Quadre 47/1';
	if (/47\/2|45\/2/.test(c)) return 'Quadre 47/2';
	if (/71\/2/.test(c)) return 'Quadre 71/2';
	if (/\bbanda\b/.test(c)) return 'Banda';
	if (/lliure/.test(c)) return 'Lliure';
	if (/art[ií]stic/.test(c)) return 'Artístic';
	if (/5 quilles|5 pins/.test(c)) return '5 Quilles';
	if (/quilles|pins/.test(c)) return 'Quilles';
	if (/biatl/.test(c)) return 'Biatló';
	if (/chap/.test(c)) return 'Chapó';
	return 'Altres';
}

export interface ResumModalitat {
	modalitat: string;
	resum: ResumMedalles;
}

/**
 * Els podis separats per modalitat. Dins de cada modalitat, una fila per competició i
 * categoria; quan la competició és la mateixa modalitat (Catalunya), només la categoria.
 */
export function resumPerModalitat(medalles: MedallaResumible[]): ResumModalitat[] {
	const grups = new Map<string, MedallaResumible[]>();
	for (const m of medalles) {
		const mod = modalitatDe(m.competicio);
		const nom = [
			modalitatDe(m.competicio) === m.competicio || m.competicio.toLowerCase() === mod.toLowerCase() ? '' : m.competicio,
			m.categoria && m.categoria !== 'absolut' ? m.categoria : ''
		]
			.filter(Boolean)
			.join(' · ');
		grups.set(mod, [...(grups.get(mod) ?? []), { ...m, competicio: nom || 'Absolut', categoria: 'absolut' }]);
	}
	return [...grups]
		.map(([modalitat, ms]) => ({ modalitat, resum: resumMedalles(ms) }))
		.sort(
			(a, b) =>
				b.resum.primers - a.resum.primers ||
				b.resum.total - a.resum.total ||
				a.modalitat.localeCompare(b.modalitat, 'ca')
		);
}
