import { describe, expect, it } from 'vitest';
import {
	ambitsAmbDades,
	competicions,
	filtraModalitat,
	indicadors,
	temporadaActual,
	type DadesExternes,
	type ExtPartidaRow,
	type ExtTotalRow
} from './externes';
import type { NacionalPartidaRow } from './nacional';

function partida(p: Partial<ExtPartidaRow>): ExtPartidaRow {
	return {
		fcb_id: '1',
		font: 'umb',
		esdeveniment: '320',
		competicio: 'World Cup 3-Cushion PORTO',
		modalitat: '3B',
		ambit: 'internacional',
		tipus: 'copa_mon',
		temporada: '2024-2025',
		data: '2025-06-29',
		fase: 'Q',
		grup: 'A',
		ordre: 1,
		jugador: 'JIMENEZ Sergio',
		caramboles: 40,
		entrades: 20,
		serie: 8,
		punts: 2,
		rival: 'CHO MyungWoo',
		nacio_rival: 'KR',
		rival_fcb_id: null,
		caramboles_rival: 30,
		entrades_rival: 20,
		serie_rival: 5,
		punts_rival: 0,
		...p
	};
}

function total(t: Partial<ExtTotalRow>): ExtTotalRow {
	return {
		fcb_id: '1',
		font: 'rfeb',
		esdeveniment: 'noticias2024/res_ce_3b',
		competicio: "Campionat d'Espanya de tres bandes · Cartagena",
		modalitat: '3B',
		ambit: 'espanya',
		tipus: 'campionat_espanya',
		temporada: '2024-2025',
		data: '2025-01-18',
		jugador: 'Sergio Jiménez Galera',
		federacio: 'CAT',
		posicio: 12,
		jugades: 2,
		guanyades: 1,
		empatades: 0,
		perdudes: 1,
		caramboles: 65,
		entrades: 47,
		serie: null,
		...t
	};
}

function nacional(p: Partial<NacionalPartidaRow>): NacionalPartidaRow {
	return {
		fcb_id: '1',
		temporada: '2025-2026',
		divisio: 'honor',
		grup: '',
		jornada: 1,
		data: '2025-10-04',
		ordre_encontre: 1,
		ordre: 1,
		jugador: 'Sergio Jiménez',
		caramboles: 40,
		rival: 'X',
		caramboles_rival: 35,
		rival_fcb_id: null,
		entrades: 25,
		equip: 'A',
		equip_rival: 'B',
		punts_equip: 2,
		punts_rival: 0,
		a_casa: true,
		...p
	};
}

const buit: DadesExternes = { nacional: [], partides: [], totals: [] };

describe('indicadors per àmbit', () => {
	it('internacional: partides, mitjana, sèrie i millor partida', () => {
		const d = {
			...buit,
			partides: [
				partida({ ordre: 1 }),
				partida({ ordre: 2, caramboles: 25, entrades: 25, serie: 12, punts: 0, punts_rival: 2, caramboles_rival: 40 })
			]
		};
		const k = indicadors(d, 'internacional');
		expect([k.n, k.w, k.e, k.l, k.pct]).toEqual([2, 1, 0, 1, 50]);
		expect(k.mitjana).toBeCloseTo(65 / 45);
		expect(k.sm).toBe(12);
		expect(k.best).toBe(2);
	});

	it('els punts de match manen sobre les caramboles (penals)', () => {
		const d = { ...buit, partides: [partida({ caramboles: 40, caramboles_rival: 40, punts: 0, punts_rival: 2 })] };
		expect(indicadors(d, 'internacional').l).toBe(1);
	});

	it('espanya suma la Lliga Nacional i els totals dels campionats', () => {
		const d = { ...buit, nacional: [nacional({})], totals: [total({})] };
		const k = indicadors(d, 'espanya');
		expect([k.n, k.w, k.l]).toEqual([3, 2, 1]);
		expect(k.mitjana).toBeCloseTo((40 + 65) / (25 + 47));
		expect(k.best).toBeCloseTo(40 / 25);
		expect(k.sm).toBeNull();
		expect(k.senseDetall).toBe(0);
	});

	it('un campionat sense partides compta per a la mitjana, no per a les partides', () => {
		const d = {
			...buit,
			totals: [total({ modalitat: '47/2', jugades: null, guanyades: null, perdudes: null, caramboles: 1272, entrades: 41 })]
		};
		const k = indicadors(d, 'espanya');
		expect([k.n, k.pct, k.senseDetall]).toEqual([0, 0, 1]);
		expect(k.mitjana).toBeCloseTo(1272 / 41);
	});

	it('per temporada', () => {
		const d = { ...buit, partides: [partida({ temporada: '2024-2025' }), partida({ temporada: '2025-2026', ordre: 2 })] };
		expect(indicadors(d, 'internacional', '2025-2026').n).toBe(1);
	});

	it('cada àmbit, les seves dades', () => {
		const d = { ...buit, partides: [partida({})], totals: [total({})] };
		expect(indicadors(d, 'espanya').n).toBe(2);
		expect(indicadors(d, 'internacional').n).toBe(1);
		expect(ambitsAmbDades(d)).toEqual(['espanya', 'internacional']);
		expect(ambitsAmbDades(buit)).toEqual([]);
	});
});

describe('modalitat', () => {
	it('la Nacional és de tres bandes, i el 47/1 no té codi català', () => {
		const d = {
			nacional: [nacional({})],
			partides: [partida({}), partida({ modalitat: '47/1', ordre: 2 })],
			totals: [total({ modalitat: '71/2' })]
		};
		const tres = filtraModalitat(d, 1);
		expect([tres.nacional.length, tres.partides.length, tres.totals.length]).toEqual([1, 1, 0]);
		const quadre = filtraModalitat(d, 6);
		expect([quadre.nacional.length, quadre.partides.length, quadre.totals.length]).toEqual([0, 0, 1]);
		expect(filtraModalitat(d, null)).toBe(d);
	});
});

describe('competicions', () => {
	it('de la més nova a la més antiga, amb el resum de cadascuna', () => {
		const d = {
			...buit,
			partides: [
				partida({ ordre: 2, punts: 0, punts_rival: 2, caramboles: 20 }),
				partida({ ordre: 1 }),
				partida({ esdeveniment: '200', competicio: 'World Championship', tipus: 'mundial', data: '2018-09-21', temporada: '2018-2019' })
			]
		};
		const cs = competicions(d, 'internacional');
		expect(cs.map((c) => c.nom)).toEqual(['World Cup 3-Cushion PORTO', 'World Championship']);
		expect(cs[0].partides.map((p) => p.ordre)).toEqual([1, 2]);
		expect([cs[0].resum.n, cs[0].resum.w, cs[0].resum.l]).toEqual([2, 1, 1]);
	});

	it('un campionat de la RFEB porta la posició i els totals', () => {
		const [c] = competicions({ ...buit, totals: [total({})] }, 'espanya');
		expect([c.posicio, c.resum.n, c.resum.w]).toEqual([12, 2, 1]);
		expect(c.resum.mitjana).toBeCloseTo(65 / 47);
	});
});

it('temporada actual', () => {
	expect(temporadaActual(new Date(2026, 10, 17))).toBe('2026-2027');
	expect(temporadaActual(new Date(2027, 6, 31))).toBe('2026-2027');
});
