import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/public', () => ({
	env: {
		PUBLIC_NEON_DATA_API_URL: 'https://neon.test/neondb/rest/v1',
		PUBLIC_NEON_ANON_TOKEN: 'anon'
	}
}));

const { viaCau } = await import('./db');
const base = 'https://neon.test/neondb/rest/v1';

describe('viaCau', () => {
	it('una lectura de la reingesta passa per la memòria cau, amb la consulta sencera', () => {
		expect(viaCau(`${base}/players?select=nom&fcb_id=eq.211`)).toBe(
			'/api/fcb/players?select=nom&fcb_id=eq.211'
		);
	});

	it('les capçaleres que canvien la resposta van a la URL, que és la clau', () => {
		const url = viaCau(`${base}/players?select=*`, {
			headers: { Accept: 'application/vnd.pgrst.object+json', Prefer: 'count=exact' }
		});
		const params = new URL(url!, 'https://x').searchParams;
		expect(params.get('__accept')).toBe('application/vnd.pgrst.object+json');
		expect(params.get('__prefer')).toBe('count=exact');
	});

	it('el directe i el que escriuen els usuaris van directes a Neon', () => {
		expect(viaCau(`${base}/open_live?select=*`)).toBeNull();
		expect(viaCau(`${base}/video_traduccio?select=*`)).toBeNull();
	});

	it('ni escriptures, ni RPC, ni res que no sigui del Data API', () => {
		expect(viaCau(`${base}/players`, { method: 'POST' })).toBeNull();
		expect(viaCau(`${base}/players`, { method: 'HEAD' })).toBeNull();
		expect(viaCau(`${base}/rpc/elimina_video`)).toBeNull();
		expect(viaCau('https://altre.test/players')).toBeNull();
	});
});
