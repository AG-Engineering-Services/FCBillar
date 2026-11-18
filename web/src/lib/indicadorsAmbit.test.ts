import { describe, expect, it } from 'vitest';
import {
	aportacionsNacional,
	aportacionsRfeb,
	aportacionsUmb,
	filtraModalitat,
	finestres,
	indicadors,
	modalitatsDe,
	temporadaActual,
	temporadaDeData
} from './indicadorsAmbit';
import { agrupaUmb, type UmbPartidaRow } from './internacional';
import type { NacionalPartidaRow, RfebIndividualRow } from './nacional';

const avui = new Date(2026, 10, 17); // novembre del 2026: temporada 2026/27

function nac(o: Partial<NacionalPartidaRow>): NacionalPartidaRow {
	return {
		fcb_id: '1', temporada: '2026-2027', divisio: 'honor', grup: '', jornada: 1, data: null, ordre_encontre: 1, ordre: 1,
		jugador: 'A', caramboles: 30, rival: 'X', caramboles_rival: 20, rival_fcb_id: null, rival_nom_fcb: null, entrades: 30,
		equip: 'E', equip_rival: 'F', punts_equip: 2, punts_rival: 0, a_casa: true, ...o
	};
}
function rfeb(o: Partial<RfebIndividualRow>): RfebIndividualRow {
	return {
		fcb_id: '1', prova_id: 'p', posicio: 3, posicio_empat: null, ronda: null, jugades: null, guanyades: null, empatades: null,
		perdudes: null, caramboles: null, entrades: null, mitjana: null, serie_major: null, temporada: '2026-2027', modalitat: '3b',
		categoria: 'absolut', tipus: 'ce', titol: 'T', lloc: null, data_inici: null, participants: 12, ...o
	};
}
function umb(o: Partial<UmbPartidaRow>): UmbPartidaRow {
	return {
		fcb_id: '1', esdeveniment_id: 1, esdeveniment: 'World Cup 3-Cushion', disciplina: '3 bandes', lloc: null, data_inici: '2026-10-10',
		fase: 'PQ', grup: '', ordre: 1, caramboles: 30, entrades: 20, punts: 2, serie: 5, rival: 'X', rival_caramboles: 20,
		rival_punts: 0, rival_fcb_id: null, ...o
	};
}

describe('temporades', () => {
	it('canvien el primer d’agost', () => {
		expect(temporadaDeData('2026-07-31')).toBe(2025);
		expect(temporadaDeData('2026-08-01')).toBe(2026);
		expect(temporadaDeData(null)).toBeNull();
		expect(temporadaActual(new Date(2026, 6, 31))).toBe(2025);
		expect(temporadaActual(new Date(2026, 7, 1))).toBe(2026);
	});
});

describe('Espanya', () => {
	it('suma les partides de la Lliga Nacional pel resultat per caramboles', () => {
		const k = indicadors(aportacionsNacional([nac({}), nac({ caramboles: 10, caramboles_rival: 30, entrades: 10 }), nac({ caramboles: 20, caramboles_rival: 20, entrades: 20 })]));
		expect([k.n, k.w, k.t, k.l, k.pct]).toEqual([3, 1, 1, 1, 33]);
		expect(k.mitjana).toBeCloseTo(60 / 60);
		expect(k.sm).toBeNull();
		expect(k.best).toBeCloseTo(1);
		expect(k.bestN).toBe(3);
	});
	it('un campionat amb jugades compta partides i G/E/P; la serie es la mes gran', () => {
		const k = indicadors(
			aportacionsRfeb([rfeb({ jugades: 5, guanyades: 3, empatades: 1, perdudes: 1, caramboles: 100, entrades: 100, serie_major: 7 }), rfeb({ jugades: 2, guanyades: 0, empatades: 0, perdudes: 2, caramboles: 20, entrades: 50, serie_major: 4 })])
		);
		expect([k.n, k.w, k.t, k.l]).toEqual([7, 3, 1, 3]);
		expect(k.sm).toBe(7);
		expect(k.mitjana).toBeCloseTo(120 / 150);
		expect(k.best).toBeNull();
		expect(k.nomesMitjana).toBe(0);
	});
	it('un campionat sense jugades nomes compta per a la mitjana', () => {
		const aps = [...aportacionsNacional([nac({})]), ...aportacionsRfeb([rfeb({ caramboles: 30, entrades: 90, modalitat: 'banda' }), rfeb({})])];
		expect(aps).toHaveLength(2);
		const k = indicadors(aps);
		expect(k.n).toBe(1);
		expect(k.nomesMitjana).toBe(1);
		expect(k.mitjana).toBeCloseTo(60 / 120);
		expect(k.best).toBeCloseTo(1);
	});
	it('sense dades, tot a zero i sense millor mitjana', () => {
		expect(indicadors([])).toMatchObject({ n: 0, mitjana: 0, sm: null, best: null, pct: 0 });
	});
});

describe('Internacional', () => {
	it('el resultat el decideixen els punts de match, no les caramboles', () => {
		const proves = agrupaUmb([umb({ caramboles: 40, rival_caramboles: 30, punts: 0, rival_punts: 2 }), umb({ ordre: 2, punts: 2, rival_punts: 0, serie: 9 })], []);
		const k = indicadors(aportacionsUmb(proves));
		expect([k.n, k.w, k.l]).toEqual([2, 1, 1]);
		expect(k.sm).toBe(9);
	});
	it('una partida a sets la guanya qui guanya mes sets', () => {
		const proves = agrupaUmb(
			[umb({ punts: null, rival_punts: null, caramboles: 52, rival_caramboles: 59, sets: '9/11,4/7,15/11,15/4,15/7', rival_sets: '15/11,15/8,10/10,9/4,10/6' })],
			[]
		);
		expect(indicadors(aportacionsUmb(proves)).w).toBe(1);
	});
});

describe('finestres', () => {
	it('reparteix per temporada i deixa les sense data nomes a l’Historic', () => {
		const aps = [
			...aportacionsNacional([nac({ temporada: '2026-2027' }), nac({ temporada: '2025-2026' }), nac({ temporada: '2025-2026' }), nac({ temporada: '2020-2021' }), nac({ temporada: '', data: null })]),
			...aportacionsUmb(agrupaUmb([umb({ data_inici: '2026-09-01' }), umb({ esdeveniment_id: 2, data_inici: '2026-07-31' }), umb({ esdeveniment_id: 3, data_inici: null })], []))
		];
		const f = finestres(aps, avui);
		expect(f.historic.n).toBe(8);
		expect(f.actual.n).toBe(2);
		expect(f.anterior.n).toBe(3);
	});
	it('usa la data quan la partida no te temporada', () => {
		const f = finestres(aportacionsNacional([nac({ temporada: '', data: '2026-10-01' })]), avui);
		expect(f.actual.n).toBe(1);
	});
});

describe('modalitat', () => {
	it('classifica per modalitat comuna i filtra', () => {
		const aps = [
			...aportacionsNacional([nac({}), nac({})]),
			...aportacionsRfeb([rfeb({ modalitat: '47_2', jugades: 3, guanyades: 3, empatades: 0, perdudes: 0 }), rfeb({ modalitat: '71_2', jugades: 1, guanyades: 0, empatades: 0, perdudes: 1 }), rfeb({ modalitat: 'banda', jugades: 1, guanyades: 1, empatades: 0, perdudes: 0 })]),
			...aportacionsUmb(agrupaUmb([umb({ disciplina: '1 banda' })], []))
		];
		expect(modalitatsDe(aps.map((a) => a.modalitat))).toEqual([
			{ clau: 'Banda', n: 2 },
			{ clau: 'Quadre', n: 2 },
			{ clau: 'Tres bandes', n: 2 }
		]);
		expect(indicadors(filtraModalitat(aps, 'Quadre')).n).toBe(4);
		expect(filtraModalitat(aps, null)).toHaveLength(aps.length);
	});
	it('una prova sense partides agafa la modalitat del nom', () => {
		const [pr] = agrupaUmb([], [{ fcb_id: '1', esdeveniment_id: 9, esdeveniment: 'European Championship 3-Cushion', lloc: null, data_inici: '2019-05-01', posicio: 5, ronda: null, mitjana: 1, participants: 24 }]);
		expect(pr.disciplina).toBe('3 bandes');
	});
});
