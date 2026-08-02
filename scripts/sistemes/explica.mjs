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
			max_tokens: 2000
		})
	});
	if (!r.ok) throw new Error('nvidia ' + r.status);
	const d = await r.json();
	return (d.choices?.[0]?.message?.content ?? '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
}

async function explica(v, trans, desc) {
	const material = trans
		? `TRANSCRIPCIÓ (subtítols coreans del vídeo):\n${trans.slice(0, 8000)}`
		: desc
			? `DESCRIPCIÓ del vídeo (coreà):\n${desc.slice(0, 2000)}`
			: `(No hi ha text del vídeo. Explica el sistema "${v.nom}" amb el teu coneixement de billar a tres bandes.)`;

	// Només amb transcripció real extraiem el càlcul a fons; amb només descripció
	// o nom, prohibim inventar correccions/exemples numèrics.
	const reglaFons = trans
		? `- APROFUNDEIX: extreu TOTES les regles, correccions i casos que dóna el vídeo (correccions de 3a banda ±caselles, casos per cada línia 1/2/3/4, bola enganxada a banda, variants de gran rotació…). Posa'ls a "correccions" (com més complet millor, fins a 8 elements).
- "exemples": 2-4 casos resolts del vídeo amb totes les xifres. Si el vídeo només en mostra un, posa'n un.`
		: `- MATERIAL LIMITAT: només tens una descripció curta o el nom, NO la lliçó sencera. NO t'inventis correccions ni exemples numèrics: deixa "calcul":"", "correccions":[] i "exemples":[] EXCEPTE que el text els contingui explícitament. Dóna queEs i uns passos qualitatius, i sigues honest sobre el que el material no concreta.`;

	const sys = `Ets un mestre de billar a tres bandes (carambola) que ensenya en CATALÀ. Et donen material en coreà d'un vídeo de YouTube sobre el sistema "${v.nom}" (categoria: ${v.categoria}). La teva feina és entendre'l i escriure'n una explicació DIDÀCTICA i DETALLADA que ENSENYI EL CÀLCUL A FONS, en català.

Respon NOMÉS amb aquest JSON (sense text abans ni després):
{
  "queEs": "<2-3 frases: què és el sistema i per a què serveix>",
  "calcul": "<LA REGLA BASE de càlcul, amb NÚMEROS: la fórmula, com es numeren bandes/rombes, com es combinen efecte i gruix. Explícita. '' si NO és un sistema de càlcul>",
  "correccions": ["<cada AJUST/CORRECCIÓ que dóna el vídeo, amb números: p.ex. 'si la 3a banda queda 1 rombe curta, suma 1', 'bola 1 enganxada a la banda: gruix ≤2/8 per evitar corba', 'línia 2: ½ tac i gruix 2/8'>", "..."],
  "passos": ["<pas concret del procediment, en ordre>", "..."],
  "exemples": ["<exemple RESOLT amb totes les xifres (posició bola 1, gruix, efecte, correccions, resultat)>", "<un altre exemple, si el vídeo en dóna>", "..."],
  "quan": "<1-2 frases: en quines situacions de joc fer-lo servir>",
  "consells": ["<consell pràctic o error típic, amb números>", "..."],
  "nivell": "<bàsic|mitjà|avançat>"
}

Regles CLAU:
${reglaFons}
- "calcul" = la regla base clara amb la fórmula i els números (buit si el material no en dóna).
- Numera i anomena com ho fa el vídeo (rombes/diamants, línies de punt, gruixos en vuitens 1/8…8/8, tacs d'efecte, ±).
- No inventis xifres que contradiguin el material. Si el material no dóna càlcul numèric, deixa "calcul":"", "correccions":[] i "exemples":[] i explica-ho qualitativament als passos.
- Terminologia catalana: banda, efecte (tac), quantitat de bola/gruix, bola 1/2/3, rombe/diamant, entrada. Concís, sense repetir-te, tot en català.`;

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
		const arr = (x) => (Array.isArray(x) ? x.map(String).filter(Boolean) : x ? [String(x)] : []);
		// compat: "exemple" (string antic) → "exemples" (array)
		const exemples = j.exemples ? arr(j.exemples) : arr(j.exemple);
		return {
			queEs: String(j.queEs),
			calcul: j.calcul ? String(j.calcul) : '',
			correccions: arr(j.correccions),
			passos: arr(j.passos),
			exemples,
			quan: j.quan ? String(j.quan) : '',
			consells: arr(j.consells),
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
		if (trans) v.transcripcio = trans.slice(0, 8000);
		fets++;
		console.log(`✓ ${v.nom.padEnd(30)} [${font}] · ${exp.correccions.length} corr · ${exp.exemples.length} ex · ${exp.nivell}`);
	} else {
		console.log(`✗ ${v.nom.padEnd(30)} — l'LLM no ha retornat explicació`);
	}
	await sleep(400);
}

try { rmSync(TMP, { recursive: true, force: true }); } catch {}

writeFileSync(BUNDLE, JSON.stringify(cataleg, null, 2));
try { mkdirSync(dirname(DATA), { recursive: true }); writeFileSync(DATA, JSON.stringify(cataleg, null, 2)); } catch {}
console.log(`\nFet: ${fets}/${cataleg.length} amb explicació (${ambSub} des de subtítols). Desat al bundle.`);
