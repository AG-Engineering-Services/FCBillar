// Helpers de format compartits entre pàgines.

/** Data ISO (YYYY-MM-DD) → dd/mm/aa. Retorna l'original si no encaixa. */
export function fmtDate(d: string | null | undefined): string {
	if (!d) return '—';
	const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d);
	if (!m) return d;
	return `${m[3]}/${m[2]}/${m[1].slice(2)}`;
}

/** Mitjana = caramboles / entrades, a 3 decimals. */
export function mitjana(car: number | null | undefined, entrades: number | null | undefined): number | null {
	if (car == null || !entrades) return null;
	return car / entrades;
}

export function fmtMitjana(v: number | null | undefined): string {
	return v != null ? v.toFixed(3) : '—';
}

export type Badge = { label: string; tone: 'win' | 'lose' | 'tie' };

/** Qui guanya una partida: 'L' (local), 'V' (visitant) o 'T' (empat); null si no hi ha resultat. */
export function winnerSide(g: {
	cara1: number | null;
	cara2: number | null;
}): 'L' | 'V' | 'T' | null {
	if (g.cara1 == null || g.cara2 == null) return null;
	if (g.cara1 === g.cara2) return 'T';
	return g.cara1 > g.cara2 ? 'L' : 'V';
}

/** Badge "W" del guanyador. side: a quin costat és la cel·la ('L' local, 'V' visitant). */
export function winnerBadge(
	g: { cara1: number | null; cara2: number | null },
	side: 'L' | 'V'
): Badge | null {
	const w = winnerSide(g);
	if (w === null) return null;
	if (w === 'T') return { label: 'E', tone: 'tie' };
	return w === side ? { label: 'W', tone: 'win' } : null;
}
