/**
 * Explicacions de text dels "Sistemes Coreans".
 *
 * Per a cada sistema del catàleg (data/sistemes.json / bundle web):
 *   1) Baixa els subtítols coreans del vídeo amb yt-dlp (manual o auto).
 *   2) Si no en té, cau cap a la descripció del vídeo (YouTube API).
 *   3) Passa el material a l'LLM (llama-3.3-70b) perquè el tradueixi i el
 *      converteixi en una explicació DIDÀCTICA i estructurada en català
 *      (què és · com s'aplica · quan · consells · nivell).
 *   4) Desa l'explicació (i un tros de la transcripció original) al catàleg.
 *
 * Escriu tant a scripts/sistemes/data/sistemes.json com al bundle de la web.
 *
 * Ús:  node explica.mjs [nomésSenseExplicacio]
 */
import { readFileSync, writeFileSync, existsSync, rmSync, mkdirSync, readdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ARREL = dirname(fileURLToPath(import.meta.url));
const env = readFileSync(join(ARREL, '.env'), 'utf8');
const NV = env.match(/^NVIDIA_API_KEY=(.+)$/m)[1].trim();
const YT = env.match(/^YOUTUBE_API_KEY=(.+)$/m)[1].trim();
const MODEL = 'meta/llama-3.3-70b-instruct';
const YTDLP = 'C:/Users/algoa/ProjectesInformatics/AMBilliard/.venv/Scripts/yt-dlp.exe';

// El bundle de la web és la font de veritat (és el que es desplega).
const BUNDLE = 'c:/Users/algoa/ProjectesInformatics/FCBillar/web/src/lib/sistemes/sistemes.json';
const DATA = join(ARREL, 'data', 'sistemes.json');
const TMP = join(ARREL, '_subs');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// --- 1) Transcripció (subtítols coreans) via yt-dlp ---
function transcripcio(id) {
	try { rmSync(TMP, { recursive: true, force: true }); } catch {}
	mkdirSync(TMP, { recursive: true });
	try {
		execFileSync(
			YTDLP,
			[
				'--skip-download', '--write-subs', '--write-auto-subs',
				'--sub-langs', 'ko,ko-orig,ko-KR', '--sub-format', 'json3',
				'--no-warnings', '--quiet',
				'-o', join(TMP, '%(id)s.%(ext)s'),
				`https://www.youtube.com/watch?v=${id}`
			],
			{ stdio: 'ignore', timeout: 90000 }
		);
	} catch {
		// pot fallar (sense subtítols, xarxa…): retornem buit i caurem a la descripció
	}
	const files = existsSync(TMP) ? readdirSync(TMP) : [];
	const f =
		files.find((x) => /\.ko\.json3$/.test(x)) ||
		files.find((x) => /\.ko-orig\.json3$/.test(x)) ||
		files.find((x) => /\.json3$/.test(x));
	if (!f) return '';
	try {
		const j = JSON.parse(readFileSync(join(TMP, f), 'utf8'));
		return (j.events || [])
			.flatMap((e) => (e.segs || []).map((s) => s.utf8 || ''))
			.join('')
			.replace(/\s+/g, ' ')
			.trim();
	} catch {
		return '';
	}
}

// --- descripció completa de reserva (YouTube API) ---
async function descripcio(id) {
	try {
		const r = await fetch(`https://www.googleapis.com/youtube/v3/videos?part=snippet&id=${id}&key=${YT}`);
		const j = await r.json();
		return (j.items?.[0]?.snippet?.description || '').trim();
	} catch {
		return '';
	}
}

// --- 2) Explicació estructurada amb l'LLM ---
async function nvidia(sys, user) {
	const r = await fetch('https://integrate.api.nvidia.com/v1/chat/completions', {
		method: 'POST',
		headers: { Authorization: `Bearer ${NV}`, 'Content-Type': 'application/json' },
		body: JSON.stringify({
			model: MODEL,
			messages: [{ role: 'system', content: sys }, { role: 'user', content: user }],
			temperature: 0.3,
			max_tokens: 900
		})
	});
	if (!r.ok) throw new Error('nvidia ' + r.status);
	const d = await r.json();
	return (d.choices?.[0]?.message?.content ?? '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
}

async function explica(v, trans, desc) {
	const material = trans
		? `TRANSCRIPCIÓ (subtítols coreans del vídeo):\n${trans.slice(0, 6000)}`
		: desc
			? `DESCRIPCIÓ del vídeo (coreà):\n${desc.slice(0, 2000)}`
			: `(No hi ha text del vídeo. Explica el sistema "${v.nom}" amb el teu coneixement de billar a tres bandes.)`;

	const sys = `Ets un mestre de billar a tres bandes (carambola) que ensenya en CATALÀ. Et donen material en coreà d'un vídeo de YouTube sobre el sistema "${v.nom}" (categoria: ${v.categoria}). La teva feina és entendre'l i escriure'n una explicació DIDÀCTICA en català.

Respon NOMÉS amb aquest JSON (sense text abans ni després):
{
  "queEs": "<2-4 frases: què és el sistema i per a què serveix>",
  "passos": ["<idea o pas clau 1>", "<pas 2>", "..."],
  "quan": "<1-2 frases: en quines situacions de joc fer-lo servir>",
  "consells": ["<consell pràctic o error típic>", "..."],
  "nivell": "<bàsic|mitjà|avançat>"
}

Regles:
- Explica DE VERITAT el mètode: números, línies, punts de banda, quantitat de bola, efecte i força, si el material ho permet. "passos" ha de tenir 2-6 elements en ordre.
- "consells": 0-3 elements (errors típics, matisos d'efecte/força). Pot ser [].
- Terminologia catalana de billar: banda, efecte, quantitat de bola, bola 1/2/3, diamant/rombe, entrada.
- No inventis dades que contradiguin el material. Si el material és pobre, recolza't en el teu coneixement del sistema pel nom, però no t'inventis xifres concretes falses.
- Concís i clar, sense floritures. Tot en català.`;

	let out = '';
	for (let a = 0; a < 6 && !out; a++) {
		try {
			out = await nvidia(sys, material);
		} catch (e) {
			if (a < 5) await sleep(4000 * (a + 1));
		}
	}
	const m = out.match(/\{[\s\S]*\}/);
	if (!m) return null;
	try {
		const j = JSON.parse(m[0]);
		if (!j.queEs) return null;
		if (!Array.isArray(j.passos)) j.passos = j.passos ? [String(j.passos)] : [];
		if (!Array.isArray(j.consells)) j.consells = j.consells ? [String(j.consells)] : [];
		return {
			queEs: String(j.queEs),
			passos: j.passos.map(String).filter(Boolean),
			quan: j.quan ? String(j.quan) : '',
			consells: j.consells.map(String).filter(Boolean),
			nivell: ['bàsic', 'mitjà', 'avançat'].includes(j.nivell) ? j.nivell : 'mitjà'
		};
	} catch {
		return null;
	}
}

// --- Execució ---
const nomesBuits = process.argv[2] === '1' || process.argv[2] === 'buits';
const cataleg = JSON.parse(readFileSync(BUNDLE, 'utf8'));
console.log(`Enriquint ${cataleg.length} sistemes amb explicacions…\n`);

let fets = 0, ambSub = 0;
for (const v of cataleg) {
	if (nomesBuits && v.explicacio) { console.log(`· ${v.nom} — ja té explicació, ometo`); continue; }
	const trans = transcripcio(v.id);
	const desc = trans ? '' : await descripcio(v.id);
	const font = trans ? 'subtítols' : desc ? 'descripció' : 'coneixement';
	if (trans) ambSub++;
	const exp = await explica(v, trans, desc);
	if (exp) {
		v.explicacio = exp;
		v.font = font;
		if (trans) v.transcripcio = trans.slice(0, 4000);
		fets++;
		console.log(`✓ ${v.nom.padEnd(30)} [${font}] · ${exp.passos.length} passos · ${exp.nivell}`);
	} else {
		console.log(`✗ ${v.nom.padEnd(30)} — l'LLM no ha retornat explicació`);
	}
	await sleep(400);
}

try { rmSync(TMP, { recursive: true, force: true }); } catch {}

writeFileSync(BUNDLE, JSON.stringify(cataleg, null, 2));
try { mkdirSync(dirname(DATA), { recursive: true }); writeFileSync(DATA, JSON.stringify(cataleg, null, 2)); } catch {}
console.log(`\nFet: ${fets}/${cataleg.length} amb explicació (${ambSub} des de subtítols). Desat al bundle.`);
