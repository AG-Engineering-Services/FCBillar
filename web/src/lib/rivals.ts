// Cerca d'un rival dins de les partides d'un jugador, per al filtre
// «Partides contra…» de la fitxa.
//
// Els noms surten de moltes maneres («GARCIA MARTINEZ, RICARDO», «Ricardo
// García»): per això cada paraula escrita ha de ser l'inici d'alguna paraula del
// nom, en qualsevol ordre i sense accents. «ric garc» troba Ricardo García i
// «garcia r» també.

import { norm } from './search';

export interface Rival {
	/** fcb_id del rival, o el nom si la partida no en porta. */
	key: string;
	nom: string;
	partides: number;
}

/** Els suggeriments no surten fins que s'han escrit tantes lletres. */
export const MIN_LLETRES = 3;

function paraules(s: string): string[] {
	return norm(s)
		.replace(/[^a-z0-9 ]/g, ' ')
		.split(/\s+/)
		.filter(Boolean);
}

/** Lletres escrites sense comptar espais ni puntuació. */
export function lletres(q: string): number {
	return paraules(q).join('').length;
}

/** Cert si cada paraula de la consulta és l'inici d'alguna paraula del nom. */
export function rivalCoincideix(nom: string, q: string): boolean {
	const qs = paraules(q);
	if (!qs.length) return false;
	const ns = paraules(nom);
	return qs.every((p) => ns.some((n) => n.startsWith(p)));
}

/** Rivals que coincideixen, primer els que comencen com la consulta i després
 *  els més jugats. Buit mentre no hi ha MIN_LLETRES lletres. */
export function suggereixRivals(rivals: Rival[], q: string, max = 8): Rival[] {
	if (lletres(q) < MIN_LLETRES) return [];
	const primera = paraules(q)[0] ?? '';
	return rivals
		.filter((r) => rivalCoincideix(r.nom, q))
		.map((r) => ({ r, comenca: paraules(r.nom)[0]?.startsWith(primera) ? 0 : 1 }))
		.sort(
			(a, b) =>
				a.comenca - b.comenca ||
				b.r.partides - a.r.partides ||
				a.r.nom.localeCompare(b.r.nom)
		)
		.slice(0, max)
		.map((x) => x.r);
}
