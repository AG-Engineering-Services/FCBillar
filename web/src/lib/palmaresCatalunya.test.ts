import { describe, expect, it } from 'vitest';
import { deLaModalitat, palmaresCatalunya, recomptePerMena, type MedallaQH, type PodiWeb } from './palmaresCatalunya';

const web = (p: Partial<PodiWeb>): PodiWeb => ({
	openId: 1,
	nom: 'Campionat de Catalunya',
	categoria: 'HONOR',
	modalitat: 1,
	tipus: 'campionat',
	temporada: '2019-2020',
	posicio: 1,
	club: 'C.B.VIC',
	...p
});
const qh = (m: Partial<MedallaQH>): MedallaQH => ({
	competicio: 'Tres bandes',
	categoria: 'honor',
	edicio: '2019-20',
	posicio: 1,
	lloc: 'C.B. Vic',
	...m
});

describe('palmaresCatalunya', () => {
	it('un títol que surt a les dues fonts compta un cop, amb el de la web', () => {
		const r = palmaresCatalunya([web({})], [qh({})]);
		expect(r).toHaveLength(1);
		expect(r[0].entries).toEqual([
			{ tipus: 'campionat', nom: 'Tres bandes', modalitat: 1, categoria: 'honor', posicio: 1, club: 'C.B.VIC', openId: 1 }
		]);
	});

	it('la mateixa temporada, modalitat i lloc en una altra categoria són dos títols', () => {
		const r = palmaresCatalunya([web({ categoria: '1a' })], [qh({ categoria: 'júnior' })]);
		expect(r[0].entries.map((e) => e.categoria)).toEqual(['1a', 'júnior']);
	});

	it('júnior i JUNIOR són la mateixa categoria', () => {
		const r = palmaresCatalunya([web({ categoria: 'JUNIOR' })], [qh({ categoria: 'júnior' })]);
		expect(r[0].entries).toHaveLength(1);
	});

	it("els tercers llocs i els opens de la web s'hi afegeixen; els anys antics venen del Quadre d'Honor", () => {
		const r = palmaresCatalunya(
			[web({ posicio: 3, temporada: '2016-2017' }), web({ tipus: 'open', nom: 'OPEN MATARÓ', categoria: null, modalitat: 1, temporada: '2016-2017', posicio: 2, openId: 7 })],
			[qh({ edicio: '1983-84', categoria: '2a', lloc: 'C.B. Sant Martí' })]
		);
		expect(r.map((g) => g.temporada)).toEqual(['2016-17', '1983-84']);
		expect(r[0].entries.map((e) => [e.tipus, e.posicio])).toEqual([
			['campionat', 3],
			['open', 2]
		]);
		expect(r[1].entries[0]).toMatchObject({ nom: 'Tres bandes', categoria: '2a', club: 'C.B. Sant Martí', openId: null });
	});

	it("l'absoluta del Quadre d'Honor no mostra categoria", () => {
		const r = palmaresCatalunya([], [qh({ competicio: 'Biatló', categoria: 'absolut' })]);
		expect(r[0].entries[0].categoria).toBe('');
	});
});

describe('recomptePerMena', () => {
	it('separa campionats i opens i deixa fora les menes buides', () => {
		const g = palmaresCatalunya(
			[web({ posicio: 3 }), web({ tipus: 'open', nom: 'OPEN LLINARS', categoria: null, posicio: 1, openId: 9 })],
			[qh({ edicio: '1983-84' }), qh({ edicio: '1990-91', posicio: 2 })]
		);
		expect(recomptePerMena(g)).toEqual([
			{ tipus: 'campionat', primers: 1, segons: 1, tercers: 1 },
			{ tipus: 'open', primers: 1, segons: 0, tercers: 0 }
		]);
	});
});

describe('deLaModalitat', () => {
	it('deixa la modalitat triada i el que no té pestanya', () => {
		const g = palmaresCatalunya(
			[web({}), web({ modalitat: 2, openId: 2 })],
			[qh({ competicio: 'Chapó', categoria: '1a' }), qh({ competicio: 'Quadre 47/2', categoria: '3a' })]
		);
		const r = deLaModalitat(g, 1, new Set([1, 2]));
		expect(r[0].entries.map((e) => e.nom)).toEqual(['Chapó', 'Quadre 47/2', 'Tres bandes']);
	});
});
