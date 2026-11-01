// La data d'un rànquing es llegeix de la taula `rankings`: la numeració no és
// regular (el 126 és l'octubre de 2026) i no se'n pot deduir el mes.
export type DatesRanquing = Map<number, [number, number]>;

export function datesRanquing(
	files: { num_seq: number; any_pub: number | null; mes_pub: number | null }[]
): DatesRanquing {
	const dates: DatesRanquing = new Map();
	for (const f of files) if (f.any_pub != null && f.mes_pub != null) dates.set(f.num_seq, [f.any_pub, f.mes_pub]);
	return dates;
}

/** Any i mes d'un rànquing. Sense data publicada, compta enrere des del 122 (juny de 2026). */
export function ymDelRanquing(seq: number, dates: DatesRanquing): [number, number] {
	const publicat = dates.get(seq);
	if (publicat) return publicat;
	let y = 2026,
		m = 6;
	for (let i = 0; i < 122 - seq; i++) {
		m--;
		if (m === 0) {
			y--;
			m = 12;
		}
		if (m === 8) m = 7;
	}
	return [y, m];
}
