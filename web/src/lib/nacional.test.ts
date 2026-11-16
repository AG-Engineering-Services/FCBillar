import { describe, expect, it } from 'vitest';
import {
	divisioNacional,
	llocNacional,
	mitjanaNacional,
	ordenaNacional,
	temporadaCurta
} from './nacional';

describe('lliga nacional', () => {
	it('escriu la mitjana amb tres decimals i coma', () => {
		expect(mitjanaNacional(1.194)).toBe('1,194');
		expect(mitjanaNacional(1.2)).toBe('1,200');
		expect(mitjanaNacional(null)).toBe('—');
	});

	it('abrevia la temporada', () => {
		expect(temporadaCurta('2025-2026')).toBe('2025/26');
		expect(temporadaCurta('rara')).toBe('rara');
	});

	it('tradueix la divisió', () => {
		expect(divisioNacional('honor')).toBe("Divisió d'Honor");
		expect(divisioNacional('1')).toBe('Primera');
		expect(divisioNacional('2')).toBe('Segona');
	});

	it('escriu el lloc', () => {
		expect(llocNacional(3)).toBe('3º');
	});

	it('ordena per temporada descendent i divisió', () => {
		const r = ordenaNacional([
			{ temporada: '2023-2024', divisio: 'honor', posicio: 1 },
			{ temporada: '2025-2026', divisio: '2', posicio: 1 },
			{ temporada: '2025-2026', divisio: 'honor', posicio: 4 }
		]);
		expect(r.map((x) => `${x.temporada}/${x.divisio}`)).toEqual([
			'2025-2026/honor',
			'2025-2026/2',
			'2023-2024/honor'
		]);
	});
});
