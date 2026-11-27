// Avisos de resultats. El servidor (`fcbillar avisa`, a GitHub Actions) envia
// a cada subscripció només els tipus que hi té marcats; aquests identificadors
// han de coincidir amb els de src/fcbillar/avisos.py.
// Els tipus que porten seguiments diuen quants n'hi ha a la campana.
export const TIPUS_AVIS = [
	{
		id: 'opens_3b',
		nom: 'Opens de 3 bandes',
		detall: 'Totes les partides acabades, agrupades cada pocs minuts.'
	},
	{
		id: 'clubs_seguits',
		nom: 'Clubs i equips seguits',
		detall: 'El resultat de cada encontre de lliga i de Copa.'
	},
	{
		id: 'jugadors_seguits',
		nom: 'Jugadors seguits',
		detall: 'Les seves partides als opens i als campionats de Catalunya.'
	}
] as const;

export type TipusAvis = (typeof TIPUS_AVIS)[number]['id'];

// Llista de seguiments que va al servidor: «j:278», «c:C.B.BANYOLES» i
// «e:C.B.BANYOLES A» (vegeu src/fcbillar/avisos.py).
export function seguiments(jugadors: string[], clubs: string[], equips: string[]): string[] {
	return [
		...jugadors.map((x) => `j:${x}`),
		...clubs.map((x) => `c:${x}`),
		...equips.map((x) => `e:${x}`)
	];
}

// Clau pública VAPID: no és secreta, viatja al navegador per definició. La
// privada és el secret VAPID_PRIVATE_KEY del repositori.
export const VAPID_PUBLIC_KEY =
	'BNxq5HpCkKQk9zOLK4jLniUgUAxTZeeMGziwX4a3pzJXGLnUJRuSfvakDKXTpP5GICtA-7c6yf9zPvG3xRJFIRA';

export function base64UrlABytes(b64: string): Uint8Array<ArrayBuffer> {
	const pad = '='.repeat((4 - (b64.length % 4)) % 4);
	const bin = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
	const bytes = new Uint8Array(new ArrayBuffer(bin.length));
	for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
	return bytes;
}
