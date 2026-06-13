import { writable } from 'svelte/store';
import { browser } from '$app/environment';

export type Theme = 'light' | 'dark';

// Color de la barra del navegador (PWA) per a cada mode — ha de coincidir
// amb el fons del <body> (slate-50 clar / slate-950 fosc).
const THEME_COLOR: Record<Theme, string> = {
	light: '#f8fafc',
	dark: '#020617'
};

function systemPrefersDark(): boolean {
	return browser && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function readStored(): Theme | null {
	if (!browser) return null;
	try {
		const v = localStorage.getItem('theme');
		return v === 'light' || v === 'dark' ? v : null;
	} catch {
		return null;
	}
}

function initial(): Theme {
	return readStored() ?? (systemPrefersDark() ? 'dark' : 'light');
}

// El mateix càlcul es fa al script inline d'app.html per evitar el flaix
// blanc; aquí el repliquem perquè l'estat del store quadri amb el DOM.
export const theme = writable<Theme>(initial());

/** Aplica el tema al DOM (classe `dark` a <html>) i el persisteix. */
export function applyTheme(t: Theme) {
	if (!browser) return;
	document.documentElement.classList.toggle('dark', t === 'dark');
	const meta = document.querySelector('meta[name="theme-color"]');
	if (meta) meta.setAttribute('content', THEME_COLOR[t]);
	try {
		localStorage.setItem('theme', t);
	} catch {
		/* localStorage pot estar bloquejat (mode privat); ignora-ho */
	}
}

/** Commuta entre clar i fosc i persisteix l'elecció de l'usuari. */
export function toggleTheme() {
	theme.update((t) => {
		const next: Theme = t === 'dark' ? 'light' : 'dark';
		applyTheme(next);
		return next;
	});
}
