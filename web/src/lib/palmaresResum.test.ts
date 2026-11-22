import { describe, expect, it } from 'vitest';
import { LLINDAR_RESUM, resumMedalles } from './palmaresResum';

describe('resumMedalles', () => {
	it('compta per lloc i per competició, amb la categoria no absoluta al nom', () => {
		const r = resumMedalles([
			{ competicio: 'Lliure', categoria: 'absolut', posicio: 1 },
			{ competicio: 'Lliure', categoria: 'absolut', posicio: 1 },
			{ competicio: 'Lliure', categoria: 'absolut', posicio: 3 },
			{ competicio: 'Quadre 71/2', categoria: 'absolut', posicio: 2 },
			{ competicio: 'Quadre 47/2', categoria: 'júnior', posicio: 1 },
		]);
		expect([r.primers, r.segons, r.tercers, r.total]).toEqual([3, 1, 1, 5]);
		expect(r.perCompeticio.map((f) => [f.competicio, f.primers, f.segons, f.tercers])).toEqual([
			['Lliure', 2, 0, 1],
			['Quadre 47/2 · júnior', 1, 0, 0],
			['Quadre 71/2', 0, 1, 0],
		]);
	});

	it('sense medalles, tot a zero', () => {
		const r = resumMedalles([]);
		expect(r.total).toBe(0);
		expect(r.perCompeticio).toEqual([]);
	});

	it('el llindar és de més de sis medalles', () => {
		expect(LLINDAR_RESUM).toBe(6);
	});
});
