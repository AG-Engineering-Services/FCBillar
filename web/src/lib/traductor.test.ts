import { describe, expect, it } from 'vitest';
import {
	ambReintentsCache,
	estimaCua,
	llegeixEnllac,
	mmss,
	properTret,
	quantFalta,
	segmentA,
	type Segment,
	type VideoTraduccio
} from './traductor';

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

describe('properTret', () => {
	it('és el proper minut 7, 22, 37 o 52', () => {
		expect(properTret(new Date('2026-09-24T10:00:00Z')).toISOString()).toBe('2026-09-24T10:07:00.000Z');
		expect(properTret(new Date('2026-09-24T10:07:00Z')).toISOString()).toBe('2026-09-24T10:22:00.000Z');
		expect(properTret(new Date('2026-09-24T10:53:10Z')).toISOString()).toBe('2026-09-24T11:07:00.000Z');
	});
});

describe('estimaCua', () => {
	const ara = new Date('2026-09-24T10:00:00Z');
	let n = 0;
	const video = (camps: Partial<VideoTraduccio>): VideoTraduccio => ({
		id: ++n,
		url: '',
		plataforma: 'youtube',
		video_id: String(n),
		idioma: 'ko',
		estat: 'pendent',
		titol: null,
		canal: null,
		durada: null,
		segments: null,
		audio_url: null,
		missatge: null,
		creat: `2026-09-24T09:${String(n).padStart(2, '0')}:00Z`,
		processat: null,
		iniciat: null,
		...camps
	});
	// Un vídeo fet de 100 s que va trigar 20 + 100 s: ritme 1 s de feina per segon.
	const fet = video({
		estat: 'fet',
		durada: 100,
		iniciat: '2026-09-24T09:00:00Z',
		processat: '2026-09-24T09:02:00Z'
	});
	const min = (d: Date) => (d.getTime() - ara.getTime()) / 60_000;

	it('el que es tradueix acaba segons el ritme dels vídeos fets', () => {
		const enCurs = video({ estat: 'processant', durada: 280, iniciat: '2026-09-24T09:59:00Z' });
		const e = estimaCua([fet, enCurs], ara).get(enCurs.id)!;
		expect(min(e.acaba)).toBeCloseTo(4); // començat fa 1 min, 20 + 280 s de feina
	});

	it('un de pendent espera el proper tret, el retard de GitHub i la preparació', () => {
		const p = video({ durada: 40 });
		const e = estimaCua([fet, p], ara).get(p.id)!;
		expect(min(e.comenca)).toBeCloseTo(7 + 5 + 1);
		expect(min(e.acaba)).toBeCloseTo(14);
	});

	it('cada tret en fa tres, i el quart va al següent', () => {
		const ps = [1, 2, 3, 4].map(() => video({ durada: 40 }));
		const est = estimaCua([fet, ...ps], ara);
		expect(min(est.get(ps[2]!.id)!.acaba)).toBeCloseTo(16);
		expect(min(est.get(ps[3]!.id)!.comenca)).toBeCloseTo(22 + 5 + 1);
	});

	it('el tret en curs encara agafa pendents', () => {
		const enCurs = video({ estat: 'processant', durada: 40, iniciat: '2026-09-24T09:59:30Z' });
		const p = video({ durada: 40 });
		const e = estimaCua([fet, enCurs, p], ara).get(p.id)!;
		expect(min(e.comenca)).toBeCloseTo(0.5);
	});

	it("si en curs ja passa de l'estimat, no el dona per acabat", () => {
		const enCurs = video({ estat: 'processant', durada: 10, iniciat: '2026-09-24T09:30:00Z' });
		expect(estimaCua([fet, enCurs], ara).get(enCurs.id)!.acaba > ara).toBe(true);
	});
});

it('quantFalta', () => {
	const ara = new Date('2026-09-24T10:00:00Z');
	const en = (m: number) => new Date(ara.getTime() + m * 60_000);
	expect(quantFalta(en(0.2), ara)).toBe("menys d'un minut");
	expect(quantFalta(en(7), ara)).toBe('~7 min');
	expect(quantFalta(en(80), ara)).toBe('~1 h 20 min');
	expect(quantFalta(en(120), ara)).toBe('~2 h');
});
