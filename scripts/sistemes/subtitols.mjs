/**
 * Genera la TRADUCCIÓ LITERAL al català dels subtítols (transcripció) de cada
 * sistema que en tingui i encara no tingui `traduccioLiteral`. Tradueix el text
 * sencer per trossos (fidel, sense resumir). Es mostra sota el vídeo a la fitxa.
 *
 * Ús:  node subtitols.mjs
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

function normalitza(s) {
	return String(s).replace(/\bdel gruix\b/gi, 'de la quantitat de bola').replace(/\bel gruix\b/gi, 'la quantitat de bola').replace(/\bgruixos\b/gi, 'quantitats de bola').replace(/\bgruix\b/gi, 'quantitat de bola');
}
async function nvidia(text) {
	const sys = `Tradueix LITERALMENT al CATALÀ aquest fragment de subtítols d'un vídeo de billar a tres bandes (l'original és en coreà o vietnamita). Regles: fidel i complet, sense resumir ni ometre res, frase per frase; NO afegeixis comentaris ni encapçalaments; usa terminologia catalana de billar (quantitat de bola —mai "gruix"—, efecte/tac, banda, bola 1/2/3, rombe/diamant). Retorna NOMÉS la traducció.`;
	const r = await fetch('https://integrate.api.nvidia.com/v1/chat/completions', { method: 'POST', headers: { Authorization: `Bearer ${NV}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ model: MODEL, messages: [{ role: 'system', content: sys }, { role: 'user', content: text }], temperature: 0.2, max_tokens: 2400 }) });
	if (!r.ok) throw new Error('nvidia ' + r.status);
	const d = await r.json();
	return (d.choices?.[0]?.message?.content ?? '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
}
// parteix el text en trossos de ~3500 car respectant els espais
function trossos(t, mida = 3500) {
	const out = []; let i = 0;
	while (i < t.length) {
		let fi = Math.min(i + mida, t.length);
		if (fi < t.length) { const tall = t.lastIndexOf(' ', fi); if (tall > i + 1000) fi = tall; }
		out.push(t.slice(i, fi)); i = fi;
	}
	return out;
}
async function tradueix(transcripcio) {
	const parts = trossos(transcripcio);
	const res = [];
	for (const p of parts) {
		let out = '';
		for (let a = 0; a < 6 && !out; a++) { try { out = await nvidia(p); } catch { if (a < 5) await sleep(4000 * (a + 1)); } }
		res.push(normalitza(out));
		await sleep(150);
	}
	return res.join(' ').replace(/\s+/g, ' ').trim();
}

const cataleg = JSON.parse(readFileSync(BUNDLE, 'utf8'));
const cua = cataleg.filter((s) => s.transcripcio && !s.traduccioLiteral);
console.log(`Traduint literalment ${cua.length} transcripcions…\n`);
let fet = 0;
for (const s of cua) {
	try {
		s.traduccioLiteral = await tradueix(s.transcripcio);
		fet++;
		if (fet % 5 === 0 || fet <= 3) console.log(`  [${fet}/${cua.length}] ${s.nom.slice(0, 34)} (${s.traduccioLiteral.length} car)`);
		if (fet % 10 === 0) writeFileSync(BUNDLE, JSON.stringify(cataleg, null, 2));
	} catch (e) { console.log(`  ✗ ${s.nom.slice(0, 34)} — ${e.message}`); }
}
for (const p of [BUNDLE, DATA]) writeFileSync(p, JSON.stringify(cataleg, null, 2));
console.log(`\nFet: ${fet}/${cua.length} amb traducció literal.`);
