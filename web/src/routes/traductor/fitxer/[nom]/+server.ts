// Serveix els mp3 i mp4 del release `traduccions` amb el tipus que toca.
//
// GitHub els dona com a `application/octet-stream`, amb `X-Content-Type-Options:
// nosniff` i com a descàrrega. Chrome i Edge els reprodueixen igualment, però
// Safari (tots els navegadors de l'iPhone) no: la veu donava «NotSupportedError» i
// els vídeos d'Instagram no arrencaven (24/09/2026). Aquí es tornen a servir com a
// `audio/mpeg` i `video/mp4`, passant-hi la capçalera Range: Safari demana els
// mitjans a trossos (206) i sense això tampoc els reprodueix.
//
// Només accepta noms de fitxers del traductor, perquè no sigui un proxy obert.
import { error } from '@sveltejs/kit';

const RELEASE = 'https://github.com/AG-Engineering-Services/FCBillar/releases/download/traduccions';
const NOM = /^(youtube|instagram|facebook)-[A-Za-z0-9_-]{3,64}\.(mp3|mp4)$/;
const TIPUS: Record<string, string> = { mp3: 'audio/mpeg', mp4: 'video/mp4' };

export async function GET({ params, request }) {
	const m = params.nom.match(NOM);
	if (!m) error(404, 'No existeix');
	const range = request.headers.get('range');
	const r = await fetch(`${RELEASE}/${params.nom}`, {
		headers: range ? { Range: range } : {},
		redirect: 'follow'
	});
	if (!r.ok && r.status !== 416) error(r.status === 404 ? 404 : 502, 'No s’ha pogut llegir');

	const capcaleres = new Headers({
		'Content-Type': TIPUS[m[2]!]!,
		'Accept-Ranges': 'bytes',
		// Un --retradueix substitueix el fitxer amb el mateix nom: la pàgina hi afegeix
		// ?v=<processat>, i així una hora de memòria cau no serveix el vell.
		'Cache-Control': 'public, max-age=3600'
	});
	for (const nom of ['Content-Length', 'Content-Range', 'ETag', 'Last-Modified']) {
		const valor = r.headers.get(nom);
		if (valor) capcaleres.set(nom, valor);
	}
	return new Response(r.body, { status: r.status, headers: capcaleres });
}
