import { describe, expect, it } from 'vitest';
import {
	agrupaNacional,
	divisioNacional,
	equipsDistints,
	mitjanaNacional,
	normalitzaEquip,
	ordenaNacional,
	resultatPartida,
	resumNacional,
	temporadaCurta,
	type NacionalPartidaRow
} from './nacional';

function fila(o: Partial<NacionalPartidaRow>): NacionalPartidaRow {
	return {
		fcb_id: '1', temporada: '2025-2026', divisio: 'honor', grup: '', jornada: 1, data: null,
		ordre_encontre: 1, ordre: 1, jugador: 'A', caramboles: 30, rival: 'B', caramboles_rival: 20,
		rival_fcb_id: null, rival_nom_fcb: null, entrades: 40, equip: 'X', equip_rival: 'Y', punts_equip: 5, punts_rival: 3,
		a_casa: true, ...o
	};
}

describe('lliga nacional', () => {
	it('escriu la mitjana amb tres decimals i coma', () => {
		expect(mitjanaNacional(1.194)).toBe('1,194');
		expect(mitjanaNacional(1.2)).toBe('1,200');
		expect(mitjanaNacional(null)).toBe('—');
	});

	it('abrevia la temporada i tradueix la divisió', () => {
		expect(temporadaCurta('2025-2026')).toBe('2025/26');
		expect(temporadaCurta('rara')).toBe('rara');
		expect(divisioNacional('honor')).toBe("Divisió d'Honor");
		expect(divisioNacional('2')).toBe('Segona');
	});

	it('decideix G/E/P per les caramboles', () => {
		expect(resultatPartida(30, 20)).toBe('G');
		expect(resultatPartida(20, 30)).toBe('P');
		expect(resultatPartida(25, 25)).toBe('E');
	});

	it("normalitza els noms d'equip", () => {
		expect(normalitzaEquip("Inviktcues Granollers 'B'")).toBe(normalitzaEquip('INVIKTCUES GRANOLLERS "B"'));
		expect(normalitzaEquip('C.B. Sabadèll “A”')).toBe('C.B. SABADELL A');
	});

	it('tria la grafia més freqüent i no duplica equips', () => {
		const r = equipsDistints(["Inv 'B'", 'INV "B"', 'INV "B"', 'Altre']);
		expect(r).toEqual(['INV "B"', 'Altre']);
	});

	it('resumeix la temporada', () => {
		const r = resumNacional([
			{ caramboles: 30, caramboles_rival: 20, entrades: 40 },
			{ caramboles: 10, caramboles_rival: 30, entrades: 20 },
			{ caramboles: 25, caramboles_rival: 25, entrades: null }
		]);
		expect(r).toMatchObject({ pj: 3, g: 1, e: 1, p: 1, caramboles: 65, entrades: 60 });
		expect(r.mitjana).toBeCloseTo(65 / 60);
		expect(resumNacional([]).mitjana).toBeNull();
	});

	it('ordena per temporada, divisió, i data amb les sense data al final', () => {
		const r = ordenaNacional([
			fila({ temporada: '2023-2024', jornada: 9 }),
			fila({ jornada: 1, data: '2025-10-01' }),
			fila({ jornada: 2, data: '2025-11-01' }),
			fila({ divisio: '1', jornada: 3, data: '2025-12-01' }),
			fila({ jornada: 3, data: null })
		]);
		expect(r.map((x) => `${x.temporada}/${x.divisio}/${x.jornada}`)).toEqual([
			'2025-2026/honor/2',
			'2025-2026/honor/1',
			'2025-2026/honor/3',
			'2025-2026/1/3',
			'2023-2024/honor/9'
		]);
	});

	it('agrupa per temporada i divisió amb equips i resum', () => {
		const g = agrupaNacional([
			fila({ equip: "T 'B'" }),
			fila({ equip: 'T "B"', caramboles: 10 }),
			fila({ equip: 'U' }),
			fila({ temporada: '2024-2025' })
		]);
		expect(g).toHaveLength(2);
		expect(g[0].equips).toHaveLength(2);
		expect(g[0].resum.pj).toBe(3);
		expect(g[1].temporada).toBe('2024-2025');
	});
});
