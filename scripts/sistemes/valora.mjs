/**
 * Reposa la valoració de comentaris (i els likes) als sistemes afegits sense
 * valoració: baixa els comentaris més rellevants i l'LLM els puntua.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ARREL = dirname(fileURLToPath(import.meta.url));
const env = readFileSync(join(ARREL, '.env'), 'utf8');
const YT = env.match(/^YOUTUBE_API_KEY=(.+)$/m)[1].trim();
const NV = env.match(/^NVIDIA_API_KEY=(.+)$/m)[1].trim();
const MODEL = 'meta/llama-3.3-70b-instruct';
const BUNDLE = 'c:/Users/algoa/ProjectesInformatics/FCBillar/web/src/lib/sistemes/sistemes.json';
const DATA = join(ARREL, 'data', 'sistemes.json');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function ytSafe(path) {
	try { const r = await fetch(`https://www.googleapis.com/youtube/v3/${path}&key=${YT}`); const d = await r.json(); if (d.error) return null; return d; } catch { return null; }
}
async function comentaris(id) {
	const d = await ytSafe(`commentThreads?part=snippet&videoId=${id}&maxResults=15&order=relevance&textFormat=plainText`);
	return (d?.items || []).map((it) => it.snippet?.topLevelComment?.snippet?.textDisplay || '').filter(Boolean);
}
async function likesDe(ids) {
	const out = {};
	for (let i = 0; i < ids.length; i += 50) {
		const d = await ytSafe(`videos?part=statistics&id=${ids.slice(i, i + 50).join(',')}`);
		for (const v of d?.items || []) out[v.id] = Number(v.statistics?.likeCount || 0);
	}
	return out;
}
async function nvidia(sys, user) {
	const r = await fetch('https://integrate.api.nvidia.com/v1/chat/completions', { method: 'POST', headers: { Authorization: `Bearer ${NV}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ model: MODEL, messages: [{ role: 'system', content: sys }, { role: 'user', content: user }], temperature: 0.2, max_tokens: 200 }) });
	if (!r.ok) throw new Error('nvidia ' + r.status);
	const d = await r.json();
	return (d.choices?.[0]?.message?.content ?? '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
}
async function valora(coms) {
	if (!coms.length) return { valoracio: null, nota: '', funciona: null };
	const sys = `Ets expert en billar a tres bandes. Et donen COMENTARIS (coreà) d'un vídeo d'un sistema. Respon NOMÉS JSON: {"valoracio": <0-100 segons com de positius/útils són>, "nota": "<3-6 paraules català sobre la recepció>", "funciona": <true si diuen que funciona a la pràctica; false o null si no queda clar>}`;
	let out = '';
	for (let a = 0; a < 5 && !out; a++) { try { out = await nvidia(sys, coms.slice(0, 15).map((c) => '- ' + c.replace(/\s+/g, ' ').slice(0, 200)).join('\n')); } catch { await sleep(3000); } }
	const m = out.match(/\{[\s\S]*\}/); if (!m) return { valoracio: null, nota: '', funciona: null };
	try { const j = JSON.parse(m[0]); return { valoracio: typeof j.valoracio === 'number' ? j.valoracio : null, nota: j.nota || '', funciona: j.funciona ?? null }; } catch { return { valoracio: null, nota: '', funciona: null }; }
}

const cataleg = JSON.parse(readFileSync(BUNDLE, 'utf8'));
const cua = cataleg.filter((s) => s.descomposicio && s.valoracio == null);
console.log(`Valorant ${cua.length} sistemes…`);
const likes = await likesDe(cua.map((s) => s.id));
let fet = 0;
for (const s of cua) {
	if (likes[s.id] != null) s.likes = likes[s.id];
	const coms = await comentaris(s.id);
	const v = await valora(coms);
	s.valoracio = v.valoracio; s.notaValoracio = v.nota; s.funcionaComentaris = v.funciona;
	fet++;
	if (fet % 10 === 0) { console.log(`  ${fet}/${cua.length}`); writeFileSync(BUNDLE, JSON.stringify(cataleg, null, 2)); }
	await sleep(200);
}
for (const p of [BUNDLE, DATA]) writeFileSync(p, JSON.stringify(cataleg, null, 2));
const amb = cataleg.filter((s) => s.descomposicio && s.valoracio != null).length;
console.log(`\nFet. Amb valoració: ${amb}/${cua.length}. Mitjana: ${Math.round(cataleg.filter((s) => s.descomposicio && s.valoracio != null).reduce((a, s) => a + s.valoracio, 0) / (amb || 1))}`);
