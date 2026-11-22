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
