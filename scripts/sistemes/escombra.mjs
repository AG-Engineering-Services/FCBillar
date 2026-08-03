/**
 * Escombra TOTS els vídeos dels 13 canals i marca els candidats a sistema de
 * DESCOMPOSICIÓ "quantitat de bola (두께) + efecte (당점/팁/기울기)".
 *
 * Fase barata: baixa títol+descripció de tots els vídeos (uploads playlist) i
 * puntua el senyal de descomposició. Desa els candidats a data/escombra.json.
 * (La verificació amb subtítols+LLM es fa després, sobre els millors candidats.)
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ARREL = dirname(fileURLToPath(import.meta.url));
const env = readFileSync(join(ARREL, '.env'), 'utf8');
const YT = env.match(/^YOUTUBE_API_KEY=(.+)$/m)[1].trim();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const CANALS = JSON.parse(readFileSync('c:/Users/algoa/AppData/Local/Temp/claude/c--Users-algoa-ProjectesInformatics-AMBilliard/2f66ab0e-5c8d-4448-8b49-8e97c8342be8/scratchpad/canals.json', 'utf8'));

async function yt(path) {
	const r = await fetch(`https://www.googleapis.com/youtube/v3/${path}&key=${YT}`);
	const d = await r.json();
	if (d.error) throw new Error(d.error.message);
	return d;
}

// Puntua el senyal de descomposició quantitat de bola + efecte.
function puntua(text) {
	const t = text;
	let s = 0; const per = [];
	if (/기울기/.test(t)) { s += 3; per.push('기울기'); }
	if (/볼\s*시스템/.test(t)) { s += 3; per.push('볼시스템'); }
	if (/(당점.{0,8}두께)|(두께.{0,8}당점)|(두께.{0,8}팁)|(팁.{0,8}두께)/.test(t)) { s += 4; per.push('당점+두께'); }
	if (/\d\s*=\s*[^=]*[+＋][^=]*/.test(t)) { s += 3; per.push('fórmula N=..+..'); }
	if (/등분|나누기|분리치기|분리각/.test(t)) { s += 2; per.push('divisió'); }
	if (/제자리/.test(t)) { s += 2; per.push('제자리'); }
	if (/당점|두께|팁/.test(t)) { s += 1; }
	if (/시스템|계산/.test(t)) { s += 1; }
	return { s, per: [...new Set(per)] };
}

const totCand = [];
const resum = {};
for (const [chId, nom] of Object.entries(CANALS)) {
	let up;
	try { up = (await yt(`channels?part=contentDetails&id=${chId}`)).items?.[0]?.contentDetails?.relatedPlaylists?.uploads; } catch (e) { console.log('  err canal', nom, e.message); continue; }
	if (!up) continue;
	let page = '', total = 0, cand = 0;
	for (let k = 0; k < 80; k++) {
		let j;
		try { j = await yt(`playlistItems?part=snippet&playlistId=${up}&maxResults=50&pageToken=${page}`); } catch (e) { break; }
		for (const it of j.items || []) {
			const sn = it.snippet;
			const vid = sn?.resourceId?.videoId; if (!vid) continue;
			total++;
			const { s, per } = puntua((sn.title || '') + ' ' + (sn.description || '').slice(0, 200));
			if (s >= 3) { totCand.push({ id: vid, canal: nom, chId, titol: sn.title, score: s, per }); cand++; }
		}
		if (!j.nextPageToken) break; page = j.nextPageToken; await sleep(40);
	}
	resum[nom] = { total, cand };
	console.log(`${nom.padEnd(20)} ${String(total).padStart(5)} vídeos → ${cand} candidats`);
}

totCand.sort((a, b) => b.score - a.score);
mkdirSync(join(ARREL, 'data'), { recursive: true });
writeFileSync(join(ARREL, 'data', 'escombra.json'), JSON.stringify({ resum, candidats: totCand }, null, 2));
console.log(`\nTotal: ${totCand.length} candidats a descomposició (desats a data/escombra.json)`);
console.log('Per senyal fort (score>=4):', totCand.filter((c) => c.score >= 4).length);
