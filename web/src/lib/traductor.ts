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
}

/** Plataforma i identificador del vídeo, o null si l'enllaç no és de cap de les tres. */
export function llegeixEnllac(url: string): { plataforma: Plataforma; video_id: string } | null {
	const s = url.trim();
	let m: RegExpMatchArray | null;
	if ((m = s.match(/(?:youtu\.be\/|youtube\.com\/(?:watch\?(?:.*&)?v=|shorts\/|embed\/|live\/))([\w-]{11})/)))
		return { plataforma: 'youtube', video_id: m[1] };
	if ((m = s.match(/instagram\.com\/(?:[\w.]+\/)?(?:reel|reels|p|tv)\/([\w-]+)/)))
		return { plataforma: 'instagram', video_id: m[1] };
	if (
		(m = s.match(
			/(?:facebook\.com\/(?:reel|share\/[rv])\/|facebook\.com\/[^/]+\/videos\/(?:[^/]+\/)?|facebook\.com\/watch\/?\?v=|fb\.watch\/)([\w-]+)/
		))
	)
		return { plataforma: 'facebook', video_id: m[1] };
	return null;
}

/** El fragment que toca a l'instant `t`, o null si és un silenci entre fragments. */
export function segmentA(segments: Segment[], t: number): Segment | null {
	let lo = 0;
	let hi = segments.length - 1;
	while (lo <= hi) {
		const mig = (lo + hi) >> 1;
		const s = segments[mig];
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
 * que cau en una d'aquestes es torna a fer.
 */
export async function ambReintentsCache<R extends { error: { code?: string } | null }>(
	consulta: () => PromiseLike<R>,
	intents = 6
): Promise<R> {
	let r = await consulta();
	for (let i = 1; i < intents && r.error?.code === 'PGRST205'; i++) {
		await new Promise((resol) => setTimeout(resol, 700));
		r = await consulta();
	}
	return r;
}

export function mmss(segons: number): string {
	const s = Math.max(0, Math.floor(segons));
	return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}
