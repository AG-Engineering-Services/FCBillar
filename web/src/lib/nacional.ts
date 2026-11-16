export interface NacionalJugadorRow {
	temporada: string;
	divisio: string;
	posicio: number;
	jugador: string;
	equip: string;
	jugades: number;
	guanyades: number;
	empatades: number;
	perdudes: number;
	caramboles: number;
	entrades: number;
	mitjana: number | null;
	punts: number | null;
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

export function llocNacional(posicio: number): string {
	return `${posicio}º`;
}

/** Temporada més recent primer; dins la temporada, Honor abans que Primera i Segona. */
export function ordenaNacional<T extends { temporada: string; divisio: string; posicio: number }>(
	rows: T[]
): T[] {
	const ordreDiv = (d: string) => ['honor', '1', '2'].indexOf(d);
	return [...rows].sort(
		(a, b) =>
			b.temporada.localeCompare(a.temporada) ||
			ordreDiv(a.divisio) - ordreDiv(b.divisio) ||
			a.posicio - b.posicio
	);
}
