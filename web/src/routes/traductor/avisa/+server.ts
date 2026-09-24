// Engega el workflow traductor.yml en el moment que algú afegeix un vídeo.
//
// La programació de GitHub no serveix per a això: el 24/09/2026, el primer dia
// del traductor, no va disparar cap dels trets de quart d'hora, i la reingesta
// diària d'aquest mateix repositori arrenca amb fins a dues hores de retard.
// La programació queda de reserva.
//
// El token (GITHUB_DISPATCH_TOKEN, a les variables privades de Vercel) és
// fine-grained, només d'aquest repositori i només amb «Actions: read and write»:
// l'únic que pot fer és llançar workflows. Tot i així la ruta és pública, i per
// això només el llança si a la cua hi ha feina, i com a molt un cop per minut per
// instància. Encara que algú la cridés sense parar, GitHub no deixa més d'una
// execució en marxa i una en espera (concurrency: traductor).
import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';

const WORKFLOW =
	'https://api.github.com/repos/AG-Engineering-Services/FCBillar/actions/workflows/traductor.yml/dispatches';
const INTERVAL_MS = 60_000;

let darrerAvis = 0;

async function hiHaFeina(): Promise<boolean> {
	const base = publicEnv.PUBLIC_NEON_DATA_API_URL;
	const token = publicEnv.PUBLIC_NEON_ANON_TOKEN;
	if (!base || !token) return false;
	// La memòria cau d'esquemes de Neon pot respondre 404 unes quantes vegades
	// després d'una migració (vegeu ambReintentsCache): es torna a provar.
	for (let intent = 0; intent < 4; intent++) {
		const r = await fetch(`${base}/video_traduccio?select=id&estat=eq.pendent&limit=1`, {
			headers: { Authorization: `Bearer ${token}`, 'Accept-Profile': 'fcbillar' }
		});
		if (r.ok) return ((await r.json()) as unknown[]).length > 0;
		if (r.status !== 404) return false;
		await new Promise((resol) => setTimeout(resol, 500));
	}
	return false;
}

export async function POST() {
	if (!env.GITHUB_DISPATCH_TOKEN) return json({ avisat: false, motiu: 'sense token' });
	if (Date.now() - darrerAvis < INTERVAL_MS) return json({ avisat: false, motiu: 'massa aviat' });
	if (!(await hiHaFeina())) return json({ avisat: false, motiu: 'cua buida' });
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
		darrerAvis = 0; // que el proper intent no hagi d'esperar
		return json({ avisat: false, motiu: `GitHub ${r.status}` }, { status: 502 });
	}
	return json({ avisat: true });
}
