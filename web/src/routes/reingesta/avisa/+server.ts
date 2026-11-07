// Engega reingest-nologin.yml quan la fitxa de l'Albert encua una reingesta.
//
// La fila de `reingest_requests` la recollia reingest-dispatch.yml, que es va
// retirar el 29/06/2026, i des d'aleshores les peticions es quedaven 'pending'
// per sempre: el botó deia «petició enviada» i no passava res. Ara, en encuar,
// la fitxa crida aquesta ruta i la reingesta arrenca en el moment, com el
// Traductor (routes/traductor/avisa, d'on surt el mateix token).
//
// La ruta és pública. Només dispara si hi ha una petició pendent dels últims
// quinze minuts (inserir-ne una demana el correu autoritzat, que valida la
// RLS), i com a molt un cop per minut per instància. El workflow té
// `concurrency: reingest`, així que GitHub no en deixa més d'una en marxa.
import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';

const WORKFLOW =
	'https://api.github.com/repos/AG-Engineering-Services/FCBillar/actions/workflows/reingest-nologin.yml/dispatches';
const INTERVAL_MS = 60_000;
const FINESTRA_MS = 15 * 60_000;

let darrerAvis = 0;

async function hiHaPeticio(): Promise<boolean> {
	const base = publicEnv.PUBLIC_NEON_DATA_API_URL;
	const token = publicEnv.PUBLIC_NEON_ANON_TOKEN;
	if (!base || !token) return false;
	const des_de = new Date(Date.now() - FINESTRA_MS).toISOString();
	// La memòria cau d'esquemes de Neon pot respondre 404 unes quantes vegades
	// després d'una migració: es torna a provar.
	for (let intent = 0; intent < 4; intent++) {
		const r = await fetch(
			`${base}/reingest_requests?select=id&status=eq.pending&requested_at=gte.${encodeURIComponent(des_de)}&limit=1`,
			{ headers: { Authorization: `Bearer ${token}`, 'Accept-Profile': 'fcbillar' } }
		);
		if (r.ok) return ((await r.json()) as unknown[]).length > 0;
		if (r.status !== 404) return false;
		await new Promise((resol) => setTimeout(resol, 500));
	}
	return false;
}

export async function POST() {
	if (!env.GITHUB_DISPATCH_TOKEN) return json({ avisat: false, motiu: 'sense token' }, { status: 503 });
	if (Date.now() - darrerAvis < INTERVAL_MS) return json({ avisat: false, motiu: 'massa aviat' });
	if (!(await hiHaPeticio())) return json({ avisat: false, motiu: 'cap petició pendent' });
	darrerAvis = Date.now();
	const r = await fetch(WORKFLOW, {
		method: 'POST',
		headers: {
			Authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
			Accept: 'application/vnd.github+json',
			'X-GitHub-Api-Version': '2022-11-28'
		},
		body: JSON.stringify({ ref: 'master' })
	});
	if (!r.ok) {
		darrerAvis = 0;
		return json({ avisat: false, motiu: `GitHub ${r.status}` }, { status: 502 });
	}
	return json({ avisat: true });
}
