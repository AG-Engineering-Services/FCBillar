import { describe, expect, it } from 'vitest';
import { deMissatge, hiHaNous, recents, FINESTRA_MS } from './avisosRebuts';

describe('avisos rebuts', () => {
	it('separa les línies del cos i treu les buides', () => {
		const a = deMissatge(
			{ title: 'Open · 2 resultats', body: '★ Grup AC: A 27-28 B (50 e.)\n\nGrup AB: C 18-19 D (50 e.)', url: '/opens/directe/223' },
			1000
		);
		expect(a.linies).toEqual(['★ Grup AC: A 27-28 B (50 e.)', 'Grup AB: C 18-19 D (50 e.)']);
		expect(a.url).toBe('/opens/directe/223');
	});

	it("només els de l'última hora, del més nou al més vell", () => {
		const ara = 10 * FINESTRA_MS;
		const vell = deMissatge({ body: 'x' }, ara - FINESTRA_MS - 1);
		const fa10 = deMissatge({ body: 'y' }, ara - 10 * 60000);
		const fa1 = deMissatge({ body: 'z' }, ara - 60000);
		expect(recents([vell, fa10, fa1], ara).map((a) => a.linies[0])).toEqual(['z', 'y']);
	});

	it("surt sol només si n'ha arribat algun després de tancar-lo", () => {
		const a = deMissatge({ body: 'x' }, 5000);
		expect(hiHaNous([a], 4000)).toBe(true);
		expect(hiHaNous([a], 5000)).toBe(false);
		expect(hiHaNous([], 0)).toBe(false);
	});
});
