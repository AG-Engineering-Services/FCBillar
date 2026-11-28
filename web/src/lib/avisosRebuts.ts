// Avisos de resultats rebuts en aquest dispositiu. El service worker desa cada
// push que arriba; en obrir l'app, el modal de resultats recents els llegeix.
// La notificació de l'iPhone talla el text a poques línies i, en tocar-la, només
// s'obre la pàgina: aquí es pot llegir sencera.

export interface AvisRebut {
	id: string;
	titol: string;
	linies: string[];
	url: string;
	rebut: number; // ms des de l'època
}

export const FINESTRA_MS = 60 * 60 * 1000;
const CONSERVA_MS = 24 * 60 * 60 * 1000;
const BASE = 'fcbillar-avisos';
const MAGATZEM = 'rebuts';

/** El missatge del push (title/body/url) com a avís desat. */
export function deMissatge(
	dades: { title?: string; body?: string; url?: string },
	rebut: number
): AvisRebut {
	return {
		id: `${rebut}-${Math.random().toString(36).slice(2, 8)}`,
		titol: dades.title || 'FCBillar',
		linies: (dades.body || '').split('\n').filter((l) => l.trim() !== ''),
		url: dades.url || '/',
		rebut
	};
}

/** Els de l'última hora, del més nou al més vell. */
export function recents(avisos: AvisRebut[], ara: number): AvisRebut[] {
	return avisos.filter((a) => ara - a.rebut <= FINESTRA_MS).sort((a, b) => b.rebut - a.rebut);
}

/** Si n'hi ha cap d'arribat després de l'últim cop que es va tancar el modal. */
export function hiHaNous(avisos: AvisRebut[], vistosFins: number): boolean {
	return avisos.some((a) => a.rebut > vistosFins);
}

function obre(): Promise<IDBDatabase> {
	return new Promise((resol, rebutja) => {
		const peticio = indexedDB.open(BASE, 1);
		peticio.onupgradeneeded = () => peticio.result.createObjectStore(MAGATZEM, { keyPath: 'id' });
		peticio.onsuccess = () => resol(peticio.result);
		peticio.onerror = () => rebutja(peticio.error);
	});
}

/** Desa un avís i esborra els de més d'un dia. */
export async function desa(avis: AvisRebut): Promise<void> {
	const db = await obre();
	await new Promise<void>((resol, rebutja) => {
		const tx = db.transaction(MAGATZEM, 'readwrite');
		const m = tx.objectStore(MAGATZEM);
		m.put(avis);
		const tots = m.getAll();
		tots.onsuccess = () => {
			for (const a of tots.result as AvisRebut[]) {
				if (avis.rebut - a.rebut > CONSERVA_MS) m.delete(a.id);
			}
		};
		tx.oncomplete = () => resol();
		tx.onerror = () => rebutja(tx.error);
	});
	db.close();
}

export async function llegeix(): Promise<AvisRebut[]> {
	const db = await obre();
	const out = await new Promise<AvisRebut[]>((resol, rebutja) => {
		const peticio = db.transaction(MAGATZEM).objectStore(MAGATZEM).getAll();
		peticio.onsuccess = () => resol(peticio.result as AvisRebut[]);
		peticio.onerror = () => rebutja(peticio.error);
	});
	db.close();
	return out;
}
