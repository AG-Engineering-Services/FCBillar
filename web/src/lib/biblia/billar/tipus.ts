/** Tipus compartits per representar una tirada de billar a tres bandes. */

/** Posició d'una bola en coordenades de diamants: [x, y]. */
export type Bola = [number, number];

/** Naturalesa d'un punt de la trajectòria. */
export type TipusPunt = 'banda' | 'bola' | 'arribada';

/** Un punt de contacte de la trajectòria. */
export interface PuntTraj {
	x: number;
	y: number;
	tipus: TipusPunt;
}

/**
 * Les tres boles:
 *  - b1: jugadora (blanca)
 *  - b2: groga
 *  - b3: vermella
 */
export interface Boles {
	b1: Bola;
	b2: Bola;
	b3: Bola;
}

/** Estat complet que emet el component en mode editor. */
export interface EstatTirada {
	boles: Boles;
	trajectoria: PuntTraj[];
}
