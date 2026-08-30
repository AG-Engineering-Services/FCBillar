import { writable } from 'svelte/store';
import { browser } from '$app/environment';

export type Theme = 'light' | 'dark';

// Color de la barra del navegador (PWA) per a cada mode. Ha de coincidir amb
// el fons del <body>: les superfícies de betum del sistema.
const THEME_COLOR: Record<Theme, string> = {
	light: '#F4F6F3',
	dark: '#161917'
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

/** Aplica el tema al DOM i el persisteix.
 *
 * Dues marques, que no diuen el mateix: `data-theme` és l'elecció explícita de
 * l'usuari i és la que fan servir els tokens per manar per damunt del sistema;
 * la classe `dark` porta l'estat ja resolt i és la que llegeix Tailwind.
 */
export function applyTheme(t: Theme) {
	if (!browser) return;
	document.documentElement.setAttribute('data-theme', t);
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
