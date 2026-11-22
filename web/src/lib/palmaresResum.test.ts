import { describe, expect, it } from 'vitest';
import { LLINDAR_RESUM, resumMedalles, resumPerModalitat } from './palmaresResum';

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

describe('resumPerModalitat', () => {
	it('separa per modalitat i, a Catalunya, deixa només la categoria', () => {
		const r = resumPerModalitat([
			{ competicio: 'Tres bandes', categoria: 'honor', posicio: 1 },
			{ competicio: 'Tres bandes', categoria: '1a', posicio: 2 },
			{ competicio: 'Lliure', categoria: 'júnior', posicio: 1 },
			{ competicio: "Campionat d'Europa tres bandes", categoria: 'absolut', posicio: 3 }
		]);
		expect(r.map((g) => g.modalitat)).toEqual(['Tres Bandes', 'Lliure']);
		expect(r[0].resum.perCompeticio.map((f) => f.competicio)).toEqual(['honor', '1a', "Campionat d'Europa tres bandes"]);
		expect(r[1].resum.perCompeticio[0].competicio).toBe('júnior');
	});
});
