/**
 * Genera els DIAGRAMES dels sistemes coreans: per a cada sistema (segons la seva
 * família de tir) construeix un exemple representatiu i GEOMÈTRICAMENT VÀLID
 * (rebots reals a les gomes) en coordenades de diamants (x 0..8, y 0..4).
 *
 * b1 = blanca (tiradora) · b2 = groga (1a bola) · b3 = vermella (2a bola/arribada)
 * traca = recorregut de la blanca: [b1, b2, banda1, …, bandaN, b3]
 *
 * Ús:  node diagrames.mjs [print|apply]
 */
import { readFileSync, writeFileSync } from 'node:fs';

const r1 = (n) => Math.round(n * 10) / 10;

// Reflexió d'un raig dins la taula [0,8]x[0,4]: des de P, direcció d, N bandes.
// Retorna els punts de rebot (sense el punt inicial).
function rebots(P, d, N) {
	let [x, y] = P;
	let [dx, dy] = d;
	const L = Math.hypot(dx, dy);
	dx /= L; dy /= L;
	const pts = [];
	for (let b = 0; b < N; b++) {
		const ts = [];
		if (dx > 1e-9) ts.push([(8 - x) / dx, 'x']);
		if (dx < -1e-9) ts.push([(0 - x) / dx, 'x']);
		if (dy > 1e-9) ts.push([(4 - y) / dy, 'y']);
		if (dy < -1e-9) ts.push([(0 - y) / dy, 'y']);
		const val = ts.filter(([t]) => t > 1e-6).sort((a, b) => a[0] - b[0])[0];
		if (!val) break;
		const [t, rail] = val;
		x += dx * t; y += dy * t;
		pts.push({ x, y, rail });
		if (rail === 'x') dx = -dx; else dy = -dy;
	}
	return { pts, dir: [dx, dy], fi: [x, y] };
}

// Construeix la traça: cue → bola1 → N bandes → bola2 (a l'extrem, allargant una mica).
function traca(cue, bola1, dir, nBandes, finalLen = 1.6) {
	const { pts, dir: dfi, fi } = rebots(bola1, dir, nBandes);
	const b3 = [
		Math.max(0.3, Math.min(7.7, fi[0] + dfi[0] * finalLen)),
		Math.max(0.3, Math.min(3.7, fi[1] + dfi[1] * finalLen))
	];
	const punts = [cue, bola1, ...pts.map((p) => [p.x, p.y]), b3].map(([x, y]) => [r1(x), r1(y)]);
	return { traca: punts, b3: [r1(b3[0]), r1(b3[1])] };
}

// Especificacions per sistema (id → família de tir). cue/bola1 en diamants; dir =
// direcció de la blanca DESPRÉS de tocar la bola 1; nBandes = bandes fins a la 2a bola.
const SPECS = {
	// ENDAVANT (앞돌리기): la blanca toca la 1a bola i fa la volta cap endavant.
	IYOiEStfn2I: { cue: [6.6, 0.7], bola1: [7.3, 1.3], dir: [-1, 1.5], nBandes: 3, nota: 'Exemple d\u2019endavant: la blanca surt, toca la bola 1 (groga) i fa 3 bandes fins a la 2a bola (vermella).' },
	M9BM0Z0NhQc: { cue: [6.2, 0.6], bola1: [7.0, 1.1], dir: [-1, 1.7], nBandes: 3, nota: 'Endavant b\u00e0sic: recorregut de 3 bandes de la blanca.' },
	// DE COSTAT (옆돌리기): la blanca va cap a la banda curta del costat.
	mBrxoCjhy9k: { cue: [4.2, 0.7], bola1: [3.2, 0.9], dir: [-1.2, 1], nBandes: 3, nota: 'De costat: la blanca toca la bola 1 i fa la volta pel costat (3 bandes).' },
	HSniKtkmrlE: { cue: [4.6, 0.7], bola1: [3.5, 1.0], dir: [-1.1, 1.1], nBandes: 3, nota: 'De costat: exemple de recorregut de 3 bandes.' },
	'8jXom-1dGZY': { cue: [5.2, 0.7], bola1: [4.2, 1.0], dir: [-1, 1.2], nBandes: 3, nota: 'De costat amb retorn: la blanca torna prop del punt de sortida.' },
	// TOCAR LA BOLA FINA (비껴치기): la 1a bola prop de banda, toc molt fi.
	wNssZQqfYDo: { cue: [3.0, 1.0], bola1: [1.4, 2.0], dir: [-0.6, 1.4], nBandes: 3, nota: 'Tocar la bola fina: toc molt fi a la bola 1, prop de la banda.' },
	x2OBi0KCWPc: { cue: [3.4, 0.9], bola1: [1.5, 1.6], dir: [-0.7, 1.3], nBandes: 3, nota: 'Short & Long: control de la llargada amb toc fi.' },
	// BRICOL (뱅크): la blanca va PRIMER a les bandes i despr\u00e9s a la bola.
	BLb_KYDGPyQ: { cue: [6.6, 0.6], bola1: [6.6, 0.6], dir: [-1, 1.3], nBandes: 2, finalLen: 2.4, nota: 'Two-bank: la blanca busca la bola despr\u00e9s de 2 bandes.' },
	VZW5_9U0few: { cue: [7.0, 0.6], bola1: [7.0, 0.6], dir: [-1, 1.4], nBandes: 3, finalLen: 2.2, nota: 'Bricol de 3 bandes: recorregut de la blanca abans d\u2019arribar a la bola.' }
};

const P = ['c:/Users/algoa/ProjectesInformatics/FCBillar/web/src/lib/sistemes/sistemes.json', 'c:/Users/algoa/ProjectesInformatics/FCBillar/scripts/sistemes/data/sistemes.json'];
const mode = process.argv[2] || 'print';

const diagrames = {};
for (const [id, s] of Object.entries(SPECS)) {
	const { traca: tr, b3 } = traca(s.cue, s.bola1, s.dir, s.nBandes, s.finalLen);
	const esBricol = s.bola1[0] === s.cue[0] && s.bola1[1] === s.cue[1];
	diagrames[id] = {
		boles: { b1: s.cue, b2: esBricol ? b3 : s.bola1, b3: esBricol ? [r1(s.cue[0] - 0.6), r1(s.cue[1] + 0.5)] : b3 },
		traca: tr,
		nota: s.nota
	};
	const dins = tr.every(([x, y]) => x >= 0 && x <= 8 && y >= 0 && y <= 4);
	console.log(`${id}: ${tr.map(([x, y]) => `(${x},${y})`).join(' → ')}  ${dins ? 'OK' : '!!FORA!!'}`);
}

if (mode === 'apply') {
	for (const p of P) {
		const c = JSON.parse(readFileSync(p, 'utf8'));
		for (const sys of c) if (diagrames[sys.id]) sys.diagrama = diagrames[sys.id];
		writeFileSync(p, JSON.stringify(c, null, 2));
	}
	console.log(`\nAplicats ${Object.keys(diagrames).length} diagrames al cat\u00e0leg.`);
} else {
	console.log(`\n(mode print — ${Object.keys(diagrames).length} diagrames calculats, no aplicats)`);
}
