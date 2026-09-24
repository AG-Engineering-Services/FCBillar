import { describe, expect, it } from 'vitest';
import { ambReintentsCache, llegeixEnllac, mmss, segmentA, type Segment } from './traductor';

describe('llegeixEnllac', () => {
	it.each([
		['https://www.youtube.com/watch?v=guRv1Z5Thn0', 'youtube', 'guRv1Z5Thn0'],
		['https://www.youtube.com/watch?si=abc&v=guRv1Z5Thn0', 'youtube', 'guRv1Z5Thn0'],
		['https://youtu.be/s8OX7DJVdl4?t=12', 'youtube', 's8OX7DJVdl4'],
		['https://youtube.com/shorts/s8OX7DJVdl4', 'youtube', 's8OX7DJVdl4'],
		['https://www.instagram.com/reel/C9xYz_AbCd/', 'instagram', 'C9xYz_AbCd'],
		['https://www.instagram.com/billar.kr/reel/C9xYz_AbCd/', 'instagram', 'C9xYz_AbCd'],
		['https://www.facebook.com/reel/1234567890', 'facebook', '1234567890'],
		['https://www.facebook.com/share/r/1AbCdEf/', 'facebook', '1AbCdEf'],
		['https://www.facebook.com/billarvn/videos/987654321/', 'facebook', '987654321'],
		['https://www.facebook.com/watch/?v=555', 'facebook', '555']
	])('%s', (url, plataforma, video_id) => {
		expect(llegeixEnllac(url)).toEqual({ plataforma, video_id });
	});

	it('rebutja el que no és de cap de les tres', () => {
		expect(llegeixEnllac('https://vimeo.com/123')).toBeNull();
		expect(llegeixEnllac('hola')).toBeNull();
	});
});

describe('segmentA', () => {
	const segs: Segment[] = [
		{ t0: 1, t1: 4, orig: 'a', ca: 'A' },
		{ t0: 5, t1: 9, orig: 'b', ca: 'B' },
		{ t0: 9, t1: 12, orig: 'c', ca: 'C' }
	];
	it('troba el fragment de cada instant', () => {
		expect(segmentA(segs, 1)?.ca).toBe('A');
		expect(segmentA(segs, 8.99)?.ca).toBe('B');
		expect(segmentA(segs, 9)?.ca).toBe('C');
	});
	it('entre fragments i fora de rang no hi ha res', () => {
		expect(segmentA(segs, 0.5)).toBeNull();
		expect(segmentA(segs, 4.5)).toBeNull();
		expect(segmentA(segs, 12)).toBeNull();
		expect(segmentA([], 3)).toBeNull();
	});
});

it('mmss', () => {
	expect(mmss(0)).toBe('0:00');
	expect(mmss(65.7)).toBe('1:05');
});

describe('ambReintentsCache', () => {
	const falla = { data: null, error: { code: 'PGRST205' } };
	const be = { data: [1], error: null };
	it('torna a provar mentre la instància no veu la taula', async () => {
		const respostes = [falla, falla, be];
		let crides = 0;
		const r = await ambReintentsCache(async () => respostes[crides++]);
		expect(r).toBe(be);
		expect(crides).toBe(3);
	});
	it('altres errors no es tornen a provar', async () => {
		let crides = 0;
		const altre = { data: null, error: { code: '23514' } };
		expect(await ambReintentsCache(async () => (crides++, altre))).toBe(altre);
		expect(crides).toBe(1);
	});
	it('es rendeix després dels intents', async () => {
		let crides = 0;
		expect(await ambReintentsCache(async () => (crides++, falla), 2)).toBe(falla);
		expect(crides).toBe(2);
	});
});
