import type { PageServerLoad } from './$types';
import { BB_URL, BB_ANON_KEY } from '$lib/biblia/api/config';
import { fetchDetall } from '$lib/biblia/api/billiardBible';

export type ModeQuiz = 'multiple' | 'efecte' | 'ambdos';

export const load: PageServerLoad = async ({ fetch, url }) => {
	const mode = (url.searchParams.get('mode') ?? 'multiple') as ModeQuiz;

	// Tots els ids analitzats, barrejats, i n'agafem uns quants.
	const r = await fetch(`${BB_URL}/rest/v1/shot_list?select=id&has_analysis_shot=eq.1`, {
		headers: { apikey: BB_ANON_KEY, Authorization: `Bearer ${BB_ANON_KEY}` }
	});
	const ids = ((await r.json()) as { id: number }[]).map((x) => x.id);
	for (let i = ids.length - 1; i > 0; i--) {
		const j = Math.floor(Math.random() * (i + 1));
		[ids[i], ids[j]] = [ids[j], ids[i]];
	}

	const detalls = await Promise.all(
		ids.slice(0, 14).map((id) => fetchDetall(fetch, id, true).catch(() => null))
	);
	const tirades = detalls
		.filter((d): d is NonNullable<typeof d> => !!d && !!d.puntContacte)
		.map((d) => ({
			id: d.id,
			boles: d.boles,
			puntContacte: d.puntContacte,
			gruix: d.gruix,
			familia: d.familia,
			video: d.video,
			tracaBlanca: d.tracaBlanca,
			tracaGroga: d.tracaGroga,
			tracaVermella: d.tracaVermella
		}));

	return { tirades, mode };
};
