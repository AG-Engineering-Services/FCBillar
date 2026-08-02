/**
 * Recull de "Sistemes Coreans" — enfoc CANAL-PRIMER.
 *
 * 1) Descoberta: busca sistemes/tutorials a YouTube i mira quins CANALS surten
 *    repetidament (senyal que s'hi dediquen). En tria els més dedicats + grans.
 * 2) Per cada canal seleccionat, n'agafa els vídeos MÉS VISTOS (search
 *    channelId + order=viewCount) i filtra els que semblen sistema/patró.
 * 3) Per als candidats (top per visites de cada canal) baixa els comentaris
 *    més rellevants i, en una sola crida a l'LLM, obté: categoria, nom, resum,
 *    i la VALORACIÓ dels comentaris (positius? diuen que funciona?).
 * 4) Es queda els millors de cada canal (visites + valoració) i desa el catàleg.
 *
 * Ús:  node recull.mjs [canals=12] [videosPerCanal=3]
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ARREL = dirname(fileURLToPath(import.meta.url));
const env = readFileSync(join(ARREL, '.env'), 'utf8');
const YT = env.match(/^YOUTUBE_API_KEY=(.+)$/m)[1].trim();
const NV = env.match(/^NVIDIA_API_KEY=(.+)$/m)[1].trim();
const MODEL = 'meta/llama-3.3-70b-instruct';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const N_CANALS = Number(process.argv[2] || 12);
const N_PER_CANAL = Number(process.argv[3] || 3);

const CATEGORIES = [
	'Bricol (bandes)',
	'Natural (sense efecte)',
	'Rotació',
	'Posició i patrons',
	'Tècnica bàsica',
	'Altres'
];

const CONSULTES = [
	'쓰리쿠션 시스템', '당구 시스템 계산법', '파이브앤하프 시스템', '뱅크샷 시스템',
	'쓰리쿠션 패턴', '무회전 시스템 당구', '앞돌리기 시스템', '뒤돌리기 시스템',
	'당구 레슨 쓰리쿠션', '쓰리쿠션 강의', '당구 시스템'
];

async function yt(path) {
	const r = await fetch(`https://www.googleapis.com/youtube/v3/${path}&key=${YT}`);
	const d = await r.json();
	if (d.error) throw new Error(`YT ${path.split('?')[0]}: ${d.error.message}`);
	return d;
}
async function ytSafe(path) { try { return await yt(path); } catch (e) { console.error('  ', e.message); return { items: [] }; } }

function esSistema(v) {
	const t = (v.titol + ' ' + v.descripcio).toLowerCase();
	return /시스템|system|패턴|pattern|계산|뱅크|bank|파이브|하프|plate|플레이트|무회전|라인|공식|레슨|강의|돌리기|접시|치기/.test(t);
}

// --- 1) Descoberta de canals ---
async function descobreixCanals() {
	const canals = new Map();
	for (const q of CONSULTES) {
		const d = await ytSafe(`search?part=snippet&q=${encodeURIComponent(q)}&type=video&maxResults=50&order=relevance&regionCode=KR&relevanceLanguage=ko`);
		for (const it of d.items || []) {
			const cid = it.snippet?.channelId; if (!cid) continue;
			const c = canals.get(cid) || { title: it.snippet.channelTitle, aparicions: 0 };
			c.aparicions++; canals.set(cid, c);
		}
		await sleep(150);
	}
	const rellevants = [...canals.entries()].filter(([, c]) => c.aparicions >= 3).map(([id]) => id);
	const stats = new Map();
	for (let i = 0; i < rellevants.length; i += 50) {
		const d = await ytSafe(`channels?part=snippet,statistics&id=${rellevants.slice(i, i + 50).join(',')}`);
		for (const c of d.items || []) stats.set(c.id, { title: c.snippet.title, subs: Number(c.statistics?.subscriberCount || 0) });
	}
	return [...canals.entries()]
		.filter(([id]) => stats.has(id))
		.map(([id, c]) => ({ id, title: stats.get(id).title, subs: stats.get(id).subs, aparicions: c.aparicions }))
		.sort((a, b) => b.aparicions - a.aparicions || b.subs - a.subs)
		.slice(0, N_CANALS);
}

// --- 2) Vídeos més vistos de cada canal ---
async function videosDeCanal(canalId) {
	const d = await ytSafe(`search?part=snippet&channelId=${canalId}&type=video&maxResults=25&order=viewCount&regionCode=KR&relevanceLanguage=ko`);
	return (d.items || []).map((it) => it.id.videoId).filter(Boolean);
}
async function estadistiques(ids) {
	const out = [];
	for (let i = 0; i < ids.length; i += 50) {
		const d = await ytSafe(`videos?part=snippet,statistics&id=${ids.slice(i, i + 50).join(',')}`);
		for (const v of d.items || []) out.push({
			id: v.id, titol: v.snippet.title, canal: v.snippet.channelTitle, canalId: v.snippet.channelId,
			descripcio: (v.snippet.description || '').slice(0, 600), data: v.snippet.publishedAt,
			miniatura: v.snippet.thumbnails?.medium?.url || v.snippet.thumbnails?.default?.url,
			visites: Number(v.statistics?.viewCount || 0), likes: Number(v.statistics?.likeCount || 0),
			comentaris: Number(v.statistics?.commentCount || 0)
		});
	}
	return out;
}

// --- 3) Comentaris més rellevants ---
async function comentaris(videoId) {
	const d = await ytSafe(`commentThreads?part=snippet&videoId=${videoId}&maxResults=15&order=relevance&textFormat=plainText`);
	return (d.items || []).map((it) => it.snippet?.topLevelComment?.snippet?.textDisplay || '').filter(Boolean);
}

// --- LLM: classifica + valora comentaris en una sola crida ---
async function nvidia(sys, user, maxTokens = 400) {
	const r = await fetch('https://integrate.api.nvidia.com/v1/chat/completions', {
		method: 'POST', headers: { Authorization: `Bearer ${NV}`, 'Content-Type': 'application/json' },
		body: JSON.stringify({ model: MODEL, messages: [{ role: 'system', content: sys }, { role: 'user', content: user }], temperature: 0.2, max_tokens: maxTokens })
	});
	if (!r.ok) throw new Error('nvidia ' + r.status);
	const d = await r.json();
	return (d.choices?.[0]?.message?.content ?? '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
}
async function analitza(v, coments) {
	const sys = `Ets un expert en billar a tres bandes (carambola). Et donen el TÍTOL, la DESCRIPCIÓ i alguns COMENTARIS (tot en coreà) d'un vídeo de YouTube d'un sistema/patró de billar.
Respon NOMÉS amb aquest JSON:
{"categoria": <una EXACTA: ${CATEGORIES.join(' | ')}>, "nom": "<nom del sistema>", "resum": "<1-2 frases en català>", "esSistema": <true si és un sistema/mètode concret; false si és una partida o vídeo genèric>, "valoracio": <0-100 segons com de positius i útils són els comentaris>, "nota": "<3-6 paraules en català sobre la recepció, p.ex. 'molt ben valorat, diuen que funciona'>", "funciona": <true si els comentaris suggereixen que el sistema funciona a la pràctica; false o null si no queda clar>}
Regles nom: CONSERVA el nom propi si en té (Five & Half, Plate, Sistema de 15, 991…); transcriu coreans (파이브앤하프=Five & Half). No tradueixis genèricament el títol. Si els comentaris estan buits, valoracio=null i funciona=null. Català a resum i nota. Res més que el JSON.`;
	const user = `TÍTOL: ${v.titol}\n\nDESCRIPCIÓ: ${v.descripcio}\n\nCOMENTARIS:\n${coments.slice(0, 15).map((c) => '- ' + c.replace(/\s+/g, ' ').slice(0, 200)).join('\n') || '(cap)'}`;
	let out = '';
	for (let a = 0; a < 6 && !out; a++) { try { out = await nvidia(sys, user); } catch { if (a < 5) await sleep(4000 * (a + 1)); } }
	const m = out.match(/\{[\s\S]*\}/); if (!m) return null;
	try {
		const j = JSON.parse(m[0]);
		if (!CATEGORIES.includes(j.categoria)) j.categoria = 'Altres';
		return j;
	} catch { return null; }
}

// --- Execució ---
console.log('1) Descobrint canals especialitzats…');
const canals = await descobreixCanals();
canals.forEach((c) => console.log(`   · ${c.title} (${(c.subs / 1000).toFixed(0)}k subs, ${c.aparicions} aparicions)`));

console.log('\n2) Agafant els vídeos més vistos de cada canal…');
const perCanal = new Map(); // canalId -> candidats[]
for (const c of canals) {
	const ids = await videosDeCanal(c.id);
	const vids = (await estadistiques(ids)).filter(esSistema).sort((a, b) => b.visites - a.visites);
	perCanal.set(c.id, vids.slice(0, N_PER_CANAL + 2)); // uns quants més per filtrar després amb valoració
	console.log(`   · ${c.title}: ${vids.length} sistemes candidats`);
	await sleep(150);
}

console.log('\n3) Valorant comentaris i classificant amb l\'LLM…');
const cataleg = [];
for (const c of canals) {
	const candidats = perCanal.get(c.id) || [];
	const analitzats = [];
	for (const v of candidats) {
		const coms = await comentaris(v.id);
		const a = await analitza(v, coms);
		if (a && a.esSistema !== false) {
			const valoracio = typeof a.valoracio === 'number' ? a.valoracio : null;
			analitzats.push({
				id: v.id, nom: a.nom || v.titol, categoria: a.categoria, resum: a.resum || '',
				canal: v.canal, canalId: v.canalId, subs: c.subs, visites: v.visites, likes: v.likes,
				comentaris: v.comentaris, data: v.data, miniatura: v.miniatura,
				valoracio, notaValoracio: a.nota || '', funcionaComentaris: a.funciona ?? null
			});
		}
		await sleep(250);
	}
	// millor combinació de visites + valoració; ens quedem N_PER_CANAL de cada canal
	const maxV = Math.max(1, ...analitzats.map((x) => x.visites));
	analitzats.sort((a, b) => {
		const sa = 0.6 * (a.visites / maxV) + 0.4 * ((a.valoracio ?? 50) / 100);
		const sb = 0.6 * (b.visites / maxV) + 0.4 * ((b.valoracio ?? 50) / 100);
		return sb - sa;
	});
	for (const x of analitzats.slice(0, N_PER_CANAL)) {
		cataleg.push(x);
		console.log(`   [${x.categoria}] ${x.nom} · ${x.visites.toLocaleString()} vis · valoració ${x.valoracio ?? '—'} · ${x.canal}`);
	}
}

// ordena el catàleg per visites (la web ja ho reordena, però per si de cas)
cataleg.sort((a, b) => b.visites - a.visites);
mkdirSync(join(ARREL, 'data'), { recursive: true });
writeFileSync(join(ARREL, 'data', 'sistemes.json'), JSON.stringify(cataleg, null, 2));
writeFileSync('c:/Users/algoa/ProjectesInformatics/FCBillar/web/src/lib/sistemes/sistemes.json', JSON.stringify(cataleg, null, 2));
console.log(`\nDesats ${cataleg.length} sistemes de ${canals.length} canals.`);
