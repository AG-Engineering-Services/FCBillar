import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';
import { fetchDetall, fetchJugadors } from '$lib/biblia/api/billiardBible';
import { tradueixKoCa } from '$lib/biblia/api/traductor';

export const load: PageServerLoad = async ({ fetch, params, url }) => {
	const id = Number(params.id);
	if (!Number.isFinite(id)) throw error(404, 'Tirada no trobada');

	const esAnalisi = url.searchParams.get('a') === '1';

	const [detall, jugadors] = await Promise.all([
		fetchDetall(fetch, id, esAnalisi),
		fetchJugadors(fetch)
	]);

	if (!detall.id) throw error(404, 'Tirada no trobada');

	const jugador = jugadors.find((j) => j.id === detall.jugadorId) ?? null;

	// Traducció al català del text d'entrenament. NO l'esperem: es transmet
	// (streaming) com una promesa perquè la fitxa carregui a l'instant i la
	// traducció aparegui quan estigui llesta ("Traduint…").
	const original = [detall.descripcio, detall.consell].filter(Boolean).join('\n\n');
	const explicacioPromesa = original ? tradueixKoCa(fetch, original) : Promise.resolve('');

	return { detall, jugador, esAnalisi, original, explicacioPromesa };
};
