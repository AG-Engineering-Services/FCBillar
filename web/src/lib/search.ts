// Normalització i coincidència de text per a cerques (jugadors i clubs).

/** Treu accents i passa a minúscules. */
export function norm(s: string): string {
	return s
		.normalize('NFD')
		.replace(/\p{Diacritic}/gu, '')
		.toLowerCase();
}

// Paraules genèriques dels noms de club que no distingeixen res: "Club",
// "Billar" i les abreviatures habituals (C.B. = Club Billar, B.C. = Billar
// Club) + connectors. Així "C.B.Banyoles", "Club Billar Banyoles",
// "Billar Banyoles" i "Club Banyoles" es redueixen tots a la clau "banyoles".
const CLUB_STOPWORDS = new Set([
	'club',
	'billar',
	'billars',
	'billares',
	'billard',
	'billards',
	'cb',
	'bc',
	'c',
	'b',
	'de',
	'del',
	'dels',
	'la',
	'el',
	'les',
	'els',
	'l',
	'd',
	'i'
]);

/** Clau distintiva d'un nom de club: sense accents, sense puntuació i sense les
 *  paraules genèriques. Buida si el text només conté paraules genèriques. */
export function clubKey(s: string): string {
	return norm(s)
		.replace(/[.\-_/&]/g, ' ')
		.replace(/[^a-z0-9 ]/g, '')
		.split(/\s+/)
		.filter((w) => w && !CLUB_STOPWORDS.has(w))
		.join(' ');
}

/** Cert si el club coincideix amb la consulta, tant per subcadena directa
 *  (manté "C.B." etc.) com per clau distintiva (ignora "Club"/"Billar"). */
export function clubMatches(club: string | null | undefined, query: string): boolean {
	if (!club) return false;
	const nq = norm(query.trim());
	if (!nq) return false;
	if (norm(club).includes(nq)) return true;
	const qk = clubKey(query);
	if (!qk) return false;
	return clubKey(club).includes(qk);
}

/** Cert si el nom de jugador conté la consulta (sense accents). */
export function playerMatches(nom: string | null | undefined, query: string): boolean {
	if (!nom) return false;
	const nq = norm(query.trim());
	if (!nq) return false;
	return norm(nom).includes(nq);
}
