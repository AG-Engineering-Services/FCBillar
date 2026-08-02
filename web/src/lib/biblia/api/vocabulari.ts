/**
 * Traducció al català del vocabulari de billiard-bible.com (당구백서).
 * Es conserva el terme coreà original com a referència.
 */

/** Famílies de tir. L'índex coincideix amb el valor `ball_choice`. */
export const FAMILIES = [
	{ idx: 0, ca: 'Totes', ko: '전체' },
	{ idx: 1, ca: 'Bàsica', ko: '기본구' },
	{ idx: 2, ca: 'Difícil', ko: '난구' },
	{ idx: 3, ca: 'Endarrere', ko: '뒤돌리기' },
	{ idx: 4, ca: 'De costat', ko: '옆돌리기' },
	{ idx: 5, ca: 'Endavant', ko: '앞돌리기' },
	{ idx: 6, ca: 'Tocar la bola fina', ko: '비껴치기' },
	{ idx: 7, ca: 'Gran rotació', ko: '대회전' },
	{ idx: 8, ca: 'Vertical', ko: '세워치기' },
	{ idx: 9, ca: 'Doble banda', ko: '더블쿠션' },
	{ idx: 10, ca: 'Travessa', ko: '횡단' },
	{ idx: 11, ca: 'Reverse', ko: '리버스' },
	{ idx: 12, ca: 'Tornada', ko: '되돌아오기' },
	{ idx: 13, ca: 'Bounding', ko: '바운딩' },
	{ idx: 14, ca: 'Bricol', ko: '뱅크샷' }
] as const;

export function familiaCat(idx: number): string {
	return FAMILIES.find((f) => f.idx === idx)?.ca ?? '—';
}

export function familiaKo(idx: number): string {
	return FAMILIES.find((f) => f.idx === idx)?.ko ?? '';
}

/** Flags de classificació d'una tirada. */
export const FLAGS = {
	posicio: { ca: 'Posició', ko: '포지션' },
	defensa: { ca: 'Defensa', ko: '디펜스' },
	evitarKiss: { ca: 'Evitar retruc', ko: '키스주의' },
	dificil: { ca: 'Difícil', ko: '난구' }
} as const;

/** Etiquetes generals de la interfície. */
export const TEXT = {
	titol: 'Bíblia del Billar',
	subtitol: 'Tirades de billar a tres bandes',
	tirsPro: 'Tirs pro',
	tirsAnalitzats: 'Tirs analitzats',
	proKo: '프로샷',
	analisiKo: '분석샷',
	jugador: 'Jugador',
	totsJugadors: 'Tots els jugadors',
	familia: 'Família',
	cerca: 'Cerca',
	marcadors: 'Marcadors',
	ambVideo: 'Amb vídeo',
	tornaEnrere: 'Torna',
	seguent: 'Següent',
	anterior: 'Anterior',
	pagina: 'Pàgina',
	de: 'de',
	capResultat: 'Cap tirada amb aquests filtres.',
	tiradesTrobades: 'tirades'
} as const;
