/**
 * Filtre específic per al canal 뽠주TV (HwanjuTV): troba els vídeos on el tir es
 * pot DESCOMPONDRE a voluntat en quantitat de bola (두께) + efecte (당점/기울기)
 * — el mètode que interessa a l'Albert (com el 1234 / 제자리 sistemes).
 *
 * Baixa els subtítols coreans de cada candidat i demana a l'LLM si el mètode és
 * d'aquest tipus. Mode 'report' (per defecte) només informa; 'apply' afegeix els
 * confirmats al catàleg.
 *
 * Ús:  node hwanju.mjs [report|apply]
 */
import { readFileSync, writeFileSync, existsSync, rmSync, mkdirSync, readdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ARREL = dirname(fileURLToPath(import.meta.url));
const env = readFileSync(join(ARREL, '.env'), 'utf8');
const YT = env.match(/^YOUTUBE_API_KEY=(.+)$/m)[1].trim();
const NV = env.match(/^NVIDIA_API_KEY=(.+)$/m)[1].trim();
const MODEL = 'meta/llama-3.3-70b-instruct';
const YTDLP = 'C:/Users/algoa/ProjectesInformatics/AMBilliard/.venv/Scripts/yt-dlp.exe';
const TMP = join(ARREL, '_subs_hj');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Candidats (vídeos-mètode del 뽠주TV, no simples demos de tir).
const CANDIDATS = [
	'VSrIi09c9ro', 'AfVJDHD-MJ0', 'u1TdnONjcek', 'K1Zwn8v6Bqg', 'sAakZctnVwI',
	'h0RmCKnyepg', 'Pj2jSknQbVU', '8d-3Yp6BQks', 'o68umf9EMC4', '--x5y8fSfiM',
	'GaWqbvQE5Xo', 'mOrRcqYeoIw', 'CT9OmtD6nYs', 'upWS8xE67Vk', '2mKuJ3WeHEk',
	'q-4Z7B12yE0', 'xO_39EVUZyg', 'SR6xn3qF3i4', 'SyY0D838DoY', 'Q3bfHaJDBG0'
];

function transcripcio(id) {
	try { rmSync(TMP, { recursive: true, force: true }); } catch {}
	mkdirSync(TMP, { recursive: true });
	try {
		execFileSync(YTDLP, ['--skip-download', '--write-subs', '--write-auto-subs', '--sub-langs', 'ko,ko-orig,ko-KR', '--sub-format', 'json3', '--no-warnings', '--quiet', '-o', join(TMP, '%(id)s.%(ext)s'), `https://www.youtube.com/watch?v=${id}`], { stdio: 'ignore', timeout: 90000 });
	} catch {}
	const files = existsSync(TMP) ? readdirSync(TMP) : [];
	const f = files.find((x) => /\.ko\.json3$/.test(x)) || files.find((x) => /\.ko-orig\.json3$/.test(x)) || files.find((x) => /\.json3$/.test(x));
	if (!f) return '';
	try { const j = JSON.parse(readFileSync(join(TMP, f), 'utf8')); return (j.events || []).flatMap((e) => (e.segs || []).map((s) => s.utf8 || '')).join('').replace(/\s+/g, ' ').trim(); } catch { return ''; }
}
async function meta(ids) {
	const out = {};
	for (let i = 0; i < ids.length; i += 50) {
		const r = await fetch(`https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&id=${ids.slice(i, i + 50).join(',')}&key=${YT}`);
		const j = await r.json();
		for (const v of j.items || []) out[v.id] = { titol: v.snippet.title, canal: v.snippet.channelTitle, data: v.snippet.publishedAt, miniatura: v.snippet.thumbnails?.medium?.url, visites: Number(v.statistics?.viewCount || 0), likes: Number(v.statistics?.likeCount || 0), comentaris: Number(v.statistics?.commentCount || 0) };
	}
	return out;
}
async function nvidia(sys, user) {
	const r = await fetch('https://integrate.api.nvidia.com/v1/chat/completions', { method: 'POST', headers: { Authorization: `Bearer ${NV}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ model: MODEL, messages: [{ role: 'system', content: sys }, { role: 'user', content: user }], temperature: 0.2, max_tokens: 400 }) });
	if (!r.ok) throw new Error('nvidia ' + r.status);
	const d = await r.json();
	return (d.choices?.[0]?.message?.content ?? '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
}
async function classifica(titol, trans) {
	const sys = `Ets expert en billar a tres bandes. Et donen el títol i la transcripció (coreà) d'un vídeo. Digues si el sistema que ensenya es basa a DESCOMPONDRE el tir en QUANTITAT DE BOLA (두께, gruix) + EFECTE (당점/팁/기울기), on el jugador pot REPARTIR a voluntat entre quantitat de bola i efecte per obtenir el mateix valor (p.ex. 3 = 3두께+0팁 = 2두께+1팁).
Respon NOMÉS JSON: {"descomposicio": <true/false>, "nom": "<nom curt en català>", "categoria": <"Endavant"|"Endarrere"|"De costat"|"Tocar la bola fina"|"Gran rotació"|"Bricol"|"Sense efecte"|"Sistemes de càlcul"|"Tècnica bàsica"|"Altres">, "resum": "<1 frase català>", "motiu": "<per què sí/no, breu>"}`;
	const out = await nvidia(sys, `TÍTOL: ${titol}\n\nTRANSCRIPCIÓ: ${(trans || '(sense subtítols)').slice(0, 5000)}`);
	const m = out.match(/\{[\s\S]*\}/); if (!m) return null;
	try { return JSON.parse(m[0]); } catch { return null; }
}

const mode = process.argv[2] || 'report';
const M = await meta(CANDIDATS);
const resultats = [];
for (const id of CANDIDATS) {
	const t = transcripcio(id);
	let c = null;
	for (let a = 0; a < 5 && !c; a++) { try { c = await classifica(M[id]?.titol || id, t); } catch { await sleep(3000); } }
	if (c) {
		resultats.push({ id, ...M[id], ...c, teSub: !!t });
		console.log(`${c.descomposicio ? '✅' : '❌'} ${(M[id]?.titol || id).slice(0, 42).padEnd(42)} ${c.descomposicio ? '→ ' + c.nom : ''} ${c.motiu ? '(' + c.motiu.slice(0, 40) + ')' : ''}`);
	} else {
		console.log(`?? ${id} — sense classificació`);
	}
	await sleep(300);
}
try { rmSync(TMP, { recursive: true, force: true }); } catch {}
const si = resultats.filter((r) => r.descomposicio);
console.log(`\nAmb descomposició quantitat de bola + efecte: ${si.length}/${resultats.length}`);
writeFileSync(join(ARREL, 'data', 'hwanju_resultats.json'), JSON.stringify(resultats, null, 2));

if (mode === 'apply') {
	const P = ['c:/Users/algoa/ProjectesInformatics/FCBillar/web/src/lib/sistemes/sistemes.json', join(ARREL, 'data', 'sistemes.json')];
	for (const p of P) {
		const cat = JSON.parse(readFileSync(p, 'utf8'));
		const tenim = new Set(cat.map((s) => s.id));
		for (const r of si) {
			if (tenim.has(r.id)) continue;
			cat.push({ id: r.id, nom: r.nom, categoria: r.categoria, resum: r.resum, canal: r.canal, canalId: 'UC6QmdmVb4T8rKj-SS1Lq3Yw', subs: 130000, visites: r.visites, likes: r.likes, comentaris: r.comentaris, data: r.data, miniatura: r.miniatura, valoracio: null, notaValoracio: '', funcionaComentaris: null });
		}
		writeFileSync(p, JSON.stringify(cat, null, 2));
	}
	console.log(`Afegits ${si.length} sistemes al catàleg (executa explica.mjs per a les explicacions).`);
}
