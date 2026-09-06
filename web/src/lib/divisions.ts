/**
 * Noms de divisió i de grup, que arriben escrits de dues maneres.
 *
 * La mateixa competició ens ve per dos camins que no es parlen. La intranet de
 * la federació escriu `HONOR`, `1a DIVISIÓ` i `GRUP A`; el PDF del calendari
 * de cada grup escriu `Honor`, `1a` i `A`. No hi ha cap identificador que els
 * lligui: només el nom.
 *
 * Mentre el calendari no va portar l'Honor això no es notava, perquè les
 * divisions numerades s'escriuen igual als dos llocs un cop tret el
 * «DIVISIÓ». El 6 de setembre de 2026, amb els dotze grups de la 26/27 al PDF
 * i l'Honor grup A ja publicat a la intranet, la pàgina de lliga va passar a
 * ensenyar dues divisions d'Honor: `HONOR` i `Honor`.
 */

/**
 * El nom d'una divisió, comparable vingui d'on vingui.
 *
 * `'1a DIVISIÓ'`, `'1ª Divisió'` i `'1a'` són la mateixa cosa, i `'HONOR'` i
 * `'Honor'` també.
 */
export function clauDivisio(divisio: string | null | undefined): string {
	return (divisio ?? '')
		.toUpperCase()
		.replace(/\s*DIVISI[ÓO].*$/, '')
		.trim();
}

/** El nom d'un grup, comparable: `'GRUP A'` i `'A'` són el mateix grup. */
export function clauNomGrup(grup: string | null | undefined): string {
	return (grup ?? '')
		.toUpperCase()
		.replace(/^GRUP\s+/, '')
		.trim();
}

/** Divisió i grup junts, per saber si dues fonts parlen del mateix grup. */
export function clauGrup(divisio: string | null | undefined, grup: string | null | undefined): string {
	return `${clauDivisio(divisio)}|${clauNomGrup(grup)}`;
}

/**
 * On va cada divisió a la llista.
 *
 * L'Honor és la de dalt de tot i es diu `'Honor'`, o sigui que ordenades com a
 * text quedaria darrere de la 4a.
 */
export function ordreDivisio(divisio: string | null | undefined): number {
	const d = clauDivisio(divisio);
	if (d.startsWith('HONOR')) return 0;
	const n = parseInt(d, 10);
	return Number.isNaN(n) ? 99 : n;
}

/** Compara dos grups per divisió i, dins la divisió, per lletra. */
export function comparaGrups(
	a: { divisio: string | null | undefined; grup: string | null | undefined },
	b: { divisio: string | null | undefined; grup: string | null | undefined }
): number {
	return (
		ordreDivisio(a.divisio) - ordreDivisio(b.divisio) ||
		clauDivisio(a.divisio).localeCompare(clauDivisio(b.divisio)) ||
		clauNomGrup(a.grup).localeCompare(clauNomGrup(b.grup))
	);
}
