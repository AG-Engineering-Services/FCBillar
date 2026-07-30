/**
 * Mapatge entre les coordenades de billiard-bible.com i les coordenades
 * de diamants del component Billar.
 *
 * Al seu sistema la superfície de joc és 500 × 250 (2:1), amb l'origen a
 * dalt a l'esquerra (y creix cap avall). El nostre és 8 × 4 diamants amb
 * l'origen a baix a l'esquerra (y creix cap amunt), per això invertim y.
 */

import { DIAMANTS_X, DIAMANTS_Y } from './geometria';
import type { Bola } from './tipus';

/** Amplada del camp de joc en coordenades de billiard-bible. */
export const BB_AMPLE = 500;
/** Alçada del camp de joc en coordenades de billiard-bible. */
export const BB_ALT = 250;

/** Converteix un punt (x,y) de billiard-bible a coordenades de diamants. */
export function bbADiamant(x: number, y: number): Bola {
	return [(x / BB_AMPLE) * DIAMANTS_X, DIAMANTS_Y - (y / BB_ALT) * DIAMANTS_Y];
}

/** Un fotograma d'una pista d'animació, ja en coordenades de diamants. */
export interface Fotograma {
	frame: number;
	x: number;
	y: number;
}

/**
 * Parseja una cadena de posicions "frame|x|y|frame|x|y|..." (coordenades
 * de billiard-bible) a una llista de fotogrames en coordenades de diamants.
 */
export function parseTraca(s: string | null | undefined): Fotograma[] {
	if (!s) return [];
	const parts = s.split('|');
	const out: Fotograma[] = [];
	for (let i = 0; i + 2 < parts.length; i += 3) {
		const frame = Number(parts[i]);
		const bx = Number(parts[i + 1]);
		const by = Number(parts[i + 2]);
		if (Number.isNaN(frame) || Number.isNaN(bx) || Number.isNaN(by)) continue;
		const [x, y] = bbADiamant(bx, by);
		out.push({ frame, x, y });
	}
	return out;
}

/** Interpola la posició d'una pista en un fotograma donat. */
export function posicioAlFrame(traca: Fotograma[], frame: number): { x: number; y: number } | null {
	if (traca.length === 0) return null;
	if (frame <= traca[0].frame) return { x: traca[0].x, y: traca[0].y };
	const darrer = traca[traca.length - 1];
	if (frame >= darrer.frame) return { x: darrer.x, y: darrer.y };
	for (let i = 0; i < traca.length - 1; i++) {
		const a = traca[i];
		const b = traca[i + 1];
		if (frame >= a.frame && frame <= b.frame) {
			const t = b.frame === a.frame ? 0 : (frame - a.frame) / (b.frame - a.frame);
			return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
		}
	}
	return { x: darrer.x, y: darrer.y };
}
