/**
 * Processador de l'EXPLORADOR: agafa les peticions pendents de la cua Supabase
 * (fcbillar.sistema_peticio), extreu el text del vídeo (subtítols de YouTube o,
 * si no n'hi ha, transcripció d'àudio amb Whisper per a IG/FB/TikTok…), el
 * tradueix i l'analitza (mateix procés que el catàleg), l'afegeix a Sistemes
 * Coreans i, si l'admin l'ha validat, el marca com que funciona. Fa el desplegament.
 *
 * Ús:  node explora.mjs            (processa la cua i fa push)
 *      node explora.mjs --no-push  (no desplega)
 */
import { readFileSync, writeFileSync, existsSync, rmSync, mkdirSync, readdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ARREL = dirname(fileURLToPath(import.meta.url));
const env = readFileSync(join(ARREL, '.env'), 'utf8');
const NV = env.match(/^NVIDIA_API_KEY=(.+)$/m)[1].trim();
// Supabase (URL + service key) del .env de l'arrel de FCBillar
const root = readFileSync('c:/Users/algoa/ProjectesInformatics/FCBillar/.env', 'utf8');
const SB_URL = root.match(/^SUPABASE_URL=(.+)$/m)[1].trim();
const SB_KEY = root.match(/^SUPABASE_SERVICE_ROLE_KEY=(.+)$/m)[1].trim();
const MODEL = 'meta/llama-3.3-70b-instruct';
const YTDLP = 'C:/Users/algoa/ProjectesInformatics/AMBilliard/.venv/Scripts/yt-dlp.exe';
const WHISPER = 'C:/Users/algoa/ProjectesInformatics/AMBilliard/.venv/Scripts/whisper.exe';
const WMODEL = 'small';
const BUNDLE = 'c:/Users/algoa/ProjectesInformatics/FCBillar/web/src/lib/sistemes/sistemes.json';
const DATA = join(ARREL, 'data', 'sistemes.json');
const TMP = join(ARREL, '_explora');
const noPush = process.argv.includes('--no-push');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const CATEGORIES = ['Endavant', 'Endarrere', 'De costat', 'Tocar la bola fina', 'Gran rotació', 'Bricol', 'Doble banda', 'Travessa', 'Sense efecte', 'Sistemes de càlcul', 'Tècnica bàsica', 'Altres'];
function familiaPerTitol(t) {
	const x = t || '';
	if (/비껴치기|빗겨치기|얇게/.test(x)) return 'Tocar la bola fina';
	if (/대회전/.test(x)) return 'Gran rotació';
	if (/더블쿠션|더블/.test(x)) return 'Doble banda';
	if (/횡단/.test(x)) return 'Travessa';
	if (/무회전|노잉글리쉬/i.test(x)) return 'Sense efecte';
	if (/뱅크|투뱅크|뱅크샷|bank|바운딩/i.test(x)) return 'Bricol';
	if (/앞돌/.test(x)) return 'Endavant';
	if (/뒤돌|되돌아/.test(x)) return 'Endarrere';
	if (/옆돌/.test(x)) return 'De costat';
	return null;
}
function normalitza(s) {
	return String(s).replace(/\bdel gruix\b/gi, 'de la quantitat de bola').replace(/\bel gruix\b/gi, 'la quantitat de bola').replace(/\bgruixos\b/gi, 'quantitats de bola').replace(/\bgruix\b/gi, 'quantitat de bola');
}

// --- Supabase REST (schema fcbillar) ---
async function sb(method, path, body, extraHeaders = {}) {
	const r = await fetch(`${SB_URL}/rest/v1/${path}`, {
		method,
		headers: { apikey: SB_KEY, Authorization: `Bearer ${SB_KEY}`, 'Content-Type': 'application/json', 'Accept-Profile': 'fcbillar', 'Content-Profile': 'fcbillar', ...extraHeaders },
		body: body ? JSON.stringify(body) : undefined
	});
	if (!r.ok) throw new Error(`SB ${method} ${path}: ${r.status} ${await r.text()}`);
	return r.status === 204 ? null : r.json();
}
const pendents = () => sb('GET', 'sistema_peticio?estat=eq.pendent&order=creat.asc&select=*');
const actualitza = (id, camps) => sb('PATCH', `sistema_peticio?id=eq.${id}`, camps, { Prefer: 'return=minimal' });
const marca = (video_id) => sb('POST', 'sistema_marca', { video_id, funciona: true, updated_at: new Date().toISOString() }, { Prefer: 'resolution=merge-duplicates,return=minimal' });

// --- yt-dlp: metadades + text (subtítols o Whisper) ---
function metadata(url) {
	const out = execFileSync(YTDLP, ['-J', '--no-warnings', url], { maxBuffer: 64 * 1024 * 1024, timeout: 120000 }).toString();
	const j = JSON.parse(out);
	return {
		id: j.id, titol: j.title || '', canal: j.channel || j.uploader || '', canalId: j.channel_id || j.uploader_id || '',
		visites: Number(j.view_count || 0), likes: Number(j.like_count || 0), comentaris: Number(j.comment_count || 0),
		subs: Number(j.channel_follower_count || 0), data: j.upload_date ? `${j.upload_date.slice(0, 4)}-${j.upload_date.slice(4, 6)}-${j.upload_date.slice(6, 8)}T00:00:00Z` : null,
		miniatura: j.thumbnail || '', llengua: j.language || '',
		teSub: Object.keys(j.subtitles || {}).some((k) => /^(ko|vi|en)/.test(k)) || Object.keys(j.automatic_captions || {}).some((k) => /^(ko|vi)/.test(k))
	};
}
function subtitols(url) {
	try { rmSync(TMP, { recursive: true, force: true }); } catch {}
	mkdirSync(TMP, { recursive: true });
	try {
		execFileSync(YTDLP, ['--skip-download', '--write-subs', '--write-auto-subs', '--sub-langs', 'ko,ko-orig,vi,vi-orig,en', '--sub-format', 'json3', '--no-warnings', '--quiet', '-o', join(TMP, 'v.%(ext)s'), url], { stdio: 'ignore', timeout: 90000 });
	} catch {}
	const files = existsSync(TMP) ? readdirSync(TMP) : [];
	const f = files.find((x) => /\.ko\.json3$/.test(x)) || files.find((x) => /\.(vi|ko-orig|vi-orig)\.json3$/.test(x)) || files.find((x) => /\.json3$/.test(x));
	if (!f) return '';
	try { const j = JSON.parse(readFileSync(join(TMP, f), 'utf8')); return (j.events || []).flatMap((e) => (e.segs || []).map((s) => s.utf8 || '')).join('').replace(/\s+/g, ' ').trim(); } catch { return ''; }
}
function ambWhisper(url) {
	try { rmSync(TMP, { recursive: true, force: true }); } catch {}
	mkdirSync(TMP, { recursive: true });
	try {
		execFileSync(YTDLP, ['-x', '--audio-format', 'mp3', '--audio-quality', '5', '--no-warnings', '--quiet', '-o', join(TMP, 'aud.%(ext)s'), url], { stdio: 'ignore', timeout: 180000 });
	} catch { return ''; }
	const mp3 = join(TMP, 'aud.mp3');
	if (!existsSync(mp3)) return '';
	try {
		execFileSync(WHISPER, [mp3, '--model', WMODEL, '--output_format', 'txt', '--output_dir', TMP, '--task', 'transcribe', '--fp16', 'False', '--verbose', 'False'], { stdio: 'ignore', timeout: 600000 });
		const txt = readdirSync(TMP).find((x) => x.endsWith('.txt'));
		return txt ? readFileSync(join(TMP, txt), 'utf8').replace(/\s+/g, ' ').trim() : '';
	} catch { return ''; }
}

// --- LLM: anàlisi (nom + família + resum + explicació a fons) ---
async function nvidia(sys, user) {
	const r = await fetch('https://integrate.api.nvidia.com/v1/chat/completions', { method: 'POST', headers: { Authorization: `Bearer ${NV}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ model: MODEL, messages: [{ role: 'system', content: sys }, { role: 'user', content: user }], temperature: 0.3, max_tokens: 2000 }) });
	if (!r.ok) throw new Error('nvidia ' + r.status);
	const d = await r.json();
	return (d.choices?.[0]?.message?.content ?? '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
}
async function analitza(titol, text) {
	const teText = !!text;
	const reglaFons = teText
		? `- APROFUNDEIX: extreu totes les regles/correccions/casos del vídeo (fins a 10 a "correccions"). "exemples": casos resolts amb xifres (fins a 5).`
		: `- SENSE TEXT: no t'inventis correccions/exemples. "calcul":"", "correccions":[], "exemples":[]. queEs i passos qualitatius.`;
	const sys = `Ets mestre de billar a tres bandes que ensenya en CATALÀ. Et donen el títol i (potser) la transcripció (en l'idioma original: coreà, vietnamita…) d'un vídeo de billar. Respon NOMÉS aquest JSON:
{"nom":"<nom curt català; conserva noms propis>","categoria":<${CATEGORIES.join('|')}>,"resum":"<1 frase>","queEs":"<2-3 frases>","calcul":"<regla base amb números; '' si cap>","correccions":["..."],"passos":["..."],"exemples":["..."],"quan":"<1-2 frases>","consells":["..."],"nivell":"<bàsic|mitjà|avançat>"}
Regles:
${reglaFons}
- Terminologia OBLIGATÒRIA: "quantitat de bola" (mai "gruix"), vuitens 1/8…8/8; "efecte"/"tac"; bola 1/2/3. Tot en català, concís. Cap caràcter no llatí al "nom".`;
	let out = '';
	for (let a = 0; a < 6 && !out; a++) { try { out = await nvidia(sys, `TÍTOL: ${titol}\n\nTRANSCRIPCIÓ: ${(text || '(sense text)').slice(0, 8000)}`); } catch { if (a < 5) await sleep(4000 * (a + 1)); } }
	const m = out.match(/\{[\s\S]*\}/); if (!m) return null;
	try {
		const j = JSON.parse(m[0]); const arr = (x) => (Array.isArray(x) ? x.map(String).filter(Boolean) : x ? [String(x)] : []);
		return {
			nom: normalitza(j.nom || titol.slice(0, 40)), categoria: CATEGORIES.includes(j.categoria) ? j.categoria : 'Altres', resum: normalitza(j.resum || ''),
			explicacio: { queEs: normalitza(j.queEs || ''), calcul: j.calcul ? normalitza(j.calcul) : '', correccions: arr(j.correccions).map(normalitza), passos: arr(j.passos).map(normalitza), exemples: arr(j.exemples).map(normalitza), quan: j.quan ? normalitza(j.quan) : '', consells: arr(j.consells).map(normalitza), nivell: ['bàsic', 'mitjà', 'avançat'].includes(j.nivell) ? j.nivell : 'mitjà' }
		};
	} catch { return null; }
}

// --- Execució ---
const cua = await pendents();
if (!cua.length) { console.log('Cap petició pendent.'); process.exit(0); }
console.log(`${cua.length} peticions pendents.\n`);
let cataleg = JSON.parse(readFileSync(BUNDLE, 'utf8'));
const tenim = new Set(cataleg.map((s) => s.id));
let afegits = 0;

for (const p of cua) {
	console.log(`▶ ${p.url}`);
	try {
		await actualitza(p.id, { estat: 'processant' });
		const meta = metadata(p.url);
		if (tenim.has(meta.id)) { await actualitza(p.id, { estat: 'duplicat', video_id: meta.id, nom: meta.titol.slice(0, 80), processat: new Date().toISOString() }); console.log('  · ja al catàleg'); continue; }
		let text = subtitols(p.url);
		let font = 'subtítols';
		if (!text) { console.log('  · sense subtítols → Whisper (àudio)…'); text = ambWhisper(p.url); font = text ? 'whisper' : 'títol'; }
		const a = await analitza(meta.titol, text);
		if (!a) { await actualitza(p.id, { estat: 'error', missatge: 'LLM sense resposta', processat: new Date().toISOString() }); console.log('  ✗ LLM'); continue; }
		const entrada = {
			id: meta.id, nom: a.nom, categoria: familiaPerTitol(meta.titol) || a.categoria, resum: a.resum,
			canal: meta.canal, canalId: meta.canalId, subs: meta.subs, visites: meta.visites, likes: meta.likes, comentaris: meta.comentaris,
			data: meta.data, miniatura: meta.miniatura, valoracio: null, notaValoracio: '', funcionaComentaris: null,
			explicacio: a.explicacio, font, explorat: true, plataforma: p.plataforma || 'youtube', url: p.url
		};
		if (text) entrada.transcripcio = text.slice(0, 8000);
		cataleg.push(entrada); tenim.add(meta.id); afegits++;
		writeFileSync(BUNDLE, JSON.stringify(cataleg, null, 2));
		if (p.validar) { try { await marca(meta.id); } catch {} }
		await actualitza(p.id, { estat: 'fet', video_id: meta.id, nom: a.nom, missatge: `${font}${p.validar ? ' · validat' : ''}`, processat: new Date().toISOString() });
		console.log(`  ✓ ${a.nom} [${entrada.categoria}] (${font})${p.validar ? ' · validat' : ''}`);
	} catch (e) {
		await actualitza(p.id, { estat: 'error', missatge: String(e.message).slice(0, 200), processat: new Date().toISOString() }).catch(() => {});
		console.log('  ✗', e.message);
	}
	await sleep(300);
}
try { rmSync(TMP, { recursive: true, force: true }); } catch {}
try { writeFileSync(DATA, JSON.stringify(cataleg, null, 2)); } catch {}

console.log(`\nAfegits ${afegits}. Catàleg: ${cataleg.length}.`);
if (afegits && !noPush) {
	console.log('Desplegant…');
	try {
		execFileSync('git', ['-C', 'c:/Users/algoa/ProjectesInformatics/FCBillar', 'add', 'web/src/lib/sistemes/sistemes.json', 'scripts/sistemes/data/sistemes.json'], { stdio: 'inherit' });
		execFileSync('git', ['-C', 'c:/Users/algoa/ProjectesInformatics/FCBillar', 'commit', '-m', `Sistemes Coreans: +${afegits} des de l'explorador`], { stdio: 'inherit' });
		execFileSync('git', ['-C', 'c:/Users/algoa/ProjectesInformatics/FCBillar', 'push', 'origin', 'master'], { stdio: 'inherit' });
		console.log('Desplegat.');
	} catch (e) { console.log('Push fallit (fes-lo a mà):', e.message); }
}
