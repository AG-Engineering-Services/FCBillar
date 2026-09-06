import { describe, expect, it } from 'vitest';
import { clauDivisio, clauGrup, clauNomGrup, comparaGrups, ordreDivisio } from './divisions';

describe('clauDivisio', () => {
	it('iguala com escriu la intranet i com escriu el calendari', () => {
		// El cas que va sortir el 6 de setembre de 2026: la pàgina de lliga
		// ensenyava dues divisions d'Honor, la publicada i la del PDF.
		expect(clauDivisio('HONOR')).toBe(clauDivisio('Honor'));
		expect(clauDivisio('1a DIVISIÓ')).toBe(clauDivisio('1a'));
	});

	it('treu el «DIVISIÓ» amb accent i sense', () => {
		expect(clauDivisio('2a DIVISIÓ')).toBe('2A');
		expect(clauDivisio('2a DIVISIO')).toBe('2A');
		expect(clauDivisio('2ª Divisió de tres bandes')).toBe('2ª');
	});

	it('no s’inventa res amb el que no hi és', () => {
		expect(clauDivisio(null)).toBe('');
		expect(clauDivisio(undefined)).toBe('');
		expect(clauDivisio('   ')).toBe('');
	});

	it('no confon dues divisions diferents', () => {
		expect(clauDivisio('1a')).not.toBe(clauDivisio('2a'));
		expect(clauDivisio('Honor')).not.toBe(clauDivisio('1a'));
	});
});

describe('clauNomGrup', () => {
	it('iguala «GRUP A» i «A»', () => {
		expect(clauNomGrup('GRUP A')).toBe('A');
		expect(clauNomGrup('Grup A')).toBe('A');
		expect(clauNomGrup('A')).toBe('A');
	});

	it('no toca els noms que no comencen per «grup»', () => {
		expect(clauNomGrup('FINAL')).toBe('FINAL');
	});
});

describe('clauGrup', () => {
	it('reconeix el mateix grup dit de les dues maneres', () => {
		expect(clauGrup('HONOR', 'GRUP A')).toBe(clauGrup('Honor', 'A'));
		expect(clauGrup('1a DIVISIÓ', 'GRUP B')).toBe(clauGrup('1a', 'B'));
	});

	it('distingeix els grups d’una mateixa divisió', () => {
		expect(clauGrup('Honor', 'A')).not.toBe(clauGrup('Honor', 'B'));
	});

	it('distingeix el mateix grup de divisions diferents', () => {
		expect(clauGrup('1a', 'A')).not.toBe(clauGrup('2a', 'A'));
	});
});

describe('ordreDivisio', () => {
	it('posa l’Honor davant de tot', () => {
		expect(ordreDivisio('Honor')).toBeLessThan(ordreDivisio('1a'));
		expect(ordreDivisio('HONOR')).toBeLessThan(ordreDivisio('1a DIVISIÓ'));
	});

	it('ordena les numerades pel número', () => {
		const noms = ['4a', '2a', 'Honor', '3a', '1a'];
		expect([...noms].sort((a, b) => ordreDivisio(a) - ordreDivisio(b))).toEqual([
			'Honor',
			'1a',
			'2a',
			'3a',
			'4a'
		]);
	});

	it('deixa al final el que no sap col·locar', () => {
		expect(ordreDivisio("L'Amistat")).toBe(99);
		expect(ordreDivisio(null)).toBe(99);
	});
});

describe('comparaGrups', () => {
	it('ordena la lliga sencera com la classifica la federació', () => {
		const grups = [
			{ divisio: '4a', grup: 'D' },
			{ divisio: '1a DIVISIÓ', grup: 'GRUP B' },
			{ divisio: 'Honor', grup: 'B' },
			{ divisio: 'HONOR', grup: 'GRUP A' },
			{ divisio: '1a', grup: 'A' },
			{ divisio: '4a', grup: 'A' }
		];

		expect([...grups].sort(comparaGrups).map((g) => `${g.divisio} ${g.grup}`)).toEqual([
			'HONOR GRUP A',
			'Honor B',
			'1a A',
			'1a DIVISIÓ GRUP B',
			'4a A',
			'4a D'
		]);
	});
});
