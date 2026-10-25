// Lectures del Data API de Neon a través de la memòria cau de Vercel.
//
// Fins a l'octubre de 2026 el navegador consultava Neon directament, i cada
// visita despertava el compute i transferia dades que només canvien quan corre
// la reingesta. Aquesta ruta fa la mateixa consulta i respon amb `s-maxage`:
// la CDN de Vercel la guarda i les visites següents no arriben a Neon. Passats
// els cinc minuts es continua servint la còpia mentre es refresca per darrere
// (`stale-while-revalidate`), o sigui que el cost és una consulta per URL i
// interval, no una per visita.
//
// Només lectures (GET) de taules senceres pel nom; ni RPC ni escriptures, que
// van directes. Qui decideix què passa per aquí és `db.ts`: les taules que han
// de ser fresques (el directe, les peticions dels usuaris) no hi passen.
//
// El JWT anònim és el mateix que ja viatja al navegador, i les capçaleres que
// canvien la resposta (`Accept`, `Prefer`) arriben com a paràmetres perquè
// formin part de la clau de la memòria cau.
import { env } from '$env/dynamic/public';
import type { RequestHandler } from './$types';

// A Frankfurt, al costat de Neon (eu-central-1): per defecte Vercel la posava a
// Virgínia, i cada consulta que no trobava la còpia creuava l'Atlàntic.
export const config = { regions: ['fra1'] };

const CAU = 'public, max-age=0, s-maxage=300, stale-while-revalidate=86400';

export const GET: RequestHandler = async ({ params, url, fetch }) => {
	const base = env.PUBLIC_NEON_DATA_API_URL;
	const token = env.PUBLIC_NEON_ANON_TOKEN;
	if (!base || !token) return new Response('Falta la configuració del Data API', { status: 500 });
	if (!/^[a-z0-9_]+$/.test(params.taula)) return new Response('Taula no vàlida', { status: 400 });

	const consulta = new URLSearchParams(url.searchParams);
	const capçaleres: Record<string, string> = {
		Authorization: `Bearer ${token}`,
		'Accept-Profile': 'fcbillar'
	};
	for (const [param, nom] of [
		['__accept', 'Accept'],
		['__prefer', 'Prefer']
	]) {
		const valor = consulta.get(param);
		if (valor) capçaleres[nom] = valor;
		consulta.delete(param);
	}

	const r = await fetch(`${base}/${params.taula}?${consulta}`, { headers: capçaleres });
	const resposta = new Headers({ 'Cache-Control': r.ok ? CAU : 'no-store' });
	for (const nom of ['Content-Type', 'Content-Range']) {
		const valor = r.headers.get(nom);
		if (valor) resposta.set(nom, valor);
	}
	return new Response(r.body, { status: r.status, headers: resposta });
};
