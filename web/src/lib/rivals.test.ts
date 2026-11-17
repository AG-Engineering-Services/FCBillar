import { describe, expect, it } from 'vitest';

import { lletres, rivalCoincideix, suggereixRivals, type Rival } from './rivals';

const rivals: Rival[] = [
	{ key: '716', nom: 'GARCIA MARTINEZ, RICARDO', partides: 2 },
	{ key: '995', nom: 'SEGURA, FRANCESC', partides: 5 },
	{ key: '12', nom: 'Martínez Gil, Jordi', partides: 1 },
	{ key: 'Pere Garriga', nom: 'Pere Garriga', partides: 3 }
];

describe('rivalCoincideix', () => {
	it.each([
		['GARCIA MARTINEZ, RICARDO', 'ric garc'],
		['GARCIA MARTINEZ, RICARDO', 'garcia r'],
		['Martínez Gil, Jordi', 'martinez'],
		['Martínez Gil, Jordi', 'MARTÍN'],
		['SEGURA, FRANCESC', 'seg,']
	])('%s coincideix amb «%s»', (nom, q) => {
		expect(rivalCoincideix(nom, q)).toBe(true);
	});

	it('cada paraula ha de començar una paraula del nom', () => {
		expect(rivalCoincideix('SEGURA, FRANCESC', 'gura')).toBe(false);
		expect(rivalCoincideix('SEGURA, FRANCESC', 'seg pere')).toBe(false);
	});
});

describe('suggereixRivals', () => {
	it('no suggereix res fins a la tercera lletra', () => {
		expect(lletres(' g. a ')).toBe(2);
		expect(suggereixRivals(rivals, 'ga')).toEqual([]);
		expect(suggereixRivals(rivals, 'gar').map((r) => r.key)).toEqual(['716', 'Pere Garriga']);
	});

	it('posa primer qui comença com la consulta', () => {
		expect(suggereixRivals(rivals, 'mart').map((r) => r.key)).toEqual(['12', '716']);
	});
});
