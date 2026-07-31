/**
 * Traducció coreà → català del text d'entrenament dels tirs analitzats.
 *
 * Si hi ha una clau d'NVIDIA (NVIDIA_API_KEY), fa servir un LLM d'NVIDIA NIM
 * (API compatible amb OpenAI) amb el glossari de billar al prompt — molt més
 * natural. Si no, cau a l'endpoint gratuït de Google Translate.
 *
 * Cada resultat es desa en una cache local (`data/traduccions.json`) amb clau
 * per motor+model, així cada text només es tradueix un cop i després funciona
 * sense connexió.
 */

import { env } from '$env/dynamic/private';
import traduccionsBase from './traduccions.json';

// A Vercel el sistema de fitxers és de només lectura: la cache base ve
// empaquetada (JSON estàtic) i les traduccions noves es guarden només en
// memòria (per instància). Per actualitzar la base, es re-desplega.
let memoria: Record<string, string> | null = null;

function clauNvidia(): string | undefined {
	return env.NVIDIA_API_KEY?.trim() || undefined;
}
function modelNvidia(): string {
	// mistral-medium: bona qualitat i prou ràpid al tier gratuït (els models de
	// 70B+ hi fan timeout de servidor sovint).
	return env.NVIDIA_MODEL?.trim() || 'mistralai/mistral-medium-3.5-128b';
}

// ---------------------------------------------------------------------------
// Glossari de billar
// ---------------------------------------------------------------------------

const GLOSSARI: Array<[string, string]> = [
	['키스', 'retruc'],
	['두께', 'quantitat de bola'],
	['당점', 'punt de contacte'],
	['수구', 'bola 1 (jugadora)'],
	['1목적구', 'bola 2 (primera bola objectiu)'],
	['2목적구', 'bola 3 (segona bola objectiu)'],
	['뒤돌리기', 'endarrere'],
	['옆돌리기', 'de costat'],
	['앞돌리기', 'endavant'],
	['비껴치기', 'rasant'],
	['대회전', 'gran rotació'],
	['더블쿠션', 'doble banda'],
	['리버스', 'reverse'],
	['뱅크샷', 'bank shot'],
	['샷', 'tir']
];

/** Correccions finals aplicades sempre al text traduït. */
const CORRECCIONS_CA: Array<[RegExp, string]> = [
	[/\bbotiga\b/gi, 'cop'],
	[/\bpetons\b/gi, 'retrucs'],
	[/\bpetó\b/gi, 'retruc'],
	[/\bxuts\b/gi, 'tirs'],
	[/\bxut\b/gi, 'tir'],
	[/\bkisses\b/gi, 'retrucs'],
	[/\bkiss\b/gi, 'retruc'],
	[/\*+/g, ''] // treu els asteriscs de markdown
];

function correccions(text: string): string {
	let t = text;
	for (const [re, rep] of CORRECCIONS_CA) t = t.replace(re, rep);
	return t;
}

// ---------------------------------------------------------------------------
// Cache
// ---------------------------------------------------------------------------

function carrega(): Record<string, string> {
	if (!memoria) memoria = { ...(traduccionsBase as Record<string, string>) };
	return memoria;
}

function desa(): void {
	// No es persisteix a disc (Vercel és de només lectura); n'hi ha prou amb la
	// cache en memòria, que ja s'ha mutat al mapa `memoria`.
}

// Mapa text→traducció del bundle, ignorant el prefix `motor:model` de la clau.
// Així el bundle pre-traduït s'usa SEMPRE, encara que l'etiqueta activa (que
// depèn de si hi ha NVIDIA_API_KEY a l'entorn de Vercel) no coincideixi amb la
// que es va fer servir en empaquetar. Sense això, a Vercel (sense clau)
// l'etiqueta és "google:v2" i mai troba les claus "nvidia:…" del bundle.
let perText: Map<string, string> | null = null;
function bundlePerText(): Map<string, string> {
	if (perText) return perText;
	perText = new Map();
	for (const [k, v] of Object.entries(carrega())) {
		const i = k.indexOf(' ');
		if (i > 0) perText.set(k.slice(i + 1), v);
	}
	return perText;
}

// ---------------------------------------------------------------------------
// Motor NVIDIA (LLM)
// ---------------------------------------------------------------------------

const SISTEMA =
	"Ets un traductor expert de billar a tres bandes (carambola). Tradueixes el text " +
	"d'entrenament del coreà al CATALÀ, de manera natural i fluida, com ho explicaria un " +
	'entrenador català. Fes servir EXACTAMENT aquests termes de billar:\n' +
	GLOSSARI.map(([ko, ca]) => `- ${ko} → ${ca}`).join('\n') +
	'\n\nNormes: conserva el sentit tècnic exacte; escriu en català correcte i natural (no ' +
	'literal, no calcat); les boles del joc són "bola 1" (jugadora), "bola 2" i "bola 3"; ' +
	'no afegeixis comentaris, títols ni notes; respon NOMÉS amb la traducció.';

async function tradueixNvidia(
	fetch: typeof globalThis.fetch,
	text: string,
	clau: string
): Promise<string> {
	const ctrl = new AbortController();
	// Timeout llarg: la traducció es transmet (streaming) i no bloqueja la pàgina,
	// així que podem esperar encara que el tier gratuït vagi lent.
	const temporitzador = setTimeout(() => ctrl.abort(), 45000);
	try {
		const r = await fetch('https://integrate.api.nvidia.com/v1/chat/completions', {
			method: 'POST',
			signal: ctrl.signal,
			headers: {
				Authorization: `Bearer ${clau}`,
				'Content-Type': 'application/json',
				Accept: 'application/json'
			},
			body: JSON.stringify({
				model: modelNvidia(),
				messages: [
					{ role: 'system', content: SISTEMA },
					{ role: 'user', content: text }
				],
				temperature: 0.2,
				top_p: 0.9,
				max_tokens: 1024
			})
		});
		if (!r.ok) throw new Error(`nvidia ${r.status}`);
		const d = (await r.json()) as { choices?: Array<{ message?: { content?: string } }> };
		let out = d.choices?.[0]?.message?.content ?? '';
		// Alguns models de raonament embolcallen la resposta amb <think>...</think>.
		out = out.replace(/<think>[\s\S]*?<\/think>/g, '').trim();
		return correccions(out);
	} finally {
		clearTimeout(temporitzador);
	}
}

// ---------------------------------------------------------------------------
// Motor Google Translate (alternativa)
// ---------------------------------------------------------------------------

function posaMarcadors(textKo: string): { marcat: string; mapa: Map<string, string> } {
	let t = textKo;
	const mapa = new Map<string, string>();
	GLOSSARI.forEach(([ko, ca], i) => {
		if (t.includes(ko)) {
			const marcador = `XX${i}XX`;
			t = t.split(ko).join(marcador);
			mapa.set(marcador, ca);
		}
	});
	return { marcat: t, mapa };
}

async function tradueixGoogle(fetch: typeof globalThis.fetch, text: string): Promise<string> {
	const { marcat, mapa } = posaMarcadors(text);
	const url =
		'https://translate.googleapis.com/translate_a/single?client=gtx&sl=ko&tl=ca&dt=t&q=' +
		encodeURIComponent(marcat);
	const r = await fetch(url);
	if (!r.ok) throw new Error(`google ${r.status}`);
	const data = (await r.json()) as [Array<[string, ...unknown[]]>, ...unknown[]];
	let out = data[0].map((seg) => seg[0]).join('');
	out = out.replace(/XX\s*(\d+)\s*XX/gi, (m, n) => mapa.get(`XX${n}XX`) ?? m);
	return correccions(out);
}

// ---------------------------------------------------------------------------
// API pública
// ---------------------------------------------------------------------------

/** Tradueix un text coreà al català. Retorna l'original si la traducció falla. */
export async function tradueixKoCa(fetch: typeof globalThis.fetch, text: string): Promise<string> {
	const t = (text ?? '').trim();
	if (!t) return '';

	const clau = clauNvidia();
	const etiqueta = clau ? `nvidia:${modelNvidia()}` : 'google:v2';
	const cache = carrega();
	const clauCache = `${etiqueta} ${t}`;
	if (clauCache in cache) return cache[clauCache];
	// Bundle pre-traduït (per text, independent del motor): és el cas normal a
	// producció i evita traduir en directe (lent/inestable a Vercel).
	const preTraduit = bundlePerText().get(t);
	if (preTraduit !== undefined) return preTraduit;

	let trad: string;
	let esFallback = false;
	try {
		trad = clau ? await tradueixNvidia(fetch, t, clau) : await tradueixGoogle(fetch, t);
	} catch {
		// Si NVIDIA falla o va lent, prova Google; si tot falla, deixa l'original.
		try {
			trad = await tradueixGoogle(fetch, t);
			esFallback = true;
		} catch {
			return text;
		}
	}
	if (!trad) return text;

	// No cachegem els fallbacks de Google: així la propera vegada es reintenta NVIDIA.
	if (!esFallback) {
		cache[clauCache] = trad;
		desa();
	}
	return trad;
}
