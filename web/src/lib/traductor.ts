// Traductor de vídeos (Aprèn → Traductor). La fila la crea l'usuari i la resta la
// omple el workflow traductor.yml; vegeu la migració 0022 i
// scripts/traductor/tradueix.py.

export type Plataforma = 'youtube' | 'instagram' | 'facebook';
export type Idioma = 'ko' | 'vi' | 'tr';
export type EstatTraduccio = 'pendent' | 'processant' | 'fet' | 'error';

export const IDIOMES: { codi: Idioma; nom: string }[] = [
	{ codi: 'ko', nom: 'Coreà' },
	{ codi: 'vi', nom: 'Vietnamita' },
	{ codi: 'tr', nom: 'Turc' }
];

export interface Segment {
	t0: number;
	t1: number;
	orig: string;
	ca: string;
}

export interface VideoTraduccio {
	id: number;
	url: string;
	plataforma: Plataforma;
	video_id: string;
	idioma: Idioma;
	estat: EstatTraduccio;
	titol: string | null;
	canal: string | null;
	durada: number | null;
	segments: Segment[] | null;
	audio_url: string | null;
	missatge: string | null;
	creat: string;
	processat: string | null;
	/** Quan el workflow va agafar la fila (migració 0023). */
	iniciat: string | null;
	/** Còpia a 480p per als que no es poden incrustar: Instagram i Facebook (0025). */
	video_url?: string | null;
}

/** Plataforma i identificador del vídeo, o null si l'enllaç no és de cap de les tres. */
export function llegeixEnllac(url: string): { plataforma: Plataforma; video_id: string } | null {
	const s = url.trim();
	let m: RegExpMatchArray | null;
	if ((m = s.match(/(?:youtu\.be\/|youtube\.com\/(?:watch\?(?:.*&)?v=|shorts\/|embed\/|live\/))([\w-]{11})/)))
		return { plataforma: 'youtube', video_id: m[1]! };
	if ((m = s.match(/instagram\.com\/(?:[\w.]+\/)?(?:reel|reels|p|tv)\/([\w-]+)/)))
		return { plataforma: 'instagram', video_id: m[1]! };
	if (
		(m = s.match(
			/(?:facebook\.com\/(?:reel|share\/[rv])\/|facebook\.com\/[^/]+\/videos\/(?:[^/]+\/)?|facebook\.com\/watch\/?\?v=|fb\.watch\/)([\w-]+)/
		))
	)
		return { plataforma: 'facebook', video_id: m[1]! };
	return null;
}

/** El fragment que toca a l'instant `t`, o null si és un silenci entre fragments. */
export function segmentA(segments: Segment[], t: number): Segment | null {
	let lo = 0;
	let hi = segments.length - 1;
	while (lo <= hi) {
		const mig = (lo + hi) >> 1;
		const s = segments[mig]!;
		if (t < s.t0) hi = mig - 1;
		else if (t >= s.t1) lo = mig + 1;
		else return s;
	}
	return null;
}

/**
 * El Data API de Neon corre en diverses instàncies, cada una amb la seva memòria
 * cau d'esquemes. Després d'una migració, unes veuen la taula nova i d'altres
 * responen PGRST205 («Could not find the table») durant molta estona: amb la
 * 0022, quaranta minuts després, encara una petició de cada dues. Una consulta
 * que cau en una d'aquestes es torna a fer. PGRST202 és el mateix per a una
 * funció nova (la 0024).
 */
export async function ambReintentsCache<R extends { error: { code?: string } | null }>(
	consulta: () => PromiseLike<R>,
	intents = 6
): Promise<R> {
	let r = await consulta();
	const noVista = () => r.error?.code === 'PGRST205' || r.error?.code === 'PGRST202';
	for (let i = 1; i < intents && noVista(); i++) {
		await new Promise((resol) => setTimeout(resol, 700));
		r = await consulta();
	}
	return r;
}

/** Els subtítols catalans en WebVTT, per a la pista del reproductor propi. */
export function aVtt(segments: Segment[]): string {
	const t = (x: number) => {
		const ms = Math.round(x * 1000);
		const h = Math.floor(ms / 3_600_000);
		const m = Math.floor(ms / 60_000) % 60;
		const s = Math.floor(ms / 1000) % 60;
		const p = (n: number, w = 2) => String(n).padStart(w, '0');
		return `${p(h)}:${p(m)}:${p(s)}.${p(ms % 1000, 3)}`;
	};
	const cues = segments
		.filter((s) => s.ca)
		.map((s) => `${t(s.t0)} --> ${t(s.t1)}\n${s.ca.replace(/-->/g, '→')}`);
	return ['WEBVTT', ...cues].join('\n\n') + '\n';
}

export function mmss(segons: number): string {
	const s = Math.max(0, Math.floor(segons));
	return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

// --- Estimació del temps que falta ---------------------------------------------
//
// Surt de com treballa el workflow traductor.yml, i s'ajusta sola amb els vídeos
// ja fets:
//  - la PWA l'engega en el moment d'afegir un vídeo (routes/traductor/avisa), i
//    comença a traduir al cap d'ARRENCADA_S. Si un pendent fa més d'AVIS_CADUCAT
//    que espera, l'avís no ha funcionat i toca la programació: els minuts 7, 22,
//    37 i 52 de cada hora (UTC; com que els fusos van per hores senceres, són els
//    mateixos minuts a tot arreu), que GitHub dispara tard o gens;
//  - cada tret prepara la màquina (~45 s el 24/09/2026) i tradueix com a molt
//    TRET_MAX vídeos, l'un darrere l'altre; si un tret no s'ha acabat, el següent
//    l'espera;
//  - el que triga un vídeo és un fix més un ritme per segon de vídeo. El ritme
//    es mesura dels vídeos ja fets amb `iniciat` → `processat`.

const MINUTS_TRET = [7, 22, 37, 52];
// Del clic al primer fragment: la cua de GitHub, la preparació de la màquina
// (~45 s) i les dependències. Mesurat el 24/09/2026: ~60-75 s.
const ARRENCADA_S = 75;
const AVIS_CADUCAT_MS = 10 * 60_000;
const RETARD_CRON_S = 5 * 60;
const PREPARACIO_S = 60;
const TRET_MAX = 3;
const FIX_PER_VIDEO_S = 20;
const RITME_PER_DEFECTE = 0.8; // segons de feina per segon de vídeo
const DURADA_PER_DEFECTE_S = 5 * 60; // quan encara no se sap quant dura

/** El proper minut de tret del workflow, estrictament després d'`ara`. */
export function properTret(ara: Date): Date {
	const t = new Date(ara);
	t.setUTCSeconds(0, 0);
	for (let i = 0; i < 4 * 24 + 1; i++) {
		t.setUTCMinutes(t.getUTCMinutes() + 1);
		if (MINUTS_TRET.includes(t.getUTCMinutes()) && t > ara) return t;
	}
	return t; // inabastable: sempre n'hi ha un dins l'hora
}

function mediana(xs: number[]): number | null {
	if (!xs.length) return null;
	const o = [...xs].sort((a, b) => a - b);
	const m = o.length >> 1;
	return o.length % 2 ? o[m]! : (o[m - 1]! + o[m]!) / 2;
}

export interface Estimacio {
	comenca: Date;
	acaba: Date;
}

/** Quan començarà i acabarà cada vídeo pendent o en curs. */
export function estimaCua(videos: VideoTraduccio[], ara: Date): Map<number, Estimacio> {
	const ms = (iso: string) => new Date(iso).getTime();
	const fets = videos.filter((v) => v.estat === 'fet' && v.durada);
	const ritme =
		mediana(
			fets
				.filter((v) => v.iniciat && v.processat)
				.map((v) => ((ms(v.processat!) - ms(v.iniciat!)) / 1000 - FIX_PER_VIDEO_S) / v.durada!)
				.filter((r) => r > 0)
		) ?? RITME_PER_DEFECTE;
	const duradaTipica = mediana(fets.map((v) => v.durada!)) ?? DURADA_PER_DEFECTE_S;
	const feina = (v: VideoTraduccio) =>
		(FIX_PER_VIDEO_S + ritme * (v.durada ?? duradaTipica)) * 1000;

	const res = new Map<number, Estimacio>();
	const perData = (a: VideoTraduccio, b: VideoTraduccio) => ms(a.creat) - ms(b.creat);

	// El que s'està traduint ara. Si ja passa de l'estimat, no l'acabem «fa estona».
	let fi = ara.getTime();
	const enCurs = videos.filter((v) => v.estat === 'processant').sort(perData);
	for (const v of enCurs) {
		const comenca = ms(v.iniciat ?? v.processat ?? v.creat);
		const acaba = Math.max(comenca + feina(v), ara.getTime() + 30_000);
		res.set(v.id, { comenca: new Date(comenca), acaba: new Date(acaba) });
		fi = Math.max(fi, acaba);
	}

	const pendents = videos.filter((v) => v.estat === 'pendent').sort(perData);
	let i = 0;
	// El tret en curs encara en pot agafar fins a completar-ne TRET_MAX.
	if (enCurs.length)
		for (let lloc = enCurs.length; lloc < TRET_MAX && i < pendents.length; lloc++, i++) {
			const v = pendents[i]!;
			res.set(v.id, { comenca: new Date(fi), acaba: new Date(fi + feina(v)) });
			fi += feina(v);
		}
	let tret = properTret(ara).getTime();
	let primerLot = true;
	while (i < pendents.length) {
		const primer = pendents[i]!;
		const avisat = ara.getTime() - ms(primer.creat) < AVIS_CADUCAT_MS;
		let t: number;
		if (avisat) {
			// L'avís ja ha engegat un tret; els lots següents van en el tret que
			// GitHub deixa en espera, que arrenca quan acaba l'anterior.
			const arrencada = primerLot ? ms(primer.creat) : fi;
			t = Math.max(arrencada + ARRENCADA_S * 1000, ara.getTime() + 15_000, fi);
		} else {
			t = Math.max(tret + (RETARD_CRON_S + PREPARACIO_S) * 1000, fi);
			tret += 15 * 60_000;
		}
		for (let n = 0; n < TRET_MAX && i < pendents.length; n++, i++) {
			const v = pendents[i]!;
			res.set(v.id, { comenca: new Date(t), acaba: new Date(t + feina(v)) });
			t += feina(v);
		}
		fi = t;
		primerLot = false;
	}
	return res;
}

/** «menys d'un minut», «~7 min», «~1 h 20 min». */
export function quantFalta(fins: Date, ara: Date): string {
	const min = Math.round((fins.getTime() - ara.getTime()) / 60_000);
	if (min < 1) return "menys d'un minut";
	if (min < 60) return `~${min} min`;
	const h = Math.floor(min / 60);
	const m = min % 60;
	return m ? `~${h} h ${m} min` : `~${h} h`;
}

export function hora(d: Date): string {
	return d.toLocaleTimeString('ca', { hour: '2-digit', minute: '2-digit' });
}

// --- Eliminar (només l'admin) -------------------------------------------------
//
// L'anon no té DELETE: s'esborra amb la funció `elimina_video_traduccio`
// (migració 0024), que demana la clau d'admin. La clau es demana el primer cop i
// es recorda en aquest navegador; si deixa de ser bona, s'oblida.

const CLAU_ADMIN = 'fcb_traductor_clau';

type CridaRpc = (
	funcio: string,
	args: Record<string, unknown>
) => PromiseLike<{ error: { code?: string; message: string } | null }>;

function llegeixClau(): string | null {
	try {
		return localStorage.getItem(CLAU_ADMIN);
	} catch {
		return null;
	}
}
function desaClau(clau: string | null) {
	try {
		if (clau) localStorage.setItem(CLAU_ADMIN, clau);
		else localStorage.removeItem(CLAU_ADMIN);
	} catch {
		// sense emmagatzematge: la tornarà a demanar
	}
}

/** Demana confirmació i la clau, i esborra. Torna true si s'ha esborrat. */
export async function eliminaVideo(
	rpc: CridaRpc,
	v: Pick<VideoTraduccio, 'id' | 'titol' | 'video_id'>
): Promise<boolean> {
	if (!confirm(`Eliminar «${v.titol ?? v.video_id}»? La traducció desapareixerà per a tothom.`))
		return false;
	const clau = llegeixClau() ?? prompt("Clau d'admin del traductor:")?.trim();
	if (!clau) return false;
	const { error } = await ambReintentsCache(() =>
		rpc('elimina_video_traduccio', { p_id: v.id, p_clau: clau })
	);
	if (error) {
		if (error.code === '42501') {
			desaClau(null);
			alert('Clau incorrecta.');
		} else alert(`No s'ha pogut eliminar: ${error.message}`);
		return false;
	}
	desaClau(clau);
	return true;
}
