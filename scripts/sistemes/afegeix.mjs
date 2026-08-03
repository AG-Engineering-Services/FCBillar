/**
 * Afegeix al catàleg els N millors candidats de descomposició (data/forts.json):
 * baixa subtítols i, en UNA crida a l'LLM, en treu nom + família + resum +
 * explicació a fons (calcul/correccions/exemples). Deduplica contra el catàleg.
 *
 * Ús:  node afegeix.mjs [N=200]
 */
import { readFileSync, writeFileSync, existsSync, rmSync, mkdirSync, readdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ARREL = dirname(fileURLToPath(import.meta.url));
const env = readFileSync(join(ARREL, '.env'), 'utf8');
const NV = env.match(/^NVIDIA_API_KEY=(.+)$/m)[1].trim();
const MODEL = 'meta/llama-3.3-70b-instruct';
const YTDLP = 'C:/Users/algoa/ProjectesInformatics/AMBilliard/.venv/Scripts/yt-dlp.exe';
const BUNDLE = 'c:/Users/algoa/ProjectesInformatics/FCBillar/web/src/lib/sistemes/sistemes.json';
const DATA = join(ARREL, 'data', 'sistemes.json');
const TMP = join(ARREL, '_subs_af');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const N = Number(process.argv[2] || 200);

const CATEGORIES = ['Endavant', 'Endarrere', 'De costat', 'Tocar la bola fina', 'Gran rotació', 'Bricol', 'Doble banda', 'Travessa', 'Sense efecte', 'Sistemes de càlcul', 'Tècnica bàsica', 'Altres'];

function familiaPerTitol(t) {
	const x = t || '';
	if (/비껴치기|빗겨치기|빗겨|얇게/.test(x)) return 'Tocar la bola fina';
	if (/대회전/.test(x)) return 'Gran rotació';
	if (/더블쿠션|더불쿠션|더블/.test(x)) return 'Doble banda';
	if (/횡단/.test(x)) return 'Travessa';
	if (/무회전|노잉글리쉬|노잉글리시/i.test(x)) return 'Sense efecte';
	if (/뱅크|투뱅크|뱅크샷|bank|바운딩/i.test(x)) return 'Bricol';
	if (/앞돌/.test(x)) return 'Endavant';
	if (/뒤돌|되돌아/.test(x)) return 'Endarrere';
	if (/옆돌/.test(x)) return 'De costat';
	if (/파이브앤하프|하프\s*시스템|시스템\s*15|볼\s*시스템|기울기|포인트|계산법/i.test(x)) return 'Sistemes de càlcul';
	if (/넣어치기|구멍치기|분리각|세워치기/.test(x)) return 'Tècnica bàsica';
	return null;
}
function normalitza(s) {
	return String(s)
		.replace(/\bdel gruix\b/gi, 'de la quantitat de bola').replace(/\bal gruix\b/gi, 'a la quantitat de bola')
		.replace(/\bel gruix\b/gi, 'la quantitat de bola').replace(/\bun gruix\b/gi, 'una quantitat de bola')
		.replace(/\baquest gruix\b/gi, 'aquesta quantitat de bola').replace(/\bgruixos\b/gi, 'quantitats de bola')
		.replace(/\bgruix\b/gi, 'quantitat de bola');
}

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
async function nvidia(sys, user) {
	const r = await fetch('https://integrate.api.nvidia.com/v1/chat/completions', { method: 'POST', headers: { Authorization: `Bearer ${NV}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ model: MODEL, messages: [{ role: 'system', content: sys }, { role: 'user', content: user }], temperature: 0.3, max_tokens: 2000 }) });
	if (!r.ok) throw new Error('nvidia ' + r.status);
	const d = await r.json();
	return (d.choices?.[0]?.message?.content ?? '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
}
async function analitza(titol, trans) {
	const teSub = !!trans;
	const reglaFons = teSub
		? `- APROFUNDEIX: extreu TOTES les regles i correccions del vídeo (per línia/posició, correccions ±, bola enganxada…), fins a 10 a "correccions". "exemples": casos resolts amb xifres (fins a 5).`
		: `- MATERIAL LIMITAT (sense subtítols): NO t'inventis correccions/exemples numèrics. "calcul":"", "correccions":[], "exemples":[]. Fes queEs i passos qualitatius.`;
	const sys = `Ets mestre de billar a tres bandes que ensenya en CATALÀ. Et donen el títol i (potser) la transcripció coreana d'un vídeo sobre un sistema on el tir es descompon en QUANTITAT DE BOLA (두께) + EFECTE (당점/기울기/팁). Respon NOMÉS aquest JSON:
{"nom":"<nom curt català; conserva noms propis: ball-system/볼시스템, 기울기=inclinació, 7빼기=menys 7, 제자리=retorn al lloc>","categoria":<${CATEGORIES.join('|')}>,"resum":"<1 frase>","queEs":"<2-3 frases>","calcul":"<regla base amb números; '' si no n'hi ha>","correccions":["..."],"passos":["..."],"exemples":["..."],"quan":"<1-2 frases>","consells":["..."],"nivell":"<bàsic|mitjà|avançat>"}
Regles:
${reglaFons}
- Terminologia OBLIGATÒRIA: "quantitat de bola" (mai "gruix"), en vuitens 1/8…8/8; "efecte"/"tac"; bola 1/2/3; rombe/diamant. Tot en català, concís.`;
	let out = '';
	for (let a = 0; a < 6 && !out; a++) { try { out = await nvidia(sys, `TÍTOL: ${titol}\n\nTRANSCRIPCIÓ: ${(trans || '(sense subtítols)').slice(0, 7000)}`); } catch { if (a < 5) await sleep(4000 * (a + 1)); } }
	const m = out.match(/\{[\s\S]*\}/); if (!m) return null;
	try {
		const j = JSON.parse(m[0]);
		if (!j.queEs && !j.nom) return null;
		const arr = (x) => (Array.isArray(x) ? x.map(String).filter(Boolean) : x ? [String(x)] : []);
		return {
			nom: j.nom ? String(j.nom) : titol.slice(0, 40),
			categoria: CATEGORIES.includes(j.categoria) ? j.categoria : 'Sistemes de càlcul',
			resum: normalitza(j.resum || ''),
			explicacio: {
				queEs: normalitza(j.queEs || ''), calcul: j.calcul ? normalitza(j.calcul) : '',
				correccions: arr(j.correccions).map(normalitza), passos: arr(j.passos).map(normalitza),
				exemples: arr(j.exemples).map(normalitza), quan: j.quan ? normalitza(j.quan) : '',
				consells: arr(j.consells).map(normalitza), nivell: ['bàsic', 'mitjà', 'avançat'].includes(j.nivell) ? j.nivell : 'mitjà'
			}
		};
	} catch { return null; }
}

// --- Execució ---
const SUBS = { '중대당구박사': 79000, '양빵당구': 209000, '뽠주TV': 130000, '초이스연구소': 54000, '야매당구쫑프로': 232000, '당구개론&패턴시스템': 111000, '수호신당구레슨': 98000, '당구달인TV': 98000, '필승당구레슨': 105000, '아이빌리TV': 370000, '3쿠션 연습문제': 2000, '방수좋아 당구TV': 300000, '짠당구': 49000 };
const forts = JSON.parse(readFileSync(join(ARREL, 'data', 'forts.json'), 'utf8'));
let cataleg = JSON.parse(readFileSync(BUNDLE, 'utf8'));
const tenim = new Set(cataleg.map((s) => s.id));
const cua = forts.filter((c) => !tenim.has(c.id)).slice(0, N);
console.log(`Afegint ${cua.length} sistemes (descomposició quantitat de bola + efecte)…\n`);

let fets = 0;
for (let i = 0; i < cua.length; i++) {
	const c = cua[i];
	const trans = transcripcio(c.id);
	const a = await analitza(c.titol, trans);
	if (a) {
		const entrada = {
			id: c.id, nom: a.nom, categoria: familiaPerTitol(c.titol) || a.categoria, resum: a.resum,
			canal: c.canal, canalId: c.chId, subs: SUBS[c.canal] || 0,
			visites: c.visites || 0, likes: 0, comentaris: c.comentaris || 0, data: c.data, miniatura: c.miniatura,
			valoracio: null, notaValoracio: '', funcionaComentaris: null,
			explicacio: a.explicacio, font: trans ? 'subtítols' : 'títol', descomposicio: true
		};
		if (trans) entrada.transcripcio = trans.slice(0, 8000);
		cataleg.push(entrada);
		fets++;
		if (fets % 5 === 0 || fets <= 3) console.log(`  [${fets}/${cua.length}] ${a.nom.slice(0, 32).padEnd(32)} [${entrada.categoria}] ${trans ? '·sub' : ''}`);
		// desa cada 10 per no perdre feina si peta
		if (fets % 10 === 0) { writeFileSync(BUNDLE, JSON.stringify(cataleg, null, 2)); }
	} else {
		console.log(`  ✗ ${c.titol.slice(0, 40)} — sense resultat`);
	}
	await sleep(200);
}
try { rmSync(TMP, { recursive: true, force: true }); } catch {}
writeFileSync(BUNDLE, JSON.stringify(cataleg, null, 2));
try { mkdirSync(dirname(DATA), { recursive: true }); writeFileSync(DATA, JSON.stringify(cataleg, null, 2)); } catch {}
console.log(`\nFet: afegits ${fets}. Catàleg ara: ${cataleg.length} sistemes.`);
