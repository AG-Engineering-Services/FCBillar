import type { PageServerLoad } from './$types';
import {
	fetchLlistaTirades,
	fetchJugadors,
	fetchComptador,
	type FiltresLlista
} from '$lib/biblia/api/billiardBible';

const MIDA = 24;

export const load: PageServerLoad = async ({ fetch, url }) => {
	const p = url.searchParams;

	// Per defecte mostrem els Tirs analitzats (els que tenen animació + explicació).
	const esAnalisi = p.get('tipus') !== 'pro';
	const jugador = Number(p.get('jugador') ?? -1);
	const familia = Number(p.get('familia') ?? 0);
	const posicio = p.get('pos') === '1';
	const defensa = p.get('def') === '1';
	const evitarKiss = p.get('kiss') === '1';
	const pagina = Math.max(1, Number(p.get('pagina') ?? 1));

	const filtres: FiltresLlista = {
		esAnalisi,
		jugador: Number.isFinite(jugador) ? jugador : -1,
		familia: Number.isFinite(familia) ? familia : 0,
		posicio,
		defensa,
		evitarKiss,
		inici: (pagina - 1) * MIDA,
		mida: MIDA
	};

	const [llista, jugadors, totalAltre] = await Promise.all([
		fetchLlistaTirades(fetch, filtres),
		fetchJugadors(fetch),
		fetchComptador(fetch, { ...filtres, esAnalisi: !esAnalisi })
	]);

	const comptadors = {
		pro: esAnalisi ? totalAltre : llista.total,
		analisi: esAnalisi ? llista.total : totalAltre
	};

	return {
		tirades: llista.tirades,
		total: llista.total,
		comptadors,
		jugadors,
		filtres: {
			esAnalisi,
			jugador: filtres.jugador,
			familia: filtres.familia,
			posicio,
			defensa,
			evitarKiss
		},
		pagina,
		mida: MIDA
	};
};
