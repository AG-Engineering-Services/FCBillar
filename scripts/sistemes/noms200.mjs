/**
 * Neteja els noms dels sistemes de descomposició afegits: genera un nom curt,
 * clar i DISTINTIU en català a partir del títol coreà real (data/forts.json),
 * amb glossari, i diferencia els duplicats.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ARREL = dirname(fileURLToPath(import.meta.url));
const env = readFileSync(join(ARREL, '.env'), 'utf8');
const NV = env.match(/^NVIDIA_API_KEY=(.+)$/m)[1].trim();
const MODEL = 'meta/llama-3.3-70b-instruct';
const BUNDLE = 'c:/Users/algoa/ProjectesInformatics/FCBillar/web/src/lib/sistemes/sistemes.json';
const DATA = join(ARREL, 'data', 'sistemes.json');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const forts = JSON.parse(readFileSync(join(ARREL, 'data', 'forts.json'), 'utf8'));
const titolPerId = Object.fromEntries(forts.map((c) => [c.id, c.titol]));
const cataleg = JSON.parse(readFileSync(BUNDLE, 'utf8'));
const nous = cataleg.filter((s) => s.descomposicio);

async function nvidia(sys, user) {
	const r = await fetch('https://integrate.api.nvidia.com/v1/chat/completions', { method: 'POST', headers: { Authorization: `Bearer ${NV}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ model: MODEL, messages: [{ role: 'system', content: sys }, { role: 'user', content: user }], temperature: 0.2, max_tokens: 1500 }) });
	if (!r.ok) throw new Error('nvidia ' + r.status);
	const d = await r.json();
	return (d.choices?.[0]?.message?.content ?? '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
}

const SYS = `Ets expert en billar a tres bandes i tradueixes al CATALÀ. Et donen una llista de TÍTOLS coreans de vídeos. Per a cada un, dóna un NOM curt, clar i DISTINTIU en català (3-7 paraules) per etiquetar el sistema.

Glossari coreà→català:
볼시스템/볼 시스템=Ball-system · 기울기=inclinació · 7빼기=menys 7 · 제자리=retorn al lloc · 더블쿠션=doble banda · 횡단=travessa · 앞돌리기=endavant · 뒤돌리기=endarrere · 옆돌리기=de costat · 비껴치기=tocar la bola fina · 대회전=gran rotació · 뱅크=bricol · 무회전=sense efecte · 두께=quantitat de bola · 당점=efecte · 스트록=cop · 계산법=mètode de càlcul · 분리각=angle de separació · 세워치기=vertical · 되돌아오기=tornada · 시스템=sistema

Regles:
- NO deixis cap caràcter coreà al nom.
- Conserva noms propis/números (Ball-system, 7, Five & Half, 40, 369…).
- Fes-los DISTINTIUS entre ells (afegeix el tret que els diferencia: tipus de tir, inclinació, doble banda, etc.). No posis dos noms iguals.
- Res de números de capítol (화, 편) ni hashtags.
Respon NOMÉS un array JSON: [{"id":"...","nom":"..."}, ...] en el mateix ordre.`;

const byId = {};
const LOT = 14;
for (let i = 0; i < nous.length; i += LOT) {
	const lot = nous.slice(i, i + LOT);
	const user = lot.map((s, k) => `${k + 1}. id=${s.id} | ${titolPerId[s.id] || s.nom}`).join('\n');
	let out = '';
	for (let a = 0; a < 5 && !out; a++) { try { out = await nvidia(SYS, user); } catch { await sleep(3000); } }
	const m = out.match(/\[[\s\S]*\]/);
	if (m) { try { JSON.parse(m[0]).forEach((x) => { if (x.id && x.nom) byId[x.id] = String(x.nom).replace(/["\[\]]/g, '').trim(); }); } catch {} }
	console.log(`  lot ${i / LOT + 1}: ${Object.keys(byId).length}/${nous.length} noms`);
	await sleep(200);
}

// aplica + dedupe (contra TOT el catàleg)
const vistos = new Map(); // nom → count
cataleg.forEach((s) => { if (!s.descomposicio) vistos.set(s.nom, (vistos.get(s.nom) || 0) + 1); });
const hangul = /[\uac00-\ud7a3]/;
for (const s of nous) {
	let nom = byId[s.id] || s.nom;
	if (hangul.test(nom)) nom = 'Sistema de bola + efecte'; // fallback si encara té coreà
	if (vistos.has(nom)) {
		const alt = `${nom} · ${s.canal}`;
		nom = vistos.has(alt) ? `${nom} (${vistos.get(nom) + 1})` : alt;
	}
	vistos.set(nom, (vistos.get(nom) || 0) + 1);
	s.nom = nom;
}

for (const p of [BUNDLE, DATA]) writeFileSync(p, JSON.stringify(cataleg, null, 2));
const cnt = {}; cataleg.forEach((s) => (cnt[s.nom] = (cnt[s.nom] || 0) + 1));
console.log('\nAmb coreà:', cataleg.filter((s) => hangul.test(s.nom)).length, '· duplicats:', Object.values(cnt).filter((n) => n > 1).length);
console.log('Mostra:', nous.slice(0, 12).map((s) => s.nom).join(' · '));
