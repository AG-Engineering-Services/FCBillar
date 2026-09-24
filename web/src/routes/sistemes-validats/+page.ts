import { redirect } from '@sveltejs/kit';

// Els validats ara son un filtre del cataleg; l'URL antic hi porta.
export function load() {
	redirect(308, '/sistemes-coreans?estat=validats');
}
