/**
 * Geometria de la taula de billar a tres bandes.
 *
 * Sistema de coordenades intern EN DIAMANTS (no en píxels):
 *   - x va de 0 a 8 al llarg de la banda llarga.
 *   - y va de 0 a 4 al llarg de la banda curta.
 *   - (0,0) és el racó inferior esquerre; y creix cap amunt.
 *
 * L'espai SVG ("píxels") té l'origen a dalt a l'esquerra i y creix cap avall,
 * per això la conversió inverteix l'eix y.
 *
 * Tota conversió de coordenades del projecte ha de passar per aquí:
 * `diamantAPixel` i `pixelADiamant` són pures i inverses l'una de l'altra.
 */

/** Unitats SVG per cada diamant. */
export const ESCALA = 50;

/**
 * Radi d'una bola en diamants, proporcional a la mida real d'una bola de
 * billar (≈61,5 mm) respecte a la superfície de joc (2,84 m = 8 diamants).
 * Amb aquest radi, dues boles que es toquen a les dades no se superposen.
 */
export const RADI_BOLA_DIAMANTS = 0.08;

/** Amplada del marc negre (rail), en unitats SVG. Proporció realista (~5%). */
export const MARGE = 22;

/** Nombre de diamants a la banda llarga (eix x). */
export const DIAMANTS_X = 8;

/** Nombre de diamants a la banda curta (eix y). */
export const DIAMANTS_Y = 4;

/** Amplada de la superfície de joc, en unitats SVG. */
export const AMPLADA_JOC = DIAMANTS_X * ESCALA;

/** Alçada de la superfície de joc, en unitats SVG. */
export const ALCADA_JOC = DIAMANTS_Y * ESCALA;

/** Amplada total del viewBox (joc + dos marcs). */
export const AMPLADA_VIEWBOX = AMPLADA_JOC + 2 * MARGE;

/** Alçada total del viewBox (joc + dos marcs). */
export const ALCADA_VIEWBOX = ALCADA_JOC + 2 * MARGE;

/** Un punt en coordenades de diamants. */
export interface PuntDiamant {
	x: number;
	y: number;
}

/** Un punt en coordenades SVG ("píxels"). */
export interface PuntPixel {
	px: number;
	py: number;
}

/**
 * Converteix coordenades de diamants a coordenades SVG.
 * Funció pura: mateix input → mateix output, sense efectes secundaris.
 */
export function diamantAPixel(x: number, y: number): PuntPixel {
	return {
		px: MARGE + x * ESCALA,
		py: MARGE + (DIAMANTS_Y - y) * ESCALA
	};
}

/**
 * Converteix coordenades SVG a coordenades de diamants.
 * És la inversa exacta de `diamantAPixel`.
 */
export function pixelADiamant(px: number, py: number): PuntDiamant {
	return {
		x: (px - MARGE) / ESCALA,
		y: DIAMANTS_Y - (py - MARGE) / ESCALA
	};
}

/**
 * Ajusta un valor a la graella d'una fracció de diamant (per defecte 1/4).
 * Útil en mode editor quan es prem Shift.
 */
export function ajustaAGraella(valor: number, fraccio = 0.25): number {
	return Math.round(valor / fraccio) * fraccio;
}

/** Limita un valor dins d'un rang tancat [min, max]. */
export function limita(valor: number, min: number, max: number): number {
	return Math.min(max, Math.max(min, valor));
}

/**
 * Limita un punt de diamants a la superfície de joc (x∈[0,8], y∈[0,4]).
 */
export function limitaADins(x: number, y: number): PuntDiamant {
	return {
		x: limita(x, 0, DIAMANTS_X),
		y: limita(y, 0, DIAMANTS_Y)
	};
}
