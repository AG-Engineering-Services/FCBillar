/**
 * Descoberta de CANALS coreans de tutorials/sistemes de billar.
 *
 * En comptes d'agafar vídeos virals solts, busquem quins canals surten
 * repetidament a les cerques de sistemes/tutorials (senyal que s'hi dediquen),
 * i n'obtenim les estadístiques (subscriptors, nre. de vídeos).
 *
 * Ús:  node descobreix-canals.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ARREL = dirname(fileURLToPath(import.meta.url));
const env = readFileSync(join(ARREL, '.env'), 'utf8');
const YT = env.match(/^YOUTUBE_API_KEY=(.+)$/m)[1].trim();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Consultes de descoberta (coreà): sistemes, patrons, lliçons de tres bandes.
const CONSULTES = [
	'쓰리쿠션 시스템',
	'당구 시스템 계산법',
	'파이브앤하프 시스템',
	'뱅크샷 시스템',
	'쓰리쿠션 패턴',
	'무회전 시스템 당구',
	'앞돌리기 시스템',
	'뒤돌리기 시스템',
	'당구 레슨 쓰리쿠션',
	'쓰리쿠션 강의',
	'당구 시스템'
];

async function ytSearch(q, order) {
	const url = `https://www.googleapis.com/youtube/v3/search?part=snippet&q=${encodeURIComponent(q)}&type=video&maxResults=50&order=${order}&regionCode=KR&relevanceLanguage=ko&key=${YT}`;
	const r = await fetch(url);
	const d = await r.json();
	if (d.error) { console.error('search error', q, d.error.message); return []; }
	return d.items || [];
}

// 1) Recompte d'aparicions per canal
const canals = new Map(); // channelId -> { title, aparicions, videos:Set }
for (const q of CONSULTES) {
	for (const order of ['relevance', 'viewCount']) {
		const items = await ytSearch(q, order);
		for (const it of items) {
			const cid = it.snippet.channelId;
			if (!cid) continue;
			const c = canals.get(cid) || { title: it.snippet.channelTitle, aparicions: 0, videos: new Set() };
			c.aparicions++;
			c.videos.add(it.id.videoId);
			canals.set(cid, c);
		}
		await sleep(150);
	}
}
console.log('Canals únics trobats:', canals.size);

// 2) Estadístiques dels canals que apareixen com a mínim 3 cops
const rellevants = [...canals.entries()].filter(([, c]) => c.aparicions >= 3);
const ids = rellevants.map(([id]) => id);
const stats = new Map();
for (let i = 0; i < ids.length; i += 50) {
	const url = `https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&id=${ids.slice(i, i + 50).join(',')}&key=${YT}`;
	const r = await fetch(url);
	const d = await r.json();
	for (const c of d.items || []) {
		stats.set(c.id, {
			title: c.snippet.title,
			subs: Number(c.statistics?.subscriberCount || 0),
			videos: Number(c.statistics?.videoCount || 0),
			views: Number(c.statistics?.viewCount || 0)
		});
	}
}

// 3) Rànquing: aparicions (dedicació al tema) × subscriptors
const taula = rellevants
	.map(([id, c]) => {
		const s = stats.get(id) || {};
		return {
			id,
			title: s.title || c.title,
			aparicions: c.aparicions,
			videosTrobats: c.videos.size,
			subs: s.subs || 0,
			videos: s.videos || 0
		};
	})
	.sort((a, b) => b.aparicions - a.aparicions || b.subs - a.subs);

console.log('\nCanals (aparicions / vídeos-tema trobats / subscriptors / total vídeos):\n');
for (const c of taula.slice(0, 25)) {
	console.log(
		`${String(c.aparicions).padStart(3)}×  ${String(c.videosTrobats).padStart(3)}v  ${(c.subs / 1000).toFixed(0).padStart(5)}k subs  ${String(c.videos).padStart(5)} vids  ${c.title}`
	);
}
