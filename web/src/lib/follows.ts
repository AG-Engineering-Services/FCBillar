// Seguiment de jugadors PER DISPOSITIU (localStorage, no servidor).
// Cada dispositiu té la seva pròpia llista de jugadors seguits.
import { writable } from 'svelte/store';

const KEY = 'fcbillar_follows';

function load(): string[] {
	if (typeof localStorage === 'undefined') return [];
	try {
		const v = JSON.parse(localStorage.getItem(KEY) || '[]');
		return Array.isArray(v) ? v.filter((x) => typeof x === 'string') : [];
	} catch {
		return [];
	}
}

export const follows = writable<string[]>(load());

follows.subscribe((v) => {
	if (typeof localStorage !== 'undefined') localStorage.setItem(KEY, JSON.stringify(v));
});

export function toggleFollow(id: string): void {
	follows.update((list) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]));
}
