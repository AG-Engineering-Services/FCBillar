import { browser } from '$app/environment';

// Marca d'administració d'aquest dispositiu. Només decideix què s'ensenya: qui
// valida de debò és la RLS de les taules de peticions. Per posar-la en un
// dispositiu nou, obre la fitxa del jugador 278 amb `?admin` a l'adreça i llança
// una reingesta amb el correu autoritzat.
export const ADMIN_EMAIL = 'algoam@gmail.com';

export function esAdminLocal(url?: URL): boolean {
	if (!browser) return false;
	if (url?.searchParams.has('admin')) return true;
	try {
		return localStorage.getItem('fcb_admin') === '1';
	} catch {
		return false;
	}
}

export function marcaAdmin() {
	try {
		localStorage.setItem('fcb_admin', '1');
	} catch {
		/* localStorage no disponible: no és crític */
	}
}
