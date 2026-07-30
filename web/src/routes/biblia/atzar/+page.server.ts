import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { BB_URL, BB_ANON_KEY } from '$lib/biblia/api/config';

// Tria una tirada ANALITZADA a l'atzar (les que tenen animació + explicació)
// i redirigeix a la seva fitxa.
export const load: PageServerLoad = async ({ fetch }) => {
	let desti = '/biblia?tipus=analisi';
	try {
		const r = await fetch(`${BB_URL}/rest/v1/shot_list?select=id&has_analysis_shot=eq.1`, {
			headers: { apikey: BB_ANON_KEY, Authorization: `Bearer ${BB_ANON_KEY}` }
		});
		if (r.ok) {
			const files = (await r.json()) as { id: number }[];
			if (files.length) {
				const tria = files[Math.floor(Math.random() * files.length)];
				desti = `/biblia/${tria.id}?a=1`;
			}
		}
	} catch {
		// si falla, caiem al llistat d'analitzats
	}
	throw redirect(307, desti);
};
