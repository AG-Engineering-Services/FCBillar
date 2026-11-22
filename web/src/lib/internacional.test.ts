import { describe, expect, it } from 'vitest';
import { agrupaUmb, disciplinaDeNom, resultatSets, resultatUmb, textSets, type UmbPartidaRow } from './internacional';

function p(o: Partial<UmbPartidaRow>): UmbPartidaRow {
	return {
		fcb_id: '1', esdeveniment_id: 1, esdeveniment: 'World Cup', disciplina: '3 bandes', lloc: 'Veghel',
		data_inici: '2024-01-10', fase: 'PQ', grup: '', ordre: 1, caramboles: 30, entrades: 20, punts: 2, serie: 5,
		rival: 'X', rival_caramboles: 20, rival_punts: 0, rival_fcb_id: null, ...o
	};
}

describe('internacional', () => {
	it('decideix pels punts de partida i, si no n’hi ha, per les caramboles', () => {
		expect(resultatUmb({ punts: 1, rival_punts: 1, caramboles: 40, rival_caramboles: 30 })).toBe('E');
		expect(resultatUmb({ punts: null, rival_punts: null, caramboles: 25, rival_caramboles: 30 })).toBe('P');
	});
	it('agrupa per prova, de la més nova a la més antiga, amb resum i classificació', () => {
		const proves = agrupaUmb(
			[p({ ordre: 2, punts: 0, rival_punts: 2, caramboles: 20, entrades: 30 }), p({}), p({ esdeveniment_id: 2, data_inici: '2025-03-01' })],
			[
				{ fcb_id: '1', esdeveniment_id: 1, esdeveniment: 'World Cup', lloc: null, data_inici: '2024-01-10', posicio: 17, ronda: 'Q', mitjana: 1.2, participants: 150 },
				{ fcb_id: '1', esdeveniment_id: 3, esdeveniment: 'Europeu', lloc: null, data_inici: '2019-05-01', posicio: 5, ronda: null, mitjana: 1, participants: 24 }
			]
		);
		expect(proves.map((x) => x.id)).toEqual([2, 1, 3]);
		expect(proves[2].pj).toBe(0);
		const v = proves[1];
		expect([v.pj, v.g, v.e, v.p]).toEqual([2, 1, 0, 1]);
		expect(v.partides.map((x) => x.ordre)).toEqual([1, 2]);
		expect(v.mitjana).toBe(1);
		expect(v.classificacio?.posicio).toBe(17);
		expect(v.any).toBe('2024');
	});
});

describe('sets', () => {
	const sets = { sets: '9/11,4/7,15/11,15/4,15/7', rival_sets: '15/11,15/8,10/10,9/4,10/6' };
	it('compta els sets pels caramboles de cada set', () => {
		expect(resultatSets(sets)).toEqual({ jo: 3, rival: 2, detall: ['9-15', '4-15', '15-10', '15-9', '15-10'] });
		expect(textSets(sets)).toBe('Sets 3-2 · 9-15, 4-15, 15-10, 15-9, 15-10');
	});
	it('no es a sets si falten les columnes o no quadren', () => {
		expect(resultatSets({})).toBeNull();
		expect(resultatSets({ sets: null, rival_sets: null })).toBeNull();
		expect(resultatSets({ sets: '1/2,3/4', rival_sets: '1/2' })).toBeNull();
		expect(textSets({ sets: 'x', rival_sets: 'y' })).toBe('');
	});
	it('sense punts, guanya qui guanya mes sets encara que faci menys caramboles', () => {
		expect(resultatUmb({ punts: null, rival_punts: null, caramboles: 53, rival_caramboles: 59, ...sets })).toBe('G');
		expect(resultatUmb({ punts: 0, rival_punts: 2, caramboles: 53, rival_caramboles: 59, ...sets })).toBe('P');
	});
});

describe('disciplinaDeNom', () => {
	it('reconeix el «(3C)» dels World Games i les proves de tres bandes que no ho diuen', () => {
		expect(disciplinaDeNom('The World Games 2013 (3C)')).toBe('3 bandes');
		expect(disciplinaDeNom('Lausanne Billard Masters')).toBe('3 bandes');
		expect(disciplinaDeNom('International Invitation Tournament Crystal Kelly')).toBe('3 bandes');
		expect(disciplinaDeNom('European Cup Final Club Team Carom Series')).toBeNull();
	});
});
