// Quins quatre jugadors d'un club formen UN equip concret.
//
// L'ordre del club el fixa la federació i diu on pot jugar cadascú. Que el B
// acabi sent el 5è, 6è, 7è i 8è és la CONSEQÜÈNCIA de repartir de dalt a baix
// —l'A s'endú l'1, 2 i 3, que no poden jugar enlloc més, i el millor que li
// queda—, no la regla. La diferència importa: els trams no són tots de quatre.

import { describe, expect, it } from 'vitest';

import { lletraEquip, potJugarA, repartiment, titulars } from './titulars';

const fins = (n: number) => Array.from({ length: n }, (_, i) => i + 1);

describe('lletraEquip', () => {
	it.each([
		['C.B. MATARO "B"', 'B'],
		['C.B. MONFORTE "E"', 'E'],
		['C.B. BANYOLES "A"', 'A']
	])('%s és l’equip %s', (nom, lletra) => {
		expect(lletraEquip(nom)).toBe(lletra);
	});

	it('un club amb un sol equip és l’A: és l’únic que té', () => {
		expect(lletraEquip('C.B. BORGES')).toBe('A');
	});

	it('la classificació els escriu sense cometes i també val', () => {
		expect(lletraEquip('C.B.MANRESA A')).toBe('A');
	});
});

describe('qui pot jugar a cada equip', () => {
	it('del 1r al 3r, només a l’A', () => {
		for (const p of [1, 2, 3]) {
			expect(potJugarA(p, 'A')).toBe(true);
			expect(potJugarA(p, 'B')).toBe(false);
		}
	});

	it('del 4t al 8è, A i B', () => {
		expect([potJugarA(4, 'B'), potJugarA(8, 'B'), potJugarA(8, 'C')]).toEqual([
			true,
			true,
			false
		]);
	});

	it('del 17è endavant, a tots', () => {
		expect(['A', 'B', 'C', 'D', 'E'].every((l) => potJugarA(17, l))).toBe(true);
	});
});

describe('repartiment', () => {
	it('amb el club sencer surten els blocs de sempre', () => {
		expect(repartiment('A', fins(24))).toEqual([1, 2, 3, 4]);
		expect(repartiment('B', fins(24))).toEqual([5, 6, 7, 8]);
		expect(repartiment('C', fins(24))).toEqual([9, 10, 11, 12]);
		expect(repartiment('D', fins(24))).toEqual([13, 14, 15, 16]);
		expect(repartiment('E', fins(24))).toEqual([17, 18, 19, 20]);
	});

	it('el B comença al 5è tot i que el 4t hi podria jugar', () => {
		expect(potJugarA(4, 'B')).toBe(true);
		expect(repartiment('B', fins(24))).not.toContain(4);
	});

	it('un club curt de gent no completa els equips de baix', () => {
		expect(repartiment('C', fins(10))).toEqual([9, 10]);
		expect(repartiment('D', fins(10))).toEqual([]);
	});

	it('els números són els que publica la federació, no es renumeren', () => {
		const sensequatre = [1, 2, 3, 5, 6, 7, 8];
		expect(repartiment('A', sensequatre)).toEqual([1, 2, 3, 5]);
		expect(repartiment('B', sensequatre)).toEqual([6, 7, 8]);
	});

	it('una lletra que no coneixem no dona ningú', () => {
		expect(repartiment('Z', fins(24))).toEqual([]);
	});
});

describe('titulars', () => {
	const plantilla = fins(12).map((posicio) => ({ jugador: `Jugador ${posicio}`, posicio }));

	it('el B són el 5è, 6è, 7è i 8è', () => {
		expect([...titulars('C.B. MATARO "B"', plantilla)]).toEqual([
			'Jugador 5',
			'Jugador 6',
			'Jugador 7',
			'Jugador 8'
		]);
	});

	it('l’A són els quatre primers', () => {
		expect([...titulars('C.B. MATARO "A"', plantilla)]).toEqual([
			'Jugador 1',
			'Jugador 2',
			'Jugador 3',
			'Jugador 4'
		]);
	});

	it('si el club no té prou gent, se’n marquen menys i no peta', () => {
		expect(titulars('X "D"', plantilla).size).toBe(0);
		expect(titulars('X "C"', plantilla).size).toBe(4);
	});

	it('amb la llista buida no en marca cap', () => {
		expect(titulars('X "A"', []).size).toBe(0);
	});
});
