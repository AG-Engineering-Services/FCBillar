import { describe, expect, it } from 'vitest';
import { datesRanquing, ymDelRanquing } from './dataRanquing';

describe('ymDelRanquing', () => {
	const dates = datesRanquing([
		{ num_seq: 126, any_pub: 2026, mes_pub: 10 },
		{ num_seq: 125, any_pub: null, mes_pub: null }
	]);

	it('fa servir la data publicada', () => {
		expect(ymDelRanquing(126, dates)).toEqual([2026, 10]);
	});

	it('sense data, compta enrere des del 122 saltant l’agost', () => {
		expect(ymDelRanquing(121, dates)).toEqual([2026, 5]);
		expect(ymDelRanquing(112, new Map())).toEqual([2025, 7]);
	});
});
